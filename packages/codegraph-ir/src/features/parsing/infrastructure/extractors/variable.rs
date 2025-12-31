/*
 * Variable Analysis Module
 *
 * Extracts variable assignments and generates:
 * - Variable nodes
 * - READS edges (variable usage)
 * - WRITES edges (variable assignment)
 *
 * MATCHES: PythonVariableAnalyzer.process_variables_in_block()
 *
 * PRODUCTION REQUIREMENTS:
 * - Track all assignments
 * - Recursive block traversal
 * - Scope-aware
 * - No fake data
 */

use crate::shared::models::Span;
use tree_sitter::Node;

/// Variable assignment info
#[derive(Debug, Clone)]
pub struct VariableAssignment {
    pub name: String,
    pub span: Span,
    pub type_annotation: Option<String>,
    pub value_text: Option<String>,
}

/// Extract variable assignments from block
///
/// Processes:
/// - Direct assignments: x = 10
/// - Tuple assignments: x, y = 1, 2
/// - Augmented assignments: x += 1
/// - Annotated assignments: x: int = 10
///
/// # Arguments
/// * `block_node` - Block AST node (function body)
/// * `source` - Source code
///
/// # Returns
/// * Vec of VariableAssignment
pub fn extract_variables_in_block(block_node: &Node, source: &str) -> Vec<VariableAssignment> {
    let mut variables = Vec::new();

    // Traverse block recursively
    traverse_for_assignments(block_node, source, &mut variables);

    variables
}

/// Recursive traversal for assignments
fn traverse_for_assignments(node: &Node, source: &str, variables: &mut Vec<VariableAssignment>) {
    match node.kind() {
        // Direct assignment: x = 10
        "assignment" => {
            extract_assignment(node, source, variables);
        }

        // Expression statement (might contain assignment)
        "expression_statement" => {
            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    match child.kind() {
                        "assignment" => {
                            extract_assignment(&child, source, variables);
                        }
                        "augmented_assignment" => {
                            extract_augmented_assignment(&child, source, variables);
                        }
                        _ => {}
                    }
                }
            }
        }

        // Augmented assignment: x += 1
        "augmented_assignment" => {
            extract_augmented_assignment(node, source, variables);
        }

        // Block (if, for, while, etc.)
        "block" => {
            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    traverse_for_assignments(&child, source, variables);
                }
            }
        }

        // Control flow statements
        "if_statement" | "for_statement" | "while_statement" | "try_statement" => {
            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    traverse_for_assignments(&child, source, variables);
                }
            }
        }

        _ => {
            // Continue traversal
            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    traverse_for_assignments(&child, source, variables);
                }
            }
        }
    }
}

/// Extract assignment: x = value or x: int = value
fn extract_assignment(node: &Node, source: &str, variables: &mut Vec<VariableAssignment>) {
    // Find left side (variable name), type annotation, and right side
    let mut left_node = None;
    let mut type_node = None;
    let mut right_node = None;

    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            match child.kind() {
                "type" => {
                    type_node = Some(child);
                }
                "=" => {
                    // Skip assignment operator
                }
                _ => {
                    if i == 0 {
                        left_node = Some(child);
                    } else if right_node.is_none() {
                        right_node = Some(child);
                    }
                }
            }
        }
    }

    // Extract type annotation if present
    let type_annotation = type_node.map(|t| get_node_text(&t, source));

    if let Some(left) = left_node {
        // Extract variable names from left side
        extract_variable_names(
            &left,
            source,
            right_node,
            type_annotation.as_deref(),
            variables,
        );
    }
}

/// Extract augmented assignment: x += 1
fn extract_augmented_assignment(
    node: &Node,
    source: &str,
    variables: &mut Vec<VariableAssignment>,
) {
    // Find left side
    if let Some(left) = node.child(0) {
        if left.kind() == "identifier" {
            let name = get_node_text(&left, source);
            let span = node_to_span(&left);

            variables.push(VariableAssignment {
                name,
                span,
                type_annotation: None, // Augmented assignments don't have type annotations
                value_text: None,
            });
        }
    }
}

/// Extract variable names from left side of assignment
fn extract_variable_names(
    node: &Node,
    source: &str,
    value_node: Option<Node>,
    type_annotation: Option<&str>,
    variables: &mut Vec<VariableAssignment>,
) {
    match node.kind() {
        "identifier" => {
            let name = get_node_text(node, source);
            let span = node_to_span(node);

            let value_text = value_node.map(|v| get_node_text(&v, source));

            variables.push(VariableAssignment {
                name,
                span,
                type_annotation: type_annotation.map(|s| s.to_string()),
                value_text,
            });
        }

        // Tuple unpacking: x, y = 1, 2
        "pattern_list" | "tuple_pattern" => {
            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    if child.kind() == "identifier" {
                        let name = get_node_text(&child, source);
                        let span = node_to_span(&child);

                        variables.push(VariableAssignment {
                            name,
                            span,
                            type_annotation: None, // Tuple unpacking doesn't support type annotations
                            value_text: None,
                        });
                    }
                }
            }
        }

        // Attribute: self.x = 10
        "attribute" => {
            // Extract attribute name
            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    if child.kind() == "identifier" && i > 0 {
                        let name = get_node_text(&child, source);
                        let span = node_to_span(&child);

                        variables.push(VariableAssignment {
                            name,
                            span,
                            type_annotation: None,
                            value_text: None,
                        });
                    }
                }
            }
        }

        _ => {}
    }
}

/// Get node text
fn get_node_text(node: &Node, source: &str) -> String {
    let start = node.start_byte();
    let end = node.end_byte();
    source[start..end].to_string()
}

/// Convert node to Span
fn node_to_span(node: &Node) -> Span {
    let start_pos = node.start_position();
    let end_pos = node.end_position();

    Span::new(
        start_pos.row as u32 + 1,
        start_pos.column as u32,
        end_pos.row as u32 + 1,
        end_pos.column as u32,
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

        // Find block
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
    fn test_simple_assignment() {
        let code = "def f():\n    x = 10";
        let tree = parse_python(code);
        let body = get_function_body(&tree).unwrap();
        let vars = extract_variables_in_block(&body, code);

        assert_eq!(vars.len(), 1);
        assert_eq!(vars[0].name, "x");
    }

    #[test]
    fn test_multiple_assignments() {
        let code = "def f():\n    x = 10\n    y = 20\n    z = 30";
        let tree = parse_python(code);
        let body = get_function_body(&tree).unwrap();
        let vars = extract_variables_in_block(&body, code);

        assert_eq!(vars.len(), 3);
        assert_eq!(vars[0].name, "x");
        assert_eq!(vars[1].name, "y");
        assert_eq!(vars[2].name, "z");
    }

    #[test]
    fn test_tuple_unpacking() {
        let code = "def f():\n    x, y = 1, 2";
        let tree = parse_python(code);
        let body = get_function_body(&tree).unwrap();
        let vars = extract_variables_in_block(&body, code);

        assert_eq!(vars.len(), 2);
        let names: Vec<_> = vars.iter().map(|v| v.name.as_str()).collect();
        assert!(names.contains(&"x"));
        assert!(names.contains(&"y"));
    }

    #[test]
    fn test_augmented_assignment() {
        let code = "def f():\n    x = 0\n    x += 1";
        let tree = parse_python(code);
        let body = get_function_body(&tree).unwrap();
        let vars = extract_variables_in_block(&body, code);

        assert_eq!(vars.len(), 2); // x = 0, x += 1
        assert_eq!(vars[0].name, "x");
        assert_eq!(vars[1].name, "x");
    }

    #[test]
    fn test_nested_blocks() {
        let code = r#"
def f():
    x = 1
    if True:
        y = 2
        for i in range(10):
            z = 3
"#;
        let tree = parse_python(code);
        let body = get_function_body(&tree).unwrap();
        let vars = extract_variables_in_block(&body, code);

        assert_eq!(vars.len(), 3); // x, y, z
        let names: Vec<_> = vars.iter().map(|v| v.name.as_str()).collect();
        assert!(names.contains(&"x"));
        assert!(names.contains(&"y"));
        assert!(names.contains(&"z"));
    }
}
