//! String Constraint Solver
//!
//! Handles string constraints:
//! - len(s) <op> value
//! - s.contains(pattern)
//! - s.startswith(prefix)
//!
//! ## Example
//!
//! ```text
//! String: user_input
//! Constraint: len(user_input) > 100
//!
//! If SCCP knows len(user_input) = 50:
//! Result: UNSAT (50 <= 100)
//! ```

use super::{ConstraintSolver, Model, ModelValue, SolverResult};
use crate::features::smt::domain::constraint::{Constraint, Theory};
use crate::features::smt::domain::path_condition::ComparisonOp;
use std::collections::HashMap;

/// String constraint solver
pub struct StringSolver {
    /// Known string lengths (from SCCP or type inference)
    string_lengths: HashMap<String, usize>,
}

impl Default for StringSolver {
    fn default() -> Self {
        Self::new()
    }
}

impl StringSolver {
    /// Create new string solver
    pub fn new() -> Self {
        Self {
            string_lengths: HashMap::new(),
        }
    }

    /// Set known string length
    pub fn set_string_length(&mut self, string: String, length: usize) {
        self.string_lengths.insert(string, length);
    }

    /// Check string length constraint
    fn check_length(&self, string: &str, op: ComparisonOp, expected_length: usize) -> SolverResult {
        // Try to get concrete length
        if let Some(&actual_length) = self.string_lengths.get(string) {
            let satisfied = match op {
                ComparisonOp::Lt => actual_length < expected_length,
                ComparisonOp::Le => actual_length <= expected_length,
                ComparisonOp::Eq => actual_length == expected_length,
                ComparisonOp::Neq => actual_length != expected_length,
                ComparisonOp::Gt => actual_length > expected_length,
                ComparisonOp::Ge => actual_length >= expected_length,
                _ => return SolverResult::Unknown,
            };

            if satisfied {
                let mut model = HashMap::new();
                model.insert(
                    format!("len({})", string),
                    ModelValue::Int(actual_length as i64),
                );
                SolverResult::Sat(Some(model))
            } else {
                SolverResult::Unsat
            }
        } else {
            // Don't know string length - cannot determine
            SolverResult::Unknown
        }
    }
}

impl ConstraintSolver for StringSolver {
    fn name(&self) -> &'static str {
        "String"
    }

    fn supported_theories(&self) -> &[Theory] {
        &[Theory::String]
    }

    fn solve(&mut self, constraint: &Constraint) -> SolverResult {
        match constraint {
            Constraint::StringLength { string, op, length } => {
                self.check_length(string, *op, *length)
            }
            _ => SolverResult::Unknown,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_string_length_satisfied() {
        let mut solver = StringSolver::new();
        solver.set_string_length("s".to_string(), 10);

        let constraint = Constraint::string_length("s".to_string(), ComparisonOp::Gt, 5);

        // Should be SAT since 10 > 5
        let result = solver.solve(&constraint);
        assert!(matches!(result, SolverResult::Sat(_)));
    }

    #[test]
    fn test_string_length_unsatisfied() {
        let mut solver = StringSolver::new();
        solver.set_string_length("s".to_string(), 3);

        let constraint = Constraint::string_length("s".to_string(), ComparisonOp::Gt, 5);

        // Should be UNSAT since 3 <= 5
        assert_eq!(solver.solve(&constraint), SolverResult::Unsat);
    }

    #[test]
    fn test_string_length_equality() {
        let mut solver = StringSolver::new();
        solver.set_string_length("s".to_string(), 10);

        let constraint = Constraint::string_length("s".to_string(), ComparisonOp::Eq, 10);

        // Should be SAT since 10 == 10
        assert!(matches!(solver.solve(&constraint), SolverResult::Sat(_)));
    }

    #[test]
    fn test_string_length_unknown() {
        let mut solver = StringSolver::new();

        let constraint = Constraint::string_length("unknown".to_string(), ComparisonOp::Gt, 5);

        // Should be Unknown since we don't know the length
        assert_eq!(solver.solve(&constraint), SolverResult::Unknown);
    }
}
