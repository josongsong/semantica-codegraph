//! Incremental Points-to Analyzer
//!
//! High-level wrapper for Incremental PTA, optimized for CI/CD and watch mode.

use crate::features::points_to::domain::{
    Constraint,
    constraint::VarId,
    abstract_location::LocationId,
};
use crate::features::points_to::infrastructure::incremental_pta::{
    IncrementalPTASolver, Delta, UpdateKind,
};

/// Incremental analysis result
#[derive(Debug, Clone)]
pub struct IncrementalResult {
    pub affected_variables: Vec<VarId>,
    pub analysis_time_ms: u64,
    pub full_recompute: bool,
}

/// High-level incremental analyzer
pub struct IncrementalAnalyzer {
    solver: IncrementalPTASolver,
    pending: Vec<UpdateKind>,
}

impl IncrementalAnalyzer {
    pub fn new() -> Self {
        Self {
            solver: IncrementalPTASolver::new(),
            pending: Vec::new(),
        }
    }

    pub fn add_alloc(&mut self, var: VarId, location: LocationId) {
        self.pending.push(UpdateKind::AddConstraint(Constraint::alloc(var, location)));
    }

    pub fn add_copy(&mut self, lhs: VarId, rhs: VarId) {
        self.pending.push(UpdateKind::AddConstraint(Constraint::copy(lhs, rhs)));
    }

    pub fn add_load(&mut self, lhs: VarId, rhs: VarId) {
        self.pending.push(UpdateKind::AddConstraint(Constraint::load(lhs, rhs)));
    }

    pub fn add_store(&mut self, lhs: VarId, rhs: VarId) {
        self.pending.push(UpdateKind::AddConstraint(Constraint::store(lhs, rhs)));
    }

    pub fn add_constraint(&mut self, constraint: Constraint) {
        self.pending.push(UpdateKind::AddConstraint(constraint));
    }

    pub fn remove_constraint(&mut self, constraint: Constraint) {
        self.pending.push(UpdateKind::RemoveConstraint(constraint));
    }

    /// Commit pending changes and compute delta
    pub fn commit(&mut self) -> IncrementalResult {
        let start = std::time::Instant::now();

        let delta = self.solver.apply_updates(self.pending.drain(..));
        let elapsed = start.elapsed();
        let affected: Vec<_> = delta.affected.into_iter().collect();

        IncrementalResult {
            affected_variables: affected,
            analysis_time_ms: elapsed.as_millis() as u64,
            full_recompute: false,
        }
    }

    pub fn may_alias(&self, v1: VarId, v2: VarId) -> bool {
        self.solver.may_alias(v1, v2)
    }

    pub fn points_to(&self, var: VarId) -> Vec<LocationId> {
        self.solver.query(var)
            .map(|set| set.iter().collect())
            .unwrap_or_default()
    }

    pub fn has_pending_changes(&self) -> bool {
        !self.pending.is_empty()
    }
}

impl Default for IncrementalAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

// LSP: Implement incremental update trait
impl crate::features::points_to::ports::PTAIncremental for IncrementalAnalyzer {
    fn apply_updates(&mut self) -> Vec<VarId> {
        self.commit().affected_variables
    }

    fn has_pending(&self) -> bool {
        self.has_pending_changes()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_incremental() {
        let mut analyzer = IncrementalAnalyzer::new();
        analyzer.add_alloc(1, 100);
        analyzer.add_copy(2, 1);
        let result = analyzer.commit();
        assert!(!result.full_recompute);
    }

    #[test]
    fn test_pending_changes() {
        let mut analyzer = IncrementalAnalyzer::new();
        assert!(!analyzer.has_pending_changes());
        analyzer.add_alloc(1, 100);
        assert!(analyzer.has_pending_changes());
        analyzer.commit();
        assert!(!analyzer.has_pending_changes());
    }
}
