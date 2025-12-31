//! Shared utility functions for processor
//!
//! Extracted from processor.rs:
//! - node_to_span (lines 1350-1360)
//! - find_body_node (lines 1338-1347)
//! - find_containing_block (lines 884-923)

use crate::shared::models::span_ref::BlockRef;
use crate::shared::models::Span;
use tree_sitter::Node as TSNode;

/// Convert tree-sitter Node to Span
///
/// # Arguments
/// * `node` - tree-sitter AST node
///
/// # Returns
/// Span with line/column information (1-indexed lines, 0-indexed columns)
pub fn node_to_span(node: &TSNode) -> Span {
    let start_pos = node.start_position();
    let end_pos = node.end_position();

    Span::new(
        start_pos.row as u32 + 1,
        start_pos.column as u32,
        end_pos.row as u32 + 1,
        end_pos.column as u32,
    )
}

/// Find the body node (block) of a function/class/loop node
///
/// # Arguments
/// * `node` - Parent AST node (function_definition, class_definition, etc.)
///
/// # Returns
/// Optional child node with kind "block"
pub fn find_body_node<'a>(node: &'a TSNode) -> Option<TSNode<'a>> {
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "block" {
                return Some(child);
            }
        }
    }
    None
}

/// Find the smallest enclosing block for a variable span
///
/// Used for SSA construction to determine variable scope.
///
/// # Arguments
/// * `var_span` - The span of the variable to locate
/// * `blocks` - List of all blocks in the function
///
/// # Returns
/// Optional block ID of the smallest containing block
pub fn find_containing_block(var_span: &Span, blocks: &[BlockRef]) -> Option<String> {
    let mut best_block: Option<&BlockRef> = None;
    let mut best_size = usize::MAX;

    for block in blocks {
        let block_span = &block.span_ref.span;

        // Check if variable span is within block span
        if var_span.start_line >= block_span.start_line && var_span.end_line <= block_span.end_line
        {
            // Further check: if on same start line, check column
            if var_span.start_line == block_span.start_line {
                if var_span.start_col < block_span.start_col {
                    continue;
                }
            }

            // If on same end line, check column
            if var_span.end_line == block_span.end_line {
                if var_span.end_col > block_span.end_col {
                    continue;
                }
            }

            // Calculate block size (smaller is better = more specific)
            // Use saturating_sub to prevent overflow when end_col < start_col
            let line_diff = block_span.end_line.saturating_sub(block_span.start_line) as usize;
            let col_diff = block_span.end_col.saturating_sub(block_span.start_col) as usize;
            let block_size = line_diff * 1000 + col_diff;

            if block_size < best_size {
                best_size = block_size;
                best_block = Some(block);
            }
        }
    }

    best_block.map(|b| b.id.clone())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::parsing::plugins::PythonPlugin;
    use crate::features::parsing::ports::LanguagePlugin;
    use tree_sitter::{Node as TSNode, Parser};

    #[test]
    fn test_node_to_span() {
        let mut parser = Parser::new();
        let plugin = PythonPlugin::new();
        let language = plugin.tree_sitter_language();
        parser.set_language(&language).unwrap();

        let code = "def foo():\n    pass";
        let tree = parser.parse(code, None).unwrap();
        let root = tree.root_node();

        let span = node_to_span(&root);
        assert_eq!(span.start_line, 1);
        assert_eq!(span.end_line, 2);
    }

    #[test]
    fn test_find_body_node() {
        let mut parser = Parser::new();
        let plugin = PythonPlugin::new();
        let language = plugin.tree_sitter_language();
        parser.set_language(&language).unwrap();

        let code = "def foo():\n    pass";
        let tree = parser.parse(code, None).unwrap();
        let root = tree.root_node();

        // Get function_definition node
        let func_node = root.child(0).unwrap();

        let body = find_body_node(&func_node);
        assert!(body.is_some());
        assert_eq!(body.unwrap().kind(), "block");
    }

    #[test]
    fn test_find_containing_block_basic() {
        use crate::shared::models::span_ref::{BlockRef, SpanRef};

        // Create test variable span (line 2, col 4-8)
        let var_span = Span::new(2, 4, 2, 8);

        // Create test blocks
        let blocks = vec![
            BlockRef::new(
                "block1".to_string(),
                "BLOCK".to_string(),
                Span::new(1, 0, 5, 0), // Outer block
                0,
            ),
            BlockRef::new(
                "block2".to_string(),
                "BLOCK".to_string(),
                Span::new(2, 0, 3, 0), // Inner block (better match)
                0,
            ),
        ];

        let result = find_containing_block(&var_span, &blocks);
        assert_eq!(result, Some("block2".to_string()));
    }

    #[test]
    fn test_find_containing_block_no_match() {
        use crate::shared::models::span_ref::BlockRef;

        let var_span = Span::new(10, 0, 10, 5);
        let blocks = vec![BlockRef::new(
            "block1".to_string(),
            "BLOCK".to_string(),
            Span::new(1, 0, 5, 0),
            0,
        )];

        let result = find_containing_block(&var_span, &blocks);
        assert_eq!(result, None);
    }
}
