// Expression AST - Type-safe filtering without closures
//
// Provides FFI-safe, serializable expression trees for filtering:
// - Field access, literals, comparisons
// - String operations (contains, regex, startswith, endswith)
// - Boolean logic (and, or, not)
// - Null checks
//
// Design: RFC-RUST-SDK-002

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};
use thiserror::Error;

/// Expression AST for filtering (FFI-safe, fully serializable)
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum Expr {
    // Field access
    Field(String),

    // Literals
    Literal(Value),

    // Comparison operators
    Eq(Box<Expr>, Box<Expr>),
    Ne(Box<Expr>, Box<Expr>),
    Lt(Box<Expr>, Box<Expr>),
    Lte(Box<Expr>, Box<Expr>),
    Gt(Box<Expr>, Box<Expr>),
    Gte(Box<Expr>, Box<Expr>),

    // String operations
    Contains(Box<Expr>, String),
    Regex(Box<Expr>, String),
    StartsWith(Box<Expr>, String),
    EndsWith(Box<Expr>, String),

    // Boolean logic
    And(Vec<Expr>),
    Or(Vec<Expr>),
    Not(Box<Expr>),

    // Null checks
    IsNull(Box<Expr>),
    IsNotNull(Box<Expr>),
}

/// Value types for literals (Arrow/JSON compatible - RFC-RUST-SDK-002 P0)
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum Value {
    Null,
    Int(i64),
    Float(f64),
    String(String),
    Bool(bool),
    List(Vec<Value>),
    Object(BTreeMap<String, Value>), // BTreeMap for deterministic ordering
    Bytes(Vec<u8>),
    Timestamp(i64), // Unix timestamp in microseconds
}

/// Errors for expression operations
#[derive(Debug, Error, Clone, PartialEq)]
pub enum ExprError {
    #[error("NaN values are not allowed in expressions")]
    NaNNotAllowed,

    #[error("Invalid expression structure: {0}")]
    InvalidStructure(String),
}

/// Comparison operator (sugar for builder)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Op {
    Eq,
    Ne,
    Lt,
    Lte,
    Gt,
    Gte,
    Contains,
    Regex,
    StartsWith,
    EndsWith,
}

impl Expr {
    /// Canonicalize expression for deterministic hashing (RFC-RUST-SDK-002 P0)
    ///
    /// Rules:
    /// 1. And/Or operands sorted by serialized representation
    /// 2. Object keys sorted (BTreeMap already handles this)
    /// 3. Float NaN rejected, -0.0 normalized to 0.0
    ///
    /// This ensures that logically equivalent expressions produce identical hashes.
    pub fn canonicalize(self) -> Result<Self, ExprError> {
        match self {
            // Recursively canonicalize And operands and sort
            Expr::And(exprs) => {
                let mut canonical = Vec::new();
                for e in exprs {
                    canonical.push(e.canonicalize()?);
                }
                // Sort by JSON serialization for determinism (stable, human-readable)
                canonical.sort_by_cached_key(|e| {
                    serde_json::to_string(e).unwrap_or_default()
                });
                Ok(Expr::And(canonical))
            }

            // Recursively canonicalize Or operands and sort
            Expr::Or(exprs) => {
                let mut canonical = Vec::new();
                for e in exprs {
                    canonical.push(e.canonicalize()?);
                }
                canonical.sort_by_cached_key(|e| {
                    serde_json::to_string(e).unwrap_or_default()
                });
                Ok(Expr::Or(canonical))
            }

            // Float normalization: reject NaN, normalize -0.0
            Expr::Literal(Value::Float(f)) => {
                if f.is_nan() {
                    return Err(ExprError::NaNNotAllowed);
                }
                let normalized = if f == -0.0 { 0.0 } else { f };
                Ok(Expr::Literal(Value::Float(normalized)))
            }

            // Recursively canonicalize nested expressions
            Expr::Eq(left, right) => Ok(Expr::Eq(
                Box::new(left.canonicalize()?),
                Box::new(right.canonicalize()?),
            )),
            Expr::Ne(left, right) => Ok(Expr::Ne(
                Box::new(left.canonicalize()?),
                Box::new(right.canonicalize()?),
            )),
            Expr::Lt(left, right) => Ok(Expr::Lt(
                Box::new(left.canonicalize()?),
                Box::new(right.canonicalize()?),
            )),
            Expr::Lte(left, right) => Ok(Expr::Lte(
                Box::new(left.canonicalize()?),
                Box::new(right.canonicalize()?),
            )),
            Expr::Gt(left, right) => Ok(Expr::Gt(
                Box::new(left.canonicalize()?),
                Box::new(right.canonicalize()?),
            )),
            Expr::Gte(left, right) => Ok(Expr::Gte(
                Box::new(left.canonicalize()?),
                Box::new(right.canonicalize()?),
            )),

            // String operations
            Expr::Contains(field, pattern) => {
                Ok(Expr::Contains(Box::new(field.canonicalize()?), pattern))
            }
            Expr::Regex(field, pattern) => {
                Ok(Expr::Regex(Box::new(field.canonicalize()?), pattern))
            }
            Expr::StartsWith(field, pattern) => {
                Ok(Expr::StartsWith(Box::new(field.canonicalize()?), pattern))
            }
            Expr::EndsWith(field, pattern) => {
                Ok(Expr::EndsWith(Box::new(field.canonicalize()?), pattern))
            }

            // Boolean
            Expr::Not(e) => Ok(Expr::Not(Box::new(e.canonicalize()?))),

            // Null checks
            Expr::IsNull(e) => Ok(Expr::IsNull(Box::new(e.canonicalize()?))),
            Expr::IsNotNull(e) => Ok(Expr::IsNotNull(Box::new(e.canonicalize()?))),

            // Field and literals (no change needed)
            other => Ok(other),
        }
    }

    /// Compute deterministic hash of expression (after canonicalization)
    pub fn hash_canonical(&self) -> Result<[u8; 32], ExprError> {
        let canonical = self.clone().canonicalize()?;
        let serialized = serde_json::to_string(&canonical)
            .map_err(|e| ExprError::InvalidStructure(e.to_string()))?;
        Ok(blake3::hash(serialized.as_bytes()).into())
    }
}

/// Expression builder for ergonomic construction
pub struct ExprBuilder;

impl ExprBuilder {
    /// Create field reference
    pub fn field(name: &str) -> Expr {
        Expr::Field(name.to_string())
    }

    /// Create literal value
    pub fn literal<T: Into<Value>>(value: T) -> Expr {
        Expr::Literal(value.into())
    }

    /// Equal comparison
    pub fn eq(field: &str, value: impl Into<Value>) -> Expr {
        Expr::Eq(
            Box::new(Expr::Field(field.to_string())),
            Box::new(Expr::Literal(value.into())),
        )
    }

    /// Not equal comparison
    pub fn ne(field: &str, value: impl Into<Value>) -> Expr {
        Expr::Ne(
            Box::new(Expr::Field(field.to_string())),
            Box::new(Expr::Literal(value.into())),
        )
    }

    /// Less than comparison
    pub fn lt(field: &str, value: impl Into<Value>) -> Expr {
        Expr::Lt(
            Box::new(Expr::Field(field.to_string())),
            Box::new(Expr::Literal(value.into())),
        )
    }

    /// Less than or equal comparison
    pub fn lte(field: &str, value: impl Into<Value>) -> Expr {
        Expr::Lte(
            Box::new(Expr::Field(field.to_string())),
            Box::new(Expr::Literal(value.into())),
        )
    }

    /// Greater than comparison
    pub fn gt(field: &str, value: impl Into<Value>) -> Expr {
        Expr::Gt(
            Box::new(Expr::Field(field.to_string())),
            Box::new(Expr::Literal(value.into())),
        )
    }

    /// Greater than or equal comparison
    pub fn gte(field: &str, value: impl Into<Value>) -> Expr {
        Expr::Gte(
            Box::new(Expr::Field(field.to_string())),
            Box::new(Expr::Literal(value.into())),
        )
    }

    /// String contains
    pub fn contains(field: &str, pattern: &str) -> Expr {
        Expr::Contains(
            Box::new(Expr::Field(field.to_string())),
            pattern.to_string(),
        )
    }

    /// Regex match
    pub fn regex(field: &str, pattern: &str) -> Expr {
        Expr::Regex(
            Box::new(Expr::Field(field.to_string())),
            pattern.to_string(),
        )
    }

    /// String starts with
    pub fn starts_with(field: &str, prefix: &str) -> Expr {
        Expr::StartsWith(
            Box::new(Expr::Field(field.to_string())),
            prefix.to_string(),
        )
    }

    /// String ends with
    pub fn ends_with(field: &str, suffix: &str) -> Expr {
        Expr::EndsWith(
            Box::new(Expr::Field(field.to_string())),
            suffix.to_string(),
        )
    }

    /// Logical AND
    pub fn and(exprs: Vec<Expr>) -> Expr {
        Expr::And(exprs)
    }

    /// Logical OR
    pub fn or(exprs: Vec<Expr>) -> Expr {
        Expr::Or(exprs)
    }

    /// Logical NOT
    pub fn not(expr: Expr) -> Expr {
        Expr::Not(Box::new(expr))
    }

    /// Is null check
    pub fn is_null(field: &str) -> Expr {
        Expr::IsNull(Box::new(Expr::Field(field.to_string())))
    }

    /// Is not null check
    pub fn is_not_null(field: &str) -> Expr {
        Expr::IsNotNull(Box::new(Expr::Field(field.to_string())))
    }
}

// Implement Into<Value> for common types
impl From<i64> for Value {
    fn from(v: i64) -> Self {
        Value::Int(v)
    }
}

impl From<i32> for Value {
    fn from(v: i32) -> Self {
        Value::Int(v as i64)
    }
}

impl From<f64> for Value {
    fn from(v: f64) -> Self {
        Value::Float(v)
    }
}

impl From<&str> for Value {
    fn from(v: &str) -> Self {
        Value::String(v.to_string())
    }
}

impl From<String> for Value {
    fn from(v: String) -> Self {
        Value::String(v)
    }
}

impl From<bool> for Value {
    fn from(v: bool) -> Self {
        Value::Bool(v)
    }
}

impl From<Vec<Value>> for Value {
    fn from(v: Vec<Value>) -> Self {
        Value::List(v)
    }
}

impl From<BTreeMap<String, Value>> for Value {
    fn from(v: BTreeMap<String, Value>) -> Self {
        Value::Object(v)
    }
}

impl From<Vec<u8>> for Value {
    fn from(v: Vec<u8>) -> Self {
        Value::Bytes(v)
    }
}

/// Expression evaluator - evaluates Expr against a field map
pub struct ExprEvaluator;

impl ExprEvaluator {
    /// Evaluate expression against field values
    pub fn eval(expr: &Expr, fields: &HashMap<String, String>) -> bool {
        match expr {
            Expr::Field(_) => {
                // Field reference alone is truthy if exists and non-empty
                false // Should not be used standalone
            }
            Expr::Literal(val) => match val {
                Value::Bool(b) => *b,
                _ => false,
            },
            Expr::Eq(left, right) => {
                Self::eval_comparison(left, right, fields, |a, b| a == b)
            }
            Expr::Ne(left, right) => {
                Self::eval_comparison(left, right, fields, |a, b| a != b)
            }
            Expr::Lt(left, right) => {
                Self::eval_numeric_comparison(left, right, fields, |a, b| a < b)
            }
            Expr::Lte(left, right) => {
                Self::eval_numeric_comparison(left, right, fields, |a, b| a <= b)
            }
            Expr::Gt(left, right) => {
                Self::eval_numeric_comparison(left, right, fields, |a, b| a > b)
            }
            Expr::Gte(left, right) => {
                Self::eval_numeric_comparison(left, right, fields, |a, b| a >= b)
            }
            Expr::Contains(field_expr, pattern) => {
                if let Expr::Field(field_name) = field_expr.as_ref() {
                    fields
                        .get(field_name)
                        .map(|v| v.contains(pattern))
                        .unwrap_or(false)
                } else {
                    false
                }
            }
            Expr::Regex(field_expr, pattern) => {
                if let Expr::Field(field_name) = field_expr.as_ref() {
                    fields
                        .get(field_name)
                        .and_then(|v| {
                            regex::Regex::new(pattern)
                                .ok()
                                .map(|re| re.is_match(v))
                        })
                        .unwrap_or(false)
                } else {
                    false
                }
            }
            Expr::StartsWith(field_expr, prefix) => {
                if let Expr::Field(field_name) = field_expr.as_ref() {
                    fields
                        .get(field_name)
                        .map(|v| v.starts_with(prefix))
                        .unwrap_or(false)
                } else {
                    false
                }
            }
            Expr::EndsWith(field_expr, suffix) => {
                if let Expr::Field(field_name) = field_expr.as_ref() {
                    fields
                        .get(field_name)
                        .map(|v| v.ends_with(suffix))
                        .unwrap_or(false)
                } else {
                    false
                }
            }
            Expr::And(exprs) => exprs.iter().all(|e| Self::eval(e, fields)),
            Expr::Or(exprs) => exprs.iter().any(|e| Self::eval(e, fields)),
            Expr::Not(expr) => !Self::eval(expr, fields),
            Expr::IsNull(field_expr) => {
                if let Expr::Field(field_name) = field_expr.as_ref() {
                    !fields.contains_key(field_name) || fields.get(field_name).unwrap().is_empty()
                } else {
                    false
                }
            }
            Expr::IsNotNull(field_expr) => {
                if let Expr::Field(field_name) = field_expr.as_ref() {
                    fields.contains_key(field_name) && !fields.get(field_name).unwrap().is_empty()
                } else {
                    false
                }
            }
        }
    }

    /// Helper: Evaluate string comparison
    fn eval_comparison<F>(
        left: &Expr,
        right: &Expr,
        fields: &HashMap<String, String>,
        op: F,
    ) -> bool
    where
        F: Fn(&str, &str) -> bool,
    {
        let left_val = Self::get_value(left, fields);
        let right_val = Self::get_value(right, fields);

        match (left_val, right_val) {
            (Some(l), Some(r)) => op(&l, &r),
            _ => false,
        }
    }

    /// Helper: Evaluate numeric comparison
    fn eval_numeric_comparison<F>(
        left: &Expr,
        right: &Expr,
        fields: &HashMap<String, String>,
        op: F,
    ) -> bool
    where
        F: Fn(f64, f64) -> bool,
    {
        let left_val = Self::get_numeric_value(left, fields);
        let right_val = Self::get_numeric_value(right, fields);

        match (left_val, right_val) {
            (Some(l), Some(r)) => op(l, r),
            _ => false,
        }
    }

    /// Helper: Get string value from expression
    fn get_value(expr: &Expr, fields: &HashMap<String, String>) -> Option<String> {
        match expr {
            Expr::Field(name) => fields.get(name).cloned(),
            Expr::Literal(val) => match val {
                Value::Null => Some("null".to_string()),
                Value::String(s) => Some(s.clone()),
                Value::Int(i) => Some(i.to_string()),
                Value::Float(f) => Some(f.to_string()),
                Value::Bool(b) => Some(b.to_string()),
                Value::List(list) => Some(format!("[{} items]", list.len())),
                Value::Object(obj) => Some(format!("{{{}fields}}", obj.len())),
                Value::Bytes(bytes) => Some(format!("<{} bytes>", bytes.len())),
                Value::Timestamp(ts) => Some(ts.to_string()),
            },
            _ => None,
        }
    }

    /// Helper: Get numeric value from expression
    fn get_numeric_value(expr: &Expr, fields: &HashMap<String, String>) -> Option<f64> {
        match expr {
            Expr::Field(name) => fields.get(name).and_then(|v| v.parse::<f64>().ok()),
            Expr::Literal(val) => match val {
                Value::Int(i) => Some(*i as f64),
                Value::Float(f) => Some(*f),
                Value::String(s) => s.parse::<f64>().ok(),
                Value::Timestamp(ts) => Some(*ts as f64),
                _ => None,
            },
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_fields() -> HashMap<String, String> {
        let mut fields = HashMap::new();
        fields.insert("name".to_string(), "process_data".to_string());
        fields.insert("language".to_string(), "python".to_string());
        fields.insert("complexity".to_string(), "15".to_string());
        fields.insert("lines".to_string(), "100".to_string());
        fields
    }

    #[test]
    fn test_eq_comparison() {
        let fields = make_fields();
        let expr = ExprBuilder::eq("language", "python");
        assert!(ExprEvaluator::eval(&expr, &fields));

        let expr = ExprBuilder::eq("language", "javascript");
        assert!(!ExprEvaluator::eval(&expr, &fields));
    }

    #[test]
    fn test_numeric_comparison() {
        let fields = make_fields();

        // Greater than
        let expr = ExprBuilder::gt("complexity", 10);
        assert!(ExprEvaluator::eval(&expr, &fields));

        let expr = ExprBuilder::gt("complexity", 20);
        assert!(!ExprEvaluator::eval(&expr, &fields));

        // Greater than or equal
        let expr = ExprBuilder::gte("complexity", 15);
        assert!(ExprEvaluator::eval(&expr, &fields));

        // Less than
        let expr = ExprBuilder::lt("complexity", 20);
        assert!(ExprEvaluator::eval(&expr, &fields));
    }

    #[test]
    fn test_string_operations() {
        let fields = make_fields();

        // Contains
        let expr = ExprBuilder::contains("name", "process");
        assert!(ExprEvaluator::eval(&expr, &fields));

        let expr = ExprBuilder::contains("name", "invalid");
        assert!(!ExprEvaluator::eval(&expr, &fields));

        // Starts with
        let expr = ExprBuilder::starts_with("name", "process");
        assert!(ExprEvaluator::eval(&expr, &fields));

        // Ends with
        let expr = ExprBuilder::ends_with("name", "data");
        assert!(ExprEvaluator::eval(&expr, &fields));

        // Regex
        let expr = ExprBuilder::regex("name", "process.*");
        assert!(ExprEvaluator::eval(&expr, &fields));
    }

    #[test]
    fn test_boolean_logic() {
        let fields = make_fields();

        // AND
        let expr = ExprBuilder::and(vec![
            ExprBuilder::eq("language", "python"),
            ExprBuilder::gt("complexity", 10),
        ]);
        assert!(ExprEvaluator::eval(&expr, &fields));

        let expr = ExprBuilder::and(vec![
            ExprBuilder::eq("language", "python"),
            ExprBuilder::gt("complexity", 20),
        ]);
        assert!(!ExprEvaluator::eval(&expr, &fields));

        // OR
        let expr = ExprBuilder::or(vec![
            ExprBuilder::eq("language", "javascript"),
            ExprBuilder::gt("complexity", 10),
        ]);
        assert!(ExprEvaluator::eval(&expr, &fields));

        // NOT
        let expr = ExprBuilder::not(ExprBuilder::eq("language", "javascript"));
        assert!(ExprEvaluator::eval(&expr, &fields));
    }

    #[test]
    fn test_null_checks() {
        let mut fields = HashMap::new();
        fields.insert("name".to_string(), "test".to_string());

        // Is not null
        let expr = ExprBuilder::is_not_null("name");
        assert!(ExprEvaluator::eval(&expr, &fields));

        // Is null
        let expr = ExprBuilder::is_null("missing_field");
        assert!(ExprEvaluator::eval(&expr, &fields));
    }

    #[test]
    fn test_complex_expression() {
        let fields = make_fields();

        // (language == "python" AND complexity >= 10) OR name contains "test"
        let expr = ExprBuilder::or(vec![
            ExprBuilder::and(vec![
                ExprBuilder::eq("language", "python"),
                ExprBuilder::gte("complexity", 10),
            ]),
            ExprBuilder::contains("name", "test"),
        ]);

        assert!(ExprEvaluator::eval(&expr, &fields));
    }

    #[test]
    fn test_serialization() {
        let expr = ExprBuilder::and(vec![
            ExprBuilder::eq("language", "python"),
            ExprBuilder::gte("complexity", 10),
        ]);

        // Serialize to JSON
        let json = serde_json::to_string(&expr).unwrap();
        assert!(json.contains("python"));
        assert!(json.contains("complexity"));

        // Deserialize back
        let deserialized: Expr = serde_json::from_str(&json).unwrap();
        assert_eq!(expr, deserialized);
    }

    // P0 Critical Tests: Canonicalization (RFC-RUST-SDK-002)

    #[test]
    fn test_canonicalize_and_ordering() {
        // Same expressions in different order should canonicalize to same hash
        let expr1 = ExprBuilder::and(vec![
            ExprBuilder::eq("language", "python"),
            ExprBuilder::gte("complexity", 10),
        ]);

        let expr2 = ExprBuilder::and(vec![
            ExprBuilder::gte("complexity", 10),
            ExprBuilder::eq("language", "python"),
        ]);

        let hash1 = expr1.hash_canonical().unwrap();
        let hash2 = expr2.hash_canonical().unwrap();

        assert_eq!(
            hash1, hash2,
            "Expressions with same operands in different order should have identical hashes"
        );
    }

    #[test]
    fn test_canonicalize_or_ordering() {
        let expr1 = ExprBuilder::or(vec![
            ExprBuilder::eq("language", "python"),
            ExprBuilder::eq("language", "javascript"),
        ]);

        let expr2 = ExprBuilder::or(vec![
            ExprBuilder::eq("language", "javascript"),
            ExprBuilder::eq("language", "python"),
        ]);

        let hash1 = expr1.hash_canonical().unwrap();
        let hash2 = expr2.hash_canonical().unwrap();

        assert_eq!(hash1, hash2, "Or expressions should be order-independent");
    }

    #[test]
    fn test_canonicalize_nested_and_or() {
        // Complex nested expression
        let expr1 = ExprBuilder::and(vec![
            ExprBuilder::or(vec![
                ExprBuilder::eq("language", "python"),
                ExprBuilder::eq("language", "rust"),
            ]),
            ExprBuilder::gte("complexity", 10),
        ]);

        let expr2 = ExprBuilder::and(vec![
            ExprBuilder::gte("complexity", 10),
            ExprBuilder::or(vec![
                ExprBuilder::eq("language", "rust"),
                ExprBuilder::eq("language", "python"),
            ]),
        ]);

        let hash1 = expr1.hash_canonical().unwrap();
        let hash2 = expr2.hash_canonical().unwrap();

        assert_eq!(
            hash1, hash2,
            "Nested expressions should canonicalize identically"
        );
    }

    #[test]
    fn test_canonicalize_float_normalization() {
        let expr1 = Expr::Literal(Value::Float(0.0));
        let expr2 = Expr::Literal(Value::Float(-0.0));

        let canonical1 = expr1.canonicalize().unwrap();
        let canonical2 = expr2.canonicalize().unwrap();

        assert_eq!(
            canonical1, canonical2,
            "0.0 and -0.0 should canonicalize to the same value"
        );
    }

    #[test]
    fn test_canonicalize_nan_rejection() {
        let expr = Expr::Literal(Value::Float(f64::NAN));
        let result = expr.canonicalize();

        assert!(result.is_err(), "NaN should be rejected");
        assert_eq!(result.unwrap_err(), ExprError::NaNNotAllowed);
    }

    #[test]
    fn test_value_null() {
        let null_value = Value::Null;
        let json = serde_json::to_string(&null_value).unwrap();
        assert_eq!(json, "null");

        let deserialized: Value = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized, Value::Null);
    }

    #[test]
    fn test_value_list() {
        let list = Value::List(vec![Value::Int(1), Value::Int(2), Value::Int(3)]);
        let json = serde_json::to_string(&list).unwrap();
        assert!(json.contains("["));

        let deserialized: Value = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized, list);
    }

    #[test]
    fn test_value_object() {
        let mut obj = BTreeMap::new();
        obj.insert("key1".to_string(), Value::String("value1".to_string()));
        obj.insert("key2".to_string(), Value::Int(42));

        let value = Value::Object(obj.clone());
        let json = serde_json::to_string(&value).unwrap();

        // BTreeMap ensures deterministic key ordering
        let deserialized: Value = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized, value);
    }

    #[test]
    fn test_value_timestamp() {
        let ts = Value::Timestamp(1672531200000000); // 2023-01-01 00:00:00 UTC in microseconds
        let json = serde_json::to_string(&ts).unwrap();

        let deserialized: Value = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized, ts);
    }

    #[test]
    fn test_deterministic_hash_stability() {
        // Same expression should always produce same hash
        let expr = ExprBuilder::and(vec![
            ExprBuilder::eq("language", "python"),
            ExprBuilder::gte("complexity", 10),
            ExprBuilder::contains("name", "process"),
        ]);

        let hash1 = expr.hash_canonical().unwrap();
        let hash2 = expr.clone().hash_canonical().unwrap();
        let hash3 = expr.hash_canonical().unwrap();

        assert_eq!(hash1, hash2);
        assert_eq!(hash2, hash3);
    }
}
