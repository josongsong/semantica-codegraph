//! Tree-sitter parser implementation
//!
//! This is where tree-sitter dependency lives.

use tree_sitter::{Parser as TSParser, Tree};

use crate::features::parsing::domain::{ParseError, ParsedTree, SyntaxKind, SyntaxNode};
use crate::features::parsing::ports::Parser;
use crate::shared::models::{CodegraphError, Result, Span};

/// Tree-sitter based parser
pub struct TreeSitterParser {
    language: TreeSitterLanguage,
}

/// Supported tree-sitter languages
#[derive(Debug, Clone, Copy)]
pub enum TreeSitterLanguage {
    Python,
    // TypeScript, JavaScript, etc. (future)
}

impl TreeSitterParser {
    /// Create a Python parser
    pub fn python() -> Self {
        Self {
            language: TreeSitterLanguage::Python,
        }
    }

    /// Get the tree-sitter language
    fn get_ts_language(&self) -> tree_sitter::Language {
        match self.language {
            TreeSitterLanguage::Python => tree_sitter_python::language(),
        }
    }

    /// Convert tree-sitter tree to our domain model
    fn convert_tree(&self, tree: &Tree, source: &str, file_path: &str) -> ParsedTree {
        let root_node = tree.root_node();
        let root = self.convert_node(&root_node, source);

        let mut errors = Vec::new();
        self.collect_errors(&root_node, source, &mut errors);

        ParsedTree::new(
            root,
            source.to_string(),
            file_path.to_string(),
            self.language_name().to_string(),
        )
        .with_errors(errors)
    }

    /// Convert a tree-sitter node to SyntaxNode
    fn convert_node(&self, node: &tree_sitter::Node, source: &str) -> SyntaxNode {
        let kind = self.map_node_kind(node.kind());
        let span = Span::new(
            node.start_position().row as u32 + 1,
            node.start_position().column as u32,
            node.end_position().row as u32 + 1,
            node.end_position().column as u32,
        );

        let text = if node.child_count() == 0 {
            Some(source.get(node.byte_range()).unwrap_or("").to_string())
        } else {
            None
        };

        let children: Vec<SyntaxNode> = (0..node.child_count())
            .filter_map(|i| node.child(i))
            .filter(|c| !c.is_extra()) // Skip comments, etc.
            .map(|c| self.convert_node(&c, source))
            .collect();

        SyntaxNode::new(kind, span)
            .with_raw_kind(node.kind())
            .with_children(children)
            .with_text(text.unwrap_or_default())
    }

    /// Map tree-sitter node kind to our SyntaxKind
    fn map_node_kind(&self, ts_kind: &str) -> SyntaxKind {
        match ts_kind {
            // Definitions
            "function_definition" => SyntaxKind::FunctionDef,
            "class_definition" => SyntaxKind::ClassDef,
            "lambda" => SyntaxKind::LambdaDef,

            // Declarations
            "assignment" => SyntaxKind::AssignmentStmt,
            "parameter" | "default_parameter" | "typed_parameter" => SyntaxKind::ParameterDecl,
            "import_statement" | "import_from_statement" => SyntaxKind::ImportDecl,

            // Expressions
            "call" => SyntaxKind::CallExpr,
            "identifier" => SyntaxKind::NameExpr,
            "attribute" => SyntaxKind::AttributeExpr,
            "string" | "integer" | "float" | "true" | "false" | "none" => SyntaxKind::LiteralExpr,
            "binary_operator" | "comparison_operator" | "boolean_operator" => {
                SyntaxKind::BinaryExpr
            }
            "unary_operator" | "not_operator" => SyntaxKind::UnaryExpr,

            // Statements
            "return_statement" => SyntaxKind::ReturnStmt,
            "if_statement" => SyntaxKind::IfStmt,
            "for_statement" => SyntaxKind::ForStmt,
            "while_statement" => SyntaxKind::WhileStmt,
            "try_statement" => SyntaxKind::TryStmt,
            "with_statement" => SyntaxKind::WithStmt,

            // Control flow
            "break_statement" => SyntaxKind::BreakStmt,
            "continue_statement" => SyntaxKind::ContinueStmt,
            "raise_statement" => SyntaxKind::RaiseStmt,
            "yield" => SyntaxKind::YieldExpr,
            "await" => SyntaxKind::AwaitExpr,

            // Other
            "block" | "module" => SyntaxKind::Block,
            "comment" => SyntaxKind::Comment,
            "decorator" => SyntaxKind::Decorator,
            "type" => SyntaxKind::TypeAnnotation,

            // Unknown
            other => SyntaxKind::Other(other.to_string()),
        }
    }

    /// Collect parse errors
    fn collect_errors(&self, node: &tree_sitter::Node, source: &str, errors: &mut Vec<ParseError>) {
        if node.is_error() || node.is_missing() {
            let span = Span::new(
                node.start_position().row as u32 + 1,
                node.start_position().column as u32,
                node.end_position().row as u32 + 1,
                node.end_position().column as u32,
            );
            errors.push(ParseError {
                message: format!("Parse error at {:?}", node.kind()),
                span,
            });
        }

        for i in 0..node.child_count() {
            if let Some(child) = node.child(i) {
                self.collect_errors(&child, source, errors);
            }
        }
    }
}

impl Parser for TreeSitterParser {
    fn parse(&self, source: &str, file_path: &str) -> Result<ParsedTree> {
        let mut parser = TSParser::new();
        parser
            .set_language(&self.get_ts_language())
            .map_err(|e| CodegraphError::parse(format!("Failed to set language: {}", e)))?;

        let tree = parser
            .parse(source, None)
            .ok_or_else(|| CodegraphError::parse("Failed to parse source code"))?;

        Ok(self.convert_tree(&tree, source, file_path))
    }

    fn supports_extension(&self, ext: &str) -> bool {
        match self.language {
            TreeSitterLanguage::Python => matches!(ext, "py" | "pyi"),
        }
    }

    fn language_name(&self) -> &'static str {
        match self.language {
            TreeSitterLanguage::Python => "python",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_python_function() {
        let parser = TreeSitterParser::python();
        let source = "def hello():\n    pass";
        let result = parser.parse(source, "test.py");

        assert!(result.is_ok());
        let tree = result.unwrap();
        assert!(!tree.has_errors);
    }

    #[test]
    fn test_parse_python_class() {
        let parser = TreeSitterParser::python();
        let source = "class Foo:\n    def bar(self):\n        pass";
        let result = parser.parse(source, "test.py");

        assert!(result.is_ok());
    }
}
