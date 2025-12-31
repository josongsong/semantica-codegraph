/*
 * CFG (Control Flow Graph) Module
 *
 * Generates control flow edges between basic blocks.
 *
 * PRODUCTION REQUIREMENTS:
 * - Accurate successor calculation
 * - All edge types (conditional, unconditional, loop, exception)
 * - No missing edges
 * - Type safe
 */

use crate::shared::models::span_ref::BlockRef;
use serde::{Deserialize, Serialize};

/// CFG Edge
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CFGEdge {
    pub source_block_id: String,
    pub target_block_id: String,
    pub edge_type: CFGEdgeType,
}

/// CFG Edge Type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CFGEdgeType {
    Unconditional, // Sequential flow
    True,          // If true branch
    False,         // If false branch
    LoopBack,      // Loop back to header
    LoopExit,      // Exit loop
    Exception,     // Exception handler
}

impl CFGEdgeType {
    pub fn as_str(&self) -> &'static str {
        match self {
            CFGEdgeType::Unconditional => "UNCONDITIONAL",
            CFGEdgeType::True => "TRUE",
            CFGEdgeType::False => "FALSE",
            CFGEdgeType::LoopBack => "LOOP_BACK",
            CFGEdgeType::LoopExit => "LOOP_EXIT",
            CFGEdgeType::Exception => "EXCEPTION",
        }
    }
}

/// Build CFG edges from blocks
///
/// Algorithm:
/// - Sequential blocks: unconditional edge
/// - Branch: true/false edges
/// - Loop: back-edge + exit edge
/// - Return: edge to exit
///
/// # Arguments
/// * `blocks` - Basic blocks
///
/// # Returns
/// * Vec of CFG edges
pub fn build_cfg_edges(blocks: &[BlockRef]) -> Vec<CFGEdge> {
    let mut edges = Vec::new();

    if blocks.len() < 2 {
        return edges;
    }

    for i in 0..blocks.len() - 1 {
        let current = &blocks[i];
        let next = &blocks[i + 1];

        match current.kind.as_str() {
            // BFG uses mixed-case names: Entry, Exit, Statement, etc.
            "ENTRY" | "Entry" => {
                // Entry → first body block
                edges.push(CFGEdge {
                    source_block_id: current.id.clone(),
                    target_block_id: next.id.clone(),
                    edge_type: CFGEdgeType::Unconditional,
                });
            }

            "STATEMENT" | "Statement" => {
                // Statement → next block
                edges.push(CFGEdge {
                    source_block_id: current.id.clone(),
                    target_block_id: next.id.clone(),
                    edge_type: CFGEdgeType::Unconditional,
                });
            }

            "BRANCH" | "Condition" => {
                // Branch/Condition → true (next) + false (skip next)
                edges.push(CFGEdge {
                    source_block_id: current.id.clone(),
                    target_block_id: next.id.clone(),
                    edge_type: CFGEdgeType::True,
                });

                // False branch (skip to block after next, or exit)
                if i + 2 < blocks.len() {
                    edges.push(CFGEdge {
                        source_block_id: current.id.clone(),
                        target_block_id: blocks[i + 2].id.clone(),
                        edge_type: CFGEdgeType::False,
                    });
                }
            }

            "LOOP" | "LoopHeader" => {
                // Loop header → body (next block)
                edges.push(CFGEdge {
                    source_block_id: current.id.clone(),
                    target_block_id: next.id.clone(),
                    edge_type: CFGEdgeType::Unconditional,
                });

                // Add back-edge from last body block to loop header
                // Find the block that should jump back (usually the last statement before next loop/condition/exit)
                if let Some(loop_body_end) = find_loop_body_end(blocks, i) {
                    edges.push(CFGEdge {
                        source_block_id: loop_body_end.id.clone(),
                        target_block_id: current.id.clone(),
                        edge_type: CFGEdgeType::LoopBack,
                    });
                }
            }

            "LOOP_CONTINUE" => {
                // Continue → find loop header (backward)
                if let Some(loop_block) = find_loop_header(blocks, i) {
                    edges.push(CFGEdge {
                        source_block_id: current.id.clone(),
                        target_block_id: loop_block.id.clone(),
                        edge_type: CFGEdgeType::LoopBack,
                    });
                }
            }

            "LOOP_EXIT" => {
                // Break → find loop exit (forward)
                if let Some(exit_block) = find_loop_exit(blocks, i) {
                    edges.push(CFGEdge {
                        source_block_id: current.id.clone(),
                        target_block_id: exit_block.id.clone(),
                        edge_type: CFGEdgeType::LoopExit,
                    });
                }
            }

            "RETURN" | "RAISE" => {
                // Return/Raise → exit block
                let exit_block = blocks.last().unwrap();
                edges.push(CFGEdge {
                    source_block_id: current.id.clone(),
                    target_block_id: exit_block.id.clone(),
                    edge_type: CFGEdgeType::Unconditional,
                });
            }

            "YIELD" | "Yield" => {
                // Yield → next (generator continues)
                edges.push(CFGEdge {
                    source_block_id: current.id.clone(),
                    target_block_id: next.id.clone(),
                    edge_type: CFGEdgeType::Unconditional,
                });
            }

            _ => {}
        }
    }

    edges
}

/// Find the last block in a loop body (for creating back-edge)
fn find_loop_body_end(blocks: &[BlockRef], loop_idx: usize) -> Option<&BlockRef> {
    // Find the last statement block before the next loop/condition/exit
    for i in (loop_idx + 1)..blocks.len() {
        let kind = blocks[i].kind.as_str();
        // If we hit another control flow structure or exit, the previous block was the loop body end
        if matches!(
            kind,
            "LoopHeader" | "Condition" | "Exit" | "LOOP" | "BRANCH"
        ) {
            if i > loop_idx + 1 {
                return Some(&blocks[i - 1]);
            }
            break;
        }
    }
    // If no control flow found, use the last statement block in the function
    if blocks.len() > loop_idx + 1 {
        // Find the last Statement block before Exit
        for i in (loop_idx + 1..blocks.len()).rev() {
            if blocks[i].kind == "Statement" {
                return Some(&blocks[i]);
            }
        }
    }
    None
}

/// Find loop header (backward search)
fn find_loop_header(blocks: &[BlockRef], current_idx: usize) -> Option<&BlockRef> {
    for i in (0..current_idx).rev() {
        let kind = blocks[i].kind.as_str();
        if kind == "LOOP" || kind == "LoopHeader" {
            return Some(&blocks[i]);
        }
    }
    None
}

/// Find loop exit (forward search)
fn find_loop_exit(blocks: &[BlockRef], current_idx: usize) -> Option<&BlockRef> {
    // Find next block after loop
    for i in (current_idx + 1)..blocks.len() {
        let kind = blocks[i].kind.as_str();
        if kind != "LOOP" && kind != "LOOP_CONTINUE" && kind != "LoopHeader" {
            return Some(&blocks[i]);
        }
    }

    // Default: exit block
    blocks.last()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::Span;

    fn make_block(id: &str, kind: &str) -> BlockRef {
        BlockRef::new(id.to_string(), kind.to_string(), Span::new(1, 0, 1, 0), 1)
    }

    #[test]
    fn test_sequential_blocks() {
        let blocks = vec![
            make_block("entry", "ENTRY"),
            make_block("stmt1", "STATEMENT"),
            make_block("stmt2", "STATEMENT"),
            make_block("exit", "EXIT"),
        ];

        let edges = build_cfg_edges(&blocks);

        // Should have 3 edges (entry→stmt1, stmt1→stmt2, stmt2→exit)
        assert_eq!(edges.len(), 3);
        assert_eq!(edges[0].edge_type, CFGEdgeType::Unconditional);
    }

    #[test]
    fn test_branch_edges() {
        let blocks = vec![
            make_block("entry", "ENTRY"),
            make_block("branch", "BRANCH"),
            make_block("then", "STATEMENT"),
            make_block("else", "STATEMENT"),
            make_block("exit", "EXIT"),
        ];

        let edges = build_cfg_edges(&blocks);

        // Branch should have 2 outgoing edges (true, false)
        let branch_edges: Vec<_> = edges
            .iter()
            .filter(|e| e.source_block_id == "branch")
            .collect();

        assert_eq!(branch_edges.len(), 2);
    }

    #[test]
    fn test_loop_back_edge() {
        let blocks = vec![
            make_block("entry", "ENTRY"),
            make_block("loop", "LOOP"),
            make_block("body", "STATEMENT"),
            make_block("continue", "LOOP_CONTINUE"),
            make_block("exit", "EXIT"),
        ];

        let edges = build_cfg_edges(&blocks);

        // Continue should have back-edge to loop
        let continue_edges: Vec<_> = edges
            .iter()
            .filter(|e| e.source_block_id == "continue")
            .collect();

        assert!(continue_edges.len() > 0);
        assert_eq!(continue_edges[0].edge_type, CFGEdgeType::LoopBack);
    }
}
