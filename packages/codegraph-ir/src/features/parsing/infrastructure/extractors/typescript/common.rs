//! Common utilities for TypeScript extractors
//!
//! Shared helper functions used across all TypeScript extractors.
//! - Node traversal
//! - Text extraction
//! - Span conversion
//! - Modifier detection

use tree_sitter::Node;
use crate::shared::models::Span;
use crate::features::parsing::infrastructure::tree_sitter::languages::typescript::node_kinds;

/// Convert tree-sitter Node to Span
pub fn node_to_span(node: &Node) -> Span {
    let start_pos = node.start_position();
    let end_pos = node.end_position();

    Span::new(
        (start_pos.row + 1) as u32,  // tree-sitter is 0-indexed, we use 1-indexed
        (start_pos.column + 1) as u32,
        (end_pos.row + 1) as u32,
        (end_pos.column + 1) as u32,
    )
}

/// Extract text from a node
pub fn node_text<'a>(node: &Node, source: &'a str) -> &'a str {
    let start = node.start_byte();
    let end = node.end_byte();
    &source[start..end]
}

/// Find first child of a specific kind
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

/// Find all children of a specific kind
pub fn find_children_by_kind<'a>(node: &'a Node, kind: &str) -> Vec<Node<'a>> {
    let mut children = Vec::new();
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == kind {
                children.push(child);
            }
        }
    }
    children
}

/// Find first child by field name (tree-sitter field)
pub fn find_child_by_field<'a>(node: &'a Node, field_name: &str) -> Option<Node<'a>> {
    node.child_by_field_name(field_name)
}

/// Extract identifier text from a node
/// Handles both direct identifiers and nested property_identifier
pub fn extract_identifier(node: &Node, source: &str) -> Option<String> {
    match node.kind() {
        node_kinds::IDENTIFIER | "property_identifier" => {
            Some(node_text(node, source).to_string())
        }
        _ => {
            // Try to find identifier child
            find_child_by_kind(node, node_kinds::IDENTIFIER)
                .map(|n| node_text(&n, source).to_string())
        }
    }
}

/// Accessibility modifiers
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Accessibility {
    Public,
    Private,
    Protected,
}

impl Accessibility {
    pub fn as_str(&self) -> &'static str {
        match self {
            Accessibility::Public => "public",
            Accessibility::Private => "private",
            Accessibility::Protected => "protected",
        }
    }
}

/// Extract accessibility modifier from node's children
pub fn extract_accessibility(node: &Node, source: &str) -> Option<Accessibility> {
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == node_kinds::ACCESSIBILITY_MODIFIER {
                let text = node_text(&child, source);
                return match text {
                    "public" => Some(Accessibility::Public),
                    "private" => Some(Accessibility::Private),
                    "protected" => Some(Accessibility::Protected),
                    _ => None,
                };
            }
        }
    }
    None
}

/// Check if node has a specific modifier
pub fn has_modifier(node: &Node, modifier_kind: &str) -> bool {
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == modifier_kind {
                return true;
            }
        }
    }
    false
}

/// Check if function/method is async
pub fn is_async(node: &Node) -> bool {
    has_modifier(node, node_kinds::ASYNC)
}

/// Check if member is static
pub fn is_static(node: &Node) -> bool {
    has_modifier(node, node_kinds::STATIC)
}

/// Check if member is readonly
pub fn is_readonly(node: &Node) -> bool {
    has_modifier(node, node_kinds::READONLY)
}

/// Check if member is abstract
pub fn is_abstract(node: &Node) -> bool {
    has_modifier(node, node_kinds::ABSTRACT)
}

/// Extract decorators from a node
pub fn extract_decorators(node: &Node, source: &str) -> Vec<String> {
    let mut decorators = Vec::new();

    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == node_kinds::DECORATOR {
                // Extract decorator name (skip '@' symbol)
                let text = node_text(&child, source);
                if let Some(stripped) = text.strip_prefix('@') {
                    decorators.push(stripped.to_string());
                } else {
                    decorators.push(text.to_string());
                }
            }
        }
    }

    decorators
}

/// Extract comment/JSDoc before a node
/// Returns the first block comment found immediately before the node
pub fn extract_jsdoc(node: &Node, source: &str) -> Option<String> {
    // Look for previous sibling that is a comment
    let parent = node.parent()?;
    let mut found_current = false;

    for i in (0..parent.child_count()).rev() {
        if let Some(child) = parent.child(i) {
            if child.id() == node.id() {
                found_current = true;
                continue;
            }

            if found_current && child.kind() == "comment" {
                let text = node_text(&child, source);
                // Extract JSDoc content (remove /** */ wrapping)
                if text.starts_with("/**") && text.ends_with("*/") {
                    let content = &text[3..text.len()-2];
                    return Some(content.trim().to_string());
                }
                return Some(text.to_string());
            }
        }
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_node_to_span() {
        // This would require creating a tree-sitter tree
        // Actual testing done in integration tests
    }

    #[test]
    fn test_accessibility_as_str() {
        assert_eq!(Accessibility::Public.as_str(), "public");
        assert_eq!(Accessibility::Private.as_str(), "private");
        assert_eq!(Accessibility::Protected.as_str(), "protected");
    }
}
