//! Multi-Stage Solver Orchestrator
//!
//! Orchestrates multiple solvers with fallback strategy:
//!
//! ```text
//! Stage 1: Lightweight (0.1ms)  ← 90-95% cases
//!    ↓ Unknown
//! Stage 2: Theory Solvers (1-5ms)  ← 5-10% cases
//!    ├─ Simplex (LinearArithmetic)
//!    ├─ ArrayBounds (Array)
//!    └─ StringSolver (String)
//!    ↓ Unknown
//! Stage 3: Z3 Fallback (10-100ms)  ← <1% cases (optional)
//! ```

use super::lightweight_checker::LightweightConstraintChecker;
use super::solvers::{
    array_bounds::ArrayBoundsSolver, simplex::SimplexSolver, string_solver::StringSolver,
    ConstraintSolver, SolverResult,
};
use super::PathFeasibility;
use crate::features::smt::domain::constraint::{Constraint, Theory};
use crate::features::smt::domain::path_condition::PathCondition;

#[cfg(feature = "z3")]
use super::solvers::z3_backend::Z3Backend;

/// Multi-stage SMT solver orchestrator
pub struct SmtOrchestrator {
    /// Stage 1: Lightweight checker (always available)
    lightweight: LightweightConstraintChecker,

    /// Stage 2: Theory-specific solvers
    simplex: SimplexSolver,
    array_bounds: ArrayBoundsSolver,
    string_solver: StringSolver,

    /// Stage 3: Z3 backend (optional)
    #[cfg(feature = "z3")]
    z3: Option<Z3Backend>,

    /// Statistics
    stats: OrchestratorStats,
}

/// Performance statistics
#[derive(Debug, Default)]
pub struct OrchestratorStats {
    /// Total queries
    pub total_queries: usize,

    /// Queries resolved by each stage
    pub lightweight_hits: usize,
    pub theory_solver_hits: usize,
    pub z3_hits: usize,
    pub unknown_results: usize,
}

impl Default for SmtOrchestrator {
    fn default() -> Self {
        Self::new()
    }
}

impl SmtOrchestrator {
    /// Create new orchestrator
    pub fn new() -> Self {
        Self {
            lightweight: LightweightConstraintChecker::new(),
            simplex: SimplexSolver::new(),
            array_bounds: ArrayBoundsSolver::new(),
            string_solver: StringSolver::new(),
            #[cfg(feature = "z3")]
            z3: None,
            stats: OrchestratorStats::default(),
        }
    }

    /// Enable Z3 backend (if compiled with z3 feature)
    #[cfg(feature = "z3")]
    pub fn enable_z3(&mut self) {
        self.z3 = Some(Z3Backend::new());
    }

    /// Check path feasibility using multi-stage approach
    pub fn check_path_feasibility(&mut self, conditions: &[PathCondition]) -> PathFeasibility {
        self.stats.total_queries += 1;

        // Stage 1: Lightweight checker (fast path)
        let result = self.lightweight.is_path_feasible(conditions);
        if result != PathFeasibility::Unknown {
            self.stats.lightweight_hits += 1;
            return result;
        }

        // Stage 2: Theory-specific solvers
        // Convert PathConditions to Constraints for theory solvers
        let constraints: Vec<Constraint> = conditions
            .iter()
            .map(|pc| Constraint::simple(pc.var.clone(), pc.op, pc.value.clone()))
            .collect();

        let result = self.solve_with_theory_solvers(&constraints);
        if result != PathFeasibility::Unknown {
            self.stats.theory_solver_hits += 1;
            return result;
        }

        // Stage 3: Z3 fallback (if available)
        #[cfg(feature = "z3")]
        if let Some(ref mut z3) = self.z3 {
            let result = z3.solve_conjunction(&constraints);
            if result != SolverResult::Unknown {
                self.stats.z3_hits += 1;
                return result.to_path_feasibility();
            }
        }

        // All stages failed to determine
        self.stats.unknown_results += 1;
        PathFeasibility::Unknown
    }

    /// Solve using theory-specific solvers
    fn solve_with_theory_solvers(&mut self, constraints: &[Constraint]) -> PathFeasibility {
        // Group constraints by theory
        let mut linear_arithmetic = Vec::new();
        let mut array_bounds = Vec::new();
        let mut string_constraints = Vec::new();

        for constraint in constraints {
            match constraint.theory() {
                Theory::LinearArithmetic => linear_arithmetic.push(constraint),
                Theory::Array => array_bounds.push(constraint),
                Theory::String => string_constraints.push(constraint),
                Theory::Simple => {} // Already handled by lightweight
            }
        }

        // Solve each theory
        if !linear_arithmetic.is_empty() {
            let result = self.simplex.solve_conjunction(constraints);
            if result == SolverResult::Unsat {
                return PathFeasibility::Infeasible;
            }
        }

        if !array_bounds.is_empty() {
            for constraint in &array_bounds {
                let result = self.array_bounds.solve(constraint);
                if result == SolverResult::Unsat {
                    return PathFeasibility::Infeasible;
                }
            }
        }

        if !string_constraints.is_empty() {
            for constraint in &string_constraints {
                let result = self.string_solver.solve(constraint);
                if result == SolverResult::Unsat {
                    return PathFeasibility::Infeasible;
                }
            }
        }

        // No contradiction found, but cannot prove SAT
        PathFeasibility::Unknown
    }

    /// Get performance statistics
    pub fn stats(&self) -> &OrchestratorStats {
        &self.stats
    }

    /// Get lightweight checker (for SCCP integration)
    pub fn lightweight_mut(&mut self) -> &mut LightweightConstraintChecker {
        &mut self.lightweight
    }

    /// Get array bounds solver (for length information)
    pub fn array_bounds_mut(&mut self) -> &mut ArrayBoundsSolver {
        &mut self.array_bounds
    }

    /// Get string solver (for string length information)
    pub fn string_solver_mut(&mut self) -> &mut StringSolver {
        &mut self.string_solver
    }
}

impl OrchestratorStats {
    /// Calculate hit rate for each stage
    pub fn hit_rates(&self) -> HitRates {
        let total = self.total_queries as f64;
        HitRates {
            lightweight: (self.lightweight_hits as f64 / total) * 100.0,
            theory_solvers: (self.theory_solver_hits as f64 / total) * 100.0,
            z3: (self.z3_hits as f64 / total) * 100.0,
            unknown: (self.unknown_results as f64 / total) * 100.0,
        }
    }
}

/// Hit rate percentages
#[derive(Debug)]
pub struct HitRates {
    pub lightweight: f64,
    pub theory_solvers: f64,
    pub z3: f64,
    pub unknown: f64,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::smt::domain::path_condition::ConstValue;

    #[test]
    fn test_orchestrator_lightweight_path() {
        let mut orchestrator = SmtOrchestrator::new();

        // Simple contradiction that lightweight can detect
        let conditions = vec![
            PathCondition::lt("x".to_string(), ConstValue::Int(10)),
            PathCondition::gt("x".to_string(), ConstValue::Int(20)),
        ];

        let result = orchestrator.check_path_feasibility(&conditions);
        assert_eq!(result, PathFeasibility::Infeasible);
        assert_eq!(orchestrator.stats.lightweight_hits, 1);
        assert_eq!(orchestrator.stats.theory_solver_hits, 0);
    }

    #[test]
    fn test_orchestrator_stats() {
        let mut orchestrator = SmtOrchestrator::new();

        // Run some queries
        for _ in 0..10 {
            let conditions = vec![PathCondition::lt("x".to_string(), ConstValue::Int(10))];
            orchestrator.check_path_feasibility(&conditions);
        }

        assert_eq!(orchestrator.stats.total_queries, 10);

        let hit_rates = orchestrator.stats.hit_rates();
        assert!(hit_rates.lightweight > 0.0);
    }
}
