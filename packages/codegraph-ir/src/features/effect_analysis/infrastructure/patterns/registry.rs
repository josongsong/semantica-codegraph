//! Pattern Registry
//!
//! Central registry for all pattern matchers with language-specific support.

use super::base::{MatchContext, MatchResult, PatternMatcher};
use std::collections::HashMap;
use std::sync::Arc;

/// Pattern registry with language-specific matchers
pub struct PatternRegistry {
    /// Language-specific patterns: language -> Vec<matcher>
    language_patterns: HashMap<String, Vec<Arc<dyn PatternMatcher>>>,

    /// Generic patterns (language-agnostic)
    generic_patterns: Vec<Arc<dyn PatternMatcher>>,
}

impl PatternRegistry {
    pub fn new() -> Self {
        Self {
            language_patterns: HashMap::new(),
            generic_patterns: Vec::new(),
        }
    }

    /// Register a language-specific pattern
    pub fn register_language_pattern(
        &mut self,
        language: impl Into<String>,
        matcher: Arc<dyn PatternMatcher>,
    ) {
        self.language_patterns
            .entry(language.into())
            .or_insert_with(Vec::new)
            .push(matcher);
    }

    /// Register a generic pattern (applies to all languages)
    pub fn register_generic_pattern(&mut self, matcher: Arc<dyn PatternMatcher>) {
        self.generic_patterns.push(matcher);
    }

    /// Match patterns against context
    pub fn match_patterns(&self, ctx: &MatchContext) -> MatchResult {
        let mut result = MatchResult::empty();

        // 1. Try language-specific patterns first (higher priority)
        if let Some(patterns) = self.language_patterns.get(ctx.language) {
            for pattern in patterns {
                let m = pattern.matches(ctx);
                if !m.effects.is_empty() {
                    result.merge(m);
                }
            }
        }

        // 2. Apply generic patterns
        for pattern in &self.generic_patterns {
            let m = pattern.matches(ctx);
            if !m.effects.is_empty() {
                result.merge(m);
            }
        }

        result
    }

    /// Sort patterns by priority (for optimization)
    pub fn optimize(&mut self) {
        // Sort language-specific patterns by priority
        for patterns in self.language_patterns.values_mut() {
            patterns.sort_by_key(|p| -p.priority());
        }

        // Sort generic patterns by priority
        self.generic_patterns.sort_by_key(|p| -p.priority());
    }
}

impl Default for PatternRegistry {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::effect_analysis::domain::EffectType;
    use crate::features::effect_analysis::infrastructure::patterns::base::KeywordPattern;

    #[test]
    fn test_registry_language_specific() {
        let mut registry = PatternRegistry::new();

        // Python print
        registry.register_language_pattern(
            "python",
            Arc::new(KeywordPattern::new("python_io", vec!["print"], EffectType::Io).exact()),
        );

        // JavaScript console
        registry.register_language_pattern(
            "javascript",
            Arc::new(KeywordPattern::new(
                "js_io",
                vec!["console"],
                EffectType::Io,
            )),
        );

        // Test Python
        let ctx = MatchContext::new("print", "python");
        let result = registry.match_patterns(&ctx);
        assert!(result.effects.contains(&EffectType::Io));

        // Test JavaScript
        let ctx = MatchContext::new("console.log", "javascript");
        let result = registry.match_patterns(&ctx);
        assert!(result.effects.contains(&EffectType::Io));
    }

    #[test]
    fn test_registry_generic() {
        let mut registry = PatternRegistry::new();

        // Generic network pattern
        registry.register_generic_pattern(Arc::new(KeywordPattern::new(
            "network",
            vec!["http", "api"],
            EffectType::Network,
        )));

        // Should match in any language
        let ctx = MatchContext::new("http_get", "python");
        let result = registry.match_patterns(&ctx);
        assert!(result.effects.contains(&EffectType::Network));

        let ctx = MatchContext::new("api_call", "javascript");
        let result = registry.match_patterns(&ctx);
        assert!(result.effects.contains(&EffectType::Network));
    }
}
