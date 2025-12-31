//! Generic (language-agnostic) effect patterns
//!
//! These patterns apply to all languages and detect common patterns
//! like design patterns, architectural patterns, etc.

use super::base::{KeywordPattern, MatchContext, MatchResult, PatternMatcher};
use crate::features::effect_analysis::domain::EffectType;
use std::collections::HashSet;

/// Generic network patterns
pub fn generic_network_patterns() -> Vec<Box<dyn PatternMatcher>> {
    vec![
        Box::new(KeywordPattern::new(
            "http",
            vec!["http", "https", "request", "fetch"],
            EffectType::Network,
        )),
        Box::new(KeywordPattern::new(
            "api",
            vec!["api", "rest", "graphql", "grpc"],
            EffectType::Network,
        )),
        Box::new(KeywordPattern::new(
            "socket",
            vec!["socket", "websocket", "tcp", "udp"],
            EffectType::Network,
        )),
    ]
}

/// Generic database patterns
pub fn generic_database_patterns() -> Vec<Box<dyn PatternMatcher>> {
    vec![
        Box::new(KeywordPattern::new(
            "db_write",
            vec!["insert", "update", "delete", "create", "drop", "alter"],
            EffectType::DbWrite,
        )),
        Box::new(KeywordPattern::new(
            "db_read",
            vec!["select", "query", "find", "search"],
            EffectType::DbRead,
        )),
        Box::new(KeywordPattern::new(
            "db_tx",
            vec!["commit", "rollback", "transaction"],
            EffectType::DbWrite,
        )),
    ]
}

/// Generic logging patterns
pub fn generic_logging_patterns() -> Vec<Box<dyn PatternMatcher>> {
    vec![
        Box::new(KeywordPattern::new(
            "log",
            vec!["log", "logger", "logging"],
            EffectType::Log,
        )),
        Box::new(KeywordPattern::new(
            "log_level",
            vec!["debug", "info", "warn", "error", "fatal", "trace"],
            EffectType::Log,
        )),
    ]
}

/// Design pattern: Callback/Handler/Observer
pub struct CallbackPattern;

impl PatternMatcher for CallbackPattern {
    fn name(&self) -> &'static str {
        "callback_pattern"
    }

    fn matches(&self, ctx: &MatchContext) -> MatchResult {
        let name_lower = ctx.name_lower();

        let is_callback = name_lower == "callback"
            || name_lower == "handler"
            || name_lower == "listener"
            || name_lower == "observer"
            || name_lower == "func"
            || name_lower == "fn"
            || name_lower == "function"
            || name_lower.ends_with("_callback")
            || name_lower.ends_with("_handler")
            || name_lower.ends_with("_listener");

        // Exclude DB/query handlers (domain-specific, not generic callbacks)
        if is_callback
            && !name_lower.contains("db")
            && !name_lower.contains("query")
            && !name_lower.contains("sql")
        {
            MatchResult::with_effect(EffectType::ExternalCall, 0.85)
                .with_reason("Callback/Handler pattern detected")
        } else {
            MatchResult::empty()
        }
    }

    fn priority(&self) -> i32 {
        10 // High priority (check before generic patterns)
    }
}

/// Design pattern: State/Cache/Singleton
pub struct StatefulPattern;

impl PatternMatcher for StatefulPattern {
    fn name(&self) -> &'static str {
        "stateful_pattern"
    }

    fn matches(&self, ctx: &MatchContext) -> MatchResult {
        let name_lower = ctx.name_lower();
        let mut effects = HashSet::new();

        // Cache patterns
        if name_lower.contains("cache") || name_lower.contains("memo") {
            effects.insert(EffectType::GlobalMutation);
            effects.insert(EffectType::ReadState); // Caches read before write
            return MatchResult::with_effects(effects, 0.9).with_reason("Cache pattern detected");
        }

        // Singleton patterns
        if name_lower.contains("singleton")
            || name_lower.contains("instance")
            || (name_lower.ends_with("_state") || name_lower == "state")
        {
            effects.insert(EffectType::GlobalMutation);
            return MatchResult::with_effects(effects, 0.85)
                .with_reason("Singleton/State pattern detected");
        }

        // Counter patterns
        if name_lower.contains("count")
            || name_lower.contains("counter")
            || name_lower.contains("attempt")
        {
            effects.insert(EffectType::GlobalMutation);
            return MatchResult::with_effects(effects, 0.8).with_reason("Counter pattern detected");
        }

        // Registry/Config patterns
        if name_lower.contains("registry")
            || name_lower.contains("config")
            || name_lower.contains("settings")
        {
            effects.insert(EffectType::GlobalMutation);
            return MatchResult::with_effects(effects, 0.85)
                .with_reason("Registry/Config pattern detected");
        }

        // Connection pool patterns
        if name_lower.contains("connection") || name_lower.contains("pool") {
            effects.insert(EffectType::GlobalMutation);
            return MatchResult::with_effects(effects, 0.8)
                .with_reason("Connection pool pattern detected");
        }

        // Idempotent tracking
        if name_lower == "processed" || name_lower.contains("visited") {
            effects.insert(EffectType::GlobalMutation);
            effects.insert(EffectType::ReadState);
            return MatchResult::with_effects(effects, 0.85)
                .with_reason("Idempotent tracking pattern detected");
        }

        MatchResult::empty()
    }

    fn priority(&self) -> i32 {
        5 // Medium priority
    }
}

/// Context-aware pattern: Transaction + Exception
pub struct TransactionExceptionPattern;

impl PatternMatcher for TransactionExceptionPattern {
    fn name(&self) -> &'static str {
        "transaction_exception"
    }

    fn matches(&self, ctx: &MatchContext) -> MatchResult {
        let name_lower = ctx.name_lower();

        // Check if this is a rollback in exception context
        if name_lower.contains("rollback") {
            // Check if "raise" or "throw" exists in scope
            let has_exception = ctx.scope_vars.iter().any(|v| v == "raise" || v == "throw");

            if has_exception {
                let mut effects = HashSet::new();
                effects.insert(EffectType::DbWrite);
                effects.insert(EffectType::Throws);
                return MatchResult::with_effects(effects, 0.9)
                    .with_reason("Transaction rollback in exception handler");
            }
        }

        MatchResult::empty()
    }

    fn priority(&self) -> i32 {
        15 // Very high priority (context-aware)
    }
}

/// Get all generic patterns
pub fn all_generic_patterns() -> Vec<Box<dyn PatternMatcher>> {
    let mut patterns: Vec<Box<dyn PatternMatcher>> = Vec::new();
    patterns.extend(generic_network_patterns());
    patterns.extend(generic_database_patterns());
    patterns.extend(generic_logging_patterns());
    patterns.push(Box::new(CallbackPattern));
    patterns.push(Box::new(StatefulPattern));
    patterns.push(Box::new(TransactionExceptionPattern));
    patterns
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_callback_pattern() {
        let ctx = MatchContext::new("callback", "any");
        let pattern = CallbackPattern;
        let result = pattern.matches(&ctx);
        assert!(result.effects.contains(&EffectType::ExternalCall));
    }

    #[test]
    fn test_cache_pattern() {
        let ctx = MatchContext::new("cache", "any");
        let pattern = StatefulPattern;
        let result = pattern.matches(&ctx);
        assert!(result.effects.contains(&EffectType::GlobalMutation));
        assert!(result.effects.contains(&EffectType::ReadState));
    }

    #[test]
    fn test_transaction_exception_context() {
        let scope = vec!["rollback".to_string(), "raise".to_string()];
        let ctx = MatchContext::new("rollback", "python").with_scope(&scope);
        let pattern = TransactionExceptionPattern;
        let result = pattern.matches(&ctx);
        assert!(result.effects.contains(&EffectType::DbWrite));
        assert!(result.effects.contains(&EffectType::Throws));
    }
}
