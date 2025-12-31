//! Path Condition Domain Models
//!
//! Represents constraints along execution paths for feasibility checking.

use serde::{Deserialize, Serialize};
use std::fmt;

/// Variable identifier in constraints
pub type VarId = String;

/// Constant value in constraints
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum ConstValue {
    Int(i64),
    Float(f64),
    Bool(bool),
    String(String),
    Null,
    /// Variable reference (for variable-variable constraints like x < y)
    Var(VarId),
}

impl fmt::Display for ConstValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Int(v) => write!(f, "{}", v),
            Self::Float(v) => write!(f, "{}", v),
            Self::Bool(v) => write!(f, "{}", v),
            Self::String(v) => write!(f, "\"{}\"", v),
            Self::Null => write!(f, "null"),
            Self::Var(v) => write!(f, "{}", v),
        }
    }
}

/// Comparison operators for path conditions
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
pub enum ComparisonOp {
    /// Equal (==)
    #[default]
    Eq,
    /// Not equal (!=)
    Neq,
    /// Less than (<)
    Lt,
    /// Greater than (>)
    Gt,
    /// Less than or equal (<=)
    Le,
    /// Greater than or equal (>=)
    Ge,
    /// Is null
    Null,
    /// Is not null
    NotNull,
}

impl fmt::Display for ComparisonOp {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Eq => write!(f, "=="),
            Self::Neq => write!(f, "!="),
            Self::Lt => write!(f, "<"),
            Self::Gt => write!(f, ">"),
            Self::Le => write!(f, "<="),
            Self::Ge => write!(f, ">="),
            Self::Null => write!(f, "is null"),
            Self::NotNull => write!(f, "is not null"),
        }
    }
}

/// Path condition representing a constraint along an execution path
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PathCondition {
    /// Variable being constrained
    pub var: VarId,

    /// Comparison operator
    pub op: ComparisonOp,

    /// Constant value (for comparison operators)
    pub value: Option<ConstValue>,

    /// Source location for debugging
    pub source_location: Option<String>,
}

impl PathCondition {
    /// Create new path condition
    pub fn new(var: VarId, op: ComparisonOp, value: Option<ConstValue>) -> Self {
        Self {
            var,
            op,
            value,
            source_location: None,
        }
    }

    /// Create equality condition: var == value
    pub fn eq(var: VarId, value: ConstValue) -> Self {
        Self::new(var, ComparisonOp::Eq, Some(value))
    }

    /// Create inequality condition: var != value
    pub fn neq(var: VarId, value: ConstValue) -> Self {
        Self::new(var, ComparisonOp::Neq, Some(value))
    }

    /// Create less than condition: var < value
    pub fn lt(var: VarId, value: ConstValue) -> Self {
        Self::new(var, ComparisonOp::Lt, Some(value))
    }

    /// Create greater than condition: var > value
    pub fn gt(var: VarId, value: ConstValue) -> Self {
        Self::new(var, ComparisonOp::Gt, Some(value))
    }

    /// Create null check: var is null
    pub fn null(var: VarId) -> Self {
        Self::new(var, ComparisonOp::Null, None)
    }

    /// Create not null check: var is not null
    pub fn not_null(var: VarId) -> Self {
        Self::new(var, ComparisonOp::NotNull, None)
    }

    /// Evaluate condition with a constant value
    pub fn evaluate(&self, value: &ConstValue) -> bool {
        if let Some(ref cond_value) = self.value {
            match self.op {
                ComparisonOp::Eq => value == cond_value,
                ComparisonOp::Neq => value != cond_value,
                ComparisonOp::Lt => self.compare_lt(value, cond_value),
                ComparisonOp::Gt => self.compare_gt(value, cond_value),
                ComparisonOp::Le => self.compare_le(value, cond_value),
                ComparisonOp::Ge => self.compare_ge(value, cond_value),
                ComparisonOp::Null => matches!(value, ConstValue::Null),
                ComparisonOp::NotNull => !matches!(value, ConstValue::Null),
            }
        } else {
            // Null checks
            match self.op {
                ComparisonOp::Null => matches!(value, ConstValue::Null),
                ComparisonOp::NotNull => !matches!(value, ConstValue::Null),
                _ => false,
            }
        }
    }

    fn compare_lt(&self, left: &ConstValue, right: &ConstValue) -> bool {
        match (left, right) {
            (ConstValue::Int(l), ConstValue::Int(r)) => l < r,
            (ConstValue::Float(l), ConstValue::Float(r)) => l < r,
            _ => false,
        }
    }

    fn compare_gt(&self, left: &ConstValue, right: &ConstValue) -> bool {
        match (left, right) {
            (ConstValue::Int(l), ConstValue::Int(r)) => l > r,
            (ConstValue::Float(l), ConstValue::Float(r)) => l > r,
            _ => false,
        }
    }

    fn compare_le(&self, left: &ConstValue, right: &ConstValue) -> bool {
        match (left, right) {
            (ConstValue::Int(l), ConstValue::Int(r)) => l <= r,
            (ConstValue::Float(l), ConstValue::Float(r)) => l <= r,
            _ => false,
        }
    }

    fn compare_ge(&self, left: &ConstValue, right: &ConstValue) -> bool {
        match (left, right) {
            (ConstValue::Int(l), ConstValue::Int(r)) => l >= r,
            (ConstValue::Float(l), ConstValue::Float(r)) => l >= r,
            _ => false,
        }
    }
}

impl fmt::Display for PathCondition {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if let Some(ref value) = self.value {
            write!(f, "{} {} {}", self.var, self.op, value)
        } else {
            write!(f, "{} {}", self.var, self.op)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_path_condition_creation() {
        let cond = PathCondition::eq("x".to_string(), ConstValue::Int(10));
        assert_eq!(cond.var, "x");
        assert_eq!(cond.op, ComparisonOp::Eq);
        assert_eq!(cond.value, Some(ConstValue::Int(10)));
    }

    #[test]
    fn test_path_condition_evaluation() {
        let cond = PathCondition::lt("x".to_string(), ConstValue::Int(10));
        assert!(cond.evaluate(&ConstValue::Int(5)));
        assert!(!cond.evaluate(&ConstValue::Int(15)));
    }

    #[test]
    fn test_null_check() {
        let cond = PathCondition::null("x".to_string());
        assert!(cond.evaluate(&ConstValue::Null));
        assert!(!cond.evaluate(&ConstValue::Int(0)));
    }

    #[test]
    fn test_not_null_check() {
        let cond = PathCondition::not_null("x".to_string());
        assert!(!cond.evaluate(&ConstValue::Null));
        assert!(cond.evaluate(&ConstValue::Int(0)));
    }
}
