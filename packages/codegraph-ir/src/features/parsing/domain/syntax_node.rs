//! Language-neutral syntax node representation
//!
//! Abstracts tree-sitter nodes for use in domain logic.

use crate::shared::models::Span;

/// Syntax node kind (language-neutral)
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SyntaxKind {
    // Definitions
    FunctionDef,
    ClassDef,
    MethodDef,
    LambdaDef,

    // Declarations
    VariableDecl,
    ParameterDecl,
    FieldDecl,
    ImportDecl,

    // Expressions
    CallExpr,
    NameExpr,
    AttributeExpr,
    LiteralExpr,
    BinaryExpr,
    UnaryExpr,

    // Statements
    AssignmentStmt,
    ReturnStmt,
    IfStmt,
    ForStmt,
    WhileStmt,
    TryStmt,
    WithStmt,

    // Control flow
    BreakStmt,
    ContinueStmt,
    RaiseStmt,
    YieldExpr,
    AwaitExpr,

    // Other
    Block,
    Comment,
    Decorator,
    TypeAnnotation,

    // Unknown/Other
    Other(String),
}

impl SyntaxKind {
    pub fn is_definition(&self) -> bool {
        matches!(
            self,
            SyntaxKind::FunctionDef
                | SyntaxKind::ClassDef
                | SyntaxKind::MethodDef
                | SyntaxKind::LambdaDef
        )
    }

    pub fn is_declaration(&self) -> bool {
        matches!(
            self,
            SyntaxKind::VariableDecl
                | SyntaxKind::ParameterDecl
                | SyntaxKind::FieldDecl
                | SyntaxKind::ImportDecl
        )
    }

    pub fn is_control_flow(&self) -> bool {
        matches!(
            self,
            SyntaxKind::IfStmt
                | SyntaxKind::ForStmt
                | SyntaxKind::WhileStmt
                | SyntaxKind::TryStmt
                | SyntaxKind::BreakStmt
                | SyntaxKind::ContinueStmt
                | SyntaxKind::ReturnStmt
                | SyntaxKind::RaiseStmt
        )
    }
}

/// Language-neutral syntax node
#[derive(Debug, Clone)]
pub struct SyntaxNode {
    pub kind: SyntaxKind,
    pub span: Span,
    pub text: Option<String>,
    pub children: Vec<SyntaxNode>,

    /// Original tree-sitter kind (for debugging)
    pub raw_kind: Option<String>,
}

impl SyntaxNode {
    pub fn new(kind: SyntaxKind, span: Span) -> Self {
        Self {
            kind,
            span,
            text: None,
            children: Vec::new(),
            raw_kind: None,
        }
    }

    pub fn with_text(mut self, text: impl Into<String>) -> Self {
        self.text = Some(text.into());
        self
    }

    pub fn with_children(mut self, children: Vec<SyntaxNode>) -> Self {
        self.children = children;
        self
    }

    pub fn with_raw_kind(mut self, raw_kind: impl Into<String>) -> Self {
        self.raw_kind = Some(raw_kind.into());
        self
    }

    /// Find first child of given kind
    pub fn find_child(&self, kind: &SyntaxKind) -> Option<&SyntaxNode> {
        self.children.iter().find(|c| &c.kind == kind)
    }

    /// Find all children of given kind
    pub fn find_children(&self, kind: &SyntaxKind) -> Vec<&SyntaxNode> {
        self.children.iter().filter(|c| &c.kind == kind).collect()
    }

    /// Get text content
    pub fn text(&self) -> &str {
        self.text.as_deref().unwrap_or("")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_syntax_kind_is_definition() {
        assert!(SyntaxKind::FunctionDef.is_definition());
        assert!(SyntaxKind::ClassDef.is_definition());
        assert!(!SyntaxKind::CallExpr.is_definition());
    }
}
