//! TypeScript Import/Export Extractor
//!
//! Handles ESM imports/exports:
//! - Named imports: import { foo, bar } from 'module'
//! - Default imports: import foo from 'module'
//! - Namespace imports: import * as foo from 'module'
//! - Import with alias: import { foo as bar } from 'module'

use tree_sitter::Node;
use crate::shared::models::Span;
use std::collections::HashMap;
use serde_json::{Value, json};

use super::common::*;
use crate::features::parsing::infrastructure::tree_sitter::languages::typescript::node_kinds;

#[derive(Debug, Clone)]
pub struct ImportInfo {
    pub span: Span,
    pub source_module: String,
    pub imported_symbols: Vec<ImportedSymbol>,
    pub is_type_only: bool,
}

#[derive(Debug, Clone)]
pub struct ImportedSymbol {
    pub name: String,
    pub alias: Option<String>,
    pub is_default: bool,
    pub is_namespace: bool,
}

pub fn extract_import_info(node: &Node, source: &str) -> Option<ImportInfo> {
    if node.kind() != node_kinds::IMPORT_STATEMENT {
        return None;
    }

    let span = node_to_span(node);

    // Extract source module (string literal)
    let source_module = find_child_by_kind(node, node_kinds::STRING)
        .map(|n| {
            let text = node_text(&n, source);
            // Remove quotes
            text.trim_matches(|c| c == '\'' || c == '"').to_string()
        })?;

    // Check if type-only import
    let is_type_only = node_text(node, source).contains("import type");

    // Extract import clause
    let imported_symbols = if let Some(import_clause) = find_child_by_kind(node, node_kinds::IMPORT_CLAUSE) {
        extract_import_clause(&import_clause, source)
    } else {
        vec![]
    };

    Some(ImportInfo {
        span,
        source_module,
        imported_symbols,
        is_type_only,
    })
}

fn extract_import_clause(node: &Node, source: &str) -> Vec<ImportedSymbol> {
    let mut symbols = Vec::new();

    // Check for default import (identifier directly in import_clause)
    if let Some(default_import) = find_child_by_kind(node, node_kinds::IDENTIFIER) {
        symbols.push(ImportedSymbol {
            name: node_text(&default_import, source).to_string(),
            alias: None,
            is_default: true,
            is_namespace: false,
        });
    }

    // Check for namespace import (import * as foo)
    if let Some(namespace_import) = find_child_by_kind(node, node_kinds::NAMESPACE_IMPORT) {
        if let Some(ident) = find_child_by_kind(&namespace_import, node_kinds::IDENTIFIER) {
            symbols.push(ImportedSymbol {
                name: "*".to_string(),
                alias: Some(node_text(&ident, source).to_string()),
                is_default: false,
                is_namespace: true,
            });
        }
    }

    // Check for named imports
    if let Some(named_imports) = find_child_by_kind(node, node_kinds::NAMED_IMPORTS) {
        let specifiers = find_children_by_kind(&named_imports, node_kinds::IMPORT_SPECIFIER);

        for specifier in specifiers {
            let name_node = find_child_by_field(&specifier, "name")
                .or_else(|| find_child_by_kind(&specifier, node_kinds::IDENTIFIER));

            if let Some(name_node) = name_node {
                let name = node_text(&name_node, source).to_string();

                // Check for alias
                let alias = find_child_by_field(&specifier, "alias")
                    .map(|n| node_text(&n, source).to_string());

                symbols.push(ImportedSymbol {
                    name,
                    alias,
                    is_default: false,
                    is_namespace: false,
                });
            }
        }
    }

    symbols
}

pub fn import_info_to_attrs(info: &ImportInfo) -> HashMap<String, Value> {
    let mut attrs = HashMap::new();

    attrs.insert("source_module".to_string(), json!(info.source_module));

    if !info.imported_symbols.is_empty() {
        let symbols: Vec<Value> = info.imported_symbols.iter().map(|s| {
            json!({
                "name": s.name,
                "alias": s.alias,
                "is_default": s.is_default,
                "is_namespace": s.is_namespace,
            })
        }).collect();
        attrs.insert("imported_symbols".to_string(), json!(symbols));
    }

    if info.is_type_only {
        attrs.insert("is_type_only".to_string(), json!(true));
    }

    attrs
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_imported_symbol_creation() {
        let symbol = ImportedSymbol {
            name: "foo".to_string(),
            alias: Some("bar".to_string()),
            is_default: false,
            is_namespace: false,
        };

        assert_eq!(symbol.name, "foo");
        assert_eq!(symbol.alias, Some("bar".to_string()));
        assert!(!symbol.is_default);
    }
}
