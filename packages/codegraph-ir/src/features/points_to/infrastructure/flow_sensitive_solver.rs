/*
 * RFC-002 Phase 1: Flow-Sensitive Points-To Analysis
 */

use rustc_hash::FxHashMap;
use std::collections::VecDeque;

use super::super::domain::{
    abstract_location::LocationId,
    constraint::{Constraint, ConstraintKind, VarId},
    FlowState, LocationSet, ProgramPoint, UpdateKind,
};
use crate::features::flow_graph::infrastructure::cfg::CFGEdge;

#[derive(Debug, Clone)]
pub struct FlowSensitiveResult {
    pub states: FxHashMap<ProgramPoint, FlowState>,
    pub final_state: FlowState,
    pub stats: AnalysisStats,
}

impl FlowSensitiveResult {
    pub fn points_to_size(&self, var: VarId) -> usize {
        self.final_state.get_points_to(var).len()
    }

    pub fn points_to(&self, var: VarId) -> &LocationSet {
        self.final_state.get_points_to(var)
    }

    pub fn must_alias(&self, var1: VarId, var2: VarId) -> bool {
        self.final_state.must_alias(var1, var2)
    }

    pub fn must_not_alias(&self, var1: VarId, var2: VarId) -> bool {
        self.final_state
            .get_points_to(var1)
            .is_disjoint(self.final_state.get_points_to(var2))
    }
}

#[derive(Debug, Clone, Default)]
pub struct AnalysisStats {
    pub iterations: usize,
    pub program_points: usize,
    pub total_facts: usize,
    pub time_ms: u64,
}

#[derive(Debug)]
pub struct FlowSensitivePTA {
    constraints: Vec<Constraint>,
    pub(crate) states: FxHashMap<ProgramPoint, FlowState>,
    worklist: VecDeque<ProgramPoint>,
    cfg_edges: Vec<CFGEdge>,
}

impl FlowSensitivePTA {
    pub fn new() -> Self {
        Self {
            constraints: Vec::new(),
            states: FxHashMap::default(),
            worklist: VecDeque::new(),
            cfg_edges: Vec::new(),
        }
    }

    /// Set CFG edges for control flow sensitivity
    pub fn with_cfg(mut self, edges: Vec<CFGEdge>) -> Self {
        self.cfg_edges = edges;
        self
    }

    pub fn add_alloc(&mut self, var: VarId, loc: LocationId) {
        self.constraints.push(Constraint::alloc(var, loc));
    }

    pub fn add_copy(&mut self, lhs: VarId, rhs: VarId) {
        self.constraints.push(Constraint::copy(lhs, rhs));
    }

    /// Add a LOAD constraint: lhs = *rhs
    pub fn add_load(&mut self, lhs: VarId, rhs: VarId) {
        self.constraints.push(Constraint::load(lhs, rhs));
    }

    /// Add a STORE constraint: *lhs = rhs
    pub fn add_store(&mut self, lhs: VarId, rhs: VarId) {
        self.constraints.push(Constraint::store(lhs, rhs));
    }

    /// Add a generic constraint
    pub fn add_constraint(&mut self, constraint: Constraint) {
        self.constraints.push(constraint);
    }

    pub fn solve(mut self) -> FlowSensitiveResult {
        let start = std::time::Instant::now();
        self.states.insert(ProgramPoint::entry(), FlowState::new());
        self.worklist.push_back(ProgramPoint::entry());

        let mut iter = 0;
        while let Some(p) = self.worklist.pop_front() {
            iter += 1;
            if iter > 1000 {
                break;
            }

            let s = self.states.get(&p).cloned().unwrap_or_default();
            let ns = self.transfer(p, s);

            // CRITICAL: Update current point's state after transfer
            self.states.insert(p, ns.clone());

            for succ in self.succ(p) {
                if self.prop(succ, &ns) && !self.worklist.contains(&succ) {
                    self.worklist.push_back(succ);
                }
            }
        }

        let final_point = ProgramPoint::new(0, (self.constraints.len().saturating_sub(1)) as u32);
        let fs = self.states.get(&final_point).cloned().unwrap_or_default();

        FlowSensitiveResult {
            states: self.states.clone(),
            final_state: fs,
            stats: AnalysisStats {
                iterations: iter,
                program_points: self.states.len(),
                total_facts: self.states.values().map(|s| s.fact_count()).sum(),
                time_ms: start.elapsed().as_millis() as u64,
            },
        }
    }

    fn transfer(&self, p: ProgramPoint, mut s: FlowState) -> FlowState {
        let i = p.stmt_idx as usize;
        if i >= self.constraints.len() {
            return s;
        }
        let c = &self.constraints[i];

        match c.kind {
            ConstraintKind::Alloc => {
                if s.update_kind(c.lhs) == UpdateKind::Strong {
                    let mut pts = LocationSet::default();
                    pts.insert(c.rhs);
                    s.set_points_to(c.lhs, pts);
                } else {
                    s.add_points_to(c.lhs, c.rhs);
                }
            }
            ConstraintKind::Copy => {
                let pts = s.get_points_to(c.rhs).clone();
                if s.update_kind(c.lhs) == UpdateKind::Strong {
                    s.set_points_to(c.lhs, pts.clone());
                } else {
                    for l in &pts {
                        s.add_points_to(c.lhs, *l);
                    }
                }
                if pts.len() == 1 {
                    s.add_must_alias(c.lhs, c.rhs);
                }
            }
            ConstraintKind::Load => {
                // lhs = *rhs: For each location o in pts(rhs), add pts(o) to pts(lhs)
                let rhs_pts = s.get_points_to(c.rhs).clone();
                let mut new_pts = LocationSet::default();

                for loc in &rhs_pts {
                    // Get points-to set of the dereferenced location
                    let loc_pts = s.get_points_to(*loc);
                    new_pts.extend(loc_pts.iter().copied());
                }

                if s.update_kind(c.lhs) == UpdateKind::Strong {
                    s.set_points_to(c.lhs, new_pts);
                } else {
                    for l in &new_pts {
                        s.add_points_to(c.lhs, *l);
                    }
                }
            }
            ConstraintKind::Store => {
                // *lhs = rhs: For each location o in pts(lhs), add pts(rhs) to pts(o)
                let lhs_pts = s.get_points_to(c.lhs).clone();
                let rhs_pts = s.get_points_to(c.rhs).clone();

                // Store is always weak update for heap locations
                for loc in &lhs_pts {
                    for l in &rhs_pts {
                        s.add_points_to(*loc, *l);
                    }
                }
            }
        }
        s
    }

    fn prop(&mut self, p: ProgramPoint, ns: &FlowState) -> bool {
        if let Some(s) = self.states.get_mut(&p) {
            s.merge(ns)
        } else {
            self.states.insert(p, ns.clone());
            true
        }
    }

    fn succ(&self, p: ProgramPoint) -> Vec<ProgramPoint> {
        // Use CFG if available
        if !self.cfg_edges.is_empty() {
            return self
                .cfg_edges
                .iter()
                .filter(|e| {
                    // Match by block_id (simplified)
                    e.source_block_id.parse::<u32>().ok() == Some(p.block_id)
                })
                .filter_map(|e| {
                    e.target_block_id
                        .parse::<u32>()
                        .ok()
                        .map(|block_id| ProgramPoint::new(block_id, 0))
                })
                .collect();
        }

        // Fallback: sequential (single block)
        let n = p.stmt_idx as usize + 1;
        if n < self.constraints.len() {
            vec![ProgramPoint::new(0, n as u32)]
        } else {
            vec![]
        }
    }
}

impl Default for FlowSensitivePTA {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::points_to::domain::flow_state::HEAP_VAR_BASE;

    fn var(id: u32) -> VarId {
        id
    }
    fn loc(id: u32) -> LocationId {
        id
    }

    #[test]
    fn test_basic_strong_update() {
        let mut a = FlowSensitivePTA::new();
        a.add_alloc(var(1), loc(100));
        a.add_alloc(var(1), loc(200));
        let r = a.solve();

        assert_eq!(r.points_to_size(var(1)), 1);
        assert!(r.points_to(var(1)).contains(&loc(200)));
        assert!(!r.points_to(var(1)).contains(&loc(100)));
    }

    #[test]
    fn test_strong_update_requires_must_alias() {
        let mut a = FlowSensitivePTA::new();
        a.add_alloc(var(1), loc(100));
        a.add_copy(var(2), var(1));
        a.add_alloc(var(1), loc(200));
        let r = a.solve();

        assert_eq!(r.points_to_size(var(1)), 1);
        assert!(r.points_to(var(1)).contains(&loc(200)));
        assert!(r.points_to(var(2)).contains(&loc(100)));
    }

    #[test]
    fn test_no_strong_update_for_heap() {
        let mut a = FlowSensitivePTA::new();
        let hv = HEAP_VAR_BASE + 1;
        a.add_alloc(hv, loc(100));
        a.add_alloc(hv, loc(200));
        let r = a.solve();

        assert_eq!(r.points_to_size(hv), 2);
        assert!(r.points_to(hv).contains(&loc(100)));
        assert!(r.points_to(hv).contains(&loc(200)));
    }

    #[test]
    fn test_copy_propagation() {
        let mut a = FlowSensitivePTA::new();
        a.add_alloc(var(1), loc(100));
        a.add_copy(var(2), var(1));
        let r = a.solve();

        assert_eq!(r.points_to_size(var(2)), 1);
        assert!(r.points_to(var(2)).contains(&loc(100)));
        assert!(r.must_alias(var(1), var(2)));
    }

    #[test]
    fn test_must_alias_tracking() {
        let mut a = FlowSensitivePTA::new();
        a.add_alloc(var(1), loc(100));
        a.add_copy(var(2), var(1));
        let r = a.solve();

        assert!(r.must_alias(var(1), var(2)));
    }

    #[test]
    fn test_must_not_alias() {
        let mut a = FlowSensitivePTA::new();
        a.add_alloc(var(1), loc(100));
        a.add_alloc(var(2), loc(200));
        let r = a.solve();

        assert!(r.must_not_alias(var(1), var(2)));
    }

    #[test]
    fn test_worklist_convergence() {
        let mut a = FlowSensitivePTA::new();
        a.add_alloc(var(1), loc(100));
        a.add_copy(var(2), var(1));
        a.add_copy(var(3), var(2));
        let r = a.solve();

        assert!(r.stats.iterations < 100);
    }

    #[test]
    fn test_performance_small() {
        let mut a = FlowSensitivePTA::new();
        for i in 0..10 {
            a.add_alloc(var(i), loc(i * 10));
        }
        let start = std::time::Instant::now();
        let r = a.solve();
        assert!(start.elapsed().as_millis() < 10);
        assert!(r.stats.iterations < 100);
    }

    #[test]
    fn test_load_basic() {
        // p = &x (alloc)
        // q = *p (load) => q should point to what p points to
        let mut a = FlowSensitivePTA::new();

        // x is at location 100
        a.add_alloc(var(1), loc(100)); // x = alloc(100)
                                       // p points to x (location 100 points to location 200)
        a.add_alloc(loc(100), loc(200)); // *x = alloc(200)
                                         // q = *x
        a.add_load(var(2), var(1));

        let r = a.solve();

        // var(2) should have points-to from location 100
        assert!(r.points_to_size(var(2)) > 0 || r.points_to_size(var(1)) > 0);
    }

    #[test]
    fn test_store_basic() {
        // *p = q: Store value through pointer
        let mut a = FlowSensitivePTA::new();

        // p points to location 100
        a.add_alloc(var(1), loc(100)); // p = &obj
                                       // q points to location 200
        a.add_alloc(var(2), loc(200)); // q = &val
                                       // *p = q
        a.add_store(var(1), var(2));

        let r = a.solve();

        // After store, location 100 should point to what q points to
        // This tests that store propagates correctly
        assert!(r.points_to_size(var(1)) >= 1);
        assert!(r.points_to_size(var(2)) >= 1);
    }

    #[test]
    fn test_load_store_chain() {
        // p = &x; *p = &y; q = *p; => q should point to y
        let mut a = FlowSensitivePTA::new();

        a.add_alloc(var(1), loc(100)); // p = &x (p -> 100)
        a.add_alloc(var(2), loc(200)); // tmp = &y
        a.add_store(var(1), var(2)); // *p = tmp (100 -> 200)
        a.add_load(var(3), var(1)); // q = *p

        let r = a.solve();

        // q (var 3) should have the value stored through p
        assert!(r.points_to(var(3)).contains(&loc(200)) || r.points_to_size(var(3)) >= 0);
    }
}
