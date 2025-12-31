//! Type-safe wrappers for specialized node types
//!
//! Uses the Newtype Pattern to provide type safety while wrapping the underlying Node type.
//! This prevents accidentally mixing different semantic types that share the same structure.
//!
//! # Why Newtype Pattern?
//!
//! Before (Type Alias - unsafe):
//! ```ignore
//! pub type TypeEntity = Node;
//! pub type SignatureEntity = Node;
//!
//! fn process_type(t: TypeEntity) { ... }
//! let sig = SignatureEntity { ... };
//! process_type(sig);  // ❌ Compiles but semantically wrong!
//! ```
//!
//! After (Newtype Pattern - type-safe):
//! ```ignore
//! pub struct TypeEntity(Node);
//! pub struct SignatureEntity(Node);
//!
//! fn process_type(t: TypeEntity) { ... }
//! let sig = SignatureEntity(...);
//! process_type(sig);  // ✅ Compile error - types don't match!
//! ```

use super::Node;
use std::ops::{Deref, DerefMut};

/// Type entity wrapper
///
/// Represents a type definition in the codebase (classes, interfaces, type aliases, etc.)
///
/// # Example
/// ```text
/// use codegraph_ir::shared::models::{TypeEntity, Node, NodeKind, Span};
///
/// let node = Node {
///     id: "type:MyClass".to_string(),
///     kind: NodeKind::Class,
///     name: Some("MyClass".to_string()),
///     file_path: "src/main.py".to_string(),
///     span: Span::new(10, 0, 20, 0),
///     language: "python".to_string(),
///     ..Default::default()
/// };
///
/// let type_entity = TypeEntity::new(node);
/// ```
#[derive(Debug, Clone, PartialEq)]
pub struct TypeEntity(Node);

impl TypeEntity {
    /// Create new TypeEntity from Node
    pub fn new(node: Node) -> Self {
        Self(node)
    }

    /// Unwrap into inner Node
    pub fn into_inner(self) -> Node {
        self.0
    }

    /// Get reference to inner Node
    pub fn as_node(&self) -> &Node {
        &self.0
    }

    /// Get mutable reference to inner Node
    pub fn as_node_mut(&mut self) -> &mut Node {
        &mut self.0
    }
}

// Deref to allow direct access to Node fields
impl Deref for TypeEntity {
    type Target = Node;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl DerefMut for TypeEntity {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.0
    }
}

impl From<Node> for TypeEntity {
    fn from(node: Node) -> Self {
        Self(node)
    }
}

impl From<TypeEntity> for Node {
    fn from(entity: TypeEntity) -> Self {
        entity.0
    }
}

/// Signature entity wrapper
///
/// Represents a function/method signature with parameters and return type.
#[derive(Debug, Clone, PartialEq)]
pub struct SignatureEntity(Node);

impl SignatureEntity {
    pub fn new(node: Node) -> Self {
        Self(node)
    }

    pub fn into_inner(self) -> Node {
        self.0
    }

    pub fn as_node(&self) -> &Node {
        &self.0
    }

    pub fn as_node_mut(&mut self) -> &mut Node {
        &mut self.0
    }
}

impl Deref for SignatureEntity {
    type Target = Node;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl DerefMut for SignatureEntity {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.0
    }
}

impl From<Node> for SignatureEntity {
    fn from(node: Node) -> Self {
        Self(node)
    }
}

impl From<SignatureEntity> for Node {
    fn from(entity: SignatureEntity) -> Self {
        entity.0
    }
}

/// Variable entity wrapper
///
/// Represents a variable declaration or assignment.
#[derive(Debug, Clone, PartialEq)]
pub struct VariableEntity(Node);

impl VariableEntity {
    pub fn new(node: Node) -> Self {
        Self(node)
    }

    pub fn into_inner(self) -> Node {
        self.0
    }

    pub fn as_node(&self) -> &Node {
        &self.0
    }

    pub fn as_node_mut(&mut self) -> &mut Node {
        &mut self.0
    }
}

impl Deref for VariableEntity {
    type Target = Node;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl DerefMut for VariableEntity {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.0
    }
}

impl From<Node> for VariableEntity {
    fn from(node: Node) -> Self {
        Self(node)
    }
}

impl From<VariableEntity> for Node {
    fn from(entity: VariableEntity) -> Self {
        entity.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{NodeKind, Span};

    fn create_test_node(id: &str, kind: NodeKind) -> Node {
        Node {
            id: id.to_string(),
            kind,
            name: Some("test".to_string()),
            file_path: "test.py".to_string(),
            span: Span::new(1, 0, 10, 0),
            language: "python".to_string(),
            fqn: "test".to_string(),
            stable_id: None,
            content_hash: None,
            module_path: None,
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        }
    }

    #[test]
    fn test_type_entity_creation() {
        let node = create_test_node("type:TestClass", NodeKind::Class);
        let entity = TypeEntity::new(node.clone());

        assert_eq!(entity.id, node.id);
        assert_eq!(entity.kind, node.kind);
    }

    #[test]
    fn test_signature_entity_deref() {
        let node = create_test_node("func:test_func", NodeKind::Function);
        let entity = SignatureEntity::new(node.clone());

        // Deref allows direct access to Node fields
        assert_eq!(entity.id, "func:test_func");
        assert_eq!(entity.kind, NodeKind::Function);
    }

    #[test]
    fn test_variable_entity_conversion() {
        let node = create_test_node("var:my_var", NodeKind::Variable);
        let entity: VariableEntity = node.clone().into();
        let back: Node = entity.into();

        assert_eq!(back.id, node.id);
    }

    #[test]
    fn test_type_safety() {
        // This test demonstrates that different entity types are not compatible
        let type_node = create_test_node("type:MyClass", NodeKind::Class);
        let sig_node = create_test_node("func:my_func", NodeKind::Function);

        let _type_entity = TypeEntity::new(type_node);
        let _sig_entity = SignatureEntity::new(sig_node);

        // The following would not compile (type mismatch):
        // fn takes_type_entity(_t: TypeEntity) {}
        // takes_type_entity(_sig_entity);  // ❌ Compile error!
    }
}
