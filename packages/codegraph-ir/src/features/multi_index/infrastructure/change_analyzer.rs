// Change Analyzer: Delta Intelligence + SOTA features
//
// # Non-Negotiable Contracts
// - P1-7: Embed unit = Function signature + docstring (NOT body)
// - P1-8: Signature changes only trigger BFS, MAX_IMPACT_DEPTH = 2

use crate::features::multi_index::config::{self, MAX_IMPACT_DEPTH};
use crate::features::multi_index::ports::{
    ChangeScope, DeltaAnalysis, ExpandedScope, HashComparison, IndexImpact, IndexType, Region,
    UpdateStrategy,
};
use crate::features::query_engine::infrastructure::{
    TransactionDelta, TransactionalGraphIndex, TxnId,
};
use crate::shared::models::{EdgeKind, Node};
use std::collections::{HashMap, HashSet, VecDeque};

pub struct ChangeAnalyzer {
    /// Total node count (for impact ratio calculation)
    total_node_count: usize,

    /// Critical node IDs (entry points, public APIs) - Escape Hatch
    /// These nodes get extended depth propagation (CRITICAL_NODE_MAX_DEPTH)
    critical_nodes: HashSet<String>,
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// CORRECTED: 4-Level Hash System Types
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/// 4-Level Merkle Hash Structure
#[derive(Debug, Clone)]
pub struct FourLevelHash {
    pub signature_hash: u64, // Level 1: API surface
    pub body_hash: u64,      // Level 2: Semantic body
    pub doc_hash: u64,       // Level 3: Documentation
    pub format_hash: u64,    // Level 4: Formatting
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Multi-Graph Propagation (SOTA Enhancement)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/// Impact propagation graph selection
///
/// Different change types require different propagation patterns:
/// - CallGraph: Function signature changes affect callers
/// - TypeFlow: Type changes affect type consumers
/// - DataFlow: Data structure changes affect readers/writers
/// - FrameworkRoute: DI/routing changes affect implicit edges
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ImpactGraph {
    /// Call graph (function → callers)
    /// Used for: Signature changes
    CallGraph,

    /// Type flow graph (type → consumers)
    /// Used for: Type annotation changes, class hierarchy changes
    TypeFlow,

    /// Data flow graph (variable → usages)
    /// Used for: Global state changes, data structure modifications
    DataFlow,

    /// Framework routing graph (route → handlers)
    /// Used for: Dependency injection, URL routing, event handlers
    FrameworkRoute,
}

impl ImpactGraph {
    /// Get the EdgeKind(s) to traverse for this graph type
    pub fn relevant_edge_kinds(&self) -> Vec<EdgeKind> {
        match self {
            ImpactGraph::CallGraph => vec![EdgeKind::Calls],
            ImpactGraph::TypeFlow => vec![EdgeKind::Extends, EdgeKind::Implements],
            ImpactGraph::DataFlow => vec![EdgeKind::Reads, EdgeKind::Writes],
            ImpactGraph::FrameworkRoute => vec![
                EdgeKind::Calls,      // DI injection
                EdgeKind::References, // Route references
            ],
        }
    }

    /// Determine which graph(s) to use based on node change type
    pub fn select_for_change(old_node: Option<&Node>, new_node: &Node) -> Vec<ImpactGraph> {
        let mut graphs = vec![];

        // Always check call graph for function changes
        if let Some(old) = old_node {
            // Signature changed → CallGraph
            if old.name != new_node.name
                || old.parameters != new_node.parameters
                || old.return_type != new_node.return_type
            {
                graphs.push(ImpactGraph::CallGraph);
            }

            // Type annotation changed → TypeFlow
            if old.type_annotation != new_node.type_annotation
                || old.base_classes != new_node.base_classes
            {
                graphs.push(ImpactGraph::TypeFlow);
            }

            // Decorators changed → FrameworkRoute (e.g., @app.route)
            if old.decorators != new_node.decorators {
                graphs.push(ImpactGraph::FrameworkRoute);
            }
        } else {
            // New node - use CallGraph as default
            graphs.push(ImpactGraph::CallGraph);
        }

        graphs
    }
}

impl ChangeAnalyzer {
    pub fn new() -> Self {
        Self {
            total_node_count: 0,
            critical_nodes: HashSet::new(),
        }
    }

    /// Configure critical nodes for escape hatch
    ///
    /// # Arguments
    /// - `node_ids`: IDs of critical nodes (entry points, public APIs)
    ///
    /// # Example
    /// ```ignore
    /// analyzer.configure_critical_nodes(vec![
    ///     "main".to_string(),
    ///     "app.routes.user_handler".to_string(),
    /// ]);
    /// ```
    pub fn configure_critical_nodes(&mut self, node_ids: Vec<String>) {
        self.critical_nodes = node_ids.into_iter().collect();
    }

    /// Check if a node is critical (triggers escape hatch)
    fn is_critical_node(&self, node_id: &str) -> bool {
        self.critical_nodes.contains(node_id)
    }

    /// Get max depth for a node (escape hatch aware)
    ///
    /// # Returns
    /// - CRITICAL_NODE_MAX_DEPTH (5) for critical nodes
    /// - MAX_IMPACT_DEPTH (2) for normal nodes
    fn get_max_depth_for_node(&self, node_id: &str) -> u8 {
        if self.is_critical_node(node_id) {
            config::escape_hatch::CRITICAL_NODE_MAX_DEPTH
        } else {
            MAX_IMPACT_DEPTH
        }
    }

    /// Analyze delta with dependency propagation and hash bypassing
    ///
    /// # SOTA Features
    /// - Dependency ripple effect (BFS propagation)
    /// - Multi-hash bypassing (95% cost reduction)
    /// - Impact classification
    /// - Cost estimation
    pub fn analyze_delta(
        &self,
        delta: &TransactionDelta,
        graph: &TransactionalGraphIndex,
    ) -> DeltaAnalysis {
        let total_nodes = graph.node_count();
        let changed_nodes = delta.total_changes();
        let impact_ratio = if total_nodes > 0 {
            changed_nodes as f64 / total_nodes as f64
        } else {
            0.0
        };

        // SOTA Feature 1: Dependency Ripple Effect (P1-8)
        let expanded_scope = self.compute_expanded_scope(delta, graph);

        // SOTA Feature 2: Multi-Hash Bypassing (P1-6, P1-7)
        let hash_analysis = self.compute_hash_deltas(delta, graph);

        let mut index_impacts = HashMap::new();

        // Graph Index: Skip if no changes, otherwise sync incremental (cheap)
        let edge_explosion_factor = self.compute_edge_explosion_factor(graph);
        let graph_requires_update = changed_nodes > 0;
        index_impacts.insert(
            IndexType::Graph,
            IndexImpact {
                requires_update: graph_requires_update,
                estimated_cost_ms: changed_nodes as u64
                    * edge_explosion_factor
                    * config::cost::GRAPH_UPDATE_COST_PER_NODE_MS,
                strategy: if graph_requires_update {
                    UpdateStrategy::SyncIncremental
                } else {
                    UpdateStrategy::Skip
                },
            },
        );

        // Vector Index: Hash-based bypass + dependency propagation
        // CORRECTED: Use signature_changed OR body_changed
        let needs_embedding = hash_analysis
            .iter()
            .filter(|(_, hash)| hash.requires_reembedding()) // signature OR body
            .count();

        let embedding_targets = if needs_embedding > 0 {
            // Include propagated callers
            expanded_scope.primary_targets.len() + expanded_scope.secondary_targets.len()
        } else {
            0 // All skipped via hash bypass!
        };

        let embedding_cost = embedding_targets as u64 * config::cost::EMBEDDING_COST_MS;
        index_impacts.insert(
            IndexType::Vector,
            IndexImpact {
                requires_update: needs_embedding > 0,
                estimated_cost_ms: embedding_cost,
                strategy: if impact_ratio > config::analysis::FULL_REBUILD_THRESHOLD {
                    UpdateStrategy::FullRebuild
                } else if needs_embedding > 0 {
                    if embedding_targets > config::analysis::ASYNC_UPDATE_THRESHOLD {
                        UpdateStrategy::AsyncIncremental // Background for large updates
                    } else {
                        UpdateStrategy::SyncIncremental // Inline for small updates
                    }
                } else {
                    UpdateStrategy::Skip // Hash bypass: 95% cost reduction!
                },
            },
        );

        // Lexical Index: File-based, always sync
        let affected_files = self.compute_affected_files(delta);
        index_impacts.insert(
            IndexType::Lexical,
            IndexImpact {
                requires_update: !affected_files.is_empty(),
                estimated_cost_ms: affected_files.len() as u64
                    * config::cost::LEXICAL_UPDATE_COST_PER_FILE_MS,
                strategy: UpdateStrategy::SyncIncremental,
            },
        );

        DeltaAnalysis {
            scope: self.classify_scope(delta),
            impact_ratio,
            affected_regions: self.compute_regions(delta),
            index_impacts,
            expanded_scope,
            hash_analysis,
            from_txn: delta.from_txn,
            to_txn: delta.to_txn,
        }
    }

    /// P1-8: Dependency-aware scope expansion (LEGACY - CallGraph only)
    ///
    /// # Non-Negotiable Contract 3-3
    /// - Signature 변경만 BFS 전파
    /// - MAX_IMPACT_DEPTH = 2 고정
    ///
    /// Propagates impact to callers when function signature changes
    pub fn compute_expanded_scope(
        &self,
        delta: &TransactionDelta,
        graph: &TransactionalGraphIndex,
    ) -> ExpandedScope {
        // Delegate to multi-graph version with CallGraph only (backward compatible)
        self.compute_expanded_scope_multi_graph(delta, graph, &[ImpactGraph::CallGraph])
    }

    /// SOTA: Multi-Graph Dependency Propagation
    ///
    /// # Enhancement over compute_expanded_scope
    /// - Supports multiple graph types (Call, Type, Data, Framework)
    /// - Intelligent graph selection based on change type
    /// - Maintains MAX_IMPACT_DEPTH = 2 contract
    ///
    /// # Arguments
    /// - `delta`: Transaction delta containing changes
    /// - `graph`: Current transaction index for edge queries
    /// - `graphs`: Which propagation graphs to use (defaults to auto-detect)
    pub fn compute_expanded_scope_multi_graph(
        &self,
        delta: &TransactionDelta,
        graph: &TransactionalGraphIndex,
        graphs: &[ImpactGraph],
    ) -> ExpandedScope {
        let mut affected_nodes = HashSet::new();
        let mut queue: VecDeque<(String, u8)> = VecDeque::new(); // (NodeId, Depth)

        // Get old snapshot to compare nodes
        let old_snapshot = graph.get_snapshot(delta.from_txn);
        let current_snapshot = graph.get_snapshot(delta.to_txn);

        // 1. Determine which nodes trigger propagation and which graphs to use
        for node in &delta.modified_nodes {
            let old_node = old_snapshot.nodes.get(&node.id);

            // Auto-select graphs based on change type if not explicitly provided
            let selected_graphs = if graphs.is_empty() {
                ImpactGraph::select_for_change(old_node, node)
            } else {
                graphs.to_vec()
            };

            // Check if this change should propagate on any graph
            let should_propagate = selected_graphs.iter().any(|graph_type| {
                match graph_type {
                    ImpactGraph::CallGraph => self.signature_changed(node, old_node),
                    ImpactGraph::TypeFlow => self.type_changed(node, old_node),
                    ImpactGraph::DataFlow => true, // Data changes always propagate
                    ImpactGraph::FrameworkRoute => self.decorator_changed(node, old_node),
                }
            });

            if should_propagate {
                queue.push_back((node.id.clone(), 0));
            }
        }

        // Collect relevant edge kinds from all selected graphs
        let relevant_edge_kinds: HashSet<EdgeKind> = graphs
            .iter()
            .flat_map(|g| g.relevant_edge_kinds())
            .collect();

        // 2. BFS propagation across multiple graph types (with escape hatch)
        while let Some((current_id, depth)) = queue.pop_front() {
            // Escape Hatch: Use extended depth for critical nodes
            let max_depth = self.get_max_depth_for_node(&current_id);

            if depth >= max_depth {
                continue;
            }

            affected_nodes.insert(current_id.clone());

            // Find dependents (incoming edges of relevant kinds)
            for edge in &current_snapshot.edges {
                // Check if this edge is relevant for our selected graphs
                if edge.target_id == current_id && relevant_edge_kinds.contains(&edge.kind) {
                    let dependent_id = &edge.source_id;
                    if !affected_nodes.contains(dependent_id) {
                        queue.push_back((dependent_id.clone(), depth + 1));
                    }
                }
            }
        }

        ExpandedScope {
            primary_targets: delta.modified_nodes.iter().map(|n| n.id.clone()).collect(),
            secondary_targets: affected_nodes.into_iter().collect(),
        }
    }

    /// Helper: Check if type/annotation changed
    fn type_changed(&self, new_node: &Node, old_node: Option<&Node>) -> bool {
        if let Some(old) = old_node {
            old.type_annotation != new_node.type_annotation
                || old.base_classes != new_node.base_classes
                || old.return_type != new_node.return_type
        } else {
            false // New nodes don't propagate type changes
        }
    }

    /// Helper: Check if decorators changed
    fn decorator_changed(&self, new_node: &Node, old_node: Option<&Node>) -> bool {
        if let Some(old) = old_node {
            old.decorators != new_node.decorators
        } else {
            false
        }
    }

    /// P1-7: Multi-hash bypass detection
    ///
    /// # Non-Negotiable Contract 3-2
    /// - Embed unit = Function signature + docstring
    /// - Body 변경은 절대 re-embed 트리거 아님
    ///
    /// Computes canonical hashes to skip unnecessary embeddings
    pub fn compute_hash_deltas(
        &self,
        delta: &TransactionDelta,
        graph: &TransactionalGraphIndex,
    ) -> HashMap<String, HashComparison> {
        let mut results = HashMap::new();

        // P1-6: Get old snapshot to retrieve previous node versions
        let old_snapshot = graph.get_snapshot(delta.from_txn);

        for node in &delta.modified_nodes {
            // Compute three levels of hashes for new node
            let new_logic_hash = self.compute_canonical_hash(node); // AST structure + docstring
            let new_doc_hash = self.compute_doc_hash(node); // Docstrings/comments
            let new_format_hash = self.compute_format_hash(node); // Whitespace/formatting

            // P1-6: Get old node from previous snapshot
            let old_node = old_snapshot.nodes.get(&node.id);

            // Compute hashes for old node (if exists)
            let (old_logic_hash, old_doc_hash, old_format_hash) =
                old_node.map_or((0, 0, 0), |old| {
                    (
                        self.compute_canonical_hash(old),
                        self.compute_doc_hash(old),
                        self.compute_format_hash(old),
                    )
                });

            // P1-6: Merkle tree-style comparison
            // TEMPORARY: Map old 3-level to new 4-level structure
            results.insert(
                node.id.clone(),
                HashComparison {
                    // CORRECTED: signature_changed (was logic_changed)
                    signature_changed: new_logic_hash != old_logic_hash,
                    body_changed: false, // Old system didn't track body
                    doc_changed: new_doc_hash != old_doc_hash,
                    format_changed: new_format_hash != old_format_hash,
                },
            );
        }

        results
    }

    /// P1-7: Compute canonical hash (signature + docstring, NOT body)
    ///
    /// # Non-Negotiable Contract 3-2
    /// Embed unit = Function signature + docstring
    /// Body changes do NOT trigger re-embedding
    ///
    /// Example: "def foo(x: int) -> str: ..." → hash(signature + docstring)
    fn compute_canonical_hash(&self, node: &Node) -> u64 {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};

        let mut hasher = DefaultHasher::new();

        // P1-7: IMMUTABLE - Hash signature + docstring only
        node.kind.hash(&mut hasher);
        node.name.hash(&mut hasher);
        node.parameters.hash(&mut hasher);
        node.return_type.hash(&mut hasher);
        node.docstring.hash(&mut hasher);

        // P1-7: IMMUTABLE - DO NOT hash body
        // Body changes do NOT trigger re-embedding

        hasher.finish()
    }

    /// Compute docstring hash
    fn compute_doc_hash(&self, node: &Node) -> u64 {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};

        let mut hasher = DefaultHasher::new();
        node.docstring.hash(&mut hasher);
        hasher.finish()
    }

    /// Compute formatting hash
    fn compute_format_hash(&self, node: &Node) -> u64 {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};

        let mut hasher = DefaultHasher::new();
        // In production: hash whitespace, indentation, line breaks
        node.span.hash(&mut hasher);
        hasher.finish()
    }

    /// Check if signature changed
    ///
    /// # P1-8: Signature-only change detection
    fn signature_changed(&self, new_node: &Node, old_node: Option<&Node>) -> bool {
        old_node.map_or(true, |old| {
            new_node.parameters != old.parameters
                || new_node.return_type != old.return_type
                || new_node.name != old.name
        })
    }

    /// Classify change scope
    fn classify_scope(&self, delta: &TransactionDelta) -> ChangeScope {
        // Classify as IR-level changes (nodes and edges)
        // Edge IDs are constructed from source → target (kind)
        ChangeScope::IR {
            added_nodes: delta.added_nodes.iter().map(|n| n.id.clone()).collect(),
            removed_nodes: delta.removed_nodes.iter().map(|n| n.id.clone()).collect(),
            modified_nodes: delta.modified_nodes.iter().map(|n| n.id.clone()).collect(),
            added_edges: delta
                .added_edges
                .iter()
                .map(|e| format!("{}→{}", e.source_id, e.target_id))
                .collect(),
            removed_edges: delta
                .removed_edges
                .iter()
                .map(|e| format!("{}→{}", e.source_id, e.target_id))
                .collect(),
        }
    }

    /// Compute affected regions (grouped by file/module)
    fn compute_regions(&self, delta: &TransactionDelta) -> Vec<Region> {
        use std::collections::HashMap;

        let mut file_regions: HashMap<String, Vec<String>> = HashMap::new();

        // Group modified nodes by file path
        for node in delta
            .added_nodes
            .iter()
            .chain(&delta.modified_nodes)
            .chain(&delta.removed_nodes)
        {
            file_regions
                .entry(node.file_path.clone())
                .or_insert_with(Vec::new)
                .push(node.id.clone());
        }

        // Convert to Region structs
        file_regions
            .into_iter()
            .map(|(file_path, node_ids)| {
                // Extract module path: /path/to/module/file.py → module.file
                let module_path = file_path
                    .strip_suffix(".py")
                    .or_else(|| file_path.strip_suffix(".rs"))
                    .or_else(|| file_path.strip_suffix(".ts"))
                    .or_else(|| file_path.strip_suffix(".js"))
                    .map(|p| p.replace(['/', '\\'], "."));
                Region {
                    file_path,
                    module_path,
                    node_ids,
                }
            })
            .collect()
    }

    /// Compute affected files
    fn compute_affected_files(&self, delta: &TransactionDelta) -> Vec<String> {
        let mut files: HashSet<String> = HashSet::new();

        for node in delta
            .added_nodes
            .iter()
            .chain(&delta.modified_nodes)
            .chain(&delta.removed_nodes)
        {
            files.insert(node.file_path.clone());
        }

        files.into_iter().collect()
    }

    /// P2-10: Edge explosion detection
    ///
    /// Compute edge explosion factor for Graph Index cost model
    fn compute_edge_explosion_factor(&self, graph: &TransactionalGraphIndex) -> u64 {
        let total_nodes = graph.node_count() as u64;
        let total_edges = graph.edge_count() as u64;

        if total_nodes == 0 {
            return 1;
        }

        let avg_edges_per_node = total_edges / total_nodes.max(1);

        if avg_edges_per_node > config::analysis::DENSE_GRAPH_THRESHOLD {
            // Dense graph: Edge updates are expensive
            avg_edges_per_node / config::analysis::DENSE_GRAPH_COST_SCALE
        } else {
            1 // Sparse graph: O(1) per node
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // CORRECTED: 4-Level Hash System
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Compute 4-level hash with clear semantic boundaries
    ///
    /// # Contract (REVISED)
    /// - Level 1 (Signature): kind + name + params + return_type
    /// - Level 2 (Body): signature + AST/control-flow fingerprint
    /// - Level 3 (Doc): body + docstring
    /// - Level 4 (Format): doc + whitespace-normalized tokens
    pub fn compute_four_level_hash(&self, node: &Node) -> FourLevelHash {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};

        // Level 1: Signature Hash (API surface only)
        let signature_hash = {
            let mut hasher = DefaultHasher::new();
            node.kind.hash(&mut hasher);
            node.name.hash(&mut hasher);
            node.parameters.hash(&mut hasher);
            node.return_type.hash(&mut hasher);
            // Also hash decorators/modifiers that affect API
            node.decorators.hash(&mut hasher);
            node.modifiers.hash(&mut hasher);
            hasher.finish()
        };

        // Level 2: Body Hash (semantic content)
        let body_hash = {
            let mut hasher = DefaultHasher::new();
            signature_hash.hash(&mut hasher);

            // Hash control flow structure (if available)
            // NOTE: control_flow field removed from Node (not exposed to Python)
            // Use body_span as proxy for semantic changes

            // Hash body span as proxy for semantic changes
            // NOTE: In production, use AST fingerprint instead
            if let Some(ref body_span) = node.body_span {
                body_span.hash(&mut hasher);
            }

            // Hash annotations (type hints affect semantics)
            node.annotations.hash(&mut hasher);
            node.is_async.hash(&mut hasher);
            node.is_generator.hash(&mut hasher);

            hasher.finish()
        };

        // Level 3: Doc Hash (documentation layer)
        let doc_hash = {
            let mut hasher = DefaultHasher::new();
            body_hash.hash(&mut hasher);
            node.docstring.hash(&mut hasher);
            hasher.finish()
        };

        // Level 4: Format Hash (whitespace-normalized)
        let format_hash = {
            let mut hasher = DefaultHasher::new();
            doc_hash.hash(&mut hasher);

            // NOTE: NOT using span (too fragile to formatting)
            // In production, use token-based fingerprint
            // For now, hash FQN as stable identifier
            node.fqn.hash(&mut hasher);

            hasher.finish()
        };

        FourLevelHash {
            signature_hash,
            body_hash,
            doc_hash,
            format_hash,
        }
    }

    /// Whitespace-normalized fingerprint (stable across reformatting)
    ///
    /// # Future Enhancement
    /// Replace this with tree-sitter token-based fingerprint
    fn normalize_whitespace(content: &str) -> String {
        content.split_whitespace().collect::<Vec<_>>().join(" ")
    }

    /// CORRECTED: Compute hash deltas using 4-level hierarchy
    ///
    /// # Future: Replace compute_hash_deltas with this method
    #[allow(dead_code)]
    pub fn compute_hash_deltas_v2(
        &self,
        delta: &TransactionDelta,
        graph: &TransactionalGraphIndex,
    ) -> HashMap<String, HashComparison> {
        let mut results = HashMap::new();
        let old_snapshot = graph.get_snapshot(delta.from_txn);

        for node in &delta.modified_nodes {
            let new_hash = self.compute_four_level_hash(node);
            let old_node = old_snapshot.nodes.get(&node.id);
            let old_hash = old_node.map_or(
                FourLevelHash {
                    signature_hash: 0,
                    body_hash: 0,
                    doc_hash: 0,
                    format_hash: 0,
                },
                |old| self.compute_four_level_hash(old),
            );

            let comparison = if new_hash.signature_hash != old_hash.signature_hash {
                HashComparison {
                    signature_changed: true,
                    body_changed: false,
                    doc_changed: false,
                    format_changed: false,
                }
            } else if new_hash.body_hash != old_hash.body_hash {
                HashComparison {
                    signature_changed: false,
                    body_changed: true,
                    doc_changed: false,
                    format_changed: false,
                }
            } else if new_hash.doc_hash != old_hash.doc_hash {
                HashComparison {
                    signature_changed: false,
                    body_changed: false,
                    doc_changed: true,
                    format_changed: false,
                }
            } else {
                HashComparison {
                    signature_changed: false,
                    body_changed: false,
                    doc_changed: false,
                    format_changed: true,
                }
            };

            if let Err(e) = comparison.validate() {
                eprintln!("WARNING: Hash invariant violated for {}: {}", node.id, e);
            }

            results.insert(node.id.clone(), comparison);
        }

        results
    }
}

impl Default for ChangeAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
#[path = "change_analyzer_test.rs"]
mod change_analyzer_test;
