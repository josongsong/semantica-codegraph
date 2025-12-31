//! Sanitizer Database
//!
//! Pattern-based sanitizer effect modeling for security analysis.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Sanitizer effect types
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SanitizerEffect {
    /// HTML escaping (prevents XSS)
    HtmlEscape,

    /// SQL escaping (prevents SQL injection)
    SqlEscape,

    /// Command escaping (prevents command injection)
    CommandEscape,

    /// Path normalization (prevents path traversal)
    PathNormalization,

    /// Input validation with regex pattern
    InputValidation(String),

    /// URL encoding
    UrlEncode,

    /// JSON encoding
    JsonEncode,

    /// No operation (no sanitization)
    NoOp,
}

/// Taint type for classification
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TaintType {
    /// Cross-site scripting
    Xss,

    /// SQL injection
    SqlInjection,

    /// Command injection
    CommandInjection,

    /// Path traversal
    PathTraversal,

    /// Generic taint
    Generic,
}

/// Sanitizer database
pub struct SanitizerDB {
    /// Function name → sanitizer effect mapping
    sanitizers: HashMap<String, SanitizerEffect>,
}

impl Default for SanitizerDB {
    fn default() -> Self {
        Self::new()
    }
}

impl SanitizerDB {
    /// Create new sanitizer database with built-in patterns
    pub fn new() -> Self {
        let mut db = Self {
            sanitizers: HashMap::new(),
        };

        // HTML escaping
        db.register("html.escape", SanitizerEffect::HtmlEscape);
        db.register("html_escape", SanitizerEffect::HtmlEscape);
        db.register("escape_html", SanitizerEffect::HtmlEscape);
        db.register("htmlspecialchars", SanitizerEffect::HtmlEscape);
        db.register("escapeHtml", SanitizerEffect::HtmlEscape);

        // SQL escaping
        db.register("sql_escape", SanitizerEffect::SqlEscape);
        db.register("escape_sql", SanitizerEffect::SqlEscape);
        db.register("mysql_real_escape_string", SanitizerEffect::SqlEscape);
        db.register("pg_escape_string", SanitizerEffect::SqlEscape);
        db.register("sqlite3_escape", SanitizerEffect::SqlEscape);

        // Command escaping
        db.register("shlex.quote", SanitizerEffect::CommandEscape);
        db.register("shell_escape", SanitizerEffect::CommandEscape);
        db.register("escapeshellarg", SanitizerEffect::CommandEscape);
        db.register("escapeshellcmd", SanitizerEffect::CommandEscape);

        // Path normalization
        db.register("os.path.abspath", SanitizerEffect::PathNormalization);
        db.register("os.path.normpath", SanitizerEffect::PathNormalization);
        db.register("path.normalize", SanitizerEffect::PathNormalization);
        db.register("realpath", SanitizerEffect::PathNormalization);

        // URL encoding
        db.register("urllib.parse.quote", SanitizerEffect::UrlEncode);
        db.register("urlencode", SanitizerEffect::UrlEncode);
        db.register("encodeURIComponent", SanitizerEffect::UrlEncode);

        // JSON encoding
        db.register("json.dumps", SanitizerEffect::JsonEncode);
        db.register("json.encode", SanitizerEffect::JsonEncode);
        db.register("JSON.stringify", SanitizerEffect::JsonEncode);

        db
    }

    /// Register new sanitizer pattern
    pub fn register(&mut self, function_name: &str, effect: SanitizerEffect) {
        self.sanitizers.insert(function_name.to_string(), effect);
    }

    /// Get sanitizer effect for a function name
    pub fn get_effect(&self, function_name: &str) -> Option<&SanitizerEffect> {
        self.sanitizers.get(function_name)
    }

    /// Check if sanitizer blocks given taint type
    pub fn blocks_taint(&self, function_name: &str, taint_type: &TaintType) -> bool {
        if let Some(effect) = self.get_effect(function_name) {
            match (effect, taint_type) {
                (SanitizerEffect::HtmlEscape, TaintType::Xss) => true,
                (SanitizerEffect::SqlEscape, TaintType::SqlInjection) => true,
                (SanitizerEffect::CommandEscape, TaintType::CommandInjection) => true,
                (SanitizerEffect::PathNormalization, TaintType::PathTraversal) => true,
                (SanitizerEffect::UrlEncode, TaintType::Xss) => true,
                (SanitizerEffect::JsonEncode, TaintType::Xss) => true,
                _ => false,
            }
        } else {
            false
        }
    }

    /// Check if function is a known sanitizer
    pub fn is_sanitizer(&self, function_name: &str) -> bool {
        self.sanitizers.contains_key(function_name)
    }

    /// Get all registered sanitizers
    pub fn all_sanitizers(&self) -> Vec<&str> {
        self.sanitizers.keys().map(|s| s.as_str()).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sanitizer_db_creation() {
        let db = SanitizerDB::new();
        assert!(db.is_sanitizer("html.escape"));
        assert!(db.is_sanitizer("sql_escape"));
        assert!(!db.is_sanitizer("unknown_function"));
    }

    #[test]
    fn test_html_escape_blocks_xss() {
        let db = SanitizerDB::new();
        assert!(db.blocks_taint("html.escape", &TaintType::Xss));
        assert!(!db.blocks_taint("html.escape", &TaintType::SqlInjection));
    }

    #[test]
    fn test_sql_escape_blocks_sql_injection() {
        let db = SanitizerDB::new();
        assert!(db.blocks_taint("sql_escape", &TaintType::SqlInjection));
        assert!(!db.blocks_taint("sql_escape", &TaintType::Xss));
    }

    #[test]
    fn test_custom_sanitizer_registration() {
        let mut db = SanitizerDB::new();
        db.register("custom_escape", SanitizerEffect::HtmlEscape);
        assert!(db.is_sanitizer("custom_escape"));
        assert!(db.blocks_taint("custom_escape", &TaintType::Xss));
    }

    #[test]
    fn test_get_all_sanitizers() {
        let db = SanitizerDB::new();
        let all = db.all_sanitizers();
        assert!(all.len() > 10);
        assert!(all.contains(&"html.escape"));
    }
}
