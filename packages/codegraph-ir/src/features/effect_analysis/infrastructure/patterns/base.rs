//! Base Pattern Matching System
//!
//! Language-agnostic pattern matching infrastructure for effect inference.

use crate::features::effect_analysis::domain::EffectType;
use std::collections::HashSet;

/// Context for pattern matching
#[derive(Debug, Clone)]
pub struct MatchContext<'a> {
    /// Identifier name to match
    pub name: &'a str,

    /// Source language (e.g., "python", "javascript", "go")
    pub language: &'a str,

    /// All variable names in scope (for context-aware matching)
    pub scope_vars: &'a [String],

    /// Additional metadata
    pub metadata: Option<&'a str>,
}

impl<'a> MatchContext<'a> {
    pub fn new(name: &'a str, language: &'a str) -> Self {
        Self {
            name,
            language,
            scope_vars: &[],
            metadata: None,
        }
    }

    pub fn with_scope(mut self, scope_vars: &'a [String]) -> Self {
        self.scope_vars = scope_vars;
        self
    }

    pub fn name_lower(&self) -> String {
        self.name.to_lowercase()
    }
}

/// Result of pattern matching
#[derive(Debug, Clone)]
pub struct MatchResult {
    /// Detected effects
    pub effects: HashSet<EffectType>,

    /// Confidence score (0.0 - 1.0)
    pub confidence: f64,

    /// Match reason (for debugging)
    pub reason: Option<String>,
}

impl MatchResult {
    pub fn empty() -> Self {
        Self {
            effects: HashSet::new(),
            confidence: 1.0,
            reason: None,
        }
    }

    pub fn with_effect(effect: EffectType, confidence: f64) -> Self {
        let mut effects = HashSet::new();
        effects.insert(effect);
        Self {
            effects,
            confidence,
            reason: None,
        }
    }

    pub fn with_effects(effects: HashSet<EffectType>, confidence: f64) -> Self {
        Self {
            effects,
            confidence,
            reason: None,
        }
    }

    pub fn with_reason(mut self, reason: impl Into<String>) -> Self {
        self.reason = Some(reason.into());
        self
    }

    /// Merge multiple match results
    pub fn merge(&mut self, other: MatchResult) {
        self.effects.extend(other.effects);
        self.confidence = self.confidence.min(other.confidence);
    }
}

/// Pattern matcher trait
pub trait PatternMatcher: Send + Sync {
    /// Pattern name (for debugging)
    fn name(&self) -> &'static str;

    /// Match pattern against context
    fn matches(&self, ctx: &MatchContext) -> MatchResult;

    /// Priority (higher = checked first)
    fn priority(&self) -> i32 {
        0
    }
}

/// Keyword-based pattern matcher
#[derive(Debug, Clone)]
pub struct KeywordPattern {
    pub name: &'static str,
    pub keywords: Vec<&'static str>,
    pub effect: EffectType,
    pub confidence: f64,
    pub exact_match: bool,
}

impl KeywordPattern {
    pub fn new(name: &'static str, keywords: Vec<&'static str>, effect: EffectType) -> Self {
        Self {
            name,
            keywords,
            effect,
            confidence: 0.9,
            exact_match: false,
        }
    }

    pub fn with_confidence(mut self, confidence: f64) -> Self {
        self.confidence = confidence;
        self
    }

    pub fn exact(mut self) -> Self {
        self.exact_match = true;
        self
    }
}

impl PatternMatcher for KeywordPattern {
    fn name(&self) -> &'static str {
        self.name
    }

    fn matches(&self, ctx: &MatchContext) -> MatchResult {
        let name_lower = ctx.name_lower();

        for keyword in &self.keywords {
            let keyword_lower = keyword.to_lowercase();
            let matches = if self.exact_match {
                name_lower == keyword_lower
            } else {
                name_lower.contains(&keyword_lower)
            };

            if matches {
                return MatchResult::with_effect(self.effect.clone(), self.confidence)
                    .with_reason(format!("Matched keyword: {}", keyword));
            }
        }

        MatchResult::empty()
    }
}

/// Regex-based pattern matcher
#[derive(Debug)]
pub struct RegexPattern {
    pub name: &'static str,
    pub pattern: regex::Regex,
    pub effect: EffectType,
    pub confidence: f64,
}

impl RegexPattern {
    pub fn new(
        name: &'static str,
        pattern: &str,
        effect: EffectType,
    ) -> Result<Self, regex::Error> {
        Ok(Self {
            name,
            pattern: regex::Regex::new(pattern)?,
            effect,
            confidence: 0.9,
        })
    }

    pub fn with_confidence(mut self, confidence: f64) -> Self {
        self.confidence = confidence;
        self
    }
}

impl PatternMatcher for RegexPattern {
    fn name(&self) -> &'static str {
        self.name
    }

    fn matches(&self, ctx: &MatchContext) -> MatchResult {
        if self.pattern.is_match(ctx.name) {
            MatchResult::with_effect(self.effect.clone(), self.confidence)
                .with_reason(format!("Matched regex: {}", self.pattern.as_str()))
        } else {
            MatchResult::empty()
        }
    }
}

/// Composite pattern (combines multiple patterns with AND/OR logic)
#[derive(Debug)]
pub enum CompositeOp {
    And,
    Or,
}

pub struct CompositePattern {
    pub name: &'static str,
    pub patterns: Vec<Box<dyn PatternMatcher>>,
    pub op: CompositeOp,
}

impl CompositePattern {
    pub fn and(name: &'static str, patterns: Vec<Box<dyn PatternMatcher>>) -> Self {
        Self {
            name,
            patterns,
            op: CompositeOp::And,
        }
    }

    pub fn or(name: &'static str, patterns: Vec<Box<dyn PatternMatcher>>) -> Self {
        Self {
            name,
            patterns,
            op: CompositeOp::Or,
        }
    }
}

impl PatternMatcher for CompositePattern {
    fn name(&self) -> &'static str {
        self.name
    }

    fn matches(&self, ctx: &MatchContext) -> MatchResult {
        match self.op {
            CompositeOp::And => {
                let mut result = MatchResult::empty();
                result.confidence = 1.0;

                for pattern in &self.patterns {
                    let m = pattern.matches(ctx);
                    if m.effects.is_empty() {
                        return MatchResult::empty();
                    }
                    result.merge(m);
                }
                result
            }
            CompositeOp::Or => {
                for pattern in &self.patterns {
                    let m = pattern.matches(ctx);
                    if !m.effects.is_empty() {
                        return m;
                    }
                }
                MatchResult::empty()
            }
        }
    }
}
