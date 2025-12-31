//! TypeScript Interface Extractor

use tree_sitter::Node;
use crate::shared::models::Span;
use std::collections::HashMap;
use serde_json::{Value, json};

use super::common::*;
use crate::features::parsing::infrastructure::tree_sitter::languages::typescript::node_kinds;

#[derive(Debug, Clone)]
pub struct InterfaceInfo {
    pub name: String,
    pub span: Span,
    pub extends: Vec<String>,
    pub type_parameters: Vec<String>,
    pub jsdoc: Option<String>,
    pub is_export: bool,
}

pub fn extract_interface_info(node: &Node, source: &str) -> Option<InterfaceInfo> {
    if node.kind() != node_kinds::INTERFACE_DECLARATION {
        return None;
    }

    let name = find_child_by_field(node, "name")
        .and_then(|n| extract_identifier(&n, source))?;

    let span = node_to_span(node);
    let extends = extract_interface_extends(node, source);
    let type_parameters = extract_interface_type_parameters(node, source);
    let jsdoc = extract_jsdoc(node, source);

    let is_export = node.parent()
        .map(|p| p.kind() == node_kinds::EXPORT_STATEMENT)
        .unwrap_or(false);

    Some(InterfaceInfo {
        name,
        span,
        extends,
        type_parameters,
        jsdoc,
        is_export,
    })
}

fn extract_interface_extends(node: &Node, source: &str) -> Vec<String> {
    let mut extends = Vec::new();

    if let Some(extends_clause) = find_child_by_kind(node, "extends_clause") {
        for i in 0..extends_clause.child_count() {
            if let Some(child) = extends_clause.child(i) {
                if child.kind() != "extends" && child.kind() != "," {
                    extends.push(node_text(&child, source).to_string());
                }
            }
        }
    }

    extends
}

fn extract_interface_type_parameters(node: &Node, source: &str) -> Vec<String> {
    let mut type_params = Vec::new();

    if let Some(type_params_node) = find_child_by_kind(node, node_kinds::TYPE_PARAMETERS) {
        for i in 0..type_params_node.child_count() {
            if let Some(param_node) = type_params_node.child(i) {
                if param_node.kind() == node_kinds::TYPE_PARAMETER {
                    type_params.push(node_text(&param_node, source).to_string());
                }
            }
        }
    }

    type_params
}

pub fn interface_info_to_attrs(info: &InterfaceInfo) -> HashMap<String, Value> {
    let mut attrs = HashMap::new();

    if !info.extends.is_empty() {
        attrs.insert("extends".to_string(), json!(info.extends));
    }

    if !info.type_parameters.is_empty() {
        attrs.insert("type_parameters".to_string(), json!(info.type_parameters));
    }

    if info.is_export {
        attrs.insert("is_export".to_string(), json!(true));
    }

    attrs
}
