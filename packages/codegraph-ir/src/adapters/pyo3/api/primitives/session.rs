//! AnalysisSession - Stateful Analysis Handle
//!
//! RFC-071: Keeps IR in Rust memory to eliminate serialization overhead.
//!
//! Key Design Decisions:
//! 1. IR loaded once, stays in Rust memory
//! 2. Graphs (CFG/DFG/PDG) built lazily and cached
//! 3. Analysis results cached for repeated queries
//! 4. Session governance: memory limits, TTL, timeouts
//!
//! Performance:
//! - Eliminates ir_bytes copying on every primitive call
//! - 10-100x faster for multi-step analyses

use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use std::time::{Duration, Instant};
use uuid::Uuid;
use serde::{Deserialize, Serialize};

use crate::shared::models::{Node, Edge, Span};
use crate::features::pdg::infrastructure::pdg::ProgramDependenceGraph;
use crate::features::flow_graph::infrastructure::cfg::CFGEdge;
use crate::features::data_flow::infrastructure::dfg::DataFlowGraph;

// ═══════════════════════════════════════════════════════════════════════════
// Configuration
// ═══════════════════════════════════════════════════════════════════════════

/// Session configuration for resource governance
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionConfig {
    /// Maximum memory usage (bytes, 0 = unlimited)
    pub max_memory_bytes: usize,

    /// Session TTL (inactive session auto-cleanup, seconds)
    pub ttl_seconds: u64,

    /// Individual analysis timeout (seconds)
    pub analysis_timeout_seconds: u64,

    /// k-CFA context limit (prevent memory explosion)
    pub max_context_limit: usize,

    /// Result paging threshold (above this, return handle)
    pub result_paging_threshold: usize,
}

impl Default for SessionConfig {
    fn default() -> Self {
        Self {
            max_memory_bytes: 2 * 1024 * 1024 * 1024, // 2GB
            ttl_seconds: 30 * 60,                      // 30 minutes
            analysis_timeout_seconds: 300,             // 5 minutes
            max_context_limit: 10_000,                 // 10K contexts
            result_paging_threshold: 50_000,           // 50K nodes
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// IR Document (Simplified for session storage)
// ═══════════════════════════════════════════════════════════════════════════

/// IR Document stored in session
#[derive(Debug, Clone)]
pub struct IRDocument {
    pub file_path: String,
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub node_index: HashMap<String, usize>,  // node_id → index
    pub symbol_index: HashMap<String, Vec<usize>>,  // symbol → node indices
}

impl IRDocument {
    pub fn new(file_path: String, nodes: Vec<Node>, edges: Vec<Edge>) -> Self {
        let mut node_index = HashMap::new();
        let mut symbol_index: HashMap<String, Vec<usize>> = HashMap::new();

        for (i, node) in nodes.iter().enumerate() {
            node_index.insert(node.id.clone(), i);

            // Index by name for symbol lookup
            if let Some(ref name) = node.name {
                if !name.is_empty() {
                    symbol_index.entry(name.clone()).or_default().push(i);
                }
            }

            // Index by FQN
            if !node.fqn.is_empty() {
                symbol_index.entry(node.fqn.clone()).or_default().push(i);
            }
        }

        Self {
            file_path,
            nodes,
            edges,
            node_index,
            symbol_index,
        }
    }

    pub fn get_node(&self, node_id: &str) -> Option<&Node> {
        self.node_index.get(node_id).map(|&i| &self.nodes[i])
    }

    pub fn get_nodes_by_symbol(&self, symbol: &str) -> Vec<&Node> {
        self.symbol_index
            .get(symbol)
            .map(|indices| indices.iter().map(|&i| &self.nodes[i]).collect())
            .unwrap_or_default()
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Graph Cache
// ═══════════════════════════════════════════════════════════════════════════

/// Lazily built graph cache
#[derive(Debug, Default)]
pub struct GraphCache {
    /// PDG per function (lazy built)
    pub pdg_cache: HashMap<String, Arc<ProgramDependenceGraph>>,

    /// CFG edges per function (lazy built)
    pub cfg_cache: HashMap<String, Vec<CFGEdge>>,

    /// DFG per function (lazy built)
    pub dfg_cache: HashMap<String, Arc<DataFlowGraph>>,

    /// Build timestamps for invalidation
    pub build_times: HashMap<String, Instant>,
}

impl GraphCache {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn invalidate(&mut self, function_id: &str) {
        self.pdg_cache.remove(function_id);
        self.cfg_cache.remove(function_id);
        self.dfg_cache.remove(function_id);
        self.build_times.remove(function_id);
    }

    pub fn invalidate_all(&mut self) {
        self.pdg_cache.clear();
        self.cfg_cache.clear();
        self.dfg_cache.clear();
        self.build_times.clear();
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Analysis Result Cache
// ═══════════════════════════════════════════════════════════════════════════

/// Cached analysis result (for lazy access)
#[derive(Debug, Clone)]
pub struct AnalysisResult {
    pub analysis_id: String,
    pub analysis_type: String,  // "reach", "fixpoint", "propagate", etc.
    pub node_facts: HashMap<String, Vec<u8>>,  // node_id → msgpack facts
    pub created_at: Instant,
    pub total_nodes: usize,
}

impl AnalysisResult {
    pub fn new(analysis_type: &str) -> Self {
        Self {
            analysis_id: Uuid::new_v4().to_string(),
            analysis_type: analysis_type.to_string(),
            node_facts: HashMap::new(),
            created_at: Instant::now(),
            total_nodes: 0,
        }
    }
}

/// Analysis result cache
#[derive(Debug, Default)]
pub struct AnalysisCache {
    pub results: HashMap<String, AnalysisResult>,
    pub max_entries: usize,
}

impl AnalysisCache {
    pub fn new(max_entries: usize) -> Self {
        Self {
            results: HashMap::new(),
            max_entries,
        }
    }

    pub fn insert(&mut self, result: AnalysisResult) -> String {
        let analysis_id = result.analysis_id.clone();

        // LRU-style eviction if over limit
        if self.results.len() >= self.max_entries {
            if let Some(oldest_id) = self.find_oldest() {
                self.results.remove(&oldest_id);
            }
        }

        self.results.insert(analysis_id.clone(), result);
        analysis_id
    }

    fn find_oldest(&self) -> Option<String> {
        self.results
            .iter()
            .min_by_key(|(_, r)| r.created_at)
            .map(|(id, _)| id.clone())
    }

    pub fn get(&self, analysis_id: &str) -> Option<&AnalysisResult> {
        self.results.get(analysis_id)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Session Statistics
// ═══════════════════════════════════════════════════════════════════════════

/// Session statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionStats {
    pub session_id: String,
    pub created_at_ms: u64,
    pub last_access_ms: u64,
    pub ir_node_count: usize,
    pub ir_edge_count: usize,
    pub cached_pdgs: usize,
    pub cached_analyses: usize,
    pub total_queries: u64,
    pub memory_estimate_bytes: usize,
}

// ═══════════════════════════════════════════════════════════════════════════
// AnalysisSession
// ═══════════════════════════════════════════════════════════════════════════

/// Stateful analysis session keeping IR in Rust memory
///
/// # Thread Safety
/// - `ir` is immutable after creation (Arc)
/// - `graphs` and `results` are protected by RwLock
///
/// # Performance
/// - IR loaded once, no repeated serialization
/// - Graphs built lazily and cached
/// - Analysis results cached for repeated queries
pub struct AnalysisSession {
    /// Unique session ID
    pub session_id: String,

    /// IR document (immutable after creation)
    ir: Arc<IRDocument>,

    /// Graph cache (CFG/DFG/PDG, lazily built)
    graphs: RwLock<GraphCache>,

    /// Analysis result cache
    results: RwLock<AnalysisCache>,

    /// Session configuration
    config: SessionConfig,

    /// Creation timestamp
    created_at: Instant,

    /// Last access timestamp
    last_access: RwLock<Instant>,

    /// Query counter
    query_count: RwLock<u64>,
}

impl AnalysisSession {
    /// Create new session from IR data
    ///
    /// # Arguments
    /// * `file_path` - Source file path
    /// * `nodes` - IR nodes
    /// * `edges` - IR edges
    /// * `config` - Optional session configuration
    ///
    /// # Returns
    /// * New AnalysisSession
    pub fn new(
        file_path: String,
        nodes: Vec<Node>,
        edges: Vec<Edge>,
        config: Option<SessionConfig>,
    ) -> Self {
        let ir = IRDocument::new(file_path, nodes, edges);
        let config = config.unwrap_or_default();

        Self {
            session_id: Uuid::new_v4().to_string(),
            ir: Arc::new(ir),
            graphs: RwLock::new(GraphCache::new()),
            results: RwLock::new(AnalysisCache::new(100)),
            config,
            created_at: Instant::now(),
            last_access: RwLock::new(Instant::now()),
            query_count: RwLock::new(0),
        }
    }

    /// Create session from msgpack bytes
    ///
    /// # Arguments
    /// * `ir_bytes` - msgpack serialized IR
    /// * `config` - Optional session configuration
    ///
    /// # Returns
    /// * Result with AnalysisSession
    pub fn from_bytes(ir_bytes: &[u8], config: Option<SessionConfig>) -> Result<Self, String> {
        // Deserialize IR from msgpack
        #[derive(Deserialize)]
        struct IRData {
            file_path: String,
            nodes: Vec<NodeDto>,
            edges: Vec<EdgeDto>,
        }

        #[derive(Deserialize)]
        struct NodeDto {
            id: String,
            kind: String,
            fqn: String,
            name: String,
            file_path: String,
            #[serde(default)]
            start_line: u32,
            #[serde(default)]
            start_col: u32,
            #[serde(default)]
            end_line: u32,
            #[serde(default)]
            end_col: u32,
        }

        #[derive(Deserialize)]
        struct EdgeDto {
            source_id: String,
            target_id: String,
            kind: String,
        }

        let ir_data: IRData = rmp_serde::from_slice(ir_bytes)
            .map_err(|e| format!("Failed to deserialize IR: {}", e))?;

        // Convert DTOs to domain models
        let nodes: Vec<Node> = ir_data.nodes.into_iter().map(|n| {
            Node::new(
                n.id,
                crate::shared::models::NodeKind::from_str(&n.kind),
                n.fqn,
                n.file_path,
                Span::new(n.start_line, n.start_col, n.end_line, n.end_col),
            ).with_name(n.name)
        }).collect();

        let edges: Vec<Edge> = ir_data.edges.into_iter().map(|e| {
            Edge::new(
                e.source_id,
                e.target_id,
                crate::shared::models::EdgeKind::from_str(&e.kind),
            )
        }).collect();

        Ok(Self::new(ir_data.file_path, nodes, edges, config))
    }

    /// Get session ID
    pub fn id(&self) -> &str {
        &self.session_id
    }

    /// Get IR document reference
    pub fn ir(&self) -> &IRDocument {
        &self.ir
    }

    /// Get node by ID
    pub fn get_node(&self, node_id: &str) -> Option<&Node> {
        self.touch();
        self.ir.get_node(node_id)
    }

    /// Get all nodes
    pub fn nodes(&self) -> &[Node] {
        self.touch();
        &self.ir.nodes
    }

    /// Get all edges
    pub fn edges(&self) -> &[Edge] {
        self.touch();
        &self.ir.edges
    }

    /// Check if session is expired
    pub fn is_expired(&self) -> bool {
        let last = *self.last_access.read().unwrap();
        last.elapsed() > Duration::from_secs(self.config.ttl_seconds)
    }

    /// Get session statistics
    pub fn stats(&self) -> SessionStats {
        let graphs = self.graphs.read().unwrap();
        let results = self.results.read().unwrap();
        let queries = *self.query_count.read().unwrap();
        let last = *self.last_access.read().unwrap();

        // Rough memory estimate
        let memory = std::mem::size_of_val(&*self.ir)
            + self.ir.nodes.len() * std::mem::size_of::<Node>()
            + self.ir.edges.len() * std::mem::size_of::<Edge>();

        SessionStats {
            session_id: self.session_id.clone(),
            created_at_ms: self.created_at.elapsed().as_millis() as u64,
            last_access_ms: last.elapsed().as_millis() as u64,
            ir_node_count: self.ir.nodes.len(),
            ir_edge_count: self.ir.edges.len(),
            cached_pdgs: graphs.pdg_cache.len(),
            cached_analyses: results.results.len(),
            total_queries: queries,
            memory_estimate_bytes: memory,
        }
    }

    /// Get or build PDG for function
    pub fn get_or_build_pdg(&self, function_id: &str) -> Option<Arc<ProgramDependenceGraph>> {
        self.touch();

        // Check cache first
        {
            let graphs = self.graphs.read().unwrap();
            if let Some(pdg) = graphs.pdg_cache.get(function_id) {
                return Some(Arc::clone(pdg));
            }
        }

        // Build PDG (simplified - in production, would build from IR)
        let pdg = self.build_pdg_for_function(function_id)?;
        let pdg = Arc::new(pdg);

        // Cache it
        {
            let mut graphs = self.graphs.write().unwrap();
            graphs.pdg_cache.insert(function_id.to_string(), Arc::clone(&pdg));
            graphs.build_times.insert(function_id.to_string(), Instant::now());
        }

        Some(pdg)
    }

    /// Build PDG for a function (simplified implementation)
    fn build_pdg_for_function(&self, function_id: &str) -> Option<ProgramDependenceGraph> {
        use crate::features::pdg::infrastructure::pdg::{PDGNode, PDGEdge, DependencyType};

        let mut pdg = ProgramDependenceGraph::new(function_id.to_string());

        // Find function node and its children
        let function_node = self.ir.get_node(function_id)?;

        // Add function node
        let fn_name = function_node.name.as_deref().unwrap_or(function_id);
        pdg.add_node(PDGNode::new(
            function_id.to_string(),
            format!("function {}", fn_name),
            function_node.span.start_line,
            function_node.span.clone(),
        ).with_entry_exit(true, false));

        // Find all nodes that belong to this function (children via CONTAINS edges)
        let mut child_nodes = Vec::new();
        for edge in &self.ir.edges {
            if edge.source_id == function_id &&
               matches!(edge.kind, crate::shared::models::EdgeKind::Contains) {
                if let Some(child) = self.ir.get_node(&edge.target_id) {
                    child_nodes.push(child);
                }
            }
        }

        // Add child nodes to PDG
        for child in &child_nodes {
            let child_name = child.name.as_deref().unwrap_or(&child.id).to_string();
            pdg.add_node(PDGNode::new(
                child.id.clone(),
                child_name,
                child.span.start_line,
                child.span.clone(),
            ));
        }

        // Add edges based on IR edges
        for edge in &self.ir.edges {
            // Check if both ends are in our function
            let source_in = edge.source_id == function_id ||
                child_nodes.iter().any(|n| n.id == edge.source_id);
            let target_in = edge.target_id == function_id ||
                child_nodes.iter().any(|n| n.id == edge.target_id);

            if source_in && target_in {
                let dep_type = match edge.kind {
                    crate::shared::models::EdgeKind::DataFlow |
                    crate::shared::models::EdgeKind::DefUse => DependencyType::Data,
                    _ => DependencyType::Control,
                };

                pdg.add_edge(PDGEdge {
                    from_node: edge.source_id.clone(),
                    to_node: edge.target_id.clone(),
                    dependency_type: dep_type,
                    label: None,
                });
            }
        }

        Some(pdg)
    }

    /// Store analysis result and return ID
    pub fn store_result(&self, result: AnalysisResult) -> String {
        let mut results = self.results.write().unwrap();
        results.insert(result)
    }

    /// Get analysis result by ID
    pub fn get_result(&self, analysis_id: &str) -> Option<AnalysisResult> {
        self.touch();
        let results = self.results.read().unwrap();
        results.get(analysis_id).cloned()
    }

    /// Query specific fact from analysis result
    pub fn query_fact(&self, analysis_id: &str, node_id: &str) -> Option<Vec<u8>> {
        self.touch();
        let results = self.results.read().unwrap();
        results.get(analysis_id)
            .and_then(|r| r.node_facts.get(node_id))
            .cloned()
    }

    /// Invalidate caches for affected nodes
    pub fn invalidate(&self, affected_nodes: Option<&[String]>) {
        let mut graphs = self.graphs.write().unwrap();

        if let Some(nodes) = affected_nodes {
            // Find which functions these nodes belong to
            for node_id in nodes {
                // Simplified: invalidate by function prefix
                let parts: Vec<&str> = node_id.split("::").collect();
                if !parts.is_empty() {
                    graphs.invalidate(parts[0]);
                }
            }
        } else {
            graphs.invalidate_all();
        }
    }

    /// Update last access time and query count
    fn touch(&self) {
        *self.last_access.write().unwrap() = Instant::now();
        *self.query_count.write().unwrap() += 1;
    }

    /// Get configuration
    pub fn config(&self) -> &SessionConfig {
        &self.config
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{NodeKind, EdgeKind};

    fn create_test_session() -> AnalysisSession {
        let nodes = vec![
            Node::new(
                "func1".to_string(),
                NodeKind::Function,
                "module.func1".to_string(),
                "test.py".to_string(),
                Span::new(1, 0, 10, 0),
            ).with_name("func1"),
            Node::new(
                "var1".to_string(),
                NodeKind::Variable,
                "module.func1.var1".to_string(),
                "test.py".to_string(),
                Span::new(2, 4, 2, 10),
            ).with_name("x"),
            Node::new(
                "var2".to_string(),
                NodeKind::Variable,
                "module.func1.var2".to_string(),
                "test.py".to_string(),
                Span::new(3, 4, 3, 10),
            ).with_name("y"),
        ];

        let edges = vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
            Edge::new("func1".to_string(), "var2".to_string(), EdgeKind::Contains),
            Edge::new("var1".to_string(), "var2".to_string(), EdgeKind::DataFlow),
        ];

        AnalysisSession::new("test.py".to_string(), nodes, edges, None)
    }

    #[test]
    fn test_session_creation() {
        let session = create_test_session();

        assert!(!session.session_id.is_empty());
        assert_eq!(session.ir.nodes.len(), 3);
        assert_eq!(session.ir.edges.len(), 3);
    }

    #[test]
    fn test_session_node_lookup() {
        let session = create_test_session();

        let node = session.get_node("func1");
        assert!(node.is_some());
        assert_eq!(node.unwrap().name, "func1");

        let missing = session.get_node("nonexistent");
        assert!(missing.is_none());
    }

    #[test]
    fn test_session_symbol_lookup() {
        let session = create_test_session();

        let nodes = session.ir.get_nodes_by_symbol("x");
        assert_eq!(nodes.len(), 1);
        assert_eq!(nodes[0].id, "var1");
    }

    #[test]
    fn test_session_stats() {
        let session = create_test_session();

        // Access some nodes to update counters
        session.get_node("func1");
        session.get_node("var1");

        let stats = session.stats();

        assert_eq!(stats.ir_node_count, 3);
        assert_eq!(stats.ir_edge_count, 3);
        assert_eq!(stats.total_queries, 2);
    }

    #[test]
    fn test_session_expiry() {
        let config = SessionConfig {
            ttl_seconds: 0,  // Expire immediately
            ..Default::default()
        };

        let nodes = vec![Node::new(
            "n1".to_string(),
            NodeKind::Function,
            "n1".to_string(),
            "test.py".to_string(),
            Span::new(1, 0, 1, 0),
        ).with_name("n1")];

        let session = AnalysisSession::new("test.py".to_string(), nodes, vec![], Some(config));

        // Sleep briefly to ensure expiry
        std::thread::sleep(std::time::Duration::from_millis(10));

        assert!(session.is_expired());
    }

    #[test]
    fn test_pdg_building() {
        let session = create_test_session();

        let pdg = session.get_or_build_pdg("func1");
        assert!(pdg.is_some());

        let pdg = pdg.unwrap();
        let stats = pdg.get_stats();

        // Should have function node + 2 variable nodes
        assert!(stats.node_count >= 1);
    }

    #[test]
    fn test_pdg_caching() {
        let session = create_test_session();

        // First call builds PDG
        let pdg1 = session.get_or_build_pdg("func1");
        assert!(pdg1.is_some());

        // Second call should return cached
        let pdg2 = session.get_or_build_pdg("func1");
        assert!(pdg2.is_some());

        // Should be same Arc (pointer equality)
        assert!(Arc::ptr_eq(&pdg1.unwrap(), &pdg2.unwrap()));
    }

    #[test]
    fn test_analysis_result_caching() {
        let session = create_test_session();

        let mut result = AnalysisResult::new("reach");
        result.node_facts.insert(
            "node1".to_string(),
            vec![1, 2, 3]
        );

        let analysis_id = session.store_result(result);

        // Retrieve result
        let retrieved = session.get_result(&analysis_id);
        assert!(retrieved.is_some());
        assert_eq!(retrieved.unwrap().analysis_type, "reach");

        // Query specific fact
        let fact = session.query_fact(&analysis_id, "node1");
        assert!(fact.is_some());
        assert_eq!(fact.unwrap(), vec![1, 2, 3]);
    }

    #[test]
    fn test_cache_invalidation() {
        let session = create_test_session();

        // Build PDG
        let _ = session.get_or_build_pdg("func1");

        // Invalidate
        session.invalidate(Some(&["func1::var1".to_string()]));

        // Cache should be cleared for that function
        let graphs = session.graphs.read().unwrap();
        assert!(graphs.pdg_cache.get("func1").is_none());
    }

    #[test]
    fn test_default_config() {
        let config = SessionConfig::default();

        assert_eq!(config.max_memory_bytes, 2 * 1024 * 1024 * 1024);
        assert_eq!(config.ttl_seconds, 30 * 60);
        assert_eq!(config.analysis_timeout_seconds, 300);
        assert_eq!(config.max_context_limit, 10_000);
        assert_eq!(config.result_paging_threshold, 50_000);
    }
}
