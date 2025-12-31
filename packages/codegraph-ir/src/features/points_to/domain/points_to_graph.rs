//! Points-to Graph
//!
//! Core data structure representing the points-to relation:
//! Variable → Set[AbstractLocation]
//!
//! Optimized for:
//! - Fast set operations (union, intersection)
//! - Memory efficiency with sparse bitmaps
//! - SCC-aware queries (cycle optimization)

use super::abstract_location::{AbstractLocation, LocationId};
use super::constraint::VarId;
use crate::features::points_to::infrastructure::sparse_bitmap::SparseBitmap;
use rustc_hash::{FxHashMap, FxHashSet};
use serde::{Deserialize, Serialize};
use std::fmt;

/// Points-to graph representing var → {locations} mapping
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PointsToGraph {
    /// Points-to sets using sparse bitmaps for memory efficiency
    /// Key: Variable ID, Value: Set of location IDs
    points_to: FxHashMap<VarId, SparseBitmap>,

    /// Location registry: ID → AbstractLocation
    locations: FxHashMap<LocationId, AbstractLocation>,

    /// SCC mapping: variable → SCC representative
    /// Variables in the same SCC share the same points-to set
    scc_map: FxHashMap<VarId, VarId>,

    /// Precomputed alias groups for fast may_alias queries
    /// Only computed when requested (lazy evaluation)
    alias_cache: Option<FxHashMap<VarId, FxHashSet<VarId>>>,

    /// Statistics
    pub stats: GraphStats,
}

/// Statistics about the points-to graph
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct GraphStats {
    pub total_variables: usize,
    pub total_locations: usize,
    pub total_edges: usize,
    pub max_points_to_size: usize,
    pub avg_points_to_size: f64,
    pub scc_count: usize,
    pub scc_total_members: usize,
}

impl Default for PointsToGraph {
    fn default() -> Self {
        Self::new()
    }
}

impl PointsToGraph {
    /// Create a new empty points-to graph
    pub fn new() -> Self {
        Self {
            points_to: FxHashMap::default(),
            locations: FxHashMap::default(),
            scc_map: FxHashMap::default(),
            alias_cache: None,
            stats: GraphStats::default(),
        }
    }

    /// Create with pre-allocated capacity
    pub fn with_capacity(vars: usize, locations: usize) -> Self {
        Self {
            points_to: FxHashMap::with_capacity_and_hasher(vars, Default::default()),
            locations: FxHashMap::with_capacity_and_hasher(locations, Default::default()),
            scc_map: FxHashMap::default(),
            alias_cache: None,
            stats: GraphStats::default(),
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Location Management
    // ═══════════════════════════════════════════════════════════════════════

    /// Register an abstract location
    #[inline]
    pub fn add_location(&mut self, location: AbstractLocation) {
        self.locations.insert(location.id, location);
        self.stats.total_locations = self.locations.len();
    }

    /// Get a location by ID
    #[inline]
    pub fn get_location(&self, id: LocationId) -> Option<&AbstractLocation> {
        self.locations.get(&id)
    }

    // ═══════════════════════════════════════════════════════════════════════
    // SCC (Strongly Connected Components) Management
    // ═══════════════════════════════════════════════════════════════════════

    /// Set SCC representative for a variable
    #[inline]
    pub fn set_scc(&mut self, var: VarId, representative: VarId) {
        if var != representative {
            self.scc_map.insert(var, representative);
        }
    }

    /// Get SCC representative for a variable
    #[inline]
    pub fn get_representative(&self, var: VarId) -> VarId {
        self.scc_map.get(&var).copied().unwrap_or(var)
    }

    /// Set SCC mappings in bulk
    pub fn set_scc_bulk(&mut self, mappings: impl IntoIterator<Item = (VarId, VarId)>) {
        for (var, rep) in mappings {
            self.set_scc(var, rep);
        }
        self.stats.scc_count = self.scc_map.values().collect::<FxHashSet<_>>().len();
        self.stats.scc_total_members = self.scc_map.len();
    }

    /// Iterate over all SCC mappings (var → representative)
    ///
    /// Returns only variables that have a different representative (i.e., are in an SCC)
    pub fn iter_scc_mappings(&self) -> impl Iterator<Item = (VarId, VarId)> + '_ {
        self.scc_map.iter().map(|(&var, &rep)| (var, rep))
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Points-to Set Operations
    // ═══════════════════════════════════════════════════════════════════════

    /// Add a location to variable's points-to set
    ///
    /// Returns true if the set changed (for worklist propagation)
    ///
    /// SCC-aware: Uses representative for variables in cycles
    #[inline]
    pub fn add_points_to(&mut self, var: VarId, location: LocationId) -> bool {
        let rep = self.get_representative(var);
        let pts = self.points_to.entry(rep).or_insert_with(SparseBitmap::new);
        let changed = pts.insert(location);

        if changed {
            self.stats.total_edges += 1;
            self.alias_cache = None; // Invalidate cache
        }
        changed
    }

    /// Add multiple locations to variable's points-to set
    ///
    /// Returns true if any location was added
    #[inline]
    pub fn add_points_to_set(&mut self, var: VarId, locations: &SparseBitmap) -> bool {
        let rep = self.get_representative(var);
        let pts = self.points_to.entry(rep).or_insert_with(SparseBitmap::new);
        let old_len = pts.len();
        pts.union_with(locations);
        let changed = pts.len() > old_len;

        if changed {
            self.stats.total_edges = self.count_edges();
            self.alias_cache = None;
        }
        changed
    }

    /// Get points-to set for a variable (as SparseBitmap)
    #[inline]
    pub fn get_points_to_bitmap(&self, var: VarId) -> Option<&SparseBitmap> {
        let rep = self.get_representative(var);
        self.points_to.get(&rep)
    }

    /// Get points-to set for a variable (as location IDs)
    pub fn get_points_to(&self, var: VarId) -> Vec<LocationId> {
        let rep = self.get_representative(var);
        self.points_to
            .get(&rep)
            .map(|pts| pts.iter().collect())
            .unwrap_or_default()
    }

    /// Get points-to set as AbstractLocation objects
    pub fn get_points_to_locations(&self, var: VarId) -> Vec<&AbstractLocation> {
        self.get_points_to(var)
            .into_iter()
            .filter_map(|id| self.locations.get(&id))
            .collect()
    }

    /// Get size of points-to set
    #[inline]
    pub fn points_to_size(&self, var: VarId) -> usize {
        let rep = self.get_representative(var);
        self.points_to.get(&rep).map(|pts| pts.len()).unwrap_or(0)
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Alias Queries
    // ═══════════════════════════════════════════════════════════════════════

    /// Check if v1 and v2 MAY point to the same location (sound over-approximation)
    ///
    /// Complexity: O(min(|pts(v1)|, |pts(v2)|))
    #[inline]
    pub fn may_alias(&self, v1: VarId, v2: VarId) -> bool {
        let rep1 = self.get_representative(v1);
        let rep2 = self.get_representative(v2);

        // Same SCC = definitely may alias
        if rep1 == rep2 {
            return true;
        }

        // Check for intersection
        match (self.points_to.get(&rep1), self.points_to.get(&rep2)) {
            (Some(pts1), Some(pts2)) => pts1.intersects(pts2),
            _ => false,
        }
    }

    /// Check if v1 and v2 MUST point to the same location (precise analysis)
    ///
    /// Returns true only when we can prove 100% aliasing
    #[inline]
    pub fn must_alias(&self, v1: VarId, v2: VarId) -> bool {
        let rep1 = self.get_representative(v1);
        let rep2 = self.get_representative(v2);

        // Same SCC = must alias
        if rep1 == rep2 {
            return true;
        }

        // Both must be singletons pointing to the same location
        match (self.points_to.get(&rep1), self.points_to.get(&rep2)) {
            (Some(pts1), Some(pts2)) => {
                pts1.len() == 1 && pts2.len() == 1 && pts1.iter().next() == pts2.iter().next()
            }
            _ => false,
        }
    }

    /// Get all variables that may alias with the given variable
    pub fn get_may_alias_set(&mut self, var: VarId) -> FxHashSet<VarId> {
        // Compute alias cache if not available
        if self.alias_cache.is_none() {
            self.compute_alias_cache();
        }

        let rep = self.get_representative(var);
        self.alias_cache
            .as_ref()
            .and_then(|cache| cache.get(&rep))
            .cloned()
            .unwrap_or_else(|| {
                let mut set = FxHashSet::default();
                set.insert(var);
                set
            })
    }

    /// Compute alias cache for fast repeated queries
    fn compute_alias_cache(&mut self) {
        let mut cache: FxHashMap<VarId, FxHashSet<VarId>> = FxHashMap::default();

        // Build reverse index: location → {vars}
        let mut loc_to_vars: FxHashMap<LocationId, Vec<VarId>> = FxHashMap::default();

        for (&var, pts) in &self.points_to {
            for loc in pts.iter() {
                loc_to_vars.entry(loc).or_default().push(var);
            }
        }

        // Variables sharing a location are aliases
        for (_, vars) in loc_to_vars {
            if vars.len() > 1 {
                let var_set: FxHashSet<VarId> = vars.iter().copied().collect();
                for &var in &vars {
                    cache.entry(var).or_default().extend(&var_set);
                }
            }
        }

        // Add reflexive entries
        for &var in self.points_to.keys() {
            cache.entry(var).or_default().insert(var);
        }

        self.alias_cache = Some(cache);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Statistics and Utilities
    // ═══════════════════════════════════════════════════════════════════════

    /// Update statistics
    pub fn update_stats(&mut self) {
        self.stats.total_variables = self.points_to.len();
        self.stats.total_locations = self.locations.len();
        self.stats.total_edges = self.count_edges();

        if !self.points_to.is_empty() {
            let sizes: Vec<usize> = self.points_to.values().map(|pts| pts.len()).collect();
            self.stats.max_points_to_size = sizes.iter().copied().max().unwrap_or(0);
            self.stats.avg_points_to_size = sizes.iter().sum::<usize>() as f64 / sizes.len() as f64;
        }
    }

    /// Count total edges (sum of all points-to set sizes)
    fn count_edges(&self) -> usize {
        self.points_to.values().map(|pts| pts.len()).sum()
    }

    /// Get all variables in the graph
    pub fn variables(&self) -> impl Iterator<Item = VarId> + '_ {
        self.points_to.keys().copied()
    }

    /// Check if variable has any points-to information
    #[inline]
    pub fn contains_var(&self, var: VarId) -> bool {
        let rep = self.get_representative(var);
        self.points_to.contains_key(&rep)
    }

    /// Clear all data
    pub fn clear(&mut self) {
        self.points_to.clear();
        self.locations.clear();
        self.scc_map.clear();
        self.alias_cache = None;
        self.stats = GraphStats::default();
    }

    /// Merge another graph into this one
    pub fn merge(&mut self, other: &PointsToGraph) {
        // Merge locations
        for (id, loc) in &other.locations {
            self.locations.entry(*id).or_insert_with(|| loc.clone());
        }

        // Merge points-to sets
        for (&var, pts) in &other.points_to {
            self.add_points_to_set(var, pts);
        }

        // Merge SCC mappings
        for (&var, &rep) in &other.scc_map {
            self.scc_map.entry(var).or_insert(rep);
        }

        self.alias_cache = None;
        self.update_stats();
    }
}

impl fmt::Display for PointsToGraph {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        writeln!(f, "PointsToGraph {{")?;
        writeln!(f, "  variables: {}", self.stats.total_variables)?;
        writeln!(f, "  locations: {}", self.stats.total_locations)?;
        writeln!(f, "  edges: {}", self.stats.total_edges)?;
        writeln!(f, "  avg_pts_size: {:.2}", self.stats.avg_points_to_size)?;
        writeln!(f, "  scc_count: {}", self.stats.scc_count)?;
        writeln!(f, "}}")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::points_to::domain::abstract_location::LocationFactory;

    #[test]
    fn test_basic_points_to() {
        let mut graph = PointsToGraph::new();
        let mut factory = LocationFactory::new();

        let loc1 = factory.create("alloc:1");
        let loc2 = factory.create("alloc:2");

        graph.add_location(loc1.clone());
        graph.add_location(loc2.clone());

        // x → {loc1}
        assert!(graph.add_points_to(1, loc1.id));
        assert!(!graph.add_points_to(1, loc1.id)); // No change

        // y → {loc2}
        graph.add_points_to(2, loc2.id);

        assert_eq!(graph.points_to_size(1), 1);
        assert_eq!(graph.points_to_size(2), 1);
        assert!(!graph.may_alias(1, 2)); // Different locations
    }

    #[test]
    fn test_may_alias() {
        let mut graph = PointsToGraph::new();
        let mut factory = LocationFactory::new();

        let loc1 = factory.create("alloc:1");
        graph.add_location(loc1.clone());

        // Both x and y point to loc1
        graph.add_points_to(1, loc1.id);
        graph.add_points_to(2, loc1.id);

        assert!(graph.may_alias(1, 2));
    }

    #[test]
    fn test_must_alias() {
        let mut graph = PointsToGraph::new();
        let mut factory = LocationFactory::new();

        let loc1 = factory.create("alloc:1");
        let loc2 = factory.create("alloc:2");
        graph.add_location(loc1.clone());
        graph.add_location(loc2.clone());

        // x → {loc1}, y → {loc1} (singletons)
        graph.add_points_to(1, loc1.id);
        graph.add_points_to(2, loc1.id);
        assert!(graph.must_alias(1, 2));

        // z → {loc1, loc2} (not singleton)
        graph.add_points_to(3, loc1.id);
        graph.add_points_to(3, loc2.id);
        assert!(!graph.must_alias(1, 3)); // z is not singleton
    }

    #[test]
    fn test_scc_optimization() {
        let mut graph = PointsToGraph::new();
        let mut factory = LocationFactory::new();

        let loc1 = factory.create("alloc:1");
        graph.add_location(loc1.clone());

        // x and y are in the same SCC (representative = 1)
        graph.set_scc(2, 1);

        // Add to x
        graph.add_points_to(1, loc1.id);

        // y should also have the points-to set (same representative)
        assert_eq!(graph.points_to_size(2), 1);
        assert!(graph.may_alias(1, 2));
        assert!(graph.must_alias(1, 2)); // Same SCC
    }
}
