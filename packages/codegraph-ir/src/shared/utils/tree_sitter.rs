//! Tree-sitter Utility Functions
//!
//! Common utilities for working with tree-sitter AST nodes.
//! Eliminates code duplication across extractors (function.rs, class.rs, etc.)
//!
//! SOTA: Centralized, tested, and efficient.

use crate::shared::models::Span;
use tree_sitter::Node;

// ═══════════════════════════════════════════════════════════════════════════
// Node Traversal Utilities
// ═══════════════════════════════════════════════════════════════════════════

/// Find a direct child node by kind
///
/// # Example
/// ```ignore
/// let name_node = find_child_by_kind(&func_node, "identifier");
/// ```
#[inline]
pub fn find_child_by_kind<'a>(node: &'a Node, kind: &str) -> Option<Node<'a>> {
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == kind {
                return Some(child);
            }
        }
    }
    None
}

/// Find all direct children by kind
#[inline]
pub fn find_children_by_kind<'a>(node: &'a Node, kind: &str) -> Vec<Node<'a>> {
    let mut result = Vec::new();
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == kind {
                result.push(child);
            }
        }
    }
    result
}

/// Find a child node by kind recursively (depth-first)
pub fn find_descendant_by_kind<'a>(node: &'a Node, kind: &str) -> Option<Node<'a>> {
    let mut stack = vec![*node];
    while let Some(current) = stack.pop() {
        if current.kind() == kind {
            return Some(current);
        }
        for i in (0..current.child_count()).rev() {
            if let Some(child) = current.child(i) {
                stack.push(child);
            }
        }
    }
    None
}

/// Find all descendants by kind
pub fn find_descendants_by_kind<'a>(node: &'a Node, kind: &str) -> Vec<Node<'a>> {
    let mut result = Vec::new();
    let mut stack = vec![*node];
    while let Some(current) = stack.pop() {
        if current.kind() == kind {
            result.push(current);
        }
        for i in (0..current.child_count()).rev() {
            if let Some(child) = current.child(i) {
                stack.push(child);
            }
        }
    }
    result
}

// ═══════════════════════════════════════════════════════════════════════════
// Text Extraction Utilities
// ═══════════════════════════════════════════════════════════════════════════

/// Extract text content from a node
#[inline]
pub fn extract_node_text<'a>(node: &Node, source: &'a str) -> &'a str {
    let start = node.start_byte();
    let end = node.end_byte();
    &source[start..end]
}

/// Extract text content from a node as owned String
#[inline]
pub fn extract_node_text_owned(node: &Node, source: &str) -> String {
    extract_node_text(node, source).to_string()
}

/// Extract identifier name from a node that has an identifier child
#[inline]
pub fn extract_identifier_name(node: &Node, source: &str) -> Option<String> {
    find_child_by_kind(node, "identifier").map(|id_node| extract_node_text_owned(&id_node, source))
}

/// Extract all identifier names from children
pub fn extract_all_identifier_names(node: &Node, source: &str) -> Vec<String> {
    find_children_by_kind(node, "identifier")
        .iter()
        .map(|id_node| extract_node_text_owned(id_node, source))
        .collect()
}

// ═══════════════════════════════════════════════════════════════════════════
// Span Conversion Utilities
// ═══════════════════════════════════════════════════════════════════════════

/// Convert tree-sitter node to Span (1-indexed lines)
#[inline]
pub fn node_to_span(node: &Node) -> Span {
    let start_pos = node.start_position();
    let end_pos = node.end_position();

    Span::new(
        start_pos.row as u32 + 1, // 1-indexed
        start_pos.column as u32,
        end_pos.row as u32 + 1, // 1-indexed
        end_pos.column as u32,
    )
}

/// Create a Span from start and end byte positions
#[inline]
pub fn bytes_to_span(start_byte: usize, end_byte: usize, source: &str) -> Span {
    let start_line = source[..start_byte].matches('\n').count() as u32 + 1;
    let end_line = source[..end_byte].matches('\n').count() as u32 + 1;

    let start_col = start_byte - source[..start_byte].rfind('\n').map(|i| i + 1).unwrap_or(0);
    let end_col = end_byte - source[..end_byte].rfind('\n').map(|i| i + 1).unwrap_or(0);

    Span::new(start_line, start_col as u32, end_line, end_col as u32)
}

// ═══════════════════════════════════════════════════════════════════════════
// Python-specific Utilities
// ═══════════════════════════════════════════════════════════════════════════

/// Extract docstring from a block node (first string literal in block)
pub fn extract_docstring(block_node: &Node, source: &str) -> Option<String> {
    if block_node.kind() != "block" {
        return None;
    }

    // First statement might be docstring
    for i in 0..block_node.child_count() {
        if let Some(stmt) = block_node.child(i) {
            if stmt.kind() == "expression_statement" {
                if let Some(string_node) = stmt.child(0) {
                    if string_node.kind() == "string" {
                        let raw = extract_node_text(&string_node, source);
                        // Remove quotes (both " and ')
                        let trimmed = raw
                            .trim_start_matches("\"\"\"")
                            .trim_end_matches("\"\"\"")
                            .trim_start_matches("'''")
                            .trim_end_matches("'''")
                            .trim_start_matches('"')
                            .trim_end_matches('"')
                            .trim_start_matches('\'')
                            .trim_end_matches('\'')
                            .trim();
                        return Some(trimmed.to_string());
                    }
                }
            }
            // Only check first statement
            break;
        }
    }
    None
}

/// Find the block child of a definition node (function_definition, class_definition)
pub fn find_block_child<'a>(node: &'a Node) -> Option<Node<'a>> {
    find_child_by_kind(node, "block")
}

/// Extract parameters from a parameters node
pub fn extract_parameters(params_node: &Node, source: &str) -> Vec<String> {
    let mut params = Vec::new();

    for i in 0..params_node.child_count() {
        if let Some(param) = params_node.child(i) {
            match param.kind() {
                "identifier" => {
                    params.push(extract_node_text_owned(&param, source));
                }
                "typed_parameter" | "default_parameter" | "typed_default_parameter" => {
                    // Extract the identifier from typed/default parameters
                    if let Some(name) = extract_identifier_name(&param, source) {
                        params.push(name);
                    }
                }
                "list_splat_pattern" | "dictionary_splat_pattern" => {
                    // *args, **kwargs
                    if let Some(id) = find_child_by_kind(&param, "identifier") {
                        params.push(extract_node_text_owned(&id, source));
                    }
                }
                _ => {}
            }
        }
    }

    params
}

/// Extract return type annotation from a function
pub fn extract_return_type(node: &Node, source: &str) -> Option<String> {
    // Look for type child (return type annotation)
    find_child_by_kind(node, "type").map(|type_node| extract_node_text_owned(&type_node, source))
}

/// Extract base classes from a class definition
pub fn extract_base_classes(class_node: &Node, source: &str) -> Vec<String> {
    let mut bases = Vec::new();

    if let Some(arg_list) = find_child_by_kind(class_node, "argument_list") {
        for i in 0..arg_list.child_count() {
            if let Some(arg) = arg_list.child(i) {
                match arg.kind() {
                    "identifier" => {
                        bases.push(extract_node_text_owned(&arg, source));
                    }
                    "attribute" => {
                        // module.ClassName
                        bases.push(extract_node_text_owned(&arg, source));
                    }
                    _ => {}
                }
            }
        }
    }

    bases
}

/// Check if a node represents an async definition
pub fn is_async_definition(node: &Node, source: &str) -> bool {
    // Check if parent is decorated_definition with async
    if let Some(parent) = node.parent() {
        if parent.kind() == "decorated_definition" {
            // Check for async keyword before def
            for i in 0..parent.child_count() {
                if let Some(child) = parent.child(i) {
                    if extract_node_text(&child, source) == "async" {
                        return true;
                    }
                }
            }
        }
    }

    // Check preceding sibling for async keyword
    if let Some(parent) = node.parent() {
        for i in 0..parent.child_count() {
            if let Some(child) = parent.child(i) {
                if std::ptr::eq(&child as *const _, node as *const _) {
                    break;
                }
                if extract_node_text(&child, source) == "async" {
                    return true;
                }
            }
        }
    }

    false
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════

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
    fn test_find_child_by_kind() {
        let code = "def foo(): pass";
        let tree = parse_python(code);
        let root = tree.root_node();
        let func = root.child(0).unwrap();

        let id = find_child_by_kind(&func, "identifier");
        assert!(id.is_some());
        assert_eq!(extract_node_text(&id.unwrap(), code), "foo");
    }

    #[test]
    fn test_find_children_by_kind() {
        let code = "def foo(a, b, c): pass";
        let tree = parse_python(code);
        let root = tree.root_node();
        let func = root.child(0).unwrap();
        let params = find_child_by_kind(&func, "parameters").unwrap();

        let identifiers = find_children_by_kind(&params, "identifier");
        assert_eq!(identifiers.len(), 3);
    }

    #[test]
    fn test_extract_identifier_name() {
        let code = "class MyClass: pass";
        let tree = parse_python(code);
        let root = tree.root_node();
        let class = root.child(0).unwrap();

        let name = extract_identifier_name(&class, code);
        assert_eq!(name, Some("MyClass".to_string()));
    }

    #[test]
    fn test_node_to_span() {
        let code = "def foo():\n    pass";
        let tree = parse_python(code);
        let root = tree.root_node();
        let func = root.child(0).unwrap();

        let span = node_to_span(&func);
        assert_eq!(span.start_line, 1);
        assert_eq!(span.start_col, 0);
        assert_eq!(span.end_line, 2);
    }

    #[test]
    fn test_extract_docstring() {
        let code = r#"def foo():
    "This is a docstring"
    pass"#;
        let tree = parse_python(code);
        let root = tree.root_node();
        let func = root.child(0).unwrap();
        let block = find_block_child(&func).unwrap();

        let docstring = extract_docstring(&block, code);
        assert_eq!(docstring, Some("This is a docstring".to_string()));
    }

    #[test]
    fn test_extract_docstring_triple_quotes() {
        let code = r#"def foo():
    """
    Multi-line docstring
    """
    pass"#;
        let tree = parse_python(code);
        let root = tree.root_node();
        let func = root.child(0).unwrap();
        let block = find_block_child(&func).unwrap();

        let docstring = extract_docstring(&block, code);
        assert!(docstring.is_some());
        assert!(docstring.unwrap().contains("Multi-line docstring"));
    }

    #[test]
    fn test_extract_parameters() {
        let code = "def foo(a, b, c=1, *args, **kwargs): pass";
        let tree = parse_python(code);
        let root = tree.root_node();
        let func = root.child(0).unwrap();
        let params_node = find_child_by_kind(&func, "parameters").unwrap();

        let params = extract_parameters(&params_node, code);
        assert!(params.contains(&"a".to_string()));
        assert!(params.contains(&"b".to_string()));
        assert!(params.contains(&"c".to_string()));
        assert!(params.contains(&"args".to_string()));
        assert!(params.contains(&"kwargs".to_string()));
    }

    #[test]
    fn test_extract_base_classes() {
        let code = "class Child(Parent, Mixin): pass";
        let tree = parse_python(code);
        let root = tree.root_node();
        let class = root.child(0).unwrap();

        let bases = extract_base_classes(&class, code);
        assert_eq!(bases.len(), 2);
        assert!(bases.contains(&"Parent".to_string()));
        assert!(bases.contains(&"Mixin".to_string()));
    }

    #[test]
    fn test_find_descendant_by_kind() {
        let code = r#"
class Foo:
    def bar(self):
        x = 1
"#;
        let tree = parse_python(code);
        let root = tree.root_node();

        // Find any identifier in the tree
        let id = find_descendant_by_kind(&root, "identifier");
        assert!(id.is_some());
    }

    #[test]
    fn test_find_descendants_by_kind() {
        let code = r#"
x = 1
y = 2
z = 3
"#;
        let tree = parse_python(code);
        let root = tree.root_node();

        // Find all identifiers
        let identifiers = find_descendants_by_kind(&root, "identifier");
        assert_eq!(identifiers.len(), 3);
    }
}
