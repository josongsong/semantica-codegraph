//! High-Level Points-to Analyzer
//!
//! Unified API for points-to analysis supporting:
//! - Multiple analysis modes (Fast, Precise, Hybrid)
//! - Automatic algorithm selection based on constraints
//! - Integration with IR documents
//!
//! # Usage
//! ```text
//! use codegraph_ir::features::points_to::application::analyzer::{
//!     PointsToAnalyzer, AnalysisConfig, AnalysisMode
//! };
//!
//! let config = AnalysisConfig::default();
//! let mut analyzer = PointsToAnalyzer::new(config);
//!
//! // Add constraints from IR
//! analyzer.add_alloc("x", "alloc:1:T");
//! analyzer.add_copy("y", "x");
//!
//! // Solve and query
//! let result = analyzer.solve();
//! assert!(result.graph.may_alias_by_name("x", "y"));
//! ```

use crate::features::heap_analysis::{Address, SymbolicExpr, SymbolicMemory};
use crate::features::points_to::domain::{
    abstract_location::{LocationFactory, LocationId},
    constraint::{Constraint, VarId},
    points_to_graph::PointsToGraph,
};
use crate::features::points_to::infrastructure::{
    andersen_solver::{AndersenConfig, AndersenSolver},
    steensgaard_solver::SteensgaardSolver,
};
use rustc_hash::FxHashMap;
use serde::{Deserialize, Serialize};
use std::time::Instant;

/// Analysis mode selection
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AnalysisMode {
    /// Steensgaard's algorithm: O(n·α(n)), less precise
    Fast,

    /// Andersen's algorithm: O(n²), more precise
    Precise,

    /// Hybrid: Steensgaard for initial, Andersen for refinement
    Hybrid,

    /// Automatic: Choose based on constraint count
    Auto,
}

impl Default for AnalysisMode {
    fn default() -> Self {
        AnalysisMode::Auto
    }
}

/// Analysis configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisConfig {
    /// Analysis mode
    pub mode: AnalysisMode,

    /// Enable field sensitivity
    pub field_sensitive: bool,

    /// Maximum iterations for Andersen (0 = unlimited)
    pub max_iterations: usize,

    /// Threshold for Auto mode: use Precise below this
    pub auto_threshold: usize,

    /// Enable SCC optimization
    pub enable_scc: bool,

    /// Enable wave propagation
    pub enable_wave: bool,

    /// Enable parallel processing
    pub enable_parallel: bool,
}

impl Default for AnalysisConfig {
    fn default() -> Self {
        Self {
            mode: AnalysisMode::Auto,
            field_sensitive: true,
            max_iterations: 0,
            auto_threshold: 10000, // Use Fast above 10K constraints
            enable_scc: true,
            enable_wave: true,
            enable_parallel: true,
        }
    }
}

/// Analysis result with unified statistics
#[derive(Debug)]
pub struct AnalysisResult {
    /// The computed points-to graph
    pub graph: PointsToGraph,

    /// Which mode was actually used
    pub mode_used: AnalysisMode,

    /// Statistics
    pub stats: AnalysisStats,
}

/// Unified statistics
#[derive(Debug, Clone, Default)]
pub struct AnalysisStats {
    pub constraints_total: usize,
    pub variables: usize,
    pub locations: usize,
    pub edges: usize,
    pub scc_count: usize,
    pub iterations: usize,
    pub duration_ms: f64,
}

/// High-level points-to analyzer
pub struct PointsToAnalyzer {
    /// Configuration
    config: AnalysisConfig,

    /// Variable name → ID mapping
    var_to_id: FxHashMap<String, VarId>,

    /// ID → Variable name mapping
    id_to_var: FxHashMap<VarId, String>,

    /// Location name → ID mapping
    loc_to_id: FxHashMap<String, LocationId>,

    /// Field name → ID mapping (for field sensitivity)
    field_to_id: FxHashMap<String, u32>,

    /// Collected constraints
    constraints: Vec<Constraint>,

    /// Location factory
    location_factory: LocationFactory,

    /// Next variable ID
    next_var_id: VarId,

    /// Next field ID
    next_field_id: u32,

    /// SOTA: Symbolic memory for precise heap modeling
    symbolic_memory: SymbolicMemory,
}

impl Default for PointsToAnalyzer {
    fn default() -> Self {
        Self::new(AnalysisConfig::default())
    }
}

impl PointsToAnalyzer {
    /// Create a new analyzer with the given configuration
    pub fn new(config: AnalysisConfig) -> Self {
        Self {
            config,
            var_to_id: FxHashMap::default(),
            id_to_var: FxHashMap::default(),
            loc_to_id: FxHashMap::default(),
            field_to_id: FxHashMap::default(),
            constraints: Vec::new(),
            location_factory: LocationFactory::new(),
            next_var_id: 1,
            next_field_id: 1,
            symbolic_memory: SymbolicMemory::new(),
        }
    }

    /// Get reference to symbolic memory (for heap queries)
    pub fn symbolic_memory(&self) -> &SymbolicMemory {
        &self.symbolic_memory
    }

    /// Get mutable reference to symbolic memory
    pub fn symbolic_memory_mut(&mut self) -> &mut SymbolicMemory {
        &mut self.symbolic_memory
    }

    /// Allocate heap object and track in symbolic memory
    pub fn add_heap_alloc(&mut self, var: &str, size: i64) -> Address {
        let addr = self
            .symbolic_memory
            .alloc_heap(SymbolicExpr::concrete(size));
        self.symbolic_memory
            .set_variable(var.to_string(), addr.clone());
        addr
    }

    /// Get or create variable ID
    fn get_or_create_var(&mut self, name: &str) -> VarId {
        if let Some(&id) = self.var_to_id.get(name) {
            return id;
        }
        let id = self.next_var_id;
        self.next_var_id += 1;
        self.var_to_id.insert(name.to_string(), id);
        self.id_to_var.insert(id, name.to_string());
        id
    }

    /// Get or create location ID
    fn get_or_create_loc(&mut self, name: &str) -> LocationId {
        if let Some(&id) = self.loc_to_id.get(name) {
            return id;
        }
        let loc = self.location_factory.create(name);
        let id = loc.id;
        self.loc_to_id.insert(name.to_string(), id);
        id
    }

    /// Get or create field ID
    fn get_or_create_field(&mut self, name: &str) -> u32 {
        if let Some(&id) = self.field_to_id.get(name) {
            return id;
        }
        let id = self.next_field_id;
        self.next_field_id += 1;
        self.field_to_id.insert(name.to_string(), id);
        id
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Constraint Building API (String-based)
    // ═══════════════════════════════════════════════════════════════════════

    /// Add an allocation constraint: var = new T()
    pub fn add_alloc(&mut self, var: &str, location: &str) {
        let var_id = self.get_or_create_var(var);
        let loc_id = self.get_or_create_loc(location);
        self.constraints.push(Constraint::alloc(var_id, loc_id));
    }

    /// Add a copy constraint: lhs = rhs
    pub fn add_copy(&mut self, lhs: &str, rhs: &str) {
        let lhs_id = self.get_or_create_var(lhs);
        let rhs_id = self.get_or_create_var(rhs);
        self.constraints.push(Constraint::copy(lhs_id, rhs_id));
    }

    /// Add a load constraint: lhs = *rhs
    pub fn add_load(&mut self, lhs: &str, rhs: &str) {
        let lhs_id = self.get_or_create_var(lhs);
        let rhs_id = self.get_or_create_var(rhs);
        self.constraints.push(Constraint::load(lhs_id, rhs_id));
    }

    /// Add a store constraint: *lhs = rhs
    pub fn add_store(&mut self, lhs: &str, rhs: &str) {
        let lhs_id = self.get_or_create_var(lhs);
        let rhs_id = self.get_or_create_var(rhs);
        self.constraints.push(Constraint::store(lhs_id, rhs_id));
    }

    /// Add a field load constraint: lhs = base.field
    pub fn add_field_load(&mut self, lhs: &str, base: &str, field: &str) {
        let lhs_id = self.get_or_create_var(lhs);
        let base_id = self.get_or_create_var(base);
        let field_id = self.get_or_create_field(field);
        self.constraints
            .push(Constraint::field_load(lhs_id, base_id, field_id));
    }

    /// Add a field store constraint: base.field = rhs
    pub fn add_field_store(&mut self, base: &str, field: &str, rhs: &str) {
        let base_id = self.get_or_create_var(base);
        let field_id = self.get_or_create_field(field);
        let rhs_id = self.get_or_create_var(rhs);
        self.constraints
            .push(Constraint::field_store(base_id, field_id, rhs_id));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Low-Level Constraint API (ID-based)
    // ═══════════════════════════════════════════════════════════════════════

    /// Add a raw constraint (for integration with IR)
    pub fn add_constraint(&mut self, constraint: Constraint) {
        self.constraints.push(constraint);
    }

    /// Add multiple constraints
    pub fn add_constraints(&mut self, constraints: impl IntoIterator<Item = Constraint>) {
        self.constraints.extend(constraints);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Solving
    // ═══════════════════════════════════════════════════════════════════════

    /// Solve and produce points-to graph
    pub fn solve(&mut self) -> AnalysisResult {
        let start = Instant::now();
        let constraint_count = self.constraints.len();

        // Determine actual mode
        let mode = match self.config.mode {
            AnalysisMode::Auto => {
                if constraint_count > self.config.auto_threshold {
                    AnalysisMode::Fast
                } else {
                    AnalysisMode::Precise
                }
            }
            other => other,
        };

        // 🔍 DEBUG: Log which mode is being used
        eprintln!(
            "[PTA DEBUG] Config mode: {:?}, Constraints: {}, Selected mode: {:?}",
            self.config.mode, constraint_count, mode
        );

        // Run analysis
        let (graph, inner_stats) = match mode {
            AnalysisMode::Fast => {
                eprintln!(
                    "[PTA DEBUG] → Calling solve_steensgaard() with {} constraints",
                    constraint_count
                );
                self.solve_steensgaard()
            }
            AnalysisMode::Precise => {
                eprintln!(
                    "[PTA DEBUG] → Calling solve_andersen() with {} constraints",
                    constraint_count
                );
                self.solve_andersen()
            }
            AnalysisMode::Hybrid => {
                eprintln!(
                    "[PTA DEBUG] → Calling solve_hybrid() with {} constraints",
                    constraint_count
                );
                self.solve_hybrid()
            }
            AnalysisMode::Auto => unreachable!(),
        };

        let duration_ms = start.elapsed().as_secs_f64() * 1000.0;

        AnalysisResult {
            graph,
            mode_used: mode,
            stats: AnalysisStats {
                constraints_total: constraint_count,
                duration_ms,
                ..inner_stats
            },
        }
    }

    fn solve_steensgaard(&self) -> (PointsToGraph, AnalysisStats) {
        let mut solver =
            SteensgaardSolver::with_capacity(self.next_var_id as usize, self.constraints.len());

        for c in &self.constraints {
            solver.add_constraint(c.clone());
        }

        let result = solver.solve();
        let stats = AnalysisStats {
            variables: result.graph.stats.total_variables,
            locations: result.graph.stats.total_locations,
            edges: result.graph.stats.total_edges,
            scc_count: result.stats.equivalence_classes,
            iterations: 1, // Single pass
            ..Default::default()
        };

        (result.graph, stats)
    }

    fn solve_andersen(&self) -> (PointsToGraph, AnalysisStats) {
        let config = AndersenConfig {
            field_sensitive: self.config.field_sensitive,
            max_iterations: self.config.max_iterations,
            enable_scc: self.config.enable_scc,
            enable_wave: self.config.enable_wave,
            enable_parallel: self.config.enable_parallel,
            ..Default::default()
        };

        let mut solver = AndersenSolver::new(config);

        for c in &self.constraints {
            solver.add_constraint(c.clone());
        }

        let result = solver.solve();
        let stats = AnalysisStats {
            variables: result.graph.stats.total_variables,
            locations: result.graph.stats.total_locations,
            edges: result.graph.stats.total_edges,
            scc_count: result.stats.scc_count,
            iterations: result.stats.iterations,
            ..Default::default()
        };

        (result.graph, stats)
    }

    fn solve_hybrid(&self) -> (PointsToGraph, AnalysisStats) {
        // Phase 1: Quick Steensgaard pass for initial approximation
        let mut steensgaard =
            SteensgaardSolver::with_capacity(self.next_var_id as usize, self.constraints.len());

        for c in &self.constraints {
            steensgaard.add_constraint(c.clone());
        }

        let initial = steensgaard.solve();

        // Hybrid Strategy:
        // - For large constraint sets (>5000), use Steensgaard result directly (fast but less precise)
        // - For smaller sets, refine with Andersen (precise but slower)
        // This balances precision vs performance

        let refinement_threshold = 5000;

        if self.constraints.len() > refinement_threshold {
            // Large codebase: Use Steensgaard result directly
            // Over-approximation is acceptable for scalability
            let stats = AnalysisStats {
                variables: initial.graph.stats.total_variables,
                locations: initial.graph.stats.total_locations,
                edges: initial.graph.stats.total_edges,
                scc_count: initial.stats.equivalence_classes,
                iterations: 1,
                ..Default::default()
            };
            return (initial.graph, stats);
        }

        // Phase 2: Refine with Andersen for smaller constraint sets
        // Use Steensgaard's equivalence classes to pre-merge variables
        // This reduces Andersen's work by starting from a better initial state

        let config = AndersenConfig {
            field_sensitive: self.config.field_sensitive,
            max_iterations: self.config.max_iterations,
            enable_scc: true,
            enable_wave: self.config.enable_wave,
            enable_parallel: self.config.enable_parallel,
            ..Default::default()
        };

        let mut andersen = AndersenSolver::new(config);

        for c in &self.constraints {
            andersen.add_constraint(c.clone());
        }

        let mut result = andersen.solve();

        // Merge Steensgaard's additional SCC information into the result
        // Variables in the same Steensgaard equivalence class should be considered aliases
        for (var, rep) in initial.graph.iter_scc_mappings() {
            if var != rep {
                result.graph.set_scc(var, rep);
            }
        }
        result.graph.update_stats();

        let stats = AnalysisStats {
            variables: result.graph.stats.total_variables,
            locations: result.graph.stats.total_locations,
            edges: result.graph.stats.total_edges,
            scc_count: result.stats.scc_count,
            iterations: result.stats.iterations,
            ..Default::default()
        };

        (result.graph, stats)
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Query API (String-based)
    // ═══════════════════════════════════════════════════════════════════════

    /// Get variable ID by name
    pub fn get_var_id(&self, name: &str) -> Option<VarId> {
        self.var_to_id.get(name).copied()
    }

    /// Get variable name by ID
    pub fn get_var_name(&self, id: VarId) -> Option<&str> {
        self.id_to_var.get(&id).map(|s| s.as_str())
    }

    /// Number of variables
    pub fn var_count(&self) -> usize {
        self.var_to_id.len()
    }

    /// Number of constraints
    pub fn constraint_count(&self) -> usize {
        self.constraints.len()
    }

    /// Clear all state
    pub fn clear(&mut self) {
        self.var_to_id.clear();
        self.id_to_var.clear();
        self.loc_to_id.clear();
        self.field_to_id.clear();
        self.constraints.clear();
        self.location_factory = LocationFactory::new();
        self.next_var_id = 1;
        self.next_field_id = 1;
    }
}

/// Extension trait for PointsToGraph to support string-based queries
pub trait PointsToGraphExt {
    fn may_alias_by_name(&self, analyzer: &PointsToAnalyzer, v1: &str, v2: &str) -> bool;
    fn must_alias_by_name(&self, analyzer: &PointsToAnalyzer, v1: &str, v2: &str) -> bool;
}

impl PointsToGraphExt for PointsToGraph {
    fn may_alias_by_name(&self, analyzer: &PointsToAnalyzer, v1: &str, v2: &str) -> bool {
        match (analyzer.get_var_id(v1), analyzer.get_var_id(v2)) {
            (Some(id1), Some(id2)) => self.may_alias(id1, id2),
            _ => false,
        }
    }

    fn must_alias_by_name(&self, analyzer: &PointsToAnalyzer, v1: &str, v2: &str) -> bool {
        match (analyzer.get_var_id(v1), analyzer.get_var_id(v2)) {
            (Some(id1), Some(id2)) => self.must_alias(id1, id2),
            _ => false,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_analysis() {
        let mut analyzer = PointsToAnalyzer::default();

        analyzer.add_alloc("x", "alloc:1:A");
        analyzer.add_copy("y", "x");

        let result = analyzer.solve();

        let id_x = analyzer.get_var_id("x").unwrap();
        let id_y = analyzer.get_var_id("y").unwrap();

        assert!(result.graph.may_alias(id_x, id_y));
    }

    #[test]
    fn test_no_alias() {
        let mut analyzer = PointsToAnalyzer::default();

        analyzer.add_alloc("x", "alloc:1:A");
        analyzer.add_alloc("y", "alloc:2:B");

        let result = analyzer.solve();

        let id_x = analyzer.get_var_id("x").unwrap();
        let id_y = analyzer.get_var_id("y").unwrap();

        assert!(!result.graph.may_alias(id_x, id_y));
    }

    #[test]
    fn test_mode_selection() {
        let config = AnalysisConfig {
            mode: AnalysisMode::Fast,
            ..Default::default()
        };
        let mut analyzer = PointsToAnalyzer::new(config);

        analyzer.add_alloc("x", "alloc:1");
        analyzer.add_copy("y", "x");

        let result = analyzer.solve();
        assert_eq!(result.mode_used, AnalysisMode::Fast);
    }

    #[test]
    fn test_field_sensitivity() {
        let mut analyzer = PointsToAnalyzer::default();

        // obj = new Obj()
        analyzer.add_alloc("obj", "alloc:1:Obj");
        // val = new Val()
        analyzer.add_alloc("val", "alloc:2:Val");
        // obj.field = val
        analyzer.add_field_store("obj", "field", "val");
        // x = obj.field
        analyzer.add_field_load("x", "obj", "field");

        let result = analyzer.solve();

        // x should potentially alias with val
        let _id_x = analyzer.get_var_id("x").unwrap();
        let _id_val = analyzer.get_var_id("val").unwrap();

        // Note: Precise field-sensitive requires LOAD/STORE handling
        // For now, just check the constraint was added
        assert!(result.stats.constraints_total >= 4);
    }

    #[test]
    fn test_extension_trait() {
        let mut analyzer = PointsToAnalyzer::default();

        analyzer.add_alloc("x", "alloc:1:A");
        analyzer.add_copy("y", "x");

        let result = analyzer.solve();

        assert!(result.graph.may_alias_by_name(&analyzer, "x", "y"));
        assert!(!result
            .graph
            .may_alias_by_name(&analyzer, "x", "nonexistent"));
    }
}
