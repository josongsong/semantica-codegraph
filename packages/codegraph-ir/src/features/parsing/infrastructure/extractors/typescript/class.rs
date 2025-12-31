//! TypeScript Class Extractor
//!
//! Extracts class metadata from TypeScript AST:
//! - Class name, extends, implements
//! - Generic type parameters
//! - Decorators
//! - Access modifiers
//! - Abstract classes

use tree_sitter::Node;
use crate::shared::models::Span;
use std::collections::HashMap;
use serde_json::{Value, json};

use super::common::*;
use crate::features::parsing::infrastructure::tree_sitter::languages::typescript::node_kinds;

/// Class metadata extracted from AST
#[derive(Debug, Clone)]
pub struct ClassInfo {
    pub name: String,
    pub span: Span,
    pub extends: Option<String>,
    pub implements: Vec<String>,
    pub type_parameters: Vec<String>,
    pub decorators: Vec<String>,
    pub jsdoc: Option<String>,
    pub is_abstract: bool,
    pub is_export: bool,
}

/// Extract class info from class_declaration node
pub fn extract_class_info(node: &Node, source: &str) -> Option<ClassInfo> {
    if node.kind() != node_kinds::CLASS_DECLARATION {
        return None;
    }

    let name = find_child_by_field(node, "name")
        .and_then(|n| extract_identifier(&n, source))?;

    let span = node_to_span(node);
    let extends = extract_extends_clause(node, source);
    let implements = extract_implements_clause(node, source);
    let type_parameters = extract_class_type_parameters(node, source);
    let decorators = extract_decorators(node, source);
    let jsdoc = extract_jsdoc(node, source);
    let is_abstract_class = is_abstract(node);

    // Check if class is exported (parent is export_statement)
    let is_export = node.parent()
        .map(|p| p.kind() == node_kinds::EXPORT_STATEMENT)
        .unwrap_or(false);

    Some(ClassInfo {
        name,
        span,
        extends,
        implements,
        type_parameters,
        decorators,
        jsdoc,
        is_abstract: is_abstract_class,
        is_export,
    })
}

/// Extract extends clause (parent class)
fn extract_extends_clause(node: &Node, source: &str) -> Option<String> {
    // Find class_heritage node
    let heritage = find_child_by_kind(node, "class_heritage")?;

    // Find extends_clause
    let extends_node = find_child_by_kind(&heritage, "extends_clause")?;

    // Extract type
    for i in 0..extends_node.child_count() {
        if let Some(child) = extends_node.child(i) {
            if child.kind() != "extends" {
                return Some(node_text(&child, source).to_string());
            }
        }
    }

    None
}

/// Extract implements clause (interfaces)
fn extract_implements_clause(node: &Node, source: &str) -> Vec<String> {
    let mut implements = Vec::new();

    // Find class_heritage node
    if let Some(heritage) = find_child_by_kind(node, "class_heritage") {
        // Find implements_clause
        if let Some(implements_node) = find_child_by_kind(&heritage, "implements_clause") {
            for i in 0..implements_node.child_count() {
                if let Some(child) = implements_node.child(i) {
                    // Skip 'implements' keyword and commas
                    if child.kind() != "implements" && child.kind() != "," {
                        implements.push(node_text(&child, source).to_string());
                    }
                }
            }
        }
    }

    implements
}

/// Extract generic type parameters from class
fn extract_class_type_parameters(node: &Node, source: &str) -> Vec<String> {
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

/// Convert ClassInfo to JSON attributes
pub fn class_info_to_attrs(info: &ClassInfo) -> HashMap<String, Value> {
    let mut attrs = HashMap::new();

    if let Some(ref extends) = info.extends {
        attrs.insert("extends".to_string(), json!(extends));
    }

    if !info.implements.is_empty() {
        attrs.insert("implements".to_string(), json!(info.implements));
    }

    if !info.type_parameters.is_empty() {
        attrs.insert("type_parameters".to_string(), json!(info.type_parameters));
    }

    if !info.decorators.is_empty() {
        attrs.insert("decorators".to_string(), json!(info.decorators));
    }

    if info.is_abstract {
        attrs.insert("is_abstract".to_string(), json!(true));
    }

    if info.is_export {
        attrs.insert("is_export".to_string(), json!(true));
    }

    attrs
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_class_info_creation() {
        let info = ClassInfo {
            name: "MyClass".to_string(),
            span: Span::new(1, 1, 10, 1),
            extends: Some("BaseClass".to_string()),
            implements: vec!["IFoo".to_string(), "IBar".to_string()],
            type_parameters: vec!["T".to_string()],
            decorators: vec!["@Component".to_string()],
            jsdoc: None,
            is_abstract: false,
            is_export: true,
        };

        assert_eq!(info.name, "MyClass");
        assert_eq!(info.extends, Some("BaseClass".to_string()));
        assert_eq!(info.implements.len(), 2);
    }

    #[test]
    fn test_class_info_to_attrs() {
        let info = ClassInfo {
            name: "MyClass".to_string(),
            span: Span::new(1, 1, 10, 1),
            extends: Some("Base".to_string()),
            implements: vec![],
            type_parameters: vec!["T".to_string(), "U extends Base".to_string()],
            decorators: vec!["@Component".to_string()],
            jsdoc: None,
            is_abstract: true,
            is_export: false,
        };

        let attrs = class_info_to_attrs(&info);

        assert!(attrs.contains_key("extends"));
        assert!(attrs.contains_key("type_parameters"));
        assert!(attrs.contains_key("decorators"));
        assert!(attrs.contains_key("is_abstract"));
    }
}
