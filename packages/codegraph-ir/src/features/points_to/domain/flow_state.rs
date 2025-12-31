//! Flow-Sensitive Analysis State
//!
//! Domain model for flow-sensitive points-to analysis:
//! - ProgramPoint: Location in CFG
//! - FlowState: Points-to facts at a program point
//! - MustAliasSet: Must-alias pairs for strong update
//!
//! # References
//! - Choi et al. (1999): "Efficient and Precise Modeling of Exceptions"
//! - Hind (2001): "Pointer Analysis: Haven't We Solved This Problem Yet?"

use rustc_hash::{FxHashMap, FxHashSet};
use std::fmt;

use super::abstract_location::LocationId;
use super::constraint::VarId;

/// Program point in CFG
///
/// Represents a unique location in the control flow graph.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ProgramPoint {
    /// Basic block ID
    pub block_id: u32,

    /// Statement index within block (0-based)
    pub stmt_idx: u32,
}

impl ProgramPoint {
    pub fn new(block_id: u32, stmt_idx: u32) -> Self {
        Self { block_id, stmt_idx }
    }

    /// Entry point of function
    pub fn entry() -> Self {
        Self::new(0, 0)
    }

    /// Next statement in same block
    pub fn next_stmt(&self) -> Self {
        Self::new(self.block_id, self.stmt_idx + 1)
    }
}

impl fmt::Display for ProgramPoint {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "B{}:{}", self.block_id, self.stmt_idx)
    }
}

/// Set of abstract locations that a variable may point to
pub type LocationSet = FxHashSet<LocationId>;

/// Points-to state at a program point
///
/// Maps each variable to its possible points-to set.
/// Flow-sensitive: different program points have different states.
#[derive(Debug, Clone, Default)]
pub struct FlowState {
    /// Variable → LocationSet mapping
    pub points_to: FxHashMap<VarId, LocationSet>,

    /// Must-alias pairs at this point
    /// (var1, var2) means var1 and var2 MUST refer to same location
    pub must_alias: FxHashSet<(VarId, VarId)>,

    /// Null-checked variables (known to be non-null)
    pub non_null: FxHashSet<VarId>,
}

impl FlowState {
    pub fn new() -> Self {
        Self::default()
    }

    /// Get points-to set for a variable (empty if not present)
    pub fn get_points_to(&self, var: VarId) -> &LocationSet {
        static EMPTY: LocationSet = LocationSet::with_hasher(rustc_hash::FxBuildHasher);
        self.points_to.get(&var).unwrap_or(&EMPTY)
    }

    /// Set points-to for a variable (strong update for locals)
    pub fn set_points_to(&mut self, var: VarId, locs: LocationSet) {
        self.points_to.insert(var, locs);
    }

    /// Add location to variable's points-to set (weak update)
    pub fn add_points_to(&mut self, var: VarId, loc: LocationId) {
        self.points_to.entry(var).or_default().insert(loc);
    }

    /// Check if two variables may alias
    pub fn may_alias(&self, var1: VarId, var2: VarId) -> bool {
        let pts1 = self.get_points_to(var1);
        let pts2 = self.get_points_to(var2);
        !pts1.is_disjoint(pts2)
    }

    /// Check if two variables must alias
    pub fn must_alias(&self, var1: VarId, var2: VarId) -> bool {
        // Explicit must-alias tracking
        if self.must_alias.contains(&(var1, var2)) || self.must_alias.contains(&(var2, var1)) {
            return true;
        }

        // Single-target must-alias
        let pts1 = self.get_points_to(var1);
        let pts2 = self.get_points_to(var2);

        pts1.len() == 1 && pts2.len() == 1 && pts1 == pts2
    }

    /// Mark variables as must-alias
    pub fn add_must_alias(&mut self, var1: VarId, var2: VarId) {
        let (min_var, max_var) = if var1 < var2 {
            (var1, var2)
        } else {
            (var2, var1)
        };
        self.must_alias.insert((min_var, max_var));
    }

    /// Mark variable as non-null (after null check)
    pub fn mark_non_null(&mut self, var: VarId) {
        self.non_null.insert(var);
    }

    /// Check if variable is known to be non-null
    pub fn is_non_null(&self, var: VarId) -> bool {
        self.non_null.contains(&var)
    }

    /// Merge another state into this one (at join points)
    ///
    /// Uses:
    /// - Union for points-to sets (may-alias is conservative)
    /// - Intersection for must-alias (must hold on ALL paths)
    /// - Intersection for non-null (must hold on ALL paths)
    pub fn merge(&mut self, other: &FlowState) -> bool {
        let mut changed = false;

        // Merge points-to sets (union)
        for (var, other_locs) in &other.points_to {
            let entry = self.points_to.entry(*var).or_default();
            let old_len = entry.len();
            entry.extend(other_locs.iter().copied());
            if entry.len() > old_len {
                changed = true;
            }
        }

        // Merge must-alias (intersection)
        let old_must_alias_len = self.must_alias.len();
        self.must_alias
            .retain(|pair| other.must_alias.contains(pair));
        if self.must_alias.len() < old_must_alias_len {
            changed = true;
        }

        // Merge non-null (intersection)
        let old_non_null_len = self.non_null.len();
        self.non_null.retain(|var| other.non_null.contains(var));
        if self.non_null.len() < old_non_null_len {
            changed = true;
        }

        changed
    }

    /// Check if state equals another (for fixpoint detection)
    pub fn equals(&self, other: &FlowState) -> bool {
        self.points_to == other.points_to
            && self.must_alias == other.must_alias
            && self.non_null == other.non_null
    }

    /// Clone state for propagation
    pub fn clone_state(&self) -> FlowState {
        self.clone()
    }

    /// Number of variables tracked
    pub fn var_count(&self) -> usize {
        self.points_to.len()
    }

    /// Total number of points-to facts
    pub fn fact_count(&self) -> usize {
        self.points_to.values().map(|s| s.len()).sum()
    }
}

/// Strong update condition
///
/// Strong update (kill + gen) is sound when:
/// 1. Target is a local variable (not heap)
/// 2. Target is a must-alias singleton
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UpdateKind {
    /// Strong update: replaces previous value
    Strong,
    /// Weak update: adds to previous value
    Weak,
}

impl FlowState {
    /// Determine update kind for a variable assignment
    ///
    /// Strong update when:
    /// - Target is a local variable (VarId < HEAP_BASE)
    /// - Target has single points-to target
    pub fn update_kind(&self, var: VarId) -> UpdateKind {
        // Local variables always get strong update
        // (Heap locations would need special handling)
        if var < HEAP_VAR_BASE {
            UpdateKind::Strong
        } else {
            UpdateKind::Weak
        }
    }
}

/// Threshold for heap variable IDs
/// Variables with ID >= this are considered heap locations
pub const HEAP_VAR_BASE: VarId = 1_000_000;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_program_point() {
        let p1 = ProgramPoint::new(1, 0);
        let p2 = p1.next_stmt();

        assert_eq!(p1.block_id, 1);
        assert_eq!(p1.stmt_idx, 0);
        assert_eq!(p2.stmt_idx, 1);
        assert_eq!(format!("{}", p1), "B1:0");
    }

    #[test]
    fn test_flow_state_basic() {
        let mut state = FlowState::new();

        // x → {loc1}
        let mut locs = LocationSet::default();
        locs.insert(100);
        state.set_points_to(1, locs);

        assert_eq!(state.get_points_to(1).len(), 1);
        assert!(state.get_points_to(1).contains(&100));
        assert!(state.get_points_to(999).is_empty()); // Unknown var
    }

    #[test]
    fn test_may_alias() {
        let mut state = FlowState::new();

        // x → {loc1}, y → {loc1}
        let mut locs = LocationSet::default();
        locs.insert(100);
        state.set_points_to(1, locs.clone());
        state.set_points_to(2, locs);

        assert!(state.may_alias(1, 2));

        // z → {loc2}
        let mut locs2 = LocationSet::default();
        locs2.insert(200);
        state.set_points_to(3, locs2);

        assert!(!state.may_alias(1, 3));
    }

    #[test]
    fn test_must_alias() {
        let mut state = FlowState::new();

        // x → {loc1}, y → {loc1} (singleton = must alias)
        let mut locs = LocationSet::default();
        locs.insert(100);
        state.set_points_to(1, locs.clone());
        state.set_points_to(2, locs);

        assert!(state.must_alias(1, 2));

        // x → {loc1, loc2}, z → {loc1} (not must alias)
        state.add_points_to(1, 200);
        assert!(!state.must_alias(1, 2));
    }

    #[test]
    fn test_explicit_must_alias() {
        let mut state = FlowState::new();

        state.add_must_alias(1, 2);
        assert!(state.must_alias(1, 2));
        assert!(state.must_alias(2, 1)); // Symmetric
    }

    #[test]
    fn test_non_null() {
        let mut state = FlowState::new();

        assert!(!state.is_non_null(1));
        state.mark_non_null(1);
        assert!(state.is_non_null(1));
    }

    #[test]
    fn test_merge_points_to() {
        let mut state1 = FlowState::new();
        let mut state2 = FlowState::new();

        // state1: x → {loc1}
        let mut locs1 = LocationSet::default();
        locs1.insert(100);
        state1.set_points_to(1, locs1);

        // state2: x → {loc2}
        let mut locs2 = LocationSet::default();
        locs2.insert(200);
        state2.set_points_to(1, locs2);

        // Merge: x → {loc1, loc2}
        let changed = state1.merge(&state2);
        assert!(changed);
        assert_eq!(state1.get_points_to(1).len(), 2);
    }

    #[test]
    fn test_merge_must_alias() {
        let mut state1 = FlowState::new();
        let mut state2 = FlowState::new();

        // state1: must_alias(x, y), must_alias(a, b)
        state1.add_must_alias(1, 2);
        state1.add_must_alias(3, 4);

        // state2: must_alias(x, y) only
        state2.add_must_alias(1, 2);

        // Merge: only must_alias(x, y) survives
        state1.merge(&state2);
        assert!(state1.must_alias(1, 2));
        assert!(!state1.must_alias(3, 4)); // Lost at merge
    }

    #[test]
    fn test_merge_non_null() {
        let mut state1 = FlowState::new();
        let mut state2 = FlowState::new();

        // state1: x non-null, y non-null
        state1.mark_non_null(1);
        state1.mark_non_null(2);

        // state2: x non-null only
        state2.mark_non_null(1);

        // Merge: only x survives
        state1.merge(&state2);
        assert!(state1.is_non_null(1));
        assert!(!state1.is_non_null(2)); // Lost at merge
    }

    #[test]
    fn test_update_kind() {
        let state = FlowState::new();

        // Local variable: strong update
        assert_eq!(state.update_kind(1), UpdateKind::Strong);

        // Heap variable: weak update
        assert_eq!(state.update_kind(HEAP_VAR_BASE + 1), UpdateKind::Weak);
    }

    #[test]
    fn test_state_equality() {
        let mut state1 = FlowState::new();
        let mut state2 = FlowState::new();

        let mut locs = LocationSet::default();
        locs.insert(100);

        state1.set_points_to(1, locs.clone());
        state2.set_points_to(1, locs);

        assert!(state1.equals(&state2));

        state1.mark_non_null(1);
        assert!(!state1.equals(&state2));
    }
}
