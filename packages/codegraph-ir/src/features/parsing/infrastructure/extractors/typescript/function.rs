//! TypeScript Function Extractor
//!
//! Extracts function metadata from TypeScript AST:
//! - Regular functions
//! - Arrow functions
//! - Async functions
//! - Generator functions
//! - Methods (class members)
//!
//! Captures:
//! - Name, parameters, return type
//! - Generic type parameters
//! - Modifiers (async, static, abstract)
//! - Decorators
//! - JSDoc comments

use tree_sitter::Node;
use crate::shared::models::Span;
use std::collections::HashMap;
use serde_json::{Value, json};

use super::common::*;
use super::r#type::extract_type_annotation;
use crate::features::parsing::infrastructure::tree_sitter::languages::typescript::{node_kinds, is_react_hook};

/// Function metadata extracted from AST
#[derive(Debug, Clone)]
pub struct FunctionInfo {
    pub name: String,
    pub span: Span,
    pub params: Vec<ParameterInfo>,
    pub return_type: Option<String>,
    pub type_parameters: Vec<String>,
    pub is_async: bool,
    pub is_generator: bool,
    pub is_arrow: bool,
    pub decorators: Vec<String>,
    pub jsdoc: Option<String>,
    pub accessibility: Option<Accessibility>,
    pub is_static: bool,
    pub is_abstract: bool,
    pub is_react_hook: bool,
}

/// Parameter information
#[derive(Debug, Clone)]
pub struct ParameterInfo {
    pub name: String,
    pub type_annotation: Option<String>,
    pub is_optional: bool,
    pub is_rest: bool,
    pub default_value: Option<String>,
}

/// Extract function info from various function node types
pub fn extract_function_info(node: &Node, source: &str) -> Option<FunctionInfo> {
    let kind = node.kind();

    match kind {
        node_kinds::FUNCTION_DECLARATION => extract_function_declaration(node, source),
        node_kinds::METHOD_DEFINITION => extract_method_definition(node, source),
        node_kinds::ARROW_FUNCTION => extract_arrow_function(node, source),
        node_kinds::FUNCTION_EXPRESSION => extract_function_expression(node, source),
        node_kinds::GENERATOR_FUNCTION_DECLARATION => extract_generator_declaration(node, source),
        _ => None,
    }
}

/// Extract regular function declaration
fn extract_function_declaration(node: &Node, source: &str) -> Option<FunctionInfo> {
    let name = find_child_by_field(node, "name")
        .and_then(|n| extract_identifier(&n, source))?;

    let span = node_to_span(node);
    let params = extract_parameters(node, source);
    let return_type = extract_return_type(node, source);
    let type_parameters = extract_type_parameters(node, source);
    let jsdoc = extract_jsdoc(node, source);
    let is_async_fn = is_async(node);
    let is_hook = is_react_hook(&name);

    Some(FunctionInfo {
        name,
        span,
        params,
        return_type,
        type_parameters,
        is_async: is_async_fn,
        is_generator: false,
        is_arrow: false,
        decorators: vec![],
        jsdoc,
        accessibility: None,
        is_static: false,
        is_abstract: false,
        is_react_hook: is_hook,
    })
}

/// Extract method definition (class member)
fn extract_method_definition(node: &Node, source: &str) -> Option<FunctionInfo> {
    let name = find_child_by_field(node, "name")
        .and_then(|n| extract_identifier(&n, source))?;

    let span = node_to_span(node);
    let params = extract_parameters(node, source);
    let return_type = extract_return_type(node, source);
    let type_parameters = extract_type_parameters(node, source);
    let decorators = extract_decorators(node, source);
    let jsdoc = extract_jsdoc(node, source);
    let accessibility = extract_accessibility(node, source);
    let is_async_fn = is_async(node);
    let is_static_fn = is_static(node);
    let is_abstract_fn = is_abstract(node);
    let is_hook = is_react_hook(&name);

    Some(FunctionInfo {
        name,
        span,
        params,
        return_type,
        type_parameters,
        is_async: is_async_fn,
        is_generator: false,
        is_arrow: false,
        decorators,
        jsdoc,
        accessibility,
        is_static: is_static_fn,
        is_abstract: is_abstract_fn,
        is_react_hook: is_hook,
    })
}

/// Extract arrow function
fn extract_arrow_function(node: &Node, source: &str) -> Option<FunctionInfo> {
    // Arrow functions don't have names in the AST, caller must provide name
    let span = node_to_span(node);
    let params = extract_parameters(node, source);
    let return_type = extract_return_type(node, source);
    let type_parameters = extract_type_parameters(node, source);
    let is_async_fn = is_async(node);

    Some(FunctionInfo {
        name: String::from("<arrow>"),  // Placeholder, will be replaced by caller
        span,
        params,
        return_type,
        type_parameters,
        is_async: is_async_fn,
        is_generator: false,
        is_arrow: true,
        decorators: vec![],
        jsdoc: None,
        accessibility: None,
        is_static: false,
        is_abstract: false,
        is_react_hook: false,
    })
}

/// Extract function expression
fn extract_function_expression(node: &Node, source: &str) -> Option<FunctionInfo> {
    // Function expressions may or may not have names
    let name = find_child_by_field(node, "name")
        .and_then(|n| extract_identifier(&n, source))
        .unwrap_or_else(|| String::from("<anonymous>"));

    let span = node_to_span(node);
    let params = extract_parameters(node, source);
    let return_type = extract_return_type(node, source);
    let type_parameters = extract_type_parameters(node, source);
    let is_async_fn = is_async(node);

    Some(FunctionInfo {
        name,
        span,
        params,
        return_type,
        type_parameters,
        is_async: is_async_fn,
        is_generator: false,
        is_arrow: false,
        decorators: vec![],
        jsdoc: None,
        accessibility: None,
        is_static: false,
        is_abstract: false,
        is_react_hook: false,
    })
}

/// Extract generator function declaration
fn extract_generator_declaration(node: &Node, source: &str) -> Option<FunctionInfo> {
    let name = find_child_by_field(node, "name")
        .and_then(|n| extract_identifier(&n, source))?;

    let span = node_to_span(node);
    let params = extract_parameters(node, source);
    let return_type = extract_return_type(node, source);
    let type_parameters = extract_type_parameters(node, source);
    let is_async_fn = is_async(node);

    Some(FunctionInfo {
        name,
        span,
        params,
        return_type,
        type_parameters,
        is_async: is_async_fn,
        is_generator: true,
        is_arrow: false,
        decorators: vec![],
        jsdoc: None,
        accessibility: None,
        is_static: false,
        is_abstract: false,
        is_react_hook: false,
    })
}

/// Extract function parameters
fn extract_parameters(node: &Node, source: &str) -> Vec<ParameterInfo> {
    let mut params = Vec::new();

    // Find formal_parameters node
    let params_node = find_child_by_kind(node, node_kinds::FORMAL_PARAMETERS);
    if params_node.is_none() {
        return params;
    }
    let params_node = params_node.unwrap();

    for i in 0..params_node.child_count() {
        if let Some(param_node) = params_node.child(i) {
            let param_kind = param_node.kind();

            match param_kind {
                node_kinds::REQUIRED_PARAMETER => {
                    if let Some(info) = extract_parameter(&param_node, source, false, false) {
                        params.push(info);
                    }
                }
                node_kinds::OPTIONAL_PARAMETER => {
                    if let Some(info) = extract_parameter(&param_node, source, true, false) {
                        params.push(info);
                    }
                }
                node_kinds::REST_PARAMETER => {
                    if let Some(info) = extract_parameter(&param_node, source, false, true) {
                        params.push(info);
                    }
                }
                _ => {}
            }
        }
    }

    params
}

/// Extract single parameter info
fn extract_parameter(
    node: &Node,
    source: &str,
    is_optional: bool,
    is_rest: bool,
) -> Option<ParameterInfo> {
    // Extract parameter name (can be identifier or pattern)
    let name = find_child_by_field(node, "pattern")
        .and_then(|n| extract_identifier(&n, source))
        .or_else(|| extract_identifier(node, source))?;

    // Extract type annotation
    let type_annotation = find_child_by_kind(node, node_kinds::TYPE_ANNOTATION)
        .and_then(|n| extract_type_annotation(&n, source));

    // Extract default value (for optional params)
    let default_value = find_child_by_field(node, "value")
        .map(|n| node_text(&n, source).to_string());

    Some(ParameterInfo {
        name,
        type_annotation,
        is_optional,
        is_rest,
        default_value,
    })
}

/// Extract return type annotation
fn extract_return_type(node: &Node, source: &str) -> Option<String> {
    // Look for type_annotation at function level
    find_child_by_kind(node, node_kinds::TYPE_ANNOTATION)
        .and_then(|n| extract_type_annotation(&n, source))
}

/// Extract generic type parameters
fn extract_type_parameters(node: &Node, source: &str) -> Vec<String> {
    let mut type_params = Vec::new();

    if let Some(type_params_node) = find_child_by_kind(node, node_kinds::TYPE_PARAMETERS) {
        for i in 0..type_params_node.child_count() {
            if let Some(param_node) = type_params_node.child(i) {
                if param_node.kind() == node_kinds::TYPE_PARAMETER {
                    let param_text = node_text(&param_node, source).to_string();
                    type_params.push(param_text);
                }
            }
        }
    }

    type_params
}

/// Convert FunctionInfo to JSON attributes
pub fn function_info_to_attrs(info: &FunctionInfo) -> HashMap<String, Value> {
    let mut attrs = HashMap::new();

    if !info.params.is_empty() {
        attrs.insert(
            "parameters".to_string(),
            json!(info.params.iter().map(|p| p.name.clone()).collect::<Vec<_>>()),
        );

        // Parameter details
        let param_details: Vec<Value> = info.params.iter().map(|p| {
            json!({
                "name": p.name,
                "type": p.type_annotation,
                "optional": p.is_optional,
                "rest": p.is_rest,
                "default": p.default_value,
            })
        }).collect();
        attrs.insert("parameter_details".to_string(), json!(param_details));
    }

    if let Some(ref return_type) = info.return_type {
        attrs.insert("return_type".to_string(), json!(return_type));
    }

    if !info.type_parameters.is_empty() {
        attrs.insert("type_parameters".to_string(), json!(info.type_parameters));
    }

    if info.is_async {
        attrs.insert("is_async".to_string(), json!(true));
    }

    if info.is_generator {
        attrs.insert("is_generator".to_string(), json!(true));
    }

    if info.is_arrow {
        attrs.insert("is_arrow".to_string(), json!(true));
    }

    if !info.decorators.is_empty() {
        attrs.insert("decorators".to_string(), json!(info.decorators));
    }

    if let Some(ref accessibility) = info.accessibility {
        attrs.insert("accessibility".to_string(), json!(accessibility.as_str()));
    }

    if info.is_static {
        attrs.insert("is_static".to_string(), json!(true));
    }

    if info.is_abstract {
        attrs.insert("is_abstract".to_string(), json!(true));
    }

    if info.is_react_hook {
        attrs.insert("is_react_hook".to_string(), json!(true));
    }

    attrs
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parameter_info_creation() {
        let param = ParameterInfo {
            name: "foo".to_string(),
            type_annotation: Some("string".to_string()),
            is_optional: true,
            is_rest: false,
            default_value: Some("'bar'".to_string()),
        };

        assert_eq!(param.name, "foo");
        assert_eq!(param.type_annotation, Some("string".to_string()));
        assert!(param.is_optional);
        assert!(!param.is_rest);
    }

    #[test]
    fn test_function_info_to_attrs() {
        let info = FunctionInfo {
            name: "testFunc".to_string(),
            span: Span::new(1, 1, 5, 1),
            params: vec![
                ParameterInfo {
                    name: "x".to_string(),
                    type_annotation: Some("number".to_string()),
                    is_optional: false,
                    is_rest: false,
                    default_value: None,
                },
            ],
            return_type: Some("string".to_string()),
            type_parameters: vec!["T".to_string()],
            is_async: true,
            is_generator: false,
            is_arrow: false,
            decorators: vec!["@log".to_string()],
            jsdoc: None,
            accessibility: Some(Accessibility::Public),
            is_static: false,
            is_abstract: false,
            is_react_hook: false,
        };

        let attrs = function_info_to_attrs(&info);

        assert!(attrs.contains_key("parameters"));
        assert!(attrs.contains_key("return_type"));
        assert!(attrs.contains_key("type_parameters"));
        assert!(attrs.contains_key("is_async"));
        assert!(attrs.contains_key("decorators"));
        assert!(attrs.contains_key("accessibility"));
    }
}
