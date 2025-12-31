//! Language Plugin Port
//!
//! Defines the contract for language-specific parsing plugins.
//! Each language (Python, Java, TypeScript, etc.) implements this trait.

use std::collections::HashMap;
use tree_sitter::{Language as TSLanguage, Node as TSNode, Tree};

use crate::features::parsing::domain::SyntaxKind;
use crate::shared::models::{Edge, Node, NodeKind, Result, Span};

/// Control flow type classification
///
/// Used by BfgVisitor to determine how to process control flow nodes
/// in a language-agnostic way.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ControlFlowType {
    /// If/else conditional
    If,
    /// Loops (for/while/do-while)
    Loop,
    /// Pattern matching (match/switch/when)
    Match,
    /// Exception handling (try/catch/finally)
    Try,
    /// Generator yield
    Yield,
    /// Return statement/expression
    Return,
    /// Break statement/expression
    Break,
    /// Continue statement/expression
    Continue,
    /// Raise/throw statement/expression
    Raise,
}

/// Exception handler components
///
/// Represents the catch and finally blocks of a try-catch-finally construct.
#[derive(Debug, Default)]
pub struct ExceptionHandlers<'a> {
    /// Catch/except blocks (can be multiple)
    pub catch_blocks: Vec<TSNode<'a>>,
    /// Finally block (optional, at most one)
    pub finally_block: Option<TSNode<'a>>,
}

/// Language identifier
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LanguageId {
    Python,
    Java,
    TypeScript,
    JavaScript,
    Kotlin,
    Rust,
    Go,
}

impl LanguageId {
    /// Get language name as string
    pub fn name(&self) -> &'static str {
        match self {
            LanguageId::Python => "python",
            LanguageId::Java => "java",
            LanguageId::TypeScript => "typescript",
            LanguageId::JavaScript => "javascript",
            LanguageId::Kotlin => "kotlin",
            LanguageId::Rust => "rust",
            LanguageId::Go => "go",
        }
    }

    /// Get language from file extension
    pub fn from_extension(ext: &str) -> Option<Self> {
        match ext.to_lowercase().as_str() {
            "py" | "pyi" => Some(LanguageId::Python),
            "java" => Some(LanguageId::Java),
            "ts" | "tsx" => Some(LanguageId::TypeScript),
            "js" | "jsx" | "mjs" | "cjs" => Some(LanguageId::JavaScript),
            "kt" | "kts" => Some(LanguageId::Kotlin),
            "rs" => Some(LanguageId::Rust),
            "go" => Some(LanguageId::Go),
            _ => None,
        }
    }

    /// Get supported file extensions
    pub fn extensions(&self) -> &'static [&'static str] {
        match self {
            LanguageId::Python => &["py", "pyi"],
            LanguageId::Java => &["java"],
            LanguageId::TypeScript => &["ts", "tsx"],
            LanguageId::JavaScript => &["js", "jsx", "mjs", "cjs"],
            LanguageId::Kotlin => &["kt", "kts"],
            LanguageId::Rust => &["rs"],
            LanguageId::Go => &["go"],
        }
    }
}

/// Extraction context passed to extractors
pub struct ExtractionContext<'a> {
    /// Source code
    pub source: &'a str,
    /// File path
    pub file_path: &'a str,
    /// Repository ID
    pub repo_id: &'a str,
    /// Module path (e.g., "foo.bar.baz")
    pub module_path: Option<String>,
    /// Language being parsed
    pub language: LanguageId,
    /// Parent node ID (for nesting)
    pub parent_id: Option<String>,
    /// Current scope (for FQN generation)
    pub scope_stack: Vec<String>,
}

impl<'a> ExtractionContext<'a> {
    pub fn new(
        source: &'a str,
        file_path: &'a str,
        repo_id: &'a str,
        language: LanguageId,
    ) -> Self {
        Self {
            source,
            file_path,
            repo_id,
            module_path: None,
            language,
            parent_id: None,
            scope_stack: Vec::new(),
        }
    }

    /// Get current FQN prefix
    pub fn fqn_prefix(&self) -> String {
        if self.scope_stack.is_empty() {
            self.module_path.clone().unwrap_or_default()
        } else {
            let module = self.module_path.as_deref().unwrap_or("");
            if module.is_empty() {
                self.scope_stack.join(".")
            } else {
                format!("{}.{}", module, self.scope_stack.join("."))
            }
        }
    }

    /// Push scope
    pub fn push_scope(&mut self, name: &str) {
        self.scope_stack.push(name.to_string());
    }

    /// Pop scope
    pub fn pop_scope(&mut self) {
        self.scope_stack.pop();
    }

    /// Get node text from tree-sitter node
    pub fn node_text(&self, node: &TSNode) -> &str {
        self.source.get(node.byte_range()).unwrap_or("")
    }
}

/// Result of extraction from a single file
#[derive(Debug, Default)]
pub struct ExtractionResult {
    /// Extracted nodes
    pub nodes: Vec<Node>,
    /// Extracted edges
    pub edges: Vec<Edge>,
    /// Errors encountered during extraction
    pub errors: Vec<String>,
}

impl ExtractionResult {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn add_node(&mut self, node: Node) {
        self.nodes.push(node);
    }

    pub fn add_edge(&mut self, edge: Edge) {
        self.edges.push(edge);
    }

    pub fn add_error(&mut self, error: impl Into<String>) {
        self.errors.push(error.into());
    }

    pub fn merge(&mut self, other: ExtractionResult) {
        self.nodes.extend(other.nodes);
        self.edges.extend(other.edges);
        self.errors.extend(other.errors);
    }
}

/// Language-specific node kind mapping
pub trait NodeKindMapper: Send + Sync {
    /// Map tree-sitter node kind to IR NodeKind
    fn map_node_kind(&self, ts_kind: &str) -> Option<NodeKind>;

    /// Map tree-sitter node kind to SyntaxKind
    fn map_syntax_kind(&self, ts_kind: &str) -> SyntaxKind;
}

/// Language Plugin trait
///
/// Each supported language implements this trait to provide:
/// - Tree-sitter grammar
/// - Node kind mapping
/// - AST extraction logic
pub trait LanguagePlugin: Send + Sync {
    /// Get the tree-sitter language
    fn tree_sitter_language(&self) -> TSLanguage;

    /// Get the language identifier
    fn language_id(&self) -> LanguageId;

    /// Get supported file extensions
    fn extensions(&self) -> &[&str] {
        self.language_id().extensions()
    }

    /// Check if this plugin supports a file extension
    fn supports(&self, ext: &str) -> bool {
        self.extensions()
            .iter()
            .any(|e| e.eq_ignore_ascii_case(ext))
    }

    /// Map tree-sitter node kind to IR NodeKind
    fn map_node_kind(&self, ts_kind: &str) -> Option<NodeKind>;

    /// Map tree-sitter node kind to SyntaxKind
    fn map_syntax_kind(&self, ts_kind: &str) -> SyntaxKind;

    /// Extract IR nodes and edges from parsed tree
    fn extract(&self, ctx: &mut ExtractionContext, tree: &Tree) -> Result<ExtractionResult>;

    /// Get language-specific comment patterns
    fn comment_patterns(&self) -> &[&str] {
        &["#", "//", "/*"]
    }

    /// Check if a name is public/exported
    fn is_public(&self, name: &str) -> bool {
        // Default: names not starting with underscore are public
        !name.starts_with('_')
    }

    /// Get docstring from node (language-specific)
    fn extract_docstring(&self, node: &TSNode, source: &str) -> Option<String> {
        None // Default: no docstring extraction
    }

    // ========================================
    // BFG (Basic Flow Graph) Support
    // ========================================

    /// Check if a tree-sitter node is a statement
    ///
    /// Used by BFG builder to identify statement boundaries for block splitting.
    /// Each language has different statement node types (e.g., assignment, declaration).
    ///
    /// # Examples
    /// - Python: "assignment", "augmented_assignment", "expression_statement"
    /// - Kotlin: "property_declaration", "assignment"
    /// - Rust: "let_declaration", "assignment_expression"
    fn is_statement_node(&self, node: &TSNode) -> bool;

    /// Check if a tree-sitter node is a control flow construct
    ///
    /// Used by BFG builder to identify control flow boundaries (if/else/match/loop).
    /// Each language has different control flow node types.
    ///
    /// # Examples
    /// - Python: "if_statement", "for_statement", "while_statement"
    /// - Kotlin: "if_expression", "when_expression"
    /// - Rust: "if_expression", "match_expression"
    fn is_control_flow_node(&self, node: &TSNode) -> bool;

    /// Get the body node of a control flow construct
    ///
    /// For example:
    /// - if_statement -> body node
    /// - for_statement -> body node
    /// - while_statement -> body node
    ///
    /// Returns None if node is not a control flow construct or has no body.
    fn get_control_flow_body<'a>(&self, node: &TSNode<'a>) -> Option<TSNode<'a>> {
        // Default implementation: look for common body field names
        node.child_by_field_name("body")
            .or_else(move || node.child_by_field_name("consequence"))
            .or_else(move || node.child_by_field_name("then"))
    }

    /// Get the else/alternative node of a control flow construct
    ///
    /// For example:
    /// - if_statement -> else_clause
    /// - match_expression -> match arms
    ///
    /// Returns None if no alternative branch exists.
    fn get_control_flow_alternative<'a>(&self, node: &TSNode<'a>) -> Option<TSNode<'a>> {
        // Default implementation: look for common alternative field names
        node.child_by_field_name("alternative")
            .or_else(move || node.child_by_field_name("else"))
            .or_else(move || node.child_by_field_name("else_clause"))
    }

    // ========================================
    // Advanced Control Flow Analysis
    // ========================================

    /// Get control flow type classification
    ///
    /// Classifies a control flow node into one of the standard types.
    /// Returns None if the node is not a control flow construct.
    ///
    /// # Examples
    /// - Python: if_statement -> ControlFlowType::If
    /// - Rust: match_expression -> ControlFlowType::Match
    /// - Java: try_statement -> ControlFlowType::Try
    fn get_control_flow_type(&self, node: &TSNode) -> Option<ControlFlowType> {
        // Default implementation: basic pattern matching
        match node.kind() {
            "if_statement" | "if_expression" => Some(ControlFlowType::If),
            "for_statement" | "while_statement" | "do_while_statement" | "loop_expression" => {
                Some(ControlFlowType::Loop)
            }
            "match_expression" | "switch_statement" | "when_expression" => {
                Some(ControlFlowType::Match)
            }
            "try_statement" | "try_expression" => Some(ControlFlowType::Try),
            _ => None,
        }
    }

    /// Get condition node for if/while/for statements
    ///
    /// Returns the condition expression that determines branch execution.
    ///
    /// # Examples
    /// - if (x > 0) -> "x > 0" node
    /// - while (i < 10) -> "i < 10" node
    fn get_control_flow_condition<'a>(&self, node: &TSNode<'a>) -> Option<TSNode<'a>> {
        node.child_by_field_name("condition")
    }

    /// Get loop iterator/range nodes
    ///
    /// Returns the iteration specification for for loops.
    ///
    /// # Examples
    /// - Python: for x in items -> ["x", "items"]
    /// - Rust: for x in 0..10 -> ["x", "0..10"]
    ///
    /// Returns empty vec for while loops or non-loop constructs.
    fn get_loop_iterator<'a>(&self, node: &TSNode<'a>) -> Vec<TSNode<'a>> {
        let mut result = Vec::new();
        if let Some(left) = node.child_by_field_name("left") {
            result.push(left);
        }
        if let Some(right) = node.child_by_field_name("right") {
            result.push(right);
        }
        // For languages with different field names, override this method
        result
    }

    /// Get match/switch/when arms
    ///
    /// Returns all case/arm nodes for pattern matching constructs.
    ///
    /// # Examples
    /// - Rust match: match_expression -> [match_arm, match_arm, ...]
    /// - Kotlin when: when_expression -> [when_entry, when_entry, ...]
    /// - Java switch: switch_expression -> [case_clause, case_clause, ...]
    fn get_match_arms<'a>(&self, node: &TSNode<'a>) -> Vec<TSNode<'a>> {
        // Default implementation: iterate children and collect arms
        let mut arms = Vec::new();
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            match child.kind() {
                "match_arm" | "when_entry" | "case_clause" | "default_clause"
                | "communication_case" | "expression_case" | "type_case" | "default_case" => {
                    arms.push(child);
                }
                _ => {}
            }
        }
        arms
    }

    /// Get exception handlers (catch and finally blocks)
    ///
    /// Extracts catch/except and finally blocks from try statements.
    ///
    /// # Examples
    /// - Python: try_statement -> ExceptionHandlers { catch: [except_clause, ...], finally: Some(...) }
    /// - Java: try_statement -> ExceptionHandlers { catch: [catch_clause, ...], finally: Some(finally_clause) }
    fn get_exception_handlers<'a>(&self, node: &TSNode<'a>) -> ExceptionHandlers<'a> {
        let mut handlers = ExceptionHandlers::default();

        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            match child.kind() {
                // Python/Java/TypeScript catch variants
                "except_clause" | "catch_clause" | "catch_block" => {
                    handlers.catch_blocks.push(child);
                }
                // Python/Java/TypeScript finally variants
                "finally_clause" | "finally_block" => {
                    handlers.finally_block = Some(child);
                }
                _ => {}
            }
        }

        handlers
    }

    /// Check if alternative is chained condition (elif/else if)
    ///
    /// Determines if an else branch is actually a chained if statement.
    ///
    /// # Examples
    /// - Python: elif_clause -> true
    /// - TypeScript: if_statement (inside else) -> true
    /// - Else block: -> false
    fn is_chained_condition(&self, node: &TSNode) -> bool {
        // Default: check for common elif/else-if patterns
        matches!(node.kind(), "elif_clause" | "else_if_clause") ||
        // Also check if it's an if_statement/if_expression (nested in else)
        (matches!(node.kind(), "if_statement" | "if_expression") &&
         node.parent().map(|p| matches!(p.kind(), "else_clause" | "alternative")).unwrap_or(false))
    }
}

/// Registry for language plugins
pub struct LanguageRegistry {
    plugins: HashMap<LanguageId, Box<dyn LanguagePlugin>>,
}

impl LanguageRegistry {
    pub fn new() -> Self {
        Self {
            plugins: HashMap::new(),
        }
    }

    /// Register a language plugin
    pub fn register(&mut self, plugin: Box<dyn LanguagePlugin>) {
        self.plugins.insert(plugin.language_id(), plugin);
    }

    /// Get plugin by language ID
    pub fn get(&self, lang: LanguageId) -> Option<&dyn LanguagePlugin> {
        self.plugins.get(&lang).map(|p| p.as_ref())
    }

    /// Get plugin by file extension
    pub fn get_by_extension(&self, ext: &str) -> Option<&dyn LanguagePlugin> {
        let lang = LanguageId::from_extension(ext)?;
        self.get(lang)
    }

    /// Get all registered plugins
    pub fn all(&self) -> impl Iterator<Item = &dyn LanguagePlugin> {
        self.plugins.values().map(|p| p.as_ref())
    }

    /// Check if any plugin supports the extension
    pub fn supports(&self, ext: &str) -> bool {
        self.get_by_extension(ext).is_some()
    }
}

impl Default for LanguageRegistry {
    fn default() -> Self {
        Self::new()
    }
}

/// Helper trait for extracting spans from tree-sitter nodes
pub trait SpanExt {
    fn to_span(&self) -> Span;
}

impl SpanExt for TSNode<'_> {
    fn to_span(&self) -> Span {
        Span::new(
            self.start_position().row as u32 + 1,
            self.start_position().column as u32,
            self.end_position().row as u32 + 1,
            self.end_position().column as u32,
        )
    }
}

/// Helper for generating unique IDs
pub struct IdGenerator {
    prefix: String,
    counter: u64,
}

impl IdGenerator {
    pub fn new(prefix: impl Into<String>) -> Self {
        Self {
            prefix: prefix.into(),
            counter: 0,
        }
    }

    pub fn next(&mut self, kind: &str) -> String {
        self.counter += 1;
        format!("{}:{}:{}", self.prefix, kind, self.counter)
    }

    pub fn next_node(&mut self) -> String {
        self.next("node")
    }

    pub fn next_edge(&mut self) -> String {
        self.next("edge")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_language_id_from_extension() {
        assert_eq!(LanguageId::from_extension("py"), Some(LanguageId::Python));
        assert_eq!(LanguageId::from_extension("java"), Some(LanguageId::Java));
        assert_eq!(
            LanguageId::from_extension("ts"),
            Some(LanguageId::TypeScript)
        );
        assert_eq!(
            LanguageId::from_extension("tsx"),
            Some(LanguageId::TypeScript)
        );
        assert_eq!(LanguageId::from_extension("kt"), Some(LanguageId::Kotlin));
        assert_eq!(LanguageId::from_extension("rs"), Some(LanguageId::Rust));
        assert_eq!(LanguageId::from_extension("go"), Some(LanguageId::Go));
        assert_eq!(LanguageId::from_extension("unknown"), None);
    }

    #[test]
    fn test_extraction_context_fqn() {
        let source = "test code";
        let mut ctx = ExtractionContext::new(source, "test.py", "repo", LanguageId::Python);
        ctx.module_path = Some("foo.bar".to_string());

        assert_eq!(ctx.fqn_prefix(), "foo.bar");

        ctx.push_scope("MyClass");
        assert_eq!(ctx.fqn_prefix(), "foo.bar.MyClass");

        ctx.push_scope("method");
        assert_eq!(ctx.fqn_prefix(), "foo.bar.MyClass.method");

        ctx.pop_scope();
        assert_eq!(ctx.fqn_prefix(), "foo.bar.MyClass");
    }

    #[test]
    fn test_id_generator() {
        let mut gen = IdGenerator::new("repo:file");
        assert_eq!(gen.next_node(), "repo:file:node:1");
        assert_eq!(gen.next_node(), "repo:file:node:2");
        assert_eq!(gen.next_edge(), "repo:file:edge:3");
    }
}
