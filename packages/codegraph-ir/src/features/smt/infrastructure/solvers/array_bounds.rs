//! Array Bounds Checker
//!
//! Checks array index bounds constraints:
//! - 0 <= index < len(array)
//! - index >= 0 && index < upper_bound
//!
//! ## Example
//!
//! ```text
//! arr[i] where:
//!   i = 5  (from SCCP)
//!   len(arr) = 10
//!
//! Constraint: 0 <= i < 10
//! Result: SAT (5 is in bounds)
//! ```

use super::{ConstraintSolver, Model, ModelValue, SolverResult};
use crate::features::smt::domain::constraint::{Constraint, Theory};
use std::collections::HashMap;

/// Array bounds constraint solver
pub struct ArrayBoundsSolver {
    /// Known array lengths (from SCCP or type inference)
    array_lengths: HashMap<String, usize>,

    /// Known index values (from SCCP)
    index_values: HashMap<String, i64>,
}

impl Default for ArrayBoundsSolver {
    fn default() -> Self {
        Self::new()
    }
}

impl ArrayBoundsSolver {
    /// Create new array bounds solver
    pub fn new() -> Self {
        Self {
            array_lengths: HashMap::new(),
            index_values: HashMap::new(),
        }
    }

    /// Set known array length
    pub fn set_array_length(&mut self, array: String, length: usize) {
        self.array_lengths.insert(array, length);
    }

    /// Set known index value (from SCCP)
    pub fn set_index_value(&mut self, index: String, value: i64) {
        self.index_values.insert(index, value);
    }

    /// Check if array access is in bounds
    fn check_bounds(
        &self,
        array: &str,
        index: &str,
        lower_bound: Option<i64>,
        upper_bound: Option<&str>,
    ) -> SolverResult {
        // Try to get concrete values
        let index_val = self.index_values.get(index);
        let array_len = self.array_lengths.get(array);

        // If we have concrete values, check directly
        if let Some(&idx) = index_val {
            // Check lower bound
            if let Some(lb) = lower_bound {
                if idx < lb {
                    return SolverResult::Unsat; // Index below lower bound
                }
            }

            // Check upper bound
            if let Some(ub_var) = upper_bound {
                if let Some(&ub) = self.index_values.get(ub_var) {
                    if idx >= ub {
                        return SolverResult::Unsat; // Index >= upper bound
                    }
                } else if let Some(&len) = array_len {
                    if idx >= len as i64 {
                        return SolverResult::Unsat; // Index >= length
                    }
                }
            }

            // All checks passed
            let mut model = HashMap::new();
            model.insert(index.to_string(), ModelValue::Int(idx));
            return SolverResult::Sat(Some(model));
        }

        // Cannot determine - need symbolic reasoning or more information
        SolverResult::Unknown
    }
}

impl ConstraintSolver for ArrayBoundsSolver {
    fn name(&self) -> &'static str {
        "ArrayBounds"
    }

    fn supported_theories(&self) -> &[Theory] {
        &[Theory::Array]
    }

    fn solve(&mut self, constraint: &Constraint) -> SolverResult {
        match constraint {
            Constraint::ArrayBounds {
                array,
                index,
                lower_bound,
                upper_bound,
            } => self.check_bounds(array, index, *lower_bound, upper_bound.as_deref()),
            _ => SolverResult::Unknown,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_array_bounds_in_bounds() {
        let mut solver = ArrayBoundsSolver::new();
        solver.set_array_length("arr".to_string(), 10);
        solver.set_index_value("i".to_string(), 5);

        let constraint = Constraint::array_bounds(
            "arr".to_string(),
            "i".to_string(),
            Some(0),
            Some("len_arr".to_string()),
        );

        // Should be SAT since 5 is in [0, 10)
        let result = solver.solve(&constraint);
        assert!(matches!(result, SolverResult::Sat(_)));
    }

    #[test]
    fn test_array_bounds_out_of_bounds() {
        let mut solver = ArrayBoundsSolver::new();
        solver.set_array_length("arr".to_string(), 10);
        solver.set_index_value("i".to_string(), 15);

        let constraint = Constraint::array_bounds(
            "arr".to_string(),
            "i".to_string(),
            Some(0),
            Some("len_arr".to_string()),
        );

        // Should be UNSAT since 15 >= 10
        assert_eq!(solver.solve(&constraint), SolverResult::Unsat);
    }

    #[test]
    fn test_array_bounds_negative_index() {
        let mut solver = ArrayBoundsSolver::new();
        solver.set_index_value("i".to_string(), -1);

        let constraint =
            Constraint::array_bounds("arr".to_string(), "i".to_string(), Some(0), None);

        // Should be UNSAT since -1 < 0
        assert_eq!(solver.solve(&constraint), SolverResult::Unsat);
    }

    #[test]
    fn test_array_bounds_unknown_values() {
        let mut solver = ArrayBoundsSolver::new();

        let constraint = Constraint::array_bounds(
            "arr".to_string(),
            "i".to_string(),
            Some(0),
            Some("len_arr".to_string()),
        );

        // Should be Unknown since we don't know index value
        assert_eq!(solver.solve(&constraint), SolverResult::Unknown);
    }
}
