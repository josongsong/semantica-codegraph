//! Steensgaard's Points-to Analysis
//!
//! Fast unification-based pointer analysis with O(n·α(n)) complexity.
//!
//! # Algorithm Overview
//! Uses equality constraints instead of subset constraints:
//! - x = y means pts(x) = pts(y), not pts(x) ⊇ pts(y)
//! - This allows using Union-Find for O(α(n)) constraint solving
//!
//! # Precision vs Performance Trade-off
//! - Less precise than Andersen's (may report more aliases)
//! - Much faster: O(n·α(n)) vs O(n³)
//! - Good for initial approximation or large codebases
//!
//! # References
//! - Steensgaard, B. "Points-to Analysis in Almost Linear Time" (POPL 1996)
//! - Horwitz, S. "Precise Flow-Insensitive May-Alias Analysis is NP-Hard" (1997)

use super::union_find::UnionFind;
use crate::features::points_to::domain::{
    abstract_location::{AbstractLocation, LocationFactory, LocationId},
    constraint::{Constraint, ConstraintKind, ConstraintSet, VarId},
    points_to_graph::PointsToGraph,
};
use rustc_hash::{FxHashMap, FxHashSet};
use std::time::Instant;

/// Steensgaard's analysis result
#[derive(Debug)]
pub struct SteensgaardResult {
    /// The computed points-to graph
    pub graph: PointsToGraph,

    /// Analysis statistics
    pub stats: SteensgaardStats,
}

/// Statistics for Steensgaard's analysis
#[derive(Debug, Clone, Default)]
pub struct SteensgaardStats {
    pub constraints_processed: usize,
    pub union_operations: usize,
    pub find_operations: usize,
    pub equivalence_classes: usize,
    pub duration_ms: f64,
}

/// Steensgaard's points-to analysis solver
///
/// # Example
/// ```rust
/// use codegraph_ir::features::points_to::infrastructure::steensgaard_solver::SteensgaardSolver;
/// use codegraph_ir::features::points_to::domain::constraint::Constraint;
///
/// let mut solver = SteensgaardSolver::new();
///
/// // x = new A() → alloc constraint
/// solver.add_constraint(Constraint::alloc(1, 100));
///
/// // y = x → copy constraint (becomes y ≡ x in Steensgaard)
/// solver.add_constraint(Constraint::copy(2, 1));
///
/// let result = solver.solve();
/// assert!(result.graph.may_alias(1, 2));
/// ```
pub struct SteensgaardSolver {
    /// Union-Find for variable equivalence classes
    var_uf: UnionFind,

    /// Union-Find for location (type) equivalence classes
    loc_uf: UnionFind,

    /// Maps each equivalence class representative to its abstract location
    class_to_location: FxHashMap<VarId, LocationId>,

    /// Location factory for creating abstract locations
    location_factory: LocationFactory,

    /// All abstract locations
    locations: FxHashMap<LocationId, AbstractLocation>,

    /// Pending constraints
    constraints: ConstraintSet,

    /// Statistics
    stats: SteensgaardStats,

    /// ✅ FIX: Track active VarIds to avoid iterating sparse space
    active_vars: FxHashSet<VarId>,

    /// ✅ FIX 2: Map LocationId → synthetic deref VarId (avoid 0x8000_0000 | loc_id!)
    deref_var_map: FxHashMap<LocationId, VarId>,

    /// Next available VarId for deref vars
    next_deref_var_id: VarId,
}

impl Default for SteensgaardSolver {
    fn default() -> Self {
        Self::new()
    }
}

impl SteensgaardSolver {
    /// Create a new Steensgaard solver
    pub fn new() -> Self {
        Self {
            var_uf: UnionFind::empty(),
            loc_uf: UnionFind::empty(),
            class_to_location: FxHashMap::default(),
            location_factory: LocationFactory::new(),
            locations: FxHashMap::default(),
            constraints: ConstraintSet::new(),
            stats: SteensgaardStats::default(),
            active_vars: FxHashSet::default(), // ✅ Initialize active_vars
            deref_var_map: FxHashMap::default(), // ✅ FIX 2: Initialize deref_var_map
            next_deref_var_id: 0,              // ✅ Start deref VarIds from 0
        }
    }

    /// Create with pre-allocated capacity
    pub fn with_capacity(vars: usize, constraints: usize) -> Self {
        Self {
            var_uf: UnionFind::new(vars),
            loc_uf: UnionFind::new(vars),
            class_to_location: FxHashMap::with_capacity_and_hasher(vars, Default::default()),
            location_factory: LocationFactory::new(),
            locations: FxHashMap::with_capacity_and_hasher(vars, Default::default()),
            constraints: ConstraintSet::with_capacity(constraints),
            stats: SteensgaardStats::default(),
            active_vars: FxHashSet::default(), // ✅ Initialize active_vars
            deref_var_map: FxHashMap::default(), // ✅ Initialize deref_var_map
            next_deref_var_id: 0,              // ✅ Start from 0
        }
    }

    /// Add a constraint to the solver
    pub fn add_constraint(&mut self, constraint: Constraint) {
        // Ensure variables exist in Union-Find
        self.var_uf.make_set(constraint.lhs);
        self.var_uf.make_set(constraint.rhs);

        // ✅ FIX: Track active VarIds
        self.active_vars.insert(constraint.lhs);
        self.active_vars.insert(constraint.rhs);

        self.constraints.add(constraint);
    }

    /// Add multiple constraints
    pub fn add_constraints(&mut self, constraints: impl IntoIterator<Item = Constraint>) {
        for c in constraints {
            self.add_constraint(c);
        }
    }

    /// Solve all constraints and produce points-to graph
    ///
    /// # Algorithm
    /// 1. Process ALLOC constraints: Create location for each allocation
    /// 2. Process COPY constraints: Unify variable equivalence classes
    /// 3. Process LOAD/STORE: Handle dereferences
    /// 4. Build points-to graph from equivalence classes
    pub fn solve(&mut self) -> SteensgaardResult {
        let start = Instant::now();

        // Phase 1: Process ALLOC constraints
        self.process_allocs();

        // Phase 2: Process COPY constraints (unification)
        self.process_copies();

        // Phase 3: Process complex constraints (LOAD/STORE)
        self.process_complex();

        // Phase 4: Build points-to graph from equivalence classes
        let graph = self.build_graph();

        self.stats.duration_ms = start.elapsed().as_secs_f64() * 1000.0;
        self.stats.equivalence_classes = self.var_uf.count();

        SteensgaardResult {
            graph,
            stats: self.stats.clone(),
        }
    }

    /// Process allocation constraints
    fn process_allocs(&mut self) {
        // Collect constraints first to avoid borrow conflict
        let allocs: Vec<_> = self.constraints.allocs().cloned().collect();

        for constraint in allocs {
            let var = constraint.lhs;
            let loc_id = constraint.rhs; // In ALLOC, rhs is the location ID

            // Create abstract location if not exists
            if !self.locations.contains_key(&loc_id) {
                let loc = self.location_factory.create(format!("alloc:{}", loc_id));
                self.locations.insert(loc.id, loc);
            }

            // Map variable's equivalence class to location
            let var_rep = self.var_uf.find(var);
            self.class_to_location.insert(var_rep, loc_id);

            self.stats.constraints_processed += 1;
            self.stats.find_operations += 1;
        }
    }

    /// Process copy constraints using unification
    fn process_copies(&mut self) {
        // Collect constraints first to avoid borrow conflict
        let copies: Vec<_> = self.constraints.copies().cloned().collect();

        for constraint in copies {
            let lhs = constraint.lhs;
            let rhs = constraint.rhs;

            // In Steensgaard's, x = y means x ≡ y (same equivalence class)
            let lhs_rep = self.var_uf.find(lhs);
            let rhs_rep = self.var_uf.find(rhs);

            if lhs_rep != rhs_rep {
                // Unify the two equivalence classes
                let new_rep = self.var_uf.union(lhs, rhs);
                self.stats.union_operations += 1;

                // Merge their location mappings
                self.merge_locations(lhs_rep, rhs_rep, new_rep);
            }

            self.stats.constraints_processed += 1;
            self.stats.find_operations += 2;
        }
    }

    /// Process complex constraints (LOAD and STORE)
    fn process_complex(&mut self) {
        for constraint in self.constraints.complex().cloned().collect::<Vec<_>>() {
            match constraint.kind {
                ConstraintKind::Load => {
                    // x = *y: Unify x with the target of y
                    self.process_load(constraint.lhs, constraint.rhs);
                }
                ConstraintKind::Store => {
                    // *x = y: Unify the target of x with y
                    self.process_store(constraint.lhs, constraint.rhs);
                }
                _ => {}
            }
            self.stats.constraints_processed += 1;
        }
    }

    /// Process load: x = *y
    fn process_load(&mut self, lhs: VarId, rhs: VarId) {
        let rhs_rep = self.var_uf.find(rhs);
        self.stats.find_operations += 1;

        // Get the location that rhs points to
        if let Some(&loc_id) = self.class_to_location.get(&rhs_rep) {
            // Create a synthetic variable representing *rhs if needed
            let deref_var = self.get_or_create_deref_var(loc_id);

            // Unify lhs with *rhs
            let lhs_rep = self.var_uf.find(lhs);
            let deref_rep = self.var_uf.find(deref_var);
            self.stats.find_operations += 2;

            if lhs_rep != deref_rep {
                let new_rep = self.var_uf.union(lhs, deref_var);
                self.stats.union_operations += 1;
                self.merge_locations(lhs_rep, deref_rep, new_rep);
            }
        }
    }

    /// Process store: *x = y
    fn process_store(&mut self, lhs: VarId, rhs: VarId) {
        let lhs_rep = self.var_uf.find(lhs);
        self.stats.find_operations += 1;

        // Get the location that lhs points to
        if let Some(&loc_id) = self.class_to_location.get(&lhs_rep) {
            // Create a synthetic variable representing *lhs if needed
            let deref_var = self.get_or_create_deref_var(loc_id);

            // Unify *lhs with rhs
            let rhs_rep = self.var_uf.find(rhs);
            let deref_rep = self.var_uf.find(deref_var);
            self.stats.find_operations += 2;

            if rhs_rep != deref_rep {
                let new_rep = self.var_uf.union(rhs, deref_var);
                self.stats.union_operations += 1;
                self.merge_locations(rhs_rep, deref_rep, new_rep);
            }
        }
    }

    /// Get or create a synthetic variable for dereferencing a location
    fn get_or_create_deref_var(&mut self, loc_id: LocationId) -> VarId {
        // ✅ CRITICAL FIX: Use HashMap to map LocationId → sequential VarId
        // Before: 0x8000_0000 | loc_id → creates 2 billion VarIds!
        // After: Sequential allocation → only creates as many as needed

        if let Some(&existing) = self.deref_var_map.get(&loc_id) {
            return existing;
        }

        // Allocate new sequential VarId for this deref var
        let deref_var = self.next_deref_var_id;
        self.next_deref_var_id += 1;

        // Store mapping and add to active_vars
        self.deref_var_map.insert(loc_id, deref_var);
        self.active_vars.insert(deref_var); // ✅ Track as active
        self.var_uf.make_set(deref_var);

        deref_var
    }

    /// Merge location mappings when unifying equivalence classes
    fn merge_locations(&mut self, rep1: VarId, rep2: VarId, new_rep: VarId) {
        let loc1 = self.class_to_location.get(&rep1).copied();
        let loc2 = self.class_to_location.get(&rep2).copied();

        // Remove old mappings
        self.class_to_location.remove(&rep1);
        self.class_to_location.remove(&rep2);

        // Merge locations
        match (loc1, loc2) {
            (Some(l1), Some(l2)) if l1 != l2 => {
                // Both have locations - unify them in loc_uf
                let new_loc = self.loc_uf.union(l1, l2);
                self.class_to_location.insert(new_rep, new_loc);
            }
            (Some(l), None) | (None, Some(l)) => {
                self.class_to_location.insert(new_rep, l);
            }
            (Some(l), Some(_)) => {
                // Same location
                self.class_to_location.insert(new_rep, l);
            }
            (None, None) => {}
        }
    }

    /// Build the final points-to graph from equivalence classes
    fn build_graph(&mut self) -> PointsToGraph {
        let mut graph = PointsToGraph::with_capacity(self.var_uf.len(), self.locations.len());

        // Register all locations
        for (_, loc) in &self.locations {
            graph.add_location(loc.clone());
        }

        // Build SCC mappings and points-to sets
        let mut scc_mappings = Vec::new();

        // ✅ FIX: Use active_vars instead of 0..var_uf.len()!
        for &var in &self.active_vars {
            let rep = self.var_uf.find(var);

            if var != rep {
                scc_mappings.push((var, rep));
            }

            // Add points-to for the representative
            if let Some(&loc_id) = self.class_to_location.get(&rep) {
                // Find the actual location representative
                let loc_rep = self.loc_uf.find(loc_id);

                // Add all locations in the equivalence class
                graph.add_points_to(var, loc_rep);
            }
        }

        // Set SCC mappings (for efficient querying)
        graph.set_scc_bulk(scc_mappings);
        graph.update_stats();

        graph
    }

    /// Get current statistics
    pub fn stats(&self) -> &SteensgaardStats {
        &self.stats
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_alloc() {
        let mut solver = SteensgaardSolver::new();

        // x = new A()
        solver.add_constraint(Constraint::alloc(1, 100));

        let result = solver.solve();
        assert_eq!(result.graph.points_to_size(1), 1);
    }

    #[test]
    fn test_copy_unification() {
        let mut solver = SteensgaardSolver::new();

        // x = new A()
        solver.add_constraint(Constraint::alloc(1, 100));
        // y = x
        solver.add_constraint(Constraint::copy(2, 1));

        let result = solver.solve();

        // x and y should alias (same equivalence class)
        assert!(result.graph.may_alias(1, 2));
        assert_eq!(
            result.graph.points_to_size(1),
            result.graph.points_to_size(2)
        );
    }

    #[test]
    fn test_chain_copy() {
        let mut solver = SteensgaardSolver::new();

        // x = new A()
        solver.add_constraint(Constraint::alloc(1, 100));
        // y = x
        solver.add_constraint(Constraint::copy(2, 1));
        // z = y
        solver.add_constraint(Constraint::copy(3, 2));

        let result = solver.solve();

        // All should alias
        assert!(result.graph.may_alias(1, 2));
        assert!(result.graph.may_alias(2, 3));
        assert!(result.graph.may_alias(1, 3));
    }

    #[test]
    fn test_no_alias() {
        let mut solver = SteensgaardSolver::new();

        // x = new A()
        solver.add_constraint(Constraint::alloc(1, 100));
        // y = new B()
        solver.add_constraint(Constraint::alloc(2, 200));

        let result = solver.solve();

        // x and y should NOT alias
        assert!(!result.graph.may_alias(1, 2));
    }

    #[test]
    fn test_steensgaard_imprecision() {
        let mut solver = SteensgaardSolver::new();

        // Classic example of Steensgaard imprecision:
        // x = new A(); y = new B();
        // p = x; q = y;
        // if (cond) p = y;
        //
        // In Steensgaard: p ≡ x ≡ y ≡ q (all unified)
        // In Andersen: pts(p) = {A,B}, pts(q) = {B}, pts(x) = {A}, pts(y) = {B}

        solver.add_constraint(Constraint::alloc(1, 100)); // x = new A()
        solver.add_constraint(Constraint::alloc(2, 200)); // y = new B()
        solver.add_constraint(Constraint::copy(3, 1)); // p = x
        solver.add_constraint(Constraint::copy(4, 2)); // q = y
        solver.add_constraint(Constraint::copy(3, 2)); // p = y (conditional)

        let result = solver.solve();

        // In Steensgaard, p and q get unified through the chain
        // This is the trade-off for linear time
        assert!(result.graph.may_alias(3, 4));
    }

    #[test]
    fn test_statistics() {
        let mut solver = SteensgaardSolver::new();

        solver.add_constraint(Constraint::alloc(1, 100));
        solver.add_constraint(Constraint::copy(2, 1));
        solver.add_constraint(Constraint::copy(3, 2));

        let result = solver.solve();

        assert_eq!(result.stats.constraints_processed, 3);
        assert!(result.stats.union_operations >= 2); // At least 2 unions for the copies
    }
}
