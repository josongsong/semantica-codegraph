//! Effect Pattern Matching System
//!
//! Language-aware pattern matching for effect inference.
//!
//! # Architecture
//!
//! ```text
//! PatternRegistry
//! ├── Language-Specific Patterns
//! │   ├── Python (print, raise, _var)
//! │   ├── JavaScript (console, throw)
//! │   └── Go (fmt.Println, panic)
//! │
//! └── Generic Patterns (language-agnostic)
//!     ├── Network (http, api, socket)
//!     ├── Database (insert, query)
//!     ├── Logging (log, debug, info)
//!     ├── Design Patterns (callback, cache, singleton)
//!     └── Context-Aware (transaction+exception)
//! ```
//!
//! # Usage
//!
//! ```text
//! use codegraph_ir::features::effect_analysis::infrastructure::patterns::{PatternRegistry, MatchContext};
//! use codegraph_ir::features::effect_analysis::domain::EffectType;
//!
//! let registry = PatternRegistry::new();
//!
//! let ctx = MatchContext::new("print", "python");
//! let result = registry.match_patterns(&ctx);
//!
//! assert!(result.effects.contains(&EffectType::Io));
//! ```

pub mod base;
pub mod generic;
pub mod javascript;
pub mod python;
pub mod registry;

pub use base::{KeywordPattern, MatchContext, MatchResult, PatternMatcher};
pub use registry::PatternRegistry;

use std::sync::Arc;

/// Create a default registry with all built-in patterns
pub fn create_default_registry() -> PatternRegistry {
    let mut registry = PatternRegistry::new();

    // Register Python patterns
    for pattern in python::all_python_patterns() {
        registry.register_language_pattern("python", Arc::from(pattern));
    }

    // Register JavaScript patterns
    for pattern in javascript::all_javascript_patterns() {
        registry.register_language_pattern("javascript", Arc::from(pattern));
    }

    // Register generic patterns
    for pattern in generic::all_generic_patterns() {
        registry.register_generic_pattern(Arc::from(pattern));
    }

    // Optimize pattern order by priority
    registry.optimize();

    registry
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::effect_analysis::domain::EffectType;

    #[test]
    fn test_default_registry_python() {
        let registry = create_default_registry();

        // Test Python print
        let ctx = MatchContext::new("print", "python");
        let result = registry.match_patterns(&ctx);
        assert!(result.effects.contains(&EffectType::Io));

        // Test Python raise
        let ctx = MatchContext::new("raise", "python");
        let result = registry.match_patterns(&ctx);
        assert!(result.effects.contains(&EffectType::Throws));
    }

    #[test]
    fn test_default_registry_generic() {
        let registry = create_default_registry();

        // Test generic network pattern (should work for any language)
        let ctx = MatchContext::new("http_get", "javascript");
        let result = registry.match_patterns(&ctx);
        assert!(result.effects.contains(&EffectType::Network));

        // Test generic cache pattern
        let ctx = MatchContext::new("cache_store", "go");
        let result = registry.match_patterns(&ctx);
        assert!(result.effects.contains(&EffectType::GlobalMutation));
        assert!(result.effects.contains(&EffectType::ReadState));
    }

    #[test]
    fn test_context_aware_pattern() {
        let registry = create_default_registry();

        // Test transaction + exception pattern
        let scope = vec!["rollback".to_string(), "raise".to_string()];
        let ctx = MatchContext::new("rollback", "python").with_scope(&scope);
        let result = registry.match_patterns(&ctx);
        assert!(result.effects.contains(&EffectType::DbWrite));
        assert!(result.effects.contains(&EffectType::Throws));
    }
}
