//! Cross-File Resolution Module (RFC-062)
//!
//! Provides high-performance cross-file symbol resolution and dependency graph
//! construction using Rust parallelism.
//!
//! Key features:
//! - Lock-free symbol index with DashMap
//! - Parallel import resolution with Rayon
//! - Dependency graph with petgraph (Tarjan SCC for cycle detection)
//! - Incremental update support
//!
//! Performance target: 62s → 5s (12x improvement)

mod dep_graph;
mod impact;
mod import_resolver;
mod scope;
mod scope_index;
mod symbol_graph;
mod symbol_index;
mod types;

pub use dep_graph::{DependencyGraph, PageRankConfig};
pub use impact::{BatchImpactAnalysis, ImpactAnalysis, ImpactSummary, RiskLevel};
pub use import_resolver::ImportResolver;
pub use scope::{Scope, ScopeKind};
pub use scope_index::{ScopeAwareIndex, ScopeStats};
pub use symbol_graph::{
    CallGraph, SymbolDependencyGraph, SymbolEdgeKind, SymbolGraphStats, SymbolNode,
};
pub use symbol_index::SymbolIndex;
pub use types::*;

#[cfg(feature = "python")]
use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use crate::shared::models::{Edge, Node};

/// Input IR document for cross-file resolution
///
/// PyO3-enabled: Can be created directly from Python
#[cfg_attr(feature = "python", pyclass(get_all, set_all))]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IRDocument {
    pub file_path: String,
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub repo_id: Option<String>,
}

impl IRDocument {
    pub fn new(file_path: String, nodes: Vec<Node>, edges: Vec<Edge>) -> Self {
        Self {
            file_path,
            nodes,
            edges,
            repo_id: None,
        }
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl IRDocument {
    #[new]
    fn py_new(file_path: String, nodes: Vec<Node>, edges: Vec<Edge>) -> Self {
        Self::new(file_path, nodes, edges)
    }

    fn __repr__(&self) -> String {
        format!(
            "IRDocument(file_path={}, nodes={}, edges={})",
            self.file_path,
            self.nodes.len(),
            self.edges.len()
        )
    }
}

/// Global context result (returned to Python)
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct GlobalContextResult {
    pub total_symbols: usize,
    pub total_files: usize,
    pub total_imports: usize,
    pub total_dependencies: usize,
    pub symbol_table: HashMap<String, Symbol>,
    pub file_dependencies: HashMap<String, Vec<String>>,
    pub file_dependents: HashMap<String, Vec<String>>,
    pub topological_order: Vec<String>,
    pub build_duration_ms: u64,

    // SOTA Priority 3: Symbol-level dependency graph
    pub symbol_graph_stats: Option<SymbolGraphStats>,
}

/// Build global context from IR documents (main entry point)
///
/// This is the high-performance Rust implementation of CrossFileResolver.
/// Uses DashMap for lock-free concurrent access and Rayon for parallelism.
///
/// SOTA: Now includes scope-aware resolution and symbol-level dependency graph
pub fn build_global_context(ir_docs: Vec<IRDocument>) -> GlobalContextResult {
    let start = Instant::now();

    // Phase 1: Build symbol index (parallel)
    let symbol_index = Arc::new(SymbolIndex::build_from_irs(&ir_docs));

    // Phase 1.5: Build scope tree (parallel) - SOTA Priority 2
    let scope_index = ScopeAwareIndex::build_from_irs(Arc::clone(&symbol_index), &ir_docs);

    // Phase 2: Resolve imports with scope awareness (parallel)
    let import_resolver = ImportResolver::new_with_scope(&symbol_index, &scope_index);
    let resolved_imports = import_resolver.resolve_all(&ir_docs);

    // Phase 3: Build file-level dependency graph
    let dep_graph = DependencyGraph::build(&resolved_imports);

    // Phase 4: Build symbol-level dependency graph - SOTA Priority 3
    let symbol_graph = SymbolDependencyGraph::build_from_irs(&ir_docs);
    let symbol_graph_stats = Some(symbol_graph.stats());

    let duration = start.elapsed();

    // Convert to result format
    GlobalContextResult {
        total_symbols: symbol_index.len(),
        total_files: ir_docs.len(),
        total_imports: resolved_imports.values().map(|v| v.len()).sum(),
        total_dependencies: dep_graph.edge_count(),
        symbol_table: symbol_index.to_hashmap(),
        file_dependencies: dep_graph.get_all_dependencies(),
        file_dependents: dep_graph.get_all_dependents(),
        topological_order: dep_graph.topological_order(),
        build_duration_ms: duration.as_millis() as u64,
        symbol_graph_stats,
    }
}

/// Incremental update for changed files
///
/// Only re-processes changed files and their transitive dependents.
///
/// SOTA: Now includes scope-aware resolution for function-scoped imports
pub fn update_global_context(
    existing: &GlobalContextResult,
    changed_ir_docs: Vec<IRDocument>,
    all_ir_docs: Vec<IRDocument>,
) -> (GlobalContextResult, Vec<String>) {
    let start = Instant::now();

    // Build symbol index from all IR docs
    let symbol_index = Arc::new(SymbolIndex::build_from_irs(&all_ir_docs));

    // Build scope tree from all IR docs - SOTA
    let scope_index = ScopeAwareIndex::build_from_irs(Arc::clone(&symbol_index), &all_ir_docs);

    // Find affected files (changed + transitive dependents)
    let changed_paths: Vec<String> = changed_ir_docs
        .iter()
        .map(|ir| ir.file_path.clone())
        .collect();

    let affected_files = compute_affected_files(&changed_paths, &existing.file_dependents);

    // Resolve imports for all with scope awareness (symbol table needs to be consistent)
    let import_resolver = ImportResolver::new_with_scope(&symbol_index, &scope_index);
    let resolved_imports = import_resolver.resolve_all(&all_ir_docs);

    // Build file-level dependency graph
    let dep_graph = DependencyGraph::build(&resolved_imports);

    // Build symbol-level dependency graph - SOTA Priority 3
    let symbol_graph = SymbolDependencyGraph::build_from_irs(&all_ir_docs);
    let symbol_graph_stats = Some(symbol_graph.stats());

    let duration = start.elapsed();

    let result = GlobalContextResult {
        total_symbols: symbol_index.len(),
        total_files: all_ir_docs.len(),
        total_imports: resolved_imports.values().map(|v| v.len()).sum(),
        total_dependencies: dep_graph.edge_count(),
        symbol_table: symbol_index.to_hashmap(),
        file_dependencies: dep_graph.get_all_dependencies(),
        file_dependents: dep_graph.get_all_dependents(),
        topological_order: dep_graph.topological_order(),
        build_duration_ms: duration.as_millis() as u64,
        symbol_graph_stats,
    };

    (result, affected_files)
}

/// Compute transitively affected files from changed files
fn compute_affected_files(
    changed: &[String],
    dependents: &HashMap<String, Vec<String>>,
) -> Vec<String> {
    use std::collections::{HashSet, VecDeque};

    let mut affected = HashSet::new();
    let mut queue: VecDeque<String> = changed.iter().cloned().collect();

    while let Some(path) = queue.pop_front() {
        if affected.insert(path.clone()) {
            // Add files that depend on this file
            if let Some(deps) = dependents.get(&path) {
                for dep in deps {
                    if !affected.contains(dep) {
                        queue.push_back(dep.clone());
                    }
                }
            }
        }
    }

    affected.into_iter().collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{EdgeKind, Node, NodeKind, Span};

    fn make_test_node(id: &str, fqn: &str, file_path: &str) -> Node {
        Node::new(
            id.to_string(),
            NodeKind::Function,
            fqn.to_string(),
            file_path.to_string(),
            Span::new(1, 0, 10, 0),
        )
    }

    fn make_import_edge(source_id: &str, target_id: &str) -> Edge {
        Edge::new(
            source_id.to_string(),
            target_id.to_string(),
            EdgeKind::Imports,
        )
    }

    #[test]
    fn test_build_global_context_empty() {
        let result = build_global_context(vec![]);
        assert_eq!(result.total_symbols, 0);
        assert_eq!(result.total_files, 0);
    }

    #[test]
    fn test_build_global_context_single_file() {
        let ir = IRDocument {
            file_path: "src/main.py".to_string(),
            nodes: vec![
                make_test_node("node1", "main.foo", "src/main.py"),
                make_test_node("node2", "main.bar", "src/main.py"),
            ],
            edges: vec![],
            repo_id: None,
        };

        let result = build_global_context(vec![ir]);
        assert_eq!(result.total_symbols, 2);
        assert_eq!(result.total_files, 1);
        assert!(result.symbol_table.contains_key("main.foo"));
        assert!(result.symbol_table.contains_key("main.bar"));
    }

    #[test]
    fn test_build_global_context_with_imports() {
        let ir1 = IRDocument {
            file_path: "src/utils.py".to_string(),
            nodes: vec![make_test_node(
                "utils_helper",
                "utils.helper",
                "src/utils.py",
            )],
            edges: vec![],
            repo_id: None,
        };

        let ir2 = IRDocument {
            file_path: "src/main.py".to_string(),
            nodes: vec![
                make_test_node("main_foo", "main.foo", "src/main.py"),
                make_test_node("import_utils", "utils.helper", "src/main.py")
                    .with_name("helper".to_string()),
            ],
            edges: vec![make_import_edge("main_foo", "import_utils")],
            repo_id: None,
        };

        let result = build_global_context(vec![ir1, ir2]);
        assert_eq!(result.total_files, 2);
        assert!(result.total_symbols >= 2);
    }

    /// SOTA Test: Function-scoped imports
    ///
    /// Tests the following Python code:
    /// ```python
    /// # utils.py
    /// def helper():
    ///     pass
    ///
    /// # main.py
    /// def foo():
    ///     import utils  # Function-scoped import!
    ///     return utils.helper()
    ///
    /// def bar():
    ///     # utils is NOT available here
    ///     pass
    /// ```
    #[test]
    #[ignore]
    fn test_function_scoped_imports() {
        use crate::shared::models::{Edge, EdgeKind, EdgeMetadata, NodeKind};

        // utils.py: defines helper function
        let ir_utils = IRDocument {
            file_path: "src/utils.py".to_string(),
            nodes: vec![make_test_node(
                "utils_helper",
                "utils.helper",
                "src/utils.py",
            )],
            edges: vec![],
            repo_id: None,
        };

        // main.py: foo() has function-scoped import
        let ir_main = IRDocument {
            file_path: "src/main.py".to_string(),
            nodes: vec![
                // Function: foo
                Node::new(
                    "main_foo".to_string(),
                    NodeKind::Function,
                    "main.foo".to_string(),
                    "src/main.py".to_string(),
                    Span::new(3, 0, 6, 0),
                )
                .with_name("foo".to_string()),
                // Import inside foo: import utils
                Node::new(
                    "import_utils".to_string(),
                    NodeKind::Import,
                    "utils".to_string(),
                    "src/main.py".to_string(),
                    Span::new(4, 4, 4, 16),
                )
                .with_name("utils".to_string()),
                // Function: bar (no import)
                Node::new(
                    "main_bar".to_string(),
                    NodeKind::Function,
                    "main.bar".to_string(),
                    "src/main.py".to_string(),
                    Span::new(8, 0, 10, 0),
                )
                .with_name("bar".to_string()),
            ],
            edges: vec![
                // foo imports utils (edge from foo to import node)
                Edge::new(
                    "main_foo".to_string(),
                    "import_utils".to_string(),
                    EdgeKind::Imports,
                ),
            ],
            repo_id: None,
        };

        // Build context with scope awareness
        let symbol_index = Arc::new(SymbolIndex::build_from_irs(&[
            ir_utils.clone(),
            ir_main.clone(),
        ]));
        let scope_index = ScopeAwareIndex::build_from_irs(
            Arc::clone(&symbol_index),
            &[ir_utils.clone(), ir_main.clone()],
        );

        // Verify scope tree was built
        let stats = scope_index.stats();
        assert_eq!(stats.module_scopes, 2); // utils.py, main.py
        assert_eq!(stats.function_scopes, 3); // utils.helper, main.foo, main.bar

        // Verify foo's scope contains the import alias
        let foo_scope_id = scope_index
            .get_node_scope("main_foo")
            .expect("foo scope not found");
        let foo_scope = scope_index
            .get_scope(&foo_scope_id)
            .expect("foo scope missing");

        // After import resolution, the alias should be registered
        let import_resolver = ImportResolver::new_with_scope(&symbol_index, &scope_index);
        let _resolved = import_resolver.resolve_all(&[ir_main.clone()]);

        // Check that utils alias is in foo's scope
        let all_aliases = foo_scope.get_all_aliases();
        let has_utils_alias = all_aliases.iter().any(|(alias, _)| alias == "utils");
        assert!(has_utils_alias, "utils alias should be in foo's scope");

        // Verify bar's scope does NOT have utils alias
        let bar_scope_id = scope_index
            .get_node_scope("main_bar")
            .expect("bar scope not found");
        let bar_scope = scope_index
            .get_scope(&bar_scope_id)
            .expect("bar scope missing");
        let bar_aliases = bar_scope.get_all_aliases();
        let has_utils_in_bar = bar_aliases.iter().any(|(alias, _)| alias == "utils");
        assert!(!has_utils_in_bar, "utils should NOT be in bar's scope");
    }

    /// SOTA Test: Import alias resolution with LEGB
    ///
    /// Tests the following Python code:
    /// ```python
    /// # Module level
    /// import math as m1  # m1 in module scope
    ///
    /// def foo():
    ///     import math as m2  # m2 shadows m1 in foo's scope
    ///     return m2.sqrt(4)
    ///
    /// m1.sqrt(4)  # m1 available at module level
    /// ```
    #[test]
    fn test_import_alias_legb_resolution() {
        use crate::shared::models::{Edge, EdgeKind, EdgeMetadata, NodeKind};

        let ir = IRDocument {
            file_path: "src/test.py".to_string(),
            nodes: vec![
                // Module-level import: import math as m1
                Node::new(
                    "import_m1".to_string(),
                    NodeKind::Import,
                    "math".to_string(),
                    "src/test.py".to_string(),
                    Span::new(1, 0, 1, 18),
                )
                .with_name("math".to_string()),
                // Function: foo
                Node::new(
                    "foo".to_string(),
                    NodeKind::Function,
                    "test.foo".to_string(),
                    "src/test.py".to_string(),
                    Span::new(3, 0, 5, 0),
                )
                .with_name("foo".to_string()),
                // Function-scoped import: import math as m2
                Node::new(
                    "import_m2".to_string(),
                    NodeKind::Import,
                    "math".to_string(),
                    "src/test.py".to_string(),
                    Span::new(4, 4, 4, 22),
                )
                .with_name("math".to_string()),
            ],
            edges: vec![
                // Module scope imports math as m1
                Edge::new(
                    "import_m1".to_string(),
                    "math".to_string(),
                    EdgeKind::Imports,
                )
                .with_metadata(EdgeMetadata {
                    alias: Some("m1".to_string()),
                    ..Default::default()
                }),
                // foo imports math as m2
                Edge::new(
                    "foo".to_string(),
                    "import_m2".to_string(),
                    EdgeKind::Imports,
                )
                .with_metadata(EdgeMetadata {
                    alias: Some("m2".to_string()),
                    ..Default::default()
                }),
            ],
            repo_id: None,
        };

        let symbol_index = Arc::new(SymbolIndex::build_from_irs(&[ir.clone()]));
        let scope_index = ScopeAwareIndex::build_from_irs(Arc::clone(&symbol_index), &[ir.clone()]);

        // Resolve imports
        let import_resolver = ImportResolver::new_with_scope(&symbol_index, &scope_index);
        let _resolved = import_resolver.resolve_all(&[ir.clone()]);

        // Module scope should have m1
        let module_scope_id = scope_index
            .get_file_scope("src/test.py")
            .expect("module scope not found");
        let module_scope = scope_index
            .get_scope(&module_scope_id)
            .expect("module scope missing");

        // Check aliases after import resolution
        let module_aliases = module_scope.get_all_aliases();
        let has_m1 = module_aliases
            .iter()
            .any(|(alias, fqn)| alias == "m1" && fqn == "math");
        assert!(has_m1, "m1 should be in module scope");

        // foo's scope should have m2
        let foo_scope_id = scope_index
            .get_node_scope("foo")
            .expect("foo scope not found");
        let foo_scope = scope_index
            .get_scope(&foo_scope_id)
            .expect("foo scope missing");
        let foo_aliases = foo_scope.get_all_aliases();
        let has_m2 = foo_aliases
            .iter()
            .any(|(alias, fqn)| alias == "m2" && fqn == "math");
        assert!(has_m2, "m2 should be in foo's scope");

        // LEGB resolution test
        // In foo's scope: m2 should resolve (local), m1 should also resolve (enclosing/global)
        let m2_resolution = scope_index.resolve_in_scope("m2", &foo_scope_id);
        assert!(m2_resolution.is_some(), "m2 should resolve in foo's scope");
        let (m2_fqn, m2_scope) = m2_resolution.unwrap();
        assert_eq!(m2_fqn, "math");
        assert_eq!(m2_scope, foo_scope_id); // Found in local scope

        let m1_resolution = scope_index.resolve_in_scope("m1", &foo_scope_id);
        assert!(m1_resolution.is_some(), "m1 should resolve via LEGB chain");
        let (m1_fqn, m1_scope) = m1_resolution.unwrap();
        assert_eq!(m1_fqn, "math");
        assert_eq!(m1_scope, module_scope_id); // Found in parent (module) scope
    }

    /// SOTA Test: Symbol-level dependency graph
    ///
    /// Tests the following Python code:
    /// ```python
    /// # utils.py
    /// def helper():
    ///     pass
    ///
    /// # main.py
    /// def process():
    ///     return helper()  # process calls helper
    ///
    /// def render():
    ///     return process()  # render calls process
    /// ```
    #[test]
    fn test_symbol_level_dependency_graph() {
        use crate::shared::models::{Edge, EdgeKind, NodeKind};

        // utils.py: defines helper
        let ir_utils = IRDocument {
            file_path: "src/utils.py".to_string(),
            nodes: vec![Node::new(
                "helper_func".to_string(),
                NodeKind::Function,
                "utils.helper".to_string(),
                "src/utils.py".to_string(),
                Span::new(1, 0, 3, 0),
            )
            .with_name("helper".to_string())],
            edges: vec![],
            repo_id: None,
        };

        // main.py: process calls helper, render calls process
        let ir_main = IRDocument {
            file_path: "src/main.py".to_string(),
            nodes: vec![
                Node::new(
                    "process_func".to_string(),
                    NodeKind::Function,
                    "main.process".to_string(),
                    "src/main.py".to_string(),
                    Span::new(1, 0, 3, 0),
                )
                .with_name("process".to_string()),
                Node::new(
                    "render_func".to_string(),
                    NodeKind::Function,
                    "main.render".to_string(),
                    "src/main.py".to_string(),
                    Span::new(5, 0, 7, 0),
                )
                .with_name("render".to_string()),
            ],
            edges: vec![
                // process calls helper
                Edge::new(
                    "process_func".to_string(),
                    "helper_func".to_string(),
                    EdgeKind::Calls,
                ),
                // render calls process
                Edge::new(
                    "render_func".to_string(),
                    "process_func".to_string(),
                    EdgeKind::Calls,
                ),
            ],
            repo_id: None,
        };

        // Build global context (includes symbol graph)
        let result = build_global_context(vec![ir_utils, ir_main]);

        // Verify symbol graph was built
        assert!(result.symbol_graph_stats.is_some());
        let stats = result.symbol_graph_stats.unwrap();

        // Should have 3 symbols (helper, process, render)
        assert_eq!(stats.total_symbols, 3);

        // Note: Cross-file edges (process→helper) are not resolved within single IR docs
        // Only intra-file edges (render→process) are captured
        // 1 Calls edge + 1 CalledBy reverse edge = 2 total edges
        assert_eq!(stats.total_edges, 2);

        // Verify call edges exist (only render→process is intra-file)
        assert_eq!(
            *stats
                .edges_by_kind
                .get(&SymbolEdgeKind::Calls)
                .unwrap_or(&0),
            1
        );
    }

    /// SOTA Test: Impact analysis
    ///
    /// Tests impact of changing a core function
    #[test]
    #[ignore]
    fn test_impact_analysis() {
        use crate::shared::models::{Edge, EdgeKind, NodeKind};

        // Create call chain: a → b → c
        let ir = IRDocument {
            file_path: "src/test.py".to_string(),
            nodes: vec![
                Node::new(
                    "a".to_string(),
                    NodeKind::Function,
                    "test.a".to_string(),
                    "src/test.py".to_string(),
                    Span::new(1, 0, 3, 0),
                )
                .with_name("a".to_string()),
                Node::new(
                    "b".to_string(),
                    NodeKind::Function,
                    "test.b".to_string(),
                    "src/test.py".to_string(),
                    Span::new(5, 0, 7, 0),
                )
                .with_name("b".to_string()),
                Node::new(
                    "c".to_string(),
                    NodeKind::Function,
                    "test.c".to_string(),
                    "src/test.py".to_string(),
                    Span::new(9, 0, 11, 0),
                )
                .with_name("c".to_string()),
            ],
            edges: vec![
                Edge::new("a".to_string(), "b".to_string(), EdgeKind::Calls),
                Edge::new("b".to_string(), "c".to_string(), EdgeKind::Calls),
            ],
            repo_id: None,
        };

        // Build symbol graph
        let symbol_graph = SymbolDependencyGraph::build_from_irs(&[ir]);
        let total_symbols = symbol_graph.stats().total_symbols;

        // Analyze impact of changing 'c' (leaf function)
        let impact_c = ImpactAnalysis::compute(&symbol_graph, "test.c", total_symbols)
            .expect("Impact analysis failed");

        assert_eq!(impact_c.target_fqn, "test.c");
        // Both 'a' and 'b' depend on 'c' transitively
        assert_eq!(impact_c.transitive_dependents.len(), 2);
        assert!(impact_c
            .transitive_dependents
            .contains(&"test.a".to_string()));
        assert!(impact_c
            .transitive_dependents
            .contains(&"test.b".to_string()));

        // Analyze impact of changing 'b' (middle function)
        let impact_b = ImpactAnalysis::compute(&symbol_graph, "test.b", total_symbols)
            .expect("Impact analysis failed");

        assert_eq!(impact_b.direct_dependents.len(), 1); // Only 'a' directly calls 'b'
        assert!(impact_b.direct_dependents.contains(&"test.a".to_string()));
    }
}
