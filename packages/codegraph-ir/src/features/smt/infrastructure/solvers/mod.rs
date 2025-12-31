//! SMT Solver Implementations
//!
//! Provides multiple solver backends with different capabilities:
//!
//! 1. **Simplex**: Linear arithmetic (2x + 3y <= 10)
//! 2. **ArrayBounds**: Array index bounds checking
//! 3. **StringSolver**: String constraint solving
//! 4. **Z3Backend**: Full SMT solver (optional, feature-gated)

use crate::features::smt::domain::constraint::{Constraint, Theory};
use crate::features::smt::infrastructure::PathFeasibility;

pub mod array_bounds;
pub mod simplex;
pub mod string_solver;

#[cfg(feature = "z3")]
pub mod z3_backend;

/// Solver capability trait
pub trait ConstraintSolver {
    /// Name of this solver
    fn name(&self) -> &'static str;

    /// Which theories does this solver support?
    fn supported_theories(&self) -> &[Theory];

    /// Can this solver handle the given constraint?
    fn can_solve(&self, constraint: &Constraint) -> bool {
        self.supported_theories().contains(&constraint.theory())
    }

    /// Solve a single constraint
    fn solve(&mut self, constraint: &Constraint) -> SolverResult;

    /// Solve multiple constraints (conjunction)
    fn solve_conjunction(&mut self, constraints: &[Constraint]) -> SolverResult {
        for constraint in constraints {
            match self.solve(constraint) {
                SolverResult::Unsat => return SolverResult::Unsat,
                SolverResult::Unknown => return SolverResult::Unknown,
                SolverResult::Sat(_) => continue,
            }
        }
        SolverResult::Sat(None) // All satisfied but no model
    }
}

/// Solver result
#[derive(Debug, Clone, PartialEq)]
pub enum SolverResult {
    /// Satisfiable (with optional model/assignment)
    Sat(Option<Model>),

    /// Unsatisfiable (contradiction)
    Unsat,

    /// Unknown (timeout, too complex, unsupported)
    Unknown,
}

impl SolverResult {
    /// Convert to PathFeasibility
    pub fn to_path_feasibility(&self) -> PathFeasibility {
        match self {
            SolverResult::Sat(_) => PathFeasibility::Feasible,
            SolverResult::Unsat => PathFeasibility::Infeasible,
            SolverResult::Unknown => PathFeasibility::Unknown,
        }
    }
}

/// Variable assignment model
pub type Model = std::collections::HashMap<String, ModelValue>;

/// Model value for different types
#[derive(Debug, Clone, PartialEq)]
pub enum ModelValue {
    Int(i64),
    Bool(bool),
    String(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_solver_result_conversion() {
        assert_eq!(
            SolverResult::Sat(None).to_path_feasibility(),
            PathFeasibility::Feasible
        );
        assert_eq!(
            SolverResult::Unsat.to_path_feasibility(),
            PathFeasibility::Infeasible
        );
        assert_eq!(
            SolverResult::Unknown.to_path_feasibility(),
            PathFeasibility::Unknown
        );
    }
}
