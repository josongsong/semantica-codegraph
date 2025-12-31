//! CFG Adapter for BraunSSABuilder
//!
//! Bridges BasicFlowGraph + CFGEdge to CFGProvider trait,
//! enabling SOTA Braun SSA construction with existing IR infrastructure.
//!
//! SOTA Integration: This adapter allows the advanced Braun (2013) algorithm
//! to work with our existing control flow graph representation.

use super::braun_ssa_builder::CFGProvider;
use crate::features::flow_graph::domain::{BasicFlowGraph, CFGEdge};
use std::collections::HashMap;

/// Adapter that implements CFGProvider using BasicFlowGraph and CFGEdges
///
/// This enables Braun's SSA algorithm to work with our existing BFG infrastructure.
pub struct BFGCFGAdapter {
    /// Function ID
    function_id: String,

    /// Entry block ID
    entry_block_id: String,

    /// Predecessor map: block_id -> list of predecessor block IDs
    predecessors: HashMap<String, Vec<String>>,
}

impl BFGCFGAdapter {
    /// Create a new adapter from BasicFlowGraph and CFGEdges
    ///
    /// # Arguments
    /// * `bfg` - The basic flow graph containing block information
    /// * `cfg_edges` - The control flow edges between blocks
    ///
    /// # Returns
    /// A CFGProvider implementation suitable for BraunSSABuilder
    pub fn new(bfg: &BasicFlowGraph, cfg_edges: &[CFGEdge]) -> Self {
        // Build predecessor map from CFG edges
        let mut predecessors: HashMap<String, Vec<String>> = HashMap::new();

        // Initialize all blocks with empty predecessor lists
        for block in &bfg.blocks {
            predecessors.entry(block.id.clone()).or_default();
        }

        // Build predecessor relationships from edges
        // Edge: source -> target means source is a predecessor of target
        for edge in cfg_edges {
            // Only include edges that belong to this function's blocks
            if predecessors.contains_key(&edge.target_block_id) {
                predecessors
                    .entry(edge.target_block_id.clone())
                    .or_default()
                    .push(edge.source_block_id.clone());
            }
        }

        Self {
            function_id: bfg.function_id.clone(),
            entry_block_id: bfg.entry_block_id.clone(),
            predecessors,
        }
    }

    /// Get the number of blocks
    pub fn block_count(&self) -> usize {
        self.predecessors.len()
    }
}

impl CFGProvider for BFGCFGAdapter {
    fn entry_block_id(&self) -> &str {
        &self.entry_block_id
    }

    fn is_entry_block(&self, block_id: &str) -> bool {
        block_id == self.entry_block_id
    }

    fn predecessors(&self, block_id: &str) -> Vec<String> {
        self.predecessors.get(block_id).cloned().unwrap_or_default()
    }

    fn function_id(&self) -> &str {
        &self.function_id
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::flow_graph::domain::{BasicFlowBlock, BlockKind, CFGEdgeKind};
    use crate::shared::models::Span;

    fn create_test_bfg() -> BasicFlowGraph {
        BasicFlowGraph {
            id: "bfg_1".to_string(),
            function_id: "test_func".to_string(),
            entry_block_id: "block_0".to_string(),
            exit_block_id: "block_2".to_string(),
            blocks: vec![
                BasicFlowBlock {
                    id: "block_0".to_string(),
                    kind: BlockKind::Entry,
                    function_node_id: "func_node".to_string(),
                    span: Span::new(1, 0, 1, 10),
                    statement_count: 1,
                },
                BasicFlowBlock {
                    id: "block_1".to_string(),
                    kind: BlockKind::Statement,
                    function_node_id: "func_node".to_string(),
                    span: Span::new(2, 0, 2, 10),
                    statement_count: 2,
                },
                BasicFlowBlock {
                    id: "block_2".to_string(),
                    kind: BlockKind::Exit,
                    function_node_id: "func_node".to_string(),
                    span: Span::new(3, 0, 3, 10),
                    statement_count: 1,
                },
            ],
            total_statements: 4,
        }
    }

    fn create_test_cfg_edges() -> Vec<CFGEdge> {
        vec![
            CFGEdge {
                source_block_id: "block_0".to_string(),
                target_block_id: "block_1".to_string(),
                kind: CFGEdgeKind::Sequential,
            },
            CFGEdge {
                source_block_id: "block_1".to_string(),
                target_block_id: "block_2".to_string(),
                kind: CFGEdgeKind::Sequential,
            },
        ]
    }

    #[test]
    fn test_adapter_creation() {
        let bfg = create_test_bfg();
        let edges = create_test_cfg_edges();
        let adapter = BFGCFGAdapter::new(&bfg, &edges);

        assert_eq!(adapter.function_id(), "test_func");
        assert_eq!(adapter.entry_block_id(), "block_0");
        assert_eq!(adapter.block_count(), 3);
    }

    #[test]
    fn test_predecessors() {
        let bfg = create_test_bfg();
        let edges = create_test_cfg_edges();
        let adapter = BFGCFGAdapter::new(&bfg, &edges);

        // Entry block has no predecessors
        assert!(adapter.predecessors("block_0").is_empty());

        // block_1 has block_0 as predecessor
        let preds_1 = adapter.predecessors("block_1");
        assert_eq!(preds_1.len(), 1);
        assert_eq!(preds_1[0], "block_0");

        // block_2 has block_1 as predecessor
        let preds_2 = adapter.predecessors("block_2");
        assert_eq!(preds_2.len(), 1);
        assert_eq!(preds_2[0], "block_1");
    }

    #[test]
    fn test_is_entry_block() {
        let bfg = create_test_bfg();
        let edges = create_test_cfg_edges();
        let adapter = BFGCFGAdapter::new(&bfg, &edges);

        assert!(adapter.is_entry_block("block_0"));
        assert!(!adapter.is_entry_block("block_1"));
        assert!(!adapter.is_entry_block("block_2"));
    }

    #[test]
    fn test_diamond_cfg() {
        // Test a diamond-shaped CFG (if-then-else merge)
        //       block_0 (entry)
        //        /    \
        //   block_1  block_2
        //        \    /
        //       block_3 (exit)

        let bfg = BasicFlowGraph {
            id: "bfg_diamond".to_string(),
            function_id: "diamond_func".to_string(),
            entry_block_id: "block_0".to_string(),
            exit_block_id: "block_3".to_string(),
            blocks: vec![
                BasicFlowBlock {
                    id: "block_0".to_string(),
                    kind: BlockKind::Condition,
                    function_node_id: "func".to_string(),
                    span: Span::new(1, 0, 1, 10),
                    statement_count: 1,
                },
                BasicFlowBlock {
                    id: "block_1".to_string(),
                    kind: BlockKind::Statement,
                    function_node_id: "func".to_string(),
                    span: Span::new(2, 0, 2, 10),
                    statement_count: 1,
                },
                BasicFlowBlock {
                    id: "block_2".to_string(),
                    kind: BlockKind::Statement,
                    function_node_id: "func".to_string(),
                    span: Span::new(3, 0, 3, 10),
                    statement_count: 1,
                },
                BasicFlowBlock {
                    id: "block_3".to_string(),
                    kind: BlockKind::Exit,
                    function_node_id: "func".to_string(),
                    span: Span::new(4, 0, 4, 10),
                    statement_count: 1,
                },
            ],
            total_statements: 4,
        };

        let edges = vec![
            CFGEdge {
                source_block_id: "block_0".to_string(),
                target_block_id: "block_1".to_string(),
                kind: CFGEdgeKind::TrueBranch,
            },
            CFGEdge {
                source_block_id: "block_0".to_string(),
                target_block_id: "block_2".to_string(),
                kind: CFGEdgeKind::FalseBranch,
            },
            CFGEdge {
                source_block_id: "block_1".to_string(),
                target_block_id: "block_3".to_string(),
                kind: CFGEdgeKind::Sequential,
            },
            CFGEdge {
                source_block_id: "block_2".to_string(),
                target_block_id: "block_3".to_string(),
                kind: CFGEdgeKind::Sequential,
            },
        ];

        let adapter = BFGCFGAdapter::new(&bfg, &edges);

        // block_3 should have TWO predecessors (block_1 and block_2)
        // This is the merge point where Braun's algorithm would insert a phi node
        let preds_3 = adapter.predecessors("block_3");
        assert_eq!(preds_3.len(), 2);
        assert!(preds_3.contains(&"block_1".to_string()));
        assert!(preds_3.contains(&"block_2".to_string()));
    }
}
