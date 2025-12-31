//! Python-specific effect patterns

use super::base::{KeywordPattern, MatchContext, MatchResult, PatternMatcher};
use crate::features::effect_analysis::domain::EffectType;
use std::collections::HashSet;

/// Python I/O patterns
pub fn python_io_patterns() -> Vec<Box<dyn PatternMatcher>> {
    vec![
        Box::new(
            KeywordPattern::new("python_print", vec!["print"], EffectType::Io)
                .exact()
                .with_confidence(0.95),
        ),
        Box::new(
            KeywordPattern::new("python_input", vec!["input"], EffectType::Io)
                .exact()
                .with_confidence(0.95),
        ),
        Box::new(KeywordPattern::new(
            "python_file",
            vec!["open", "file", "write", "read"],
            EffectType::Io,
        )),
    ]
}

/// Python exception patterns
pub fn python_exception_patterns() -> Vec<Box<dyn PatternMatcher>> {
    vec![
        Box::new(
            KeywordPattern::new("python_raise", vec!["raise"], EffectType::Throws)
                .exact()
                .with_confidence(0.95),
        ),
        Box::new(KeywordPattern::new(
            "python_raise_prefix",
            vec!["raise_"],
            EffectType::Throws,
        )),
    ]
}

/// Python global/state patterns
pub struct PythonGlobalPattern;

impl PatternMatcher for PythonGlobalPattern {
    fn name(&self) -> &'static str {
        "python_global"
    }

    fn matches(&self, ctx: &MatchContext) -> MatchResult {
        let name_lower = ctx.name_lower();
        let mut effects = HashSet::new();

        // Python naming conventions
        if name_lower.starts_with("_") && !name_lower.starts_with("__") {
            // Single underscore = private module-level variable (often global state)
            effects.insert(EffectType::GlobalMutation);
        }

        if name_lower.starts_with("__") && name_lower.ends_with("__") {
            // Dunder methods - typically not global mutation
            return MatchResult::empty();
        }

        if !effects.is_empty() {
            MatchResult::with_effects(effects, 0.8)
                .with_reason("Python naming convention (_var = private global)")
        } else {
            MatchResult::empty()
        }
    }
}

/// Python async/await patterns
pub fn python_async_patterns() -> Vec<Box<dyn PatternMatcher>> {
    vec![Box::new(KeywordPattern::new(
        "python_await",
        vec!["await", "async"],
        EffectType::Network, // Often used for I/O
    ))]
}

/// Get all Python patterns
pub fn all_python_patterns() -> Vec<Box<dyn PatternMatcher>> {
    let mut patterns: Vec<Box<dyn PatternMatcher>> = Vec::new();
    patterns.extend(python_io_patterns());
    patterns.extend(python_exception_patterns());
    patterns.extend(python_async_patterns());
    patterns.push(Box::new(PythonGlobalPattern));
    patterns
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_python_print() {
        let ctx = MatchContext::new("print", "python");
        let patterns = python_io_patterns();
        let result = patterns[0].matches(&ctx);
        assert!(result.effects.contains(&EffectType::Io));
        assert!(result.confidence > 0.9);
    }

    #[test]
    fn test_python_raise() {
        let ctx = MatchContext::new("raise", "python");
        let patterns = python_exception_patterns();
        let result = patterns[0].matches(&ctx);
        assert!(result.effects.contains(&EffectType::Throws));
    }

    #[test]
    fn test_python_private_global() {
        let ctx = MatchContext::new("_instance", "python");
        let pattern = PythonGlobalPattern;
        let result = pattern.matches(&ctx);
        assert!(result.effects.contains(&EffectType::GlobalMutation));
    }

    #[test]
    fn test_python_dunder_no_match() {
        let ctx = MatchContext::new("__init__", "python");
        let pattern = PythonGlobalPattern;
        let result = pattern.matches(&ctx);
        assert!(result.effects.is_empty());
    }
}
