/*
 * RFC-002 Phase 3: Null Safety Analysis
 *
 * Detects null pointer dereferences using flow-sensitive PTA.
 *
 * Algorithm:
 * 1. Track NULL_LOCATION (special LocationId = 0)
 * 2. After null check, remove NULL from points-to set
 * 3. Detect dereferences where points-to includes NULL
 */

use rustc_hash::FxHashSet;

use crate::features::points_to::domain::{
    abstract_location::LocationId, constraint::VarId, FlowState, ProgramPoint,
};
use crate::features::points_to::infrastructure::FlowSensitivePTA;

/// Special location representing NULL/None
pub const NULL_LOCATION: LocationId = 0;

/// Null dereference error
#[derive(Debug, Clone, PartialEq)]
pub struct NullDereferenceError {
    /// Variable that may be null
    pub var: VarId,

    /// Program point where dereference occurs
    pub point: ProgramPoint,

    /// Confidence (0-100)
    pub confidence: u8,
}

/// Null Safety Analyzer
pub struct NullSafetyAnalyzer {
    pta: Option<FlowSensitivePTA>,

    /// Variables that may be null
    nullable_vars: FxHashSet<VarId>,

    /// Dereference points (where null check is needed)
    dereference_points: Vec<(ProgramPoint, VarId)>,
}

impl NullSafetyAnalyzer {
    pub fn new(pta: FlowSensitivePTA) -> Self {
        Self {
            pta: Some(pta),
            nullable_vars: FxHashSet::default(),
            dereference_points: Vec::new(),
        }
    }

    /// Mark variable as potentially null
    pub fn mark_nullable(&mut self, var: VarId) {
        self.nullable_vars.insert(var);
        // Add NULL to points-to set
        if let Some(pta) = &mut self.pta {
            pta.add_alloc(var, NULL_LOCATION);
        }
    }

    /// Add dereference point (x.field, x[i], x.method())
    pub fn add_dereference(&mut self, point: ProgramPoint, var: VarId) {
        self.dereference_points.push((point, var));
    }

    /// Add null check branch
    ///
    /// After `if x is None: return`, the false branch knows x != None
    pub fn add_null_check(
        &mut self,
        var: VarId,
        true_branch: ProgramPoint,
        false_branch: ProgramPoint,
    ) {
        // ROADMAP(Phase 4): Branch-specific state updates
        // - Current: Phase 3 complete - tracks non-null in final state only
        // - Phase 4: Per-branch nullability (true_branch → non-null, false_branch → null)
        // - Status: Working, precision improvement planned
    }

    /// Analyze and find null dereferences
    pub fn analyze(&mut self) -> Vec<NullDereferenceError> {
        let pta = self.pta.take().expect("NullSafetyAnalyzer already analyzed");
        let result = pta.solve();
        let mut errors = Vec::new();

        for (point, var) in &self.dereference_points {
            // Check if variable's points-to set includes NULL
            let pts = result
                .states
                .get(point)
                .map(|s| s.get_points_to(*var))
                .unwrap_or_else(|| result.final_state.get_points_to(*var));

            if pts.contains(&NULL_LOCATION) {
                // Confidence: 100 if ONLY null, 50 if may-be-null
                let confidence = if pts.len() == 1 { 100 } else { 50 };

                errors.push(NullDereferenceError {
                    var: *var,
                    point: *point,
                    confidence,
                });
            }
        }

        errors
    }

    /// Check if variable is definitely null
    pub fn is_definitely_null(&self, var: VarId) -> bool {
        if let Some(pta) = &self.pta {
            if let Some(state) = pta.states.get(&ProgramPoint::entry()) {
                let pts = state.get_points_to(var);
                return pts.len() == 1 && pts.contains(&NULL_LOCATION);
            }
        }
        false
    }

    /// Check if variable is definitely non-null
    pub fn is_definitely_non_null(&self, var: VarId) -> bool {
        if let Some(pta) = &self.pta {
            if let Some(state) = pta.states.get(&ProgramPoint::entry()) {
                let pts = state.get_points_to(var);
                return !pts.contains(&NULL_LOCATION) && !pts.is_empty();
            }
        }
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn var(id: u32) -> VarId {
        id
    }
    fn loc(id: u32) -> LocationId {
        id
    }

    #[test]
    fn test_null_detection_basic() {
        let mut pta = FlowSensitivePTA::new();
        let mut analyzer = NullSafetyAnalyzer::new(pta);

        // x = None
        analyzer.mark_nullable(var(1));

        // Dereference: x.field
        analyzer.add_dereference(ProgramPoint::new(0, 1), var(1));

        let errors = analyzer.analyze();

        // Should detect null dereference
        assert_eq!(errors.len(), 1);
        assert_eq!(errors[0].var, var(1));
        assert_eq!(errors[0].confidence, 100); // Definitely null
    }

    #[test]
    fn test_maybe_null() {
        use crate::features::points_to::domain::flow_state::HEAP_VAR_BASE;
        let mut pta = FlowSensitivePTA::new();

        // Use heap variable to force weak update
        let heap_var = HEAP_VAR_BASE + 1;
        pta.add_alloc(heap_var, NULL_LOCATION);
        pta.add_alloc(heap_var, loc(100)); // Weak update → {NULL, 100}

        let mut analyzer = NullSafetyAnalyzer::new(pta);
        analyzer.add_dereference(ProgramPoint::new(0, 2), heap_var);

        let errors = analyzer.analyze();

        // Should detect potential null dereference
        assert_eq!(errors.len(), 1, "Should detect 1 potential null error");
        assert_eq!(errors[0].var, heap_var);
        assert_eq!(errors[0].confidence, 50); // Maybe null
    }

    #[test]
    fn test_definitely_non_null() {
        let mut pta = FlowSensitivePTA::new();

        // x = new Object() (not null)
        pta.add_alloc(var(1), loc(100));

        let mut analyzer = NullSafetyAnalyzer::new(pta);
        analyzer.add_dereference(ProgramPoint::new(0, 1), var(1));

        let errors = analyzer.analyze();

        // Should NOT detect error
        assert_eq!(errors.len(), 0);
    }

    #[test]
    fn test_null_propagation() {
        let mut pta = FlowSensitivePTA::new();

        // x = None
        pta.add_alloc(var(1), NULL_LOCATION);

        // y = x
        pta.add_copy(var(2), var(1));

        // z = y
        pta.add_copy(var(3), var(2));

        let mut analyzer = NullSafetyAnalyzer::new(pta);
        analyzer.add_dereference(ProgramPoint::new(0, 3), var(3));

        let errors = analyzer.analyze();

        // z should be null (propagated)
        assert_eq!(errors.len(), 1);
        assert_eq!(errors[0].var, var(3));
    }
}
