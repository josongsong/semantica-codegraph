/*
 * Function Analysis Module
 *
 * Extracts function metadata from AST:
 * - Name, FQN
 * - Parameters
 * - Return type
 * - Docstring
 * - Span
 *
 * Phase 1: Basic metadata only (no dataflow/CF)
 */

use crate::shared::models::Span;
use tree_sitter::Node;

/// Function metadata extracted from AST
#[derive(Debug, Clone)]
pub struct FunctionInfo {
    pub name: String,
    pub span: Span,
    pub params: Vec<String>,
    pub return_type: Option<String>,
    pub docstring: Option<String>,
    pub is_async: bool,
}

/// Extract function metadata from function_definition node
pub fn extract_function_info(node: &Node, source: &str) -> Option<FunctionInfo> {
    // Verify node type
    if node.kind() != "function_definition" {
        return None;
    }

    // Extract name
    let name = extract_function_name(node, source)?;

    // Extract span
    let span = node_to_span(node);

    // Extract parameters
    let params = extract_parameters(node, source);

    // Extract return type
    let return_type = extract_return_type(node, source);

    // Extract docstring
    let docstring = extract_docstring(node, source);

    // Check if async
    let is_async = is_async_function(node, source);

    Some(FunctionInfo {
        name,
        span,
        params,
        return_type,
        docstring,
        is_async,
    })
}

/// Extract function name from identifier child
fn extract_function_name(node: &Node, source: &str) -> Option<String> {
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "identifier" {
                let start = child.start_byte();
                let end = child.end_byte();
                return Some(source[start..end].to_string());
            }
        }
    }
    None
}

/// Extract parameters from parameters node
fn extract_parameters(node: &Node, source: &str) -> Vec<String> {
    let mut params = Vec::new();

    // Find parameters node
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "parameters" {
                // Extract each parameter
                for j in 0..child.child_count() {
                    if let Some(param) = child.child(j) {
                        if param.kind() == "identifier" {
                            let start = param.start_byte();
                            let end = param.end_byte();
                            params.push(source[start..end].to_string());
                        }
                    }
                }
                break;
            }
        }
    }

    params
}

/// Extract return type from type annotation
fn extract_return_type(node: &Node, source: &str) -> Option<String> {
    // Look for -> type annotation
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "type" {
                let start = child.start_byte();
                let end = child.end_byte();
                return Some(source[start..end].to_string());
            }
        }
    }
    None
}

/// Extract docstring from function body
fn extract_docstring(node: &Node, source: &str) -> Option<String> {
    // Find block (body)
    for i in 0..node.child_count() {
        if let Some(block) = node.child(i) {
            if block.kind() == "block" {
                // Iterate through block children to find first string
                for j in 0..block.child_count() {
                    if let Some(stmt) = block.child(j) {
                        if stmt.kind() == "expression_statement" {
                            if let Some(string_node) = stmt.child(0) {
                                if string_node.kind() == "string" {
                                    let start = string_node.start_byte();
                                    let end = string_node.end_byte();
                                    let raw = &source[start..end];
                                    // Remove quotes (both " and ')
                                    let trimmed = raw
                                        .trim_start_matches('"')
                                        .trim_end_matches('"')
                                        .trim_start_matches('\'')
                                        .trim_end_matches('\'');
                                    return Some(trimmed.to_string());
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    None
}

/// Check if function is async
fn is_async_function(node: &Node, source: &str) -> bool {
    // Look for 'async' keyword before 'def'
    if let Some(parent) = node.parent() {
        for i in 0..parent.child_count() {
            if let Some(child) = parent.child(i) {
                let start = child.start_byte();
                let end = child.end_byte();
                if &source[start..end] == "async" {
                    return true;
                }
            }
        }
    }
    false
}

/// Convert tree-sitter node to Span
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

    #[test]
    fn test_extract_function_name() {
        let code = "def hello(): pass";
        let tree = parse_python(code);
        let root = tree.root_node();
        let func = root.child(0).unwrap();

        let info = extract_function_info(&func, code).unwrap();
        assert_eq!(info.name, "hello");
    }

    #[test]
    fn test_extract_parameters() {
        let code = "def add(x, y): return x + y";
        let tree = parse_python(code);
        let root = tree.root_node();
        let func = root.child(0).unwrap();

        let info = extract_function_info(&func, code).unwrap();
        assert_eq!(info.params, vec!["x", "y"]);
    }

    #[test]
    fn test_extract_docstring() {
        let code = r#"
def greet():
    "Hello world"
    pass
"#;
        let tree = parse_python(code);
        let root = tree.root_node();
        let func = root.child(0).unwrap();

        let info = extract_function_info(&func, code).unwrap();
        assert_eq!(info.docstring, Some("Hello world".to_string()));
    }
}
