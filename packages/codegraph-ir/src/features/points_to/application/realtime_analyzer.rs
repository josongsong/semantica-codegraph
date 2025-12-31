//! Real-time Points-to Analyzer
//!
//! High-level wrapper for Demand-Driven PTA, optimized for IDE and real-time queries.

use crate::features::points_to::domain::{
    Constraint,
    constraint::VarId,
    abstract_location::LocationId,
};
use crate::features::points_to::infrastructure::demand_driven::DemandDrivenSolver;

/// Query result with timing
#[derive(Debug, Clone)]
pub struct RealtimeQueryResult {
    pub locations: Vec<LocationId>,
    pub query_time_us: u64,
}

/// High-level real-time analyzer
pub struct RealtimeAnalyzer {
    solver: DemandDrivenSolver,
}

impl RealtimeAnalyzer {
    pub fn new() -> Self {
        Self {
            solver: DemandDrivenSolver::new(),
        }
    }

    pub fn add_alloc(&mut self, var: VarId, location: LocationId) {
        self.solver.add_constraint(Constraint::alloc(var, location));
    }

    pub fn add_copy(&mut self, lhs: VarId, rhs: VarId) {
        self.solver.add_constraint(Constraint::copy(lhs, rhs));
    }

    pub fn add_load(&mut self, lhs: VarId, rhs: VarId) {
        self.solver.add_constraint(Constraint::load(lhs, rhs));
    }

    pub fn add_store(&mut self, lhs: VarId, rhs: VarId) {
        self.solver.add_constraint(Constraint::store(lhs, rhs));
    }

    pub fn add_constraint(&mut self, constraint: Constraint) {
        self.solver.add_constraint(constraint);
    }

    /// Query: What does this variable point to? (fast, on-demand)
    pub fn query_points_to(&mut self, var: VarId) -> RealtimeQueryResult {
        let start = std::time::Instant::now();
        let result = self.solver.query_points_to(var);
        let elapsed = start.elapsed();

        RealtimeQueryResult {
            locations: result.points_to.iter().collect(),
            query_time_us: elapsed.as_micros() as u64,
        }
    }

    /// Query: Do these two variables alias?
    pub fn query_may_alias(&mut self, v1: VarId, v2: VarId) -> bool {
        self.solver.query_may_alias(v1, v2)
    }

    /// Query: Can data flow from source to sink?
    pub fn query_may_flow(&mut self, source: VarId, sink: VarId) -> bool {
        self.solver.query_may_flow(source, sink)
    }
}

impl Default for RealtimeAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

// LSP: Implement demand-driven query trait
impl crate::features::points_to::ports::PTAQuery for RealtimeAnalyzer {
    fn query_points_to(&mut self, var: VarId) -> Vec<LocationId> {
        self.query_points_to(var).locations
    }

    fn query_may_alias(&mut self, v1: VarId, v2: VarId) -> bool {
        self.query_may_alias(v1, v2)
    }

    fn query_may_flow(&mut self, source: VarId, sink: VarId) -> bool {
        self.query_may_flow(source, sink)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_query() {
        let mut analyzer = RealtimeAnalyzer::new();
        analyzer.add_alloc(1, 100);
        analyzer.add_copy(2, 1);
        let result = analyzer.query_points_to(2);
        assert!(!result.locations.is_empty());
    }

    #[test]
    fn test_may_alias() {
        let mut analyzer = RealtimeAnalyzer::new();
        analyzer.add_alloc(1, 100);
        analyzer.add_copy(2, 1);
        assert!(analyzer.query_may_alias(1, 2));
    }
}
