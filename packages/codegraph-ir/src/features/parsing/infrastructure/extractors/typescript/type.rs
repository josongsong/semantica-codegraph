//! TypeScript Type Extractor
//!
//! Extracts type information from TypeScript AST:
//! - Simple types (string, number, etc.)
//! - Generic types (Array<T>, Map<K, V>)
//! - Union types (A | B | C)
//! - Intersection types (A & B & C)
//! - Tuple types ([string, number])
//! - Function types ((x: number) => string)
//! - Object types ({x: number, y: string})
//!
//! No hardcoded strings - uses constants from node_kinds

use tree_sitter::Node;
use super::common::*;
use crate::features::parsing::infrastructure::tree_sitter::languages::typescript::node_kinds;

/// Extract type annotation from type_annotation node
pub fn extract_type_annotation(node: &Node, source: &str) -> Option<String> {
    if node.kind() != node_kinds::TYPE_ANNOTATION {
        return None;
    }

    // Type annotation contains the actual type as a child
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            // Skip the ':' token
            if child.kind() != ":" {
                return Some(extract_type(&child, source));
            }
        }
    }

    None
}

/// Extract type from any type node
pub fn extract_type(node: &Node, source: &str) -> String {
    let kind = node.kind();

    match kind {
        // Simple types
        node_kinds::TYPE_IDENTIFIER => extract_identifier(node, source).unwrap_or_default(),
        node_kinds::PREDEFINED_TYPE => node_text(node, source).to_string(),

        // Generic types: Array<T>, Map<K, V>
        node_kinds::GENERIC_TYPE => extract_generic_type(node, source),

        // Union types: A | B | C
        node_kinds::UNION_TYPE => extract_union_type(node, source),

        // Intersection types: A & B & C
        node_kinds::INTERSECTION_TYPE => extract_intersection_type(node, source),

        // Tuple types: [string, number]
        node_kinds::TUPLE_TYPE => extract_tuple_type(node, source),

        // Array types: string[]
        node_kinds::ARRAY_TYPE => extract_array_type(node, source),

        // Function types: (x: number) => string
        node_kinds::FUNCTION_TYPE => extract_function_type(node, source),

        // Object types: {x: number, y: string}
        node_kinds::OBJECT_TYPE => extract_object_type(node, source),

        // Fallback: use raw text
        _ => node_text(node, source).to_string(),
    }
}

/// Extract generic type: Array<T>, Map<K, V>
fn extract_generic_type(node: &Node, source: &str) -> String {
    // Generic type has a name and type_arguments
    let name = find_child_by_kind(node, node_kinds::TYPE_IDENTIFIER)
        .and_then(|n| extract_identifier(&n, source))
        .unwrap_or_else(|| "unknown".to_string());

    // Extract type arguments
    if let Some(type_args_node) = find_child_by_kind(node, "type_arguments") {
        let mut type_args = Vec::new();

        for i in 0..type_args_node.child_count() {
            if let Some(child) = type_args_node.child(i) {
                // Skip < > , tokens
                if !matches!(child.kind(), "<" | ">" | ",") {
                    type_args.push(extract_type(&child, source));
                }
            }
        }

        if !type_args.is_empty() {
            return format!("{}<{}>", name, type_args.join(", "));
        }
    }

    name
}

/// Extract union type: A | B | C
fn extract_union_type(node: &Node, source: &str) -> String {
    let mut types = Vec::new();

    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            // Skip | tokens
            if child.kind() != "|" {
                types.push(extract_type(&child, source));
            }
        }
    }

    types.join(" | ")
}

/// Extract intersection type: A & B & C
fn extract_intersection_type(node: &Node, source: &str) -> String {
    let mut types = Vec::new();

    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            // Skip & tokens
            if child.kind() != "&" {
                types.push(extract_type(&child, source));
            }
        }
    }

    types.join(" & ")
}

/// Extract tuple type: [string, number]
fn extract_tuple_type(node: &Node, source: &str) -> String {
    let mut types = Vec::new();

    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            // Skip [ ] , tokens
            if !matches!(child.kind(), "[" | "]" | ",") {
                types.push(extract_type(&child, source));
            }
        }
    }

    format!("[{}]", types.join(", "))
}

/// Extract array type: string[]
fn extract_array_type(node: &Node, source: &str) -> String {
    // Array type has element_type child
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() != "[" && child.kind() != "]" {
                let element_type = extract_type(&child, source);
                return format!("{}[]", element_type);
            }
        }
    }

    "unknown[]".to_string()
}

/// Extract function type: (x: number) => string
fn extract_function_type(node: &Node, source: &str) -> String {
    // For function types, use raw text for simplicity
    // Full parsing would require parameter extraction
    node_text(node, source).to_string()
}

/// Extract object type: {x: number, y: string}
fn extract_object_type(node: &Node, source: &str) -> String {
    // For object types, use raw text for simplicity
    // Full parsing would require property extraction
    node_text(node, source).to_string()
}

/// Check if a type string is nullable (ends with | null or | undefined)
pub fn is_nullable_type(type_str: &str) -> bool {
    type_str.contains("| null") || type_str.contains("| undefined")
}

/// Decompose union type into components
pub fn decompose_union_type(type_str: &str) -> Vec<String> {
    type_str
        .split('|')
        .map(|s| s.trim().to_string())
        .collect()
}

/// Decompose intersection type into components
pub fn decompose_intersection_type(type_str: &str) -> Vec<String> {
    type_str
        .split('&')
        .map(|s| s.trim().to_string())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_nullable_type() {
        assert!(is_nullable_type("string | null"));
        assert!(is_nullable_type("number | undefined"));
        assert!(is_nullable_type("string | null | undefined"));
        assert!(!is_nullable_type("string"));
    }

    #[test]
    fn test_decompose_union_type() {
        let types = decompose_union_type("string | number | boolean");
        assert_eq!(types, vec!["string", "number", "boolean"]);

        let types = decompose_union_type("A | null");
        assert_eq!(types, vec!["A", "null"]);
    }

    #[test]
    fn test_decompose_intersection_type() {
        let types = decompose_intersection_type("A & B & C");
        assert_eq!(types, vec!["A", "B", "C"]);

        let types = decompose_intersection_type("Base & Mixin");
        assert_eq!(types, vec!["Base", "Mixin"]);
    }
}
