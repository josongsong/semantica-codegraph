//! JavaScript-specific patterns
//!
//! Patterns that are specific to JavaScript/TypeScript, including:
//! - Console I/O (console.log, console.error, etc.)
//! - Exception handling (throw)
//! - Promise/async patterns
//! - DOM manipulation
//! - Browser APIs

use super::base::{MatchContext, MatchResult, PatternMatcher};
use crate::features::effect_analysis::domain::EffectType;
use std::collections::HashSet;

// ============================================================================
// I/O Patterns
// ============================================================================

/// JavaScript console I/O patterns
pub fn javascript_io_patterns() -> Vec<Box<dyn PatternMatcher>> {
    vec![
        Box::new(
            KeywordPattern::new(
                "js_console_log",
                vec!["console.log", "console", "log"],
                EffectType::Io,
            )
            .with_confidence(0.95),
        ),
        Box::new(
            KeywordPattern::new(
                "js_console_error",
                vec![
                    "console.error",
                    "console.warn",
                    "console.info",
                    "console.debug",
                ],
                EffectType::Io,
            )
            .with_confidence(0.95),
        ),
        Box::new(
            KeywordPattern::new(
                "js_alert",
                vec!["alert", "confirm", "prompt"],
                EffectType::Io,
            )
            .with_confidence(0.9),
        ),
    ]
}

// ============================================================================
// Exception Patterns
// ============================================================================

/// JavaScript exception patterns
pub fn javascript_exception_patterns() -> Vec<Box<dyn PatternMatcher>> {
    vec![
        Box::new(
            KeywordPattern::new("js_throw", vec!["throw"], EffectType::Throws)
                .exact()
                .with_confidence(0.95),
        ),
        Box::new(
            KeywordPattern::new(
                "js_reject",
                vec!["reject", "Promise.reject"],
                EffectType::Throws,
            )
            .with_confidence(0.85),
        ),
    ]
}

// ============================================================================
// Async/Promise Patterns
// ============================================================================

/// JavaScript async/Promise patterns
pub fn javascript_async_patterns() -> Vec<Box<dyn PatternMatcher>> {
    vec![
        Box::new(
            KeywordPattern::new(
                "js_promise",
                vec!["Promise", "async", "await"],
                EffectType::ExternalCall,
            )
            .with_confidence(0.8),
        ),
        Box::new(
            KeywordPattern::new(
                "js_settimeout",
                vec!["setTimeout", "setInterval"],
                EffectType::ExternalCall,
            )
            .with_confidence(0.9),
        ),
    ]
}

// ============================================================================
// DOM Manipulation Patterns
// ============================================================================

/// JavaScript DOM manipulation patterns
pub fn javascript_dom_patterns() -> Vec<Box<dyn PatternMatcher>> {
    vec![
        Box::new(
            KeywordPattern::new(
                "js_dom_write",
                vec![
                    "innerHTML",
                    "outerHTML",
                    "textContent",
                    "appendChild",
                    "removeChild",
                    "setAttribute",
                ],
                EffectType::GlobalMutation,
            )
            .with_confidence(0.85),
        ),
        Box::new(
            KeywordPattern::new(
                "js_dom_read",
                vec![
                    "getElementById",
                    "querySelector",
                    "querySelectorAll",
                    "getElementsByClassName",
                ],
                EffectType::ReadState,
            )
            .with_confidence(0.8),
        ),
    ]
}

// ============================================================================
// Storage Patterns
// ============================================================================

/// JavaScript storage patterns (localStorage, sessionStorage, cookies)
pub fn javascript_storage_patterns() -> Vec<Box<dyn PatternMatcher>> {
    vec![
        Box::new(
            KeywordPattern::new(
                "js_localstorage",
                vec!["localStorage", "sessionStorage"],
                EffectType::GlobalMutation,
            )
            .with_confidence(0.9),
        ),
        Box::new(
            KeywordPattern::new(
                "js_cookie",
                vec!["document.cookie", "cookie"],
                EffectType::GlobalMutation,
            )
            .with_confidence(0.85),
        ),
    ]
}

// ============================================================================
// Network Patterns (JavaScript-specific)
// ============================================================================

/// JavaScript network patterns
pub fn javascript_network_patterns() -> Vec<Box<dyn PatternMatcher>> {
    vec![
        Box::new(
            KeywordPattern::new("js_fetch", vec!["fetch"], EffectType::Network)
                .with_confidence(0.95),
        ),
        Box::new(
            KeywordPattern::new("js_xhr", vec!["XMLHttpRequest", "xhr"], EffectType::Network)
                .with_confidence(0.9),
        ),
        Box::new(
            KeywordPattern::new(
                "js_websocket",
                vec!["WebSocket", "websocket"],
                EffectType::Network,
            )
            .with_confidence(0.95),
        ),
    ]
}

// ============================================================================
// Custom Pattern: JavaScript Global Mutation
// ============================================================================

/// Detects JavaScript global variable patterns
pub struct JavaScriptGlobalPattern;

impl PatternMatcher for JavaScriptGlobalPattern {
    fn name(&self) -> &'static str {
        "js_global_var"
    }

    fn matches(&self, ctx: &MatchContext) -> MatchResult {
        let name_lower = ctx.name.to_lowercase();

        // JavaScript globals: window.*, global.*, globalThis.*
        if name_lower.starts_with("window.")
            || name_lower.starts_with("global.")
            || name_lower.starts_with("globalthis.")
        {
            return MatchResult::with_effect(EffectType::GlobalMutation, 0.9)
                .with_reason("JavaScript global object mutation");
        }

        // JavaScript var (function-scoped, can be global)
        if name_lower == "var" {
            return MatchResult::with_effect(EffectType::GlobalMutation, 0.7)
                .with_reason("JavaScript 'var' declaration (potentially global)");
        }

        MatchResult::empty()
    }

    fn priority(&self) -> i32 {
        50
    }
}

// ============================================================================
// Aggregate Function
// ============================================================================

/// Returns all JavaScript-specific patterns
pub fn all_javascript_patterns() -> Vec<Box<dyn PatternMatcher>> {
    let mut patterns: Vec<Box<dyn PatternMatcher>> = Vec::new();

    patterns.extend(javascript_io_patterns());
    patterns.extend(javascript_exception_patterns());
    patterns.extend(javascript_async_patterns());
    patterns.extend(javascript_dom_patterns());
    patterns.extend(javascript_storage_patterns());
    patterns.extend(javascript_network_patterns());

    // Custom patterns
    patterns.push(Box::new(JavaScriptGlobalPattern));

    patterns
}

// ============================================================================
// Helper: KeywordPattern (re-export for convenience)
// ============================================================================

use super::base::KeywordPattern;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_javascript_console_log() {
        let ctx = MatchContext::new("console.log", "javascript");
        let patterns = javascript_io_patterns();
        let result = patterns[0].matches(&ctx);
        assert!(result.effects.contains(&EffectType::Io));
        assert!(result.confidence > 0.9);
    }

    #[test]
    fn test_javascript_throw() {
        let ctx = MatchContext::new("throw", "javascript");
        let patterns = javascript_exception_patterns();
        let result = patterns[0].matches(&ctx);
        assert!(result.effects.contains(&EffectType::Throws));
    }

    #[test]
    fn test_javascript_global_window() {
        let ctx = MatchContext::new("window.location", "javascript");
        let pattern = JavaScriptGlobalPattern;
        let result = pattern.matches(&ctx);
        assert!(result.effects.contains(&EffectType::GlobalMutation));
    }

    #[test]
    fn test_javascript_fetch() {
        let ctx = MatchContext::new("fetch", "javascript");
        let patterns = javascript_network_patterns();
        let result = patterns[0].matches(&ctx);
        assert!(result.effects.contains(&EffectType::Network));
    }
}
