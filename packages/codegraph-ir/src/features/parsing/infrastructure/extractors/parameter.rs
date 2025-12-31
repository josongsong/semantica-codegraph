/*
 * Parameter Analysis Module
 *
 * Extracts function/method parameters from AST:
 * - Parameter names
 * - Type annotations
 * - Default values
 * - Special parameters (self, *args, **kwargs)
 *
 * MATCHES: FunctionAnalyzer.process_parameters()
 *
 * PRODUCTION REQUIREMENTS:
 * - Handle all Python parameter types
 * - Preserve order
 * - Extract type hints
 * - No fake data
 */

use crate::shared::models::Span;
use tree_sitter::Node;

/// Parameter information
#[derive(Debug, Clone, PartialEq, Eq)]
#[allow(dead_code)]
pub struct Parameter {
    pub name: String,
    pub type_annotation: Option<String>,
    pub default_value: Option<String>,
    pub kind: ParameterKind,
    pub span: Span,
}

/// Parameter kind
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)]
pub enum ParameterKind {
    Positional,     // x
    PositionalOnly, // x, / (Python 3.8+)
    KeywordOnly,    // *, x
    VarArgs,        // *args
    VarKeyword,     // **kwargs
}

/// Extract parameters from parameters node
///
/// # Arguments
/// * `node` - parameters AST node
/// * `source` - Source code
///
/// # Returns
/// * Vec of Parameter structs
#[allow(dead_code)]
pub fn extract_parameters(node: &Node, source: &str) -> Vec<Parameter> {
    let mut params = Vec::new();

    if node.kind() != "parameters" {
        return params;
    }

    let mut keyword_only = false;

    // Iterate through children
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            let child_text = get_node_text(&child, source);

            // Check for * (keyword-only marker)
            if child_text == "*" {
                keyword_only = true;
                continue;
            }

            match child.kind() {
                // Regular parameter
                "identifier" => {
                    let name = child_text;
                    let span = node_to_span(&child);

                    params.push(Parameter {
                        name,
                        type_annotation: None,
                        default_value: None,
                        kind: if keyword_only {
                            ParameterKind::KeywordOnly
                        } else {
                            ParameterKind::Positional
                        },
                        span,
                    });
                }

                // Typed parameter: x: int
                "typed_parameter" => {
                    if let Some(param) = extract_typed_parameter(&child, source, keyword_only) {
                        params.push(param);
                    }
                }

                // Default parameter: x=10
                "default_parameter" => {
                    if let Some(param) = extract_default_parameter(&child, source, keyword_only) {
                        params.push(param);
                    }
                }

                // Typed default parameter: x: int = 10
                "typed_default_parameter" => {
                    if let Some(param) =
                        extract_typed_default_parameter(&child, source, keyword_only)
                    {
                        params.push(param);
                    }
                }

                // *args
                "list_splat_pattern" => {
                    if let Some(param) = extract_varargs(&child, source) {
                        params.push(param);
                    }
                    keyword_only = true; // After *args, all params are keyword-only
                }

                // **kwargs
                "dictionary_splat_pattern" => {
                    if let Some(param) = extract_varkeyword(&child, source) {
                        params.push(param);
                    }
                }

                _ => {}
            }
        }
    }

    params
}

/// Extract typed parameter (x: int)
fn extract_typed_parameter(node: &Node, source: &str, keyword_only: bool) -> Option<Parameter> {
    let mut name = None;
    let mut type_annotation = None;

    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            match child.kind() {
                "identifier" => {
                    name = Some(get_node_text(&child, source));
                }
                "type" => {
                    type_annotation = Some(get_node_text(&child, source));
                }
                _ => {}
            }
        }
    }

    let name = name?;
    let span = node_to_span(node);

    Some(Parameter {
        name,
        type_annotation,
        default_value: None,
        kind: if keyword_only {
            ParameterKind::KeywordOnly
        } else {
            ParameterKind::Positional
        },
        span,
    })
}

/// Extract default parameter (x=10)
fn extract_default_parameter(node: &Node, source: &str, keyword_only: bool) -> Option<Parameter> {
    let mut name = None;
    let mut default_value = None;

    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            match child.kind() {
                "identifier" => {
                    name = Some(get_node_text(&child, source));
                }
                "integer" | "float" | "string" | "true" | "false" | "none" => {
                    default_value = Some(get_node_text(&child, source));
                }
                _ => {}
            }
        }
    }

    let name = name?;
    let span = node_to_span(node);

    Some(Parameter {
        name,
        type_annotation: None,
        default_value,
        kind: if keyword_only {
            ParameterKind::KeywordOnly
        } else {
            ParameterKind::Positional
        },
        span,
    })
}

/// Extract typed default parameter (x: int = 10)
fn extract_typed_default_parameter(
    node: &Node,
    source: &str,
    keyword_only: bool,
) -> Option<Parameter> {
    let mut name = None;
    let mut type_annotation = None;
    let mut default_value = None;

    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            match child.kind() {
                "identifier" => {
                    name = Some(get_node_text(&child, source));
                }
                "type" => {
                    type_annotation = Some(get_node_text(&child, source));
                }
                "integer" | "float" | "string" | "true" | "false" | "none" => {
                    default_value = Some(get_node_text(&child, source));
                }
                _ => {}
            }
        }
    }

    let name = name?;
    let span = node_to_span(node);

    Some(Parameter {
        name,
        type_annotation,
        default_value,
        kind: if keyword_only {
            ParameterKind::KeywordOnly
        } else {
            ParameterKind::Positional
        },
        span,
    })
}

/// Extract *args
fn extract_varargs(node: &Node, source: &str) -> Option<Parameter> {
    // Find identifier child
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "identifier" {
                let name = get_node_text(&child, source);
                let span = node_to_span(node);

                return Some(Parameter {
                    name,
                    type_annotation: None,
                    default_value: None,
                    kind: ParameterKind::VarArgs,
                    span,
                });
            }
        }
    }
    None
}

/// Extract **kwargs
fn extract_varkeyword(node: &Node, source: &str) -> Option<Parameter> {
    // Find identifier child
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "identifier" {
                let name = get_node_text(&child, source);
                let span = node_to_span(node);

                return Some(Parameter {
                    name,
                    type_annotation: None,
                    default_value: None,
                    kind: ParameterKind::VarKeyword,
                    span,
                });
            }
        }
    }
    None
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

    fn get_parameters_node<'a>(
        tree: &'a tree_sitter::Tree,
        code: &str,
    ) -> Option<tree_sitter::Node<'a>> {
        let root = tree.root_node();
        let func = root.child(0)?;

        // Find parameters node
        for i in 0..func.child_count() {
            if let Some(child) = func.child(i) {
                if child.kind() == "parameters" {
                    return Some(child);
                }
            }
        }
        None
    }

    #[test]
    fn test_simple_parameters() {
        let code = "def func(x, y, z): pass";
        let tree = parse_python(code);
        let params_node = get_parameters_node(&tree, code).unwrap();
        let params = extract_parameters(&params_node, code);

        assert_eq!(params.len(), 3);
        assert_eq!(params[0].name, "x");
        assert_eq!(params[1].name, "y");
        assert_eq!(params[2].name, "z");

        for param in &params {
            assert_eq!(param.kind, ParameterKind::Positional);
        }
    }

    #[test]
    fn test_typed_parameters() {
        let code = "def func(x: int, y: str): pass";
        let tree = parse_python(code);
        let params_node = get_parameters_node(&tree, code).unwrap();
        let params = extract_parameters(&params_node, code);

        assert_eq!(params.len(), 2);
        assert_eq!(params[0].name, "x");
        assert_eq!(params[0].type_annotation, Some("int".to_string()));
        assert_eq!(params[1].name, "y");
        assert_eq!(params[1].type_annotation, Some("str".to_string()));
    }

    #[test]
    fn test_default_parameters() {
        let code = "def func(x=10, y=\"hello\"): pass";
        let tree = parse_python(code);
        let params_node = get_parameters_node(&tree, code).unwrap();
        let params = extract_parameters(&params_node, code);

        assert_eq!(params.len(), 2);
        assert_eq!(params[0].name, "x");
        assert_eq!(params[0].default_value, Some("10".to_string()));
        assert_eq!(params[1].name, "y");
        assert_eq!(params[1].default_value, Some("\"hello\"".to_string()));
    }

    #[test]
    fn test_typed_default_parameters() {
        let code = "def func(x: int = 10, y: str = \"test\"): pass";
        let tree = parse_python(code);
        let params_node = get_parameters_node(&tree, code).unwrap();
        let params = extract_parameters(&params_node, code);

        assert_eq!(params.len(), 2);
        assert_eq!(params[0].name, "x");
        assert_eq!(params[0].type_annotation, Some("int".to_string()));
        assert_eq!(params[0].default_value, Some("10".to_string()));
    }

    #[test]
    fn test_varargs_kwargs() {
        let code = "def func(*args, **kwargs): pass";
        let tree = parse_python(code);
        let params_node = get_parameters_node(&tree, code).unwrap();
        let params = extract_parameters(&params_node, code);

        assert_eq!(params.len(), 2);
        assert_eq!(params[0].name, "args");
        assert_eq!(params[0].kind, ParameterKind::VarArgs);
        assert_eq!(params[1].name, "kwargs");
        assert_eq!(params[1].kind, ParameterKind::VarKeyword);
    }

    #[test]
    fn test_keyword_only_parameters() {
        let code = "def func(x, *, y, z): pass";
        let tree = parse_python(code);
        let params_node = get_parameters_node(&tree, code).unwrap();
        let params = extract_parameters(&params_node, code);

        assert_eq!(params.len(), 3);
        assert_eq!(params[0].kind, ParameterKind::Positional);
        assert_eq!(params[1].kind, ParameterKind::KeywordOnly);
        assert_eq!(params[2].kind, ParameterKind::KeywordOnly);
    }

    #[test]
    fn test_complex_signature() {
        let code = "def func(a, b: int, c=10, d: str = \"test\", *args, e, **kwargs): pass";
        let tree = parse_python(code);
        let params_node = get_parameters_node(&tree, code).unwrap();
        let params = extract_parameters(&params_node, code);

        assert_eq!(params.len(), 7);

        // a
        assert_eq!(params[0].name, "a");
        assert_eq!(params[0].kind, ParameterKind::Positional);

        // b: int
        assert_eq!(params[1].name, "b");
        assert_eq!(params[1].type_annotation, Some("int".to_string()));

        // c=10
        assert_eq!(params[2].name, "c");
        assert_eq!(params[2].default_value, Some("10".to_string()));

        // d: str = "test"
        assert_eq!(params[3].name, "d");
        assert_eq!(params[3].type_annotation, Some("str".to_string()));
        assert_eq!(params[3].default_value, Some("\"test\"".to_string()));

        // *args
        assert_eq!(params[4].name, "args");
        assert_eq!(params[4].kind, ParameterKind::VarArgs);

        // e (keyword-only)
        assert_eq!(params[5].name, "e");
        assert_eq!(params[5].kind, ParameterKind::KeywordOnly);

        // **kwargs
        assert_eq!(params[6].name, "kwargs");
        assert_eq!(params[6].kind, ParameterKind::VarKeyword);
    }
}
