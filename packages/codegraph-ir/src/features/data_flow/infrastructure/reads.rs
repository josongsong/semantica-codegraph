/*
 * READS Analysis - Variable usage tracking
 *
 * Extracts variable reads (usage) from expressions.
 *
 * PRODUCTION GRADE:
 * - Track all variable references
 * - Distinguish reads from writes
 * - No fake data
 */

use crate::shared::models::Span;
use tree_sitter::Node;

/// Variable read (usage)
#[derive(Debug, Clone)]
pub struct VariableRead {
    pub name: String,
    pub span: Span,
}

/// Extract variable reads from block
///
/// Finds all identifier usages (not assignments).
pub fn extract_reads_in_block(block_node: &Node, source: &str) -> Vec<VariableRead> {
    let mut reads = Vec::new();
    traverse_for_reads(block_node, source, &mut reads);
    reads
}

fn traverse_for_reads(node: &Node, source: &str, reads: &mut Vec<VariableRead>) {
    // Skip assignment left sides
    if node.kind() == "assignment" {
        // Only traverse right side
        if let Some(right) = node.child(2) {
            // After '='
            traverse_for_reads(&right, source, reads);
        }
        return;
    }

    // Identifier = potential read
    if node.kind() == "identifier" {
        let name = get_node_text(node, source);
        let span = node_to_span(node);

        reads.push(VariableRead { name, span });
    }

    // Recurse
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            traverse_for_reads(&child, source, reads);
        }
    }
}

fn get_node_text(node: &Node, source: &str) -> String {
    source[node.start_byte()..node.end_byte()].to_string()
}

fn node_to_span(node: &Node) -> Span {
    let start = node.start_position();
    let end = node.end_position();
    Span::new(
        start.row as u32 + 1,
        start.column as u32,
        end.row as u32 + 1,
        end.column as u32,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use tree_sitter::Parser;

    fn parse_python(code: &str) -> tree_sitter::Tree {
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_python::language())
            .unwrap();
        parser.parse(code, None).unwrap()
    }

    fn get_function_body<'a>(tree: &'a tree_sitter::Tree) -> Option<Node<'a>> {
        let root = tree.root_node();
        let func = root.child(0)?;

        for i in 0..func.child_count() {
            if let Some(child) = func.child(i) {
                if child.kind() == "block" {
                    return Some(child);
                }
            }
        }
        None
    }

    #[test]
    fn test_simple_read() {
        let code = "def f():\n    return x";
        let tree = parse_python(code);
        let body = get_function_body(&tree).unwrap();
        let reads = extract_reads_in_block(&body, code);

        assert_eq!(reads.len(), 1);
        assert_eq!(reads[0].name, "x");
    }

    #[test]
    fn test_read_vs_write() {
        let code = "def f():\n    x = 1\n    y = x + 2";
        let tree = parse_python(code);
        let body = get_function_body(&tree).unwrap();
        let reads = extract_reads_in_block(&body, code);

        // Should read 'x' (not 'y' which is written)
        let names: Vec<_> = reads.iter().map(|r| r.name.as_str()).collect();
        assert!(names.contains(&"x"));
    }
}
