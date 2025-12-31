//! L3: Flow Graph Extraction and Type Resolution
//!
//! Extracted from processor_legacy.rs (lines 1235-1335)
//!
//! This stage handles:
//! - Grouping BFG blocks by containing function
//! - Creating per-function BasicFlowGraph structures
//!
//! # Functions
//! - `extract_bfg_graphs_with_nodes()` - Group blocks by function using IR (96 LOC)
//! - `extract_bfg_graphs()` - Fallback without IR nodes (5 LOC)

use crate::features::flow_graph::infrastructure::bfg::{BasicFlowGraph, BfgVisitor};
use crate::features::ir_generation::infrastructure::ir_builder::IRBuilder;
use crate::shared::models::{Node, NodeKind};
use std::collections::HashMap;

/// Extract BFG graphs from visitor (grouped by function using IR nodes)
///
/// Groups blocks by their containing function based on span analysis.
/// Each function gets its own BasicFlowGraph with entry/exit blocks.
///
/// # Algorithm
/// 1. Find all function nodes in IR
/// 2. For each block, find containing function by span comparison
/// 3. Group blocks by function name
/// 4. Create BasicFlowGraph for each function
///
/// # Special Cases
/// - If no functions found: all blocks grouped under "main"
/// - If no IR nodes: fallback to single "main" function
///
/// # Arguments
/// * `visitor` - BFG visitor with accumulated blocks
/// * `_builder` - IR builder (unused, kept for API compatibility)
/// * `nodes` - IR nodes (used to find function boundaries)
///
/// # Returns
/// Vector of BasicFlowGraph, one per function
#[allow(dead_code)]
pub fn extract_bfg_graphs_with_nodes(
    visitor: &BfgVisitor,
    _builder: &IRBuilder,
    nodes: &[Node],
) -> Vec<BasicFlowGraph> {
    let blocks = visitor.get_blocks();

    if blocks.is_empty() {
        return Vec::new();
    }

    // Find all function nodes
    let function_nodes: Vec<_> = nodes
        .iter()
        .filter(|n| matches!(n.kind, NodeKind::Function | NodeKind::Method))
        .collect();

    if function_nodes.is_empty() {
        // No functions found - group all blocks under "main"
        let entry_id = blocks.first().map(|b| b.id.clone()).unwrap_or_default();
        let exit_id = blocks.last().map(|b| b.id.clone()).unwrap_or_default();

        return vec![BasicFlowGraph {
            id: "bfg:main".to_string(),
            function_id: "main".to_string(),
            entry_block_id: entry_id,
            exit_block_id: exit_id,
            blocks: blocks.to_vec(),
            total_statements: blocks.iter().map(|b| b.statement_count).sum(),
        }];
    }

    // Group blocks by function based on span containment
    let mut function_blocks: HashMap<String, Vec<crate::shared::models::span_ref::BlockRef>> =
        HashMap::new();

    for block in blocks {
        // Find which function contains this block (by span)
        let containing_func = function_nodes.iter().find(|func| {
            let func_span = &func.span;
            let block_span = &block.span_ref.span;

            // Check if block span is within function span
            (block_span.start_line > func_span.start_line
                || (block_span.start_line == func_span.start_line
                    && block_span.start_col >= func_span.start_col))
                && (block_span.end_line < func_span.end_line
                    || (block_span.end_line == func_span.end_line
                        && block_span.end_col <= func_span.end_col))
        });

        let func_name = containing_func
            .and_then(|f| f.name.as_ref())
            .cloned()
            .unwrap_or_else(|| "main".to_string());

        function_blocks
            .entry(func_name)
            .or_insert_with(Vec::new)
            .push(block.clone());
    }

    // Create one BFG per function
    let mut graphs = Vec::new();

    for (func_name, func_blocks) in function_blocks {
        if func_blocks.is_empty() {
            continue;
        }

        // Find entry and exit blocks
        // SAFETY: func_blocks is guaranteed to be non-empty by the check above
        let entry_id = func_blocks
            .iter()
            .find(|b| b.kind == "ENTRY" || b.id.contains(":entry"))
            .map(|b| b.id.clone())
            .unwrap_or_else(|| func_blocks.first().unwrap().id.clone());

        // SAFETY: func_blocks is guaranteed to be non-empty by the check above
        let exit_id = func_blocks
            .iter()
            .find(|b| b.kind == "EXIT" || b.id.contains(":exit"))
            .map(|b| b.id.clone())
            .unwrap_or_else(|| func_blocks.last().unwrap().id.clone());

        let graph = BasicFlowGraph {
            id: format!("bfg:{}", func_name),
            function_id: func_name,
            entry_block_id: entry_id,
            exit_block_id: exit_id,
            blocks: func_blocks.clone(),
            total_statements: func_blocks.iter().map(|b| b.statement_count).sum(),
        };

        graphs.push(graph);
    }

    graphs
}

/// Extract BFG graphs from visitor (fallback without nodes)
///
/// Simple wrapper that calls extract_bfg_graphs_with_nodes with empty nodes array.
/// All blocks will be grouped under "main" function.
///
/// # Arguments
/// * `visitor` - BFG visitor with accumulated blocks
/// * `_builder` - IR builder (unused)
///
/// # Returns
/// Vector with single BasicFlowGraph for "main"
#[allow(dead_code)]
pub fn extract_bfg_graphs(visitor: &BfgVisitor, _builder: &IRBuilder) -> Vec<BasicFlowGraph> {
    extract_bfg_graphs_with_nodes(visitor, _builder, &[])
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::parsing::plugins::PythonPlugin;
    use crate::shared::models::Span;

    #[test]
    fn test_extract_bfg_graphs_no_functions() {
        let plugin = PythonPlugin::new();
        let visitor = BfgVisitor::new(&plugin);
        let builder = IRBuilder::new(
            "test_repo".to_string(),
            "test.py".to_string(),
            "python".to_string(),
            "test".to_string(),
        );

        let graphs = extract_bfg_graphs(&visitor, &builder);

        // No blocks → empty result
        assert_eq!(graphs.len(), 0);
    }

    #[test]
    fn test_extract_bfg_graphs_with_nodes_empty() {
        let plugin = PythonPlugin::new();
        let visitor = BfgVisitor::new(&plugin);
        let builder = IRBuilder::new(
            "test_repo".to_string(),
            "test.py".to_string(),
            "python".to_string(),
            "test".to_string(),
        );
        let nodes = vec![];

        let graphs = extract_bfg_graphs_with_nodes(&visitor, &builder, &nodes);

        assert_eq!(graphs.len(), 0);
    }

    #[test]
    fn test_extract_bfg_graphs_with_function_nodes() {
        let plugin = PythonPlugin::new();
        let visitor = BfgVisitor::new(&plugin);

        // We can't add blocks directly to visitor in tests easily,
        // so this test is more of a smoke test
        let builder = IRBuilder::new(
            "test_repo".to_string(),
            "test.py".to_string(),
            "python".to_string(),
            "test".to_string(),
        );

        let func_node = Node::new(
            "func:test".to_string(),
            NodeKind::Function,
            "test".to_string(),    // fqn
            "test.py".to_string(), // file_path
            Span::new(1, 0, 5, 0),
        );

        let graphs = extract_bfg_graphs_with_nodes(&visitor, &builder, &[func_node]);

        // No blocks in visitor → empty
        assert_eq!(graphs.len(), 0);
    }
}
