//! PathCondition Converter - Bridge between Taint and SMT modules
//!
//! **Purpose**: Convert simple Taint PathCondition to rich SMT PathCondition
//!
//! ## Problem
//! - Taint module: `PathCondition { var: String, value: bool, operator: Option<String> }`
//! - SMT module: `PathCondition { var: VarId, op: ComparisonOp, value: Option<ConstValue> }`
//!
//! ## Solution
//! Provide conversion layer for interoperability.
//!
//! ## Examples
//! ```text
//! use codegraph_ir::features::taint_analysis::infrastructure::path_condition_converter::*;
//!
//! // Taint condition: x > 5 (true branch)
//! let taint_cond = TaintPathCondition::comparison("x", ">", "5", true);
//!
//! // Convert to SMT condition
//! let smt_cond = convert_to_smt(&taint_cond)?;
//!
//! assert_eq!(smt_cond.var, "x");
//! assert_eq!(smt_cond.op, ComparisonOp::Gt);
//! assert_eq!(smt_cond.value, Some(ConstValue::Int(5)));
//! ```

use super::path_sensitive::PathCondition as TaintPathCondition;
use crate::errors::CodegraphError;
use crate::features::smt::domain::{ComparisonOp, ConstValue, PathCondition as SmtPathCondition};

/// Result type for conversion operations
pub type ConversionResult<T> = Result<T, CodegraphError>;

/// Convert Taint PathCondition to SMT PathCondition
///
/// # Algorithm
/// 1. Parse operator string ("==", ">", "<", etc.) → ComparisonOp enum
/// 2. Parse compared_value string → ConstValue typed value
/// 3. Handle negation (value=false → negate operator)
///
/// # Time Complexity
/// O(1) - Simple string parsing and enum mapping
///
/// # Example
/// ```text
/// let taint = TaintPathCondition::comparison("count", ">", "10", true);
/// let smt = convert_to_smt(&taint)?;
///
/// assert_eq!(smt.var, "count");
/// assert_eq!(smt.op, ComparisonOp::Gt);
/// assert_eq!(smt.value, Some(ConstValue::Int(10)));
/// ```
pub fn convert_to_smt(taint_cond: &TaintPathCondition) -> ConversionResult<SmtPathCondition> {
    // Parse operator
    let op = if let Some(operator) = &taint_cond.operator {
        parse_operator(operator, taint_cond.value)?
    } else {
        // Boolean condition: x (true) or !x (false)
        if taint_cond.value {
            ComparisonOp::NotNull // Treat as truthy check
        } else {
            ComparisonOp::Null // Treat as falsy check
        }
    };

    // Parse value
    let value = if let Some(compared_value) = &taint_cond.compared_value {
        Some(parse_const_value(compared_value)?)
    } else {
        None
    };

    Ok(SmtPathCondition {
        var: taint_cond.var.clone(),
        op,
        value,
        source_location: None,
    })
}

/// Convert batch of Taint conditions to SMT conditions
///
/// # Example
/// ```text
/// let taint_conditions = vec![
///     TaintPathCondition::boolean("is_admin", true),
///     TaintPathCondition::comparison("age", ">=", "18", true),
/// ];
///
/// let smt_conditions = convert_batch(&taint_conditions)?;
/// assert_eq!(smt_conditions.len(), 2);
/// ```
pub fn convert_batch(
    taint_conditions: &[TaintPathCondition],
) -> ConversionResult<Vec<SmtPathCondition>> {
    taint_conditions
        .iter()
        .map(convert_to_smt)
        .collect::<ConversionResult<Vec<_>>>()
}

/// Parse operator string to ComparisonOp enum
///
/// Handles negation for false branches:
/// - "==" (false) → Neq
/// - ">" (false) → Le
/// - ">=" (false) → Lt
fn parse_operator(operator_str: &str, is_true_branch: bool) -> ConversionResult<ComparisonOp> {
    let base_op = match operator_str {
        "==" => ComparisonOp::Eq,
        "!=" => ComparisonOp::Neq,
        "<" => ComparisonOp::Lt,
        ">" => ComparisonOp::Gt,
        "<=" => ComparisonOp::Le,
        ">=" => ComparisonOp::Ge,
        "is null" => ComparisonOp::Null,
        "is not null" => ComparisonOp::NotNull,
        _ => {
            return Err(CodegraphError::parse_error(format!(
                "Unknown operator: {}",
                operator_str
            )))
        }
    };

    // Apply negation for false branch
    Ok(if is_true_branch {
        base_op
    } else {
        negate_op(base_op)
    })
}

/// Negate comparison operator
///
/// Logic:
/// - == → !=
/// - != → ==
/// - < → >=
/// - > → <=
/// - <= → >
/// - >= → <
fn negate_op(op: ComparisonOp) -> ComparisonOp {
    match op {
        ComparisonOp::Eq => ComparisonOp::Neq,
        ComparisonOp::Neq => ComparisonOp::Eq,
        ComparisonOp::Lt => ComparisonOp::Ge,
        ComparisonOp::Gt => ComparisonOp::Le,
        ComparisonOp::Le => ComparisonOp::Gt,
        ComparisonOp::Ge => ComparisonOp::Lt,
        ComparisonOp::Null => ComparisonOp::NotNull,
        ComparisonOp::NotNull => ComparisonOp::Null,
    }
}

/// Parse string to typed ConstValue
///
/// Attempts to infer type from string format:
/// - "123" → Int(123)
/// - "3.14" → Float(3.14)
/// - "true"/"false" → Bool(true/false)
/// - "null" → Null
/// - '"text"' → String("text")
/// - Other → String (fallback)
fn parse_const_value(value_str: &str) -> ConversionResult<ConstValue> {
    // Try integer
    if let Ok(i) = value_str.parse::<i64>() {
        return Ok(ConstValue::Int(i));
    }

    // Try float
    if let Ok(f) = value_str.parse::<f64>() {
        return Ok(ConstValue::Float(f));
    }

    // Try boolean
    match value_str.to_lowercase().as_str() {
        "true" => return Ok(ConstValue::Bool(true)),
        "false" => return Ok(ConstValue::Bool(false)),
        "null" | "nil" | "none" => return Ok(ConstValue::Null),
        _ => {}
    }

    // String (remove quotes if present)
    let cleaned = value_str.trim_matches('"').trim_matches('\'');
    Ok(ConstValue::String(cleaned.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_convert_boolean_true() {
        let taint = TaintPathCondition::boolean("is_admin", true);
        let smt = convert_to_smt(&taint).unwrap();

        assert_eq!(smt.var, "is_admin");
        assert_eq!(smt.op, ComparisonOp::NotNull);
        assert_eq!(smt.value, None);
    }

    #[test]
    fn test_convert_boolean_false() {
        let taint = TaintPathCondition::boolean("is_guest", false);
        let smt = convert_to_smt(&taint).unwrap();

        assert_eq!(smt.var, "is_guest");
        assert_eq!(smt.op, ComparisonOp::Null);
    }

    #[test]
    fn test_convert_comparison_int() {
        let taint = TaintPathCondition::comparison("age", ">", "18", true);
        let smt = convert_to_smt(&taint).unwrap();

        assert_eq!(smt.var, "age");
        assert_eq!(smt.op, ComparisonOp::Gt);
        assert_eq!(smt.value, Some(ConstValue::Int(18)));
    }

    #[test]
    fn test_convert_comparison_negated() {
        let taint = TaintPathCondition::comparison("count", ">=", "10", false);
        let smt = convert_to_smt(&taint).unwrap();

        assert_eq!(smt.var, "count");
        assert_eq!(smt.op, ComparisonOp::Lt); // Negated >= → <
        assert_eq!(smt.value, Some(ConstValue::Int(10)));
    }

    #[test]
    fn test_convert_comparison_float() {
        let taint = TaintPathCondition::comparison("price", "<=", "99.99", true);
        let smt = convert_to_smt(&taint).unwrap();

        assert_eq!(smt.var, "price");
        assert_eq!(smt.op, ComparisonOp::Le);
        assert_eq!(smt.value, Some(ConstValue::Float(99.99)));
    }

    #[test]
    fn test_convert_comparison_string() {
        let taint = TaintPathCondition::comparison("name", "==", "\"admin\"", true);
        let smt = convert_to_smt(&taint).unwrap();

        assert_eq!(smt.var, "name");
        assert_eq!(smt.op, ComparisonOp::Eq);
        assert_eq!(smt.value, Some(ConstValue::String("admin".to_string())));
    }

    #[test]
    fn test_convert_batch() {
        let taint_conditions = vec![
            TaintPathCondition::boolean("is_logged_in", true),
            TaintPathCondition::comparison("role", "==", "\"admin\"", true),
            TaintPathCondition::comparison("age", ">=", "18", true),
        ];

        let smt_conditions = convert_batch(&taint_conditions).unwrap();

        assert_eq!(smt_conditions.len(), 3);
        assert_eq!(smt_conditions[0].op, ComparisonOp::NotNull);
        assert_eq!(smt_conditions[1].op, ComparisonOp::Eq);
        assert_eq!(smt_conditions[2].op, ComparisonOp::Ge);
    }

    #[test]
    fn test_parse_const_value_types() {
        assert_eq!(parse_const_value("123").unwrap(), ConstValue::Int(123));
        assert_eq!(parse_const_value("3.14").unwrap(), ConstValue::Float(3.14));
        assert_eq!(parse_const_value("true").unwrap(), ConstValue::Bool(true));
        assert_eq!(parse_const_value("null").unwrap(), ConstValue::Null);
        assert_eq!(
            parse_const_value("\"hello\"").unwrap(),
            ConstValue::String("hello".to_string())
        );
    }

    #[test]
    fn test_negate_operators() {
        assert_eq!(negate_op(ComparisonOp::Eq), ComparisonOp::Neq);
        assert_eq!(negate_op(ComparisonOp::Lt), ComparisonOp::Ge);
        assert_eq!(negate_op(ComparisonOp::Gt), ComparisonOp::Le);
        assert_eq!(negate_op(ComparisonOp::Le), ComparisonOp::Gt);
        assert_eq!(negate_op(ComparisonOp::Ge), ComparisonOp::Lt);
        assert_eq!(negate_op(ComparisonOp::Null), ComparisonOp::NotNull);
    }
}
