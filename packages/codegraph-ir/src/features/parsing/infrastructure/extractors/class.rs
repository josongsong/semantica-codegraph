/*
 * Class Analysis Module
 *
 * Extracts class metadata from AST:
 * - Name, FQN
 * - Base classes (inheritance)
 * - Methods
 * - Docstring
 * - Span
 *
 * Phase 1: Basic metadata only
 */

use crate::shared::models::Span;
use tree_sitter::Node;

/// Class metadata extracted from AST
#[derive(Debug, Clone)]
pub struct ClassInfo {
    pub name: String,
    pub span: Span,
    pub base_classes: Vec<String>,
    pub methods: Vec<String>,
    pub docstring: Option<String>,
}

/// Extract class metadata from class_definition node
pub fn extract_class_info(node: &Node, source: &str) -> Option<ClassInfo> {
    // Verify node type
    if node.kind() != "class_definition" {
        return None;
    }

    // Extract name
    let name = extract_class_name(node, source)?;

    // Extract span
    let span = node_to_span(node);

    // Extract base classes
    let base_classes = extract_base_classes(node, source);

    // Extract methods
    let methods = extract_methods(node, source);

    // Extract docstring
    let docstring = extract_docstring(node, source);

    Some(ClassInfo {
        name,
        span,
        base_classes,
        methods,
        docstring,
    })
}

/// Extract class name from identifier child
fn extract_class_name(node: &Node, source: &str) -> Option<String> {
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

/// Extract base classes from argument_list
fn extract_base_classes(node: &Node, source: &str) -> Vec<String> {
    let mut bases = Vec::new();

    // Find argument_list (inheritance)
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "argument_list" {
                // Extract each base class
                for j in 0..child.child_count() {
                    if let Some(base) = child.child(j) {
                        if base.kind() == "identifier" {
                            let start = base.start_byte();
                            let end = base.end_byte();
                            bases.push(source[start..end].to_string());
                        }
                    }
                }
                break;
            }
        }
    }

    bases
}

/// Extract method names from class body
fn extract_methods(node: &Node, source: &str) -> Vec<String> {
    let mut methods = Vec::new();

    // Find block (body)
    for i in 0..node.child_count() {
        if let Some(block) = node.child(i) {
            if block.kind() == "block" {
                // Find function_definition nodes
                for j in 0..block.child_count() {
                    if let Some(stmt) = block.child(j) {
                        if stmt.kind() == "function_definition" {
                            // Extract method name
                            for k in 0..stmt.child_count() {
                                if let Some(name_node) = stmt.child(k) {
                                    if name_node.kind() == "identifier" {
                                        let start = name_node.start_byte();
                                        let end = name_node.end_byte();
                                        methods.push(source[start..end].to_string());
                                        break;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    methods
}

/// Extract docstring from class body
fn extract_docstring(node: &Node, source: &str) -> Option<String> {
    // Find block (body)
    for i in 0..node.child_count() {
        if let Some(block) = node.child(i) {
            if block.kind() == "block" {
                // First statement might be docstring
                for j in 0..block.child_count() {
                    if let Some(stmt) = block.child(j) {
                        if stmt.kind() == "expression_statement" {
                            if let Some(string_node) = stmt.child(0) {
                                if string_node.kind() == "string" {
                                    let start = string_node.start_byte();
                                    let end = string_node.end_byte();
                                    let raw = &source[start..end];
                                    // Remove quotes
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
    fn test_extract_class_name() {
        let code = "class MyClass: pass";
        let tree = parse_python(code);
        let root = tree.root_node();
        let class = root.child(0).unwrap();

        let info = extract_class_info(&class, code).unwrap();
        assert_eq!(info.name, "MyClass");
    }

    #[test]
    fn test_extract_base_classes() {
        let code = "class Child(Parent): pass";
        let tree = parse_python(code);
        let root = tree.root_node();
        let class = root.child(0).unwrap();

        let info = extract_class_info(&class, code).unwrap();
        assert_eq!(info.base_classes, vec!["Parent"]);
    }

    #[test]
    fn test_extract_methods() {
        let code = r#"
class MyClass:
    def method1(self):
        pass
    
    def method2(self):
        pass
"#;
        let tree = parse_python(code);
        let root = tree.root_node();
        let class = root.child(0).unwrap();

        let info = extract_class_info(&class, code).unwrap();
        assert_eq!(info.methods, vec!["method1", "method2"]);
    }

    #[test]
    fn test_extract_class_docstring() {
        let code = r#"
class MyClass:
    "This is a docstring"
    pass
"#;
        let tree = parse_python(code);
        let root = tree.root_node();
        let class = root.child(0).unwrap();

        let info = extract_class_info(&class, code).unwrap();
        assert_eq!(info.docstring, Some("This is a docstring".to_string()));
    }
}
