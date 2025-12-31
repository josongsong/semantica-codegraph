//! Pipeline Execution Context
//!
//! Mutable context passed to stage executors for reading/writing data.

use crate::shared::models::{Node, Edge, Occurrence, CodegraphError};
use crate::pipeline::dag::StageId;
use super::super::memory::{GraphContext, GraphContextBuilder, ChunkData, SymbolData};
use std::sync::Arc;
use std::collections::HashMap;
use std::path::PathBuf;

/// Pipeline execution context
///
/// This is passed to each stage executor and provides:
/// - Read access to previous stage results (Arc references)
/// - Write access to store this stage's results
/// - Repository metadata
pub struct PipelineContext {
    /// Repository root path
    pub repo_root: PathBuf,

    /// Repository name
    pub repo_name: String,

    /// All nodes (L1 output, Arc-wrapped)
    nodes: Option<Arc<Vec<Node>>>,

    /// All edges (L1 output, Arc-wrapped)
    edges: Option<Arc<Vec<Edge>>>,

    /// All occurrences (L1 output, Arc-wrapped)
    occurrences: Option<Arc<Vec<Occurrence>>>,

    /// Chunks (L2 output, Arc-wrapped)
    chunks: Option<Arc<Vec<ChunkData>>>,

    /// Symbols (L5 output, Arc-wrapped)
    symbols: Option<Arc<Vec<SymbolData>>>,

    /// Stage-specific data (Arc-wrapped, type-erased)
    stage_data: HashMap<String, Arc<dyn std::any::Any + Send + Sync>>,

    /// Completed stages (for dependency checking)
    completed_stages: Vec<StageId>,
}

impl PipelineContext {
    /// Create new context
    pub fn new(repo_root: PathBuf, repo_name: String) -> Self {
        Self {
            repo_root,
            repo_name,
            nodes: None,
            edges: None,
            occurrences: None,
            chunks: None,
            symbols: None,
            stage_data: HashMap::new(),
            completed_stages: Vec::new(),
        }
    }

    // ========================================================================
    // Read Methods (Arc references, zero-copy)
    // ========================================================================

    /// Get nodes (L1 output)
    pub fn get_nodes(&self) -> Result<Arc<Vec<Node>>, CodegraphError> {
        self.nodes.clone().ok_or_else(|| {
            CodegraphError::internal("Nodes not available (L1 not completed?)")
        })
    }

    /// Get edges (L1 output)
    pub fn get_edges(&self) -> Result<Arc<Vec<Edge>>, CodegraphError> {
        self.edges.clone().ok_or_else(|| {
            CodegraphError::internal("Edges not available (L1 not completed?)")
        })
    }

    /// Get occurrences (L1 output)
    pub fn get_occurrences(&self) -> Result<Arc<Vec<Occurrence>>, CodegraphError> {
        self.occurrences.clone().ok_or_else(|| {
            CodegraphError::internal("Occurrences not available (L1 not completed?)")
        })
    }

    /// Get chunks (L2 output)
    pub fn get_chunks(&self) -> Result<Arc<Vec<ChunkData>>, CodegraphError> {
        self.chunks.clone().ok_or_else(|| {
            CodegraphError::internal("Chunks not available (L2 not completed?)")
        })
    }

    /// Get symbols (L5 output)
    pub fn get_symbols(&self) -> Result<Arc<Vec<SymbolData>>, CodegraphError> {
        self.symbols.clone().ok_or_else(|| {
            CodegraphError::internal("Symbols not available (L5 not completed?)")
        })
    }

    /// Get stage-specific data (type-safe)
    pub fn get_stage_data<T: 'static + Send + Sync>(&self, key: &str) -> Option<Arc<T>> {
        self.stage_data.get(key)?
            .clone()
            .downcast::<T>()
            .ok()
    }

    // ========================================================================
    // Write Methods (store Arc-wrapped data)
    // ========================================================================

    /// Set nodes (L1)
    pub fn set_nodes(&mut self, nodes: Vec<Node>) {
        self.nodes = Some(Arc::new(nodes));
    }

    /// Set edges (L1)
    pub fn set_edges(&mut self, edges: Vec<Edge>) {
        self.edges = Some(Arc::new(edges));
    }

    /// Set occurrences (L1)
    pub fn set_occurrences(&mut self, occurrences: Vec<Occurrence>) {
        self.occurrences = Some(Arc::new(occurrences));
    }

    /// Set chunks (L2)
    pub fn set_chunks(&mut self, chunks: Vec<ChunkData>) {
        self.chunks = Some(Arc::new(chunks));
    }

    /// Set symbols (L5)
    pub fn set_symbols(&mut self, symbols: Vec<SymbolData>) {
        self.symbols = Some(Arc::new(symbols));
    }

    /// Set stage-specific data (Arc-wrapped)
    pub fn set_stage_data<T: 'static + Send + Sync>(&mut self, key: String, data: T) {
        self.stage_data.insert(key, Arc::new(data));
    }

    // ========================================================================
    // Dependency Checking
    // ========================================================================

    /// Mark stage as completed
    pub fn mark_completed(&mut self, stage_id: StageId) {
        if !self.completed_stages.contains(&stage_id) {
            self.completed_stages.push(stage_id);
        }
    }

    /// Check if stage is completed
    pub fn is_completed(&self, stage_id: StageId) -> bool {
        self.completed_stages.contains(&stage_id)
    }

    /// Check if all dependencies are satisfied
    pub fn dependencies_satisfied(&self, dependencies: &[StageId]) -> bool {
        dependencies.iter().all(|dep| self.is_completed(*dep))
    }

    // ========================================================================
    // Conversion
    // ========================================================================

    /// Build final GraphContext from this context
    pub fn build_graph_context(&self) -> GraphContext {
        let mut builder = GraphContextBuilder::new(
            self.repo_name.clone(),
            self.repo_root.to_string_lossy().to_string(),
        );

        if let Some(ref nodes) = self.nodes {
            builder = builder.with_nodes((**nodes).clone());
        }

        if let Some(ref edges) = self.edges {
            builder = builder.with_edges((**edges).clone());
        }

        if let Some(ref occurrences) = self.occurrences {
            builder = builder.with_occurrences((**occurrences).clone());
        }

        if let Some(ref chunks) = self.chunks {
            builder = builder.with_chunks((**chunks).clone());
        }

        if let Some(ref symbols) = self.symbols {
            builder = builder.with_symbols((**symbols).clone());
        }

        // Copy stage data
        for (key, value) in &self.stage_data {
            // Note: We can't easily clone Arc<dyn Any>, so we'll need to handle this differently
            // For now, stage_data is only in the context, not the final GraphContext
        }

        builder.build()
    }

    /// Alias for build_graph_context()
    pub fn to_graph_context(&self) -> GraphContext {
        self.build_graph_context()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{Node, NodeKind, Span};

    #[test]
    fn test_pipeline_context_basic() {
        let mut ctx = PipelineContext::new(
            PathBuf::from("/test"),
            "test-repo".to_string(),
        );

        // Set nodes
        let nodes = vec![
            Node {
                id: "node1".to_string(),
                kind: NodeKind::Function,
                fqn: "test.func".to_string(),
                file_path: "test.py".to_string(),
                language: "python".to_string(),
                span: Span { start_line: 1, end_line: 10, start_col: 0, end_col: 0 },
                name: Some("func".to_string()),
                ..Default::default()
            },
        ];

        ctx.set_nodes(nodes);

        // Get nodes (Arc reference)
        let nodes_ref = ctx.get_nodes().unwrap();
        assert_eq!(nodes_ref.len(), 1);
        assert_eq!(nodes_ref[0].id, "node1");

        // Arc allows multiple references
        let nodes_ref2 = ctx.get_nodes().unwrap();
        assert_eq!(Arc::strong_count(&nodes_ref), 3); // ctx.nodes + nodes_ref + nodes_ref2
    }

    #[test]
    fn test_dependency_checking() {
        let mut ctx = PipelineContext::new(
            PathBuf::from("/test"),
            "test-repo".to_string(),
        );

        // Initially nothing completed
        assert!(!ctx.is_completed(StageId::L1IrBuild));

        // Mark L1 complete
        ctx.mark_completed(StageId::L1IrBuild);
        assert!(ctx.is_completed(StageId::L1IrBuild));

        // Check dependencies
        let l2_deps = vec![StageId::L1IrBuild];
        assert!(ctx.dependencies_satisfied(&l2_deps));

        let l3_deps = vec![StageId::L1IrBuild, StageId::L2Chunking];
        assert!(!ctx.dependencies_satisfied(&l3_deps)); // L2 not done
    }

    #[test]
    fn test_stage_data() {
        let mut ctx = PipelineContext::new(
            PathBuf::from("/test"),
            "test-repo".to_string(),
        );

        #[derive(Debug, Clone, PartialEq)]
        struct TestData {
            value: usize,
        }

        // Set typed data
        ctx.set_stage_data("test_key".to_string(), TestData { value: 42 });

        // Get typed data
        let data = ctx.get_stage_data::<TestData>("test_key").unwrap();
        assert_eq!(data.value, 42);

        // Wrong type returns None
        assert!(ctx.get_stage_data::<String>("test_key").is_none());
    }
}
