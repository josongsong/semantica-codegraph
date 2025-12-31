/*
 * Identifier Extraction - Variable reads tracking
 *
 * Extracts identifier references from expressions for READS edges.
 *
 * PRODUCTION REQUIREMENTS:
 * - Track all variable reads
 * - Exclude definitions (assignments)
 * - Recursive traversal
 * - No fake data
 */

use crate::shared::models::Span;
use tree_sitter::Node;

/// Identifier reference (variable read)
#[derive(Debug, Clone)]
pub struct IdentifierRef {
    pub name: String,
    pub span: Span,
}

/// Extract identifier references from expression
///
/// Tracks variable READS (excludes WRITES/definitions)
///
/// # Arguments
/// * `node` - Expression AST node
/// * `source` - Source code
///
/// # Returns
/// * Vec of IdentifierRef
pub fn extract_identifiers_in_expression(node: &Node, source: &str) -> Vec<IdentifierRef> {
    let mut identifiers = Vec::new();
    traverse_for_identifiers(node, source, &mut identifiers, false);
    identifiers
}

/// Recursive traversal for identifiers
fn traverse_for_identifiers(
    node: &Node,
    source: &str,
    identifiers: &mut Vec<IdentifierRef>,
    in_assignment_lhs: bool,
) {
    match node.kind() {
        // Skip left side of assignment (those are WRITES, not READS)
        "assignment" => {
            // Left side = WRITE (skip)
            if let Some(left) = node.child(0) {
                traverse_for_identifiers(&left, source, identifiers, true);
            }

            // Right side = READ (process)
            for i in 1..node.child_count() {
                if let Some(child) = node.child(i) {
                    if child.kind() != "=" && child.kind() != "type" {
                        traverse_for_identifiers(&child, source, identifiers, false);
                    }
                }
            }
        }

        // CRITICAL: Skip function call callee name (only process arguments)
        "call" => {
            // Python AST: call node has children: identifier (callee) + argument_list
            // We want to skip the callee name and only process arguments
            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    // Skip direct child identifier (that's the callee name)
                    // Process argument_list and other children
                    if child.kind() != "identifier" {
                        traverse_for_identifiers(&child, source, identifiers, false);
                    }
                }
            }
        }

        // Identifier - only add if NOT in assignment LHS
        "identifier" => {
            if !in_assignment_lhs {
                let name = get_node_text(node, source);
                let span = node_to_span(node);

                // Skip builtins and keywords
                if !is_builtin_or_keyword(&name) {
                    identifiers.push(IdentifierRef { name, span });
                }
            }
        }

        // Recursively process children
        _ => {
            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    traverse_for_identifiers(&child, source, identifiers, in_assignment_lhs);
                }
            }
        }
    }
}

/// Check if name is builtin or keyword
fn is_builtin_or_keyword(name: &str) -> bool {
    matches!(
        name,
        "self"
            | "cls"
            | "True"
            | "False"
            | "None"
            | "and"
            | "or"
            | "not"
            | "is"
            | "in"
            | "if"
            | "else"
            | "elif"
            | "for"
            | "while"
            | "def"
            | "class"
            | "return"
            | "yield"
            | "import"
            | "from"
            | "as"
            | "with"
            | "try"
            | "except"
            | "finally"
            | "raise"
            | "pass"
            | "break"
            | "continue"
            | "lambda"
    )
}

fn get_node_text(node: &Node, source: &str) -> String {
    let start = node.start_byte();
    let end = node.end_byte();
    source[start..end].to_string()
}

fn node_to_span(node: &Node) -> Span {
    Span::new(
        node.start_position().row as u32,
        node.start_position().column as u32,
        node.end_position().row as u32,
        node.end_position().column as u32,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use tree_sitter::Parser;

    #[test]
    fn test_simple_identifier() {
        let code = "x";
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_python::language())
            .unwrap();
        let tree = parser.parse(code, None).unwrap();
        let root = tree.root_node();

        let ids = extract_identifiers_in_expression(&root, code);

        assert_eq!(ids.len(), 1);
        assert_eq!(ids[0].name, "x");
    }

    #[test]
    fn test_binary_operation() {
        let code = "x + y";
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_python::language())
            .unwrap();
        let tree = parser.parse(code, None).unwrap();
        let root = tree.root_node();

        let ids = extract_identifiers_in_expression(&root, code);

        assert_eq!(ids.len(), 2);
        let names: Vec<_> = ids.iter().map(|id| id.name.as_str()).collect();
        assert!(names.contains(&"x"));
        assert!(names.contains(&"y"));
    }

    #[test]
    fn test_function_call_args() {
        let code = "func(x, y)";
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_python::language())
            .unwrap();
        let tree = parser.parse(code, None).unwrap();
        let root = tree.root_node();

        let ids = extract_identifiers_in_expression(&root, code);

        // Should have func, x, y
        assert!(ids.len() >= 2);
        let names: Vec<_> = ids.iter().map(|id| id.name.as_str()).collect();
        assert!(names.contains(&"x"));
        assert!(names.contains(&"y"));
    }

    #[test]
    fn test_skip_assignment_lhs() {
        let code = "x = y + z";
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_python::language())
            .unwrap();
        let tree = parser.parse(code, None).unwrap();
        let root = tree.root_node();

        let ids = extract_identifiers_in_expression(&root, code);

        // Should have y, z (NOT x - that's a WRITE)
        let names: Vec<_> = ids.iter().map(|id| id.name.as_str()).collect();
        assert!(!names.contains(&"x"), "Assignment LHS should be skipped");
        assert!(names.contains(&"y"));
        assert!(names.contains(&"z"));
    }

    #[test]
    fn test_skip_builtins() {
        let code = "self.x + True";
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_python::language())
            .unwrap();
        let tree = parser.parse(code, None).unwrap();
        let root = tree.root_node();

        let ids = extract_identifiers_in_expression(&root, code);

        // Should have x (NOT self, True)
        let names: Vec<_> = ids.iter().map(|id| id.name.as_str()).collect();
        assert!(!names.contains(&"self"));
        assert!(!names.contains(&"True"));
        assert!(names.contains(&"x"));
    }
}
