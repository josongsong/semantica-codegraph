//! Unified Constraint Model
//!
//! Represents constraints across different theories:
//! - Arithmetic: x + y <= 10
//! - Array: a[i] where 0 <= i < len(a)
//! - String: len(s) > 5

use super::path_condition::{ComparisonOp, ConstValue, VarId};
use std::collections::HashMap;

/// Unified constraint type supporting multiple theories
#[derive(Debug, Clone, PartialEq)]
pub enum Constraint {
    /// Simple path condition (already supported by LightweightChecker)
    Simple {
        var: VarId,
        op: ComparisonOp,
        value: Option<ConstValue>,
    },

    /// Linear arithmetic: a1*x1 + a2*x2 + ... + c <op> 0
    /// Example: 2*x + 3*y - 10 <= 0 represents 2x + 3y <= 10
    LinearArithmetic {
        coefficients: HashMap<VarId, i64>,
        constant: i64,
        op: ComparisonOp,
    },

    /// Array bounds: array_var[index_var] where index_expr <op> bound
    /// Example: arr[i] requires 0 <= i < len(arr)
    ArrayBounds {
        array: VarId,
        index: VarId,
        lower_bound: Option<i64>,
        upper_bound: Option<VarId>, // Often len(array)
    },

    /// String constraint: len(string_var) <op> value
    StringLength {
        string: VarId,
        op: ComparisonOp,
        length: usize,
    },
}

impl Constraint {
    /// Create simple constraint from PathCondition
    pub fn simple(var: VarId, op: ComparisonOp, value: Option<ConstValue>) -> Self {
        Self::Simple { var, op, value }
    }

    /// Create linear arithmetic constraint: sum(coeffs * vars) + constant <op> 0
    ///
    /// # Example
    /// ```text
    /// // 2*x + 3*y <= 10
    /// // Normalized: 2*x + 3*y - 10 <= 0
    /// let coeffs = [("x", 2), ("y", 3)].into_iter()
    ///     .map(|(k, v)| (k.to_string(), v))
    ///     .collect();
    /// let constraint = Constraint::linear_arithmetic(coeffs, -10, ComparisonOp::Le);
    /// ```
    pub fn linear_arithmetic(
        coefficients: HashMap<VarId, i64>,
        constant: i64,
        op: ComparisonOp,
    ) -> Self {
        Self::LinearArithmetic {
            coefficients,
            constant,
            op,
        }
    }

    /// Create array bounds constraint: 0 <= index < upper_bound
    pub fn array_bounds(
        array: VarId,
        index: VarId,
        lower_bound: Option<i64>,
        upper_bound: Option<VarId>,
    ) -> Self {
        Self::ArrayBounds {
            array,
            index,
            lower_bound,
            upper_bound,
        }
    }

    /// Create string length constraint: len(string) <op> length
    pub fn string_length(string: VarId, op: ComparisonOp, length: usize) -> Self {
        Self::StringLength { string, op, length }
    }

    /// Get all variables referenced in this constraint
    pub fn variables(&self) -> Vec<&VarId> {
        match self {
            Self::Simple { var, .. } => vec![var],
            Self::LinearArithmetic { coefficients, .. } => coefficients.keys().collect(),
            Self::ArrayBounds {
                array,
                index,
                upper_bound,
                ..
            } => {
                let mut vars = vec![array, index];
                if let Some(ub) = upper_bound {
                    vars.push(ub);
                }
                vars
            }
            Self::StringLength { string, .. } => vec![string],
        }
    }

    /// Check which theory this constraint belongs to
    pub fn theory(&self) -> Theory {
        match self {
            Self::Simple { .. } => Theory::Simple,
            Self::LinearArithmetic { .. } => Theory::LinearArithmetic,
            Self::ArrayBounds { .. } => Theory::Array,
            Self::StringLength { .. } => Theory::String,
        }
    }
}

/// Constraint theory classification
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Theory {
    /// Simple comparisons (x < 10)
    Simple,

    /// Linear arithmetic (2x + 3y <= 10)
    LinearArithmetic,

    /// Array theory (a[i] bounds)
    Array,

    /// String theory (length, patterns)
    String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_constraint() {
        let c = Constraint::simple("x".to_string(), ComparisonOp::Lt, Some(ConstValue::Int(10)));

        assert_eq!(c.theory(), Theory::Simple);
        assert_eq!(c.variables(), vec!["x"]);
    }

    #[test]
    fn test_linear_arithmetic_constraint() {
        // 2*x + 3*y <= 10
        let mut coeffs = HashMap::new();
        coeffs.insert("x".to_string(), 2);
        coeffs.insert("y".to_string(), 3);

        let c = Constraint::linear_arithmetic(coeffs, -10, ComparisonOp::Le);

        assert_eq!(c.theory(), Theory::LinearArithmetic);
        assert_eq!(c.variables().len(), 2);
    }

    #[test]
    fn test_array_bounds_constraint() {
        let c = Constraint::array_bounds(
            "arr".to_string(),
            "i".to_string(),
            Some(0),
            Some("len_arr".to_string()),
        );

        assert_eq!(c.theory(), Theory::Array);
        assert_eq!(c.variables().len(), 3); // arr, i, len_arr
    }

    #[test]
    fn test_string_length_constraint() {
        let c = Constraint::string_length("s".to_string(), ComparisonOp::Gt, 5);

        assert_eq!(c.theory(), Theory::String);
        assert_eq!(c.variables(), vec!["s"]);
    }
}
