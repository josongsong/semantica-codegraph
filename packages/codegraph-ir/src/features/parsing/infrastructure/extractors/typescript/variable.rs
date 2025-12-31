//! TypeScript Variable Extractor

use tree_sitter::Node;
use crate::shared::models::Span;
use std::collections::HashMap;
use serde_json::{Value, json};

use super::common::*;
use super::r#type::extract_type_annotation;
use crate::features::parsing::infrastructure::tree_sitter::languages::typescript::node_kinds;

#[derive(Debug, Clone)]
pub struct VariableInfo {
    pub name: String,
    pub span: Span,
    pub type_annotation: Option<String>,
    pub is_const: bool,
    pub is_let: bool,
    pub is_export: bool,
}

pub fn extract_variable_info(node: &Node, source: &str) -> Vec<VariableInfo> {
    if node.kind() != node_kinds::VARIABLE_DECLARATION {
        return vec![];
    }

    let mut variables = Vec::new();

    // Check declaration kind (const, let, var)
    let is_const = has_modifier(node, "const");
    let is_let = has_modifier(node, "let");

    // Check if exported
    let is_export = node.parent()
        .and_then(|p| p.parent())
        .map(|p| p.kind() == node_kinds::EXPORT_STATEMENT)
        .unwrap_or(false);

    // Extract variable declarators
    let declarators = find_children_by_kind(node, "variable_declarator");

    for declarator in declarators {
        if let Some(name_node) = find_child_by_field(&declarator, "name") {
            if let Some(name) = extract_identifier(&name_node, source) {
                let span = node_to_span(&declarator);

                let type_annotation = find_child_by_kind(&declarator, node_kinds::TYPE_ANNOTATION)
                    .and_then(|n| extract_type_annotation(&n, source));

                variables.push(VariableInfo {
                    name,
                    span,
                    type_annotation,
                    is_const,
                    is_let,
                    is_export,
                });
            }
        }
    }

    variables
}

pub fn variable_info_to_attrs(info: &VariableInfo) -> HashMap<String, Value> {
    let mut attrs = HashMap::new();

    if let Some(ref type_ann) = info.type_annotation {
        attrs.insert("type_annotation".to_string(), json!(type_ann));
    }

    if info.is_const {
        attrs.insert("is_const".to_string(), json!(true));
    } else if info.is_let {
        attrs.insert("is_let".to_string(), json!(true));
    } else {
        attrs.insert("is_var".to_string(), json!(true));
    }

    if info.is_export {
        attrs.insert("is_export".to_string(), json!(true));
    }

    attrs
}
