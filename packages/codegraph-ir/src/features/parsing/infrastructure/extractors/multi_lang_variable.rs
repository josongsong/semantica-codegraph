//! Multi-language variable extraction
//!
//! Provides a plugin-based architecture for extracting variable assignments
//! across different programming languages.
//!
//! Architecture:
//! - `VariableExtractor` trait: Common interface for all languages
//! - Language-specific implementations: Python, TypeScript, Java, Kotlin, Rust, Go
//! - Common utilities: Shared logic for span extraction, type annotation parsing

use crate::shared::models::Span;
use tree_sitter::Node;

/// Variable assignment metadata
#[derive(Debug, Clone)]
pub struct VariableAssignment {
    pub name: String,
    pub span: Span,
    pub type_annotation: Option<String>,
    pub value_text: Option<String>,
}

/// Common interface for variable extraction across languages
pub trait VariableExtractor {
    /// Extract all variable assignments from a block
    fn extract_variables(&self, block_node: &Node, source: &str) -> Vec<VariableAssignment>;

    /// Check if a node is a variable assignment
    fn is_assignment(&self, node: &Node) -> bool;

    /// Extract variable name from assignment node
    fn extract_name(&self, node: &Node, source: &str) -> Option<String>;

    /// Extract type annotation if present
    fn extract_type(&self, node: &Node, source: &str) -> Option<String> {
        // Default: no type annotation
        None
    }
}

// ========================================
// Python Variable Extractor
// ========================================

pub struct PythonVariableExtractor;

impl PythonVariableExtractor {
    pub fn new() -> Self {
        Self
    }

    /// Recursive traversal for Python assignments
    fn traverse_for_assignments(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        match node.kind() {
            "assignment" => {
                self.extract_assignment(node, source, variables);
            }
            // Walrus operator: (n := len(x))
            "named_expression" => {
                self.extract_named_expression(node, source, variables);
            }
            "expression_statement" => {
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        match child.kind() {
                            "assignment" => self.extract_assignment(&child, source, variables),
                            "augmented_assignment" => {
                                self.extract_augmented_assignment(&child, source, variables)
                            }
                            "named_expression" => {
                                self.extract_named_expression(&child, source, variables)
                            }
                            _ => {}
                        }
                    }
                }
            }
            "if_statement" | "elif_clause" | "else_clause" | "for_statement"
            | "while_statement" | "try_statement" | "except_clause" | "finally_clause"
            | "with_statement" | "match_statement" | "case_clause" => {
                // Recurse into control flow blocks (including conditions for walrus operator)
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        self.traverse_for_assignments(&child, source, variables);
                    }
                }
            }
            // Also traverse into comparison and other expressions (for walrus operator)
            "comparison_operator" | "boolean_operator" | "parenthesized_expression" => {
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        self.traverse_for_assignments(&child, source, variables);
                    }
                }
            }
            _ => {
                // Recurse into other nodes
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        self.traverse_for_assignments(&child, source, variables);
                    }
                }
            }
        }
    }

    fn extract_assignment(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        if let Some(left) = node.child_by_field_name("left") {
            if left.kind() == "identifier" {
                if let Some(name) = self.extract_name(&left, source) {
                    let span = node_to_span(&left);
                    let type_annotation = self.extract_type(node, source);
                    let value_text = node
                        .child_by_field_name("right")
                        .and_then(|r| r.utf8_text(source.as_bytes()).ok())
                        .map(|s| s.to_string());

                    variables.push(VariableAssignment {
                        name,
                        span,
                        type_annotation,
                        value_text,
                    });
                }
            }
        }
    }

    fn extract_augmented_assignment(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        if let Some(left) = node.child_by_field_name("left") {
            if left.kind() == "identifier" {
                if let Some(name) = self.extract_name(&left, source) {
                    let span = node_to_span(&left);
                    variables.push(VariableAssignment {
                        name,
                        span,
                        type_annotation: None,
                        value_text: None,
                    });
                }
            }
        }
    }

    fn extract_named_expression(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        // Walrus operator: (name := value)
        // name field contains the identifier
        if let Some(name_node) = node.child_by_field_name("name") {
            if let Some(name) = self.extract_name(&name_node, source) {
                let span = node_to_span(&name_node);
                let value_text = node
                    .child_by_field_name("value")
                    .and_then(|v| v.utf8_text(source.as_bytes()).ok())
                    .map(|s| s.to_string());

                variables.push(VariableAssignment {
                    name,
                    span,
                    type_annotation: None,
                    value_text,
                });
            }
        }
    }
}

impl VariableExtractor for PythonVariableExtractor {
    fn extract_variables(&self, block_node: &Node, source: &str) -> Vec<VariableAssignment> {
        let mut variables = Vec::new();
        self.traverse_for_assignments(block_node, source, &mut variables);
        variables
    }

    fn is_assignment(&self, node: &Node) -> bool {
        matches!(
            node.kind(),
            "assignment" | "augmented_assignment" | "named_expression"
        )
    }

    fn extract_name(&self, node: &Node, source: &str) -> Option<String> {
        node.utf8_text(source.as_bytes())
            .ok()
            .map(|s| s.to_string())
    }

    fn extract_type(&self, node: &Node, source: &str) -> Option<String> {
        node.child_by_field_name("type")
            .and_then(|t| t.utf8_text(source.as_bytes()).ok())
            .map(|s| s.to_string())
    }
}

// ========================================
// TypeScript Variable Extractor
// ========================================

pub struct TypeScriptVariableExtractor;

impl TypeScriptVariableExtractor {
    pub fn new() -> Self {
        Self
    }

    fn traverse_for_assignments(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        match node.kind() {
            // TypeScript uses "lexical_declaration" for let/const
            "lexical_declaration" => {
                self.extract_lexical_declaration(node, source, variables);
            }
            // Variable declaration for var
            "variable_declaration" => {
                self.extract_variable_declaration(node, source, variables);
            }
            // Assignment expression: x = 10
            "assignment_expression" => {
                self.extract_assignment_expression(node, source, variables);
            }
            // Augmented assignment: x += 1
            "augmented_assignment_expression" => {
                self.extract_augmented_assignment(node, source, variables);
            }
            // Control flow blocks
            "if_statement" | "else_clause" | "for_statement" | "for_in_statement"
            | "while_statement" | "try_statement" | "catch_clause" | "finally_clause"
            | "switch_statement" | "case_clause" | "default_clause" => {
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        self.traverse_for_assignments(&child, source, variables);
                    }
                }
            }
            _ => {
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        self.traverse_for_assignments(&child, source, variables);
                    }
                }
            }
        }
    }

    fn extract_lexical_declaration(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        // lexical_declaration -> variable_declarator -> identifier
        for i in 0..node.child_count() {
            if let Some(declarator) = node.child(i) {
                if declarator.kind() == "variable_declarator" {
                    if let Some(name_node) = declarator.child_by_field_name("name") {
                        if let Some(name) = self.extract_name(&name_node, source) {
                            let span = node_to_span(&name_node);
                            let type_annotation = declarator
                                .child_by_field_name("type")
                                .and_then(|t| t.utf8_text(source.as_bytes()).ok())
                                .map(|s| s.to_string());
                            let value_text = declarator
                                .child_by_field_name("value")
                                .and_then(|v| v.utf8_text(source.as_bytes()).ok())
                                .map(|s| s.to_string());

                            variables.push(VariableAssignment {
                                name,
                                span,
                                type_annotation,
                                value_text,
                            });
                        }
                    }
                }
            }
        }
    }

    fn extract_variable_declaration(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        // variable_declaration -> variable_declarator -> identifier
        for i in 0..node.child_count() {
            if let Some(declarator) = node.child(i) {
                if declarator.kind() == "variable_declarator" {
                    if let Some(name_node) = declarator.child_by_field_name("name") {
                        if let Some(name) = self.extract_name(&name_node, source) {
                            let span = node_to_span(&name_node);
                            let type_annotation = declarator
                                .child_by_field_name("type")
                                .and_then(|t| t.utf8_text(source.as_bytes()).ok())
                                .map(|s| s.to_string());
                            let value_text = declarator
                                .child_by_field_name("value")
                                .and_then(|v| v.utf8_text(source.as_bytes()).ok())
                                .map(|s| s.to_string());

                            variables.push(VariableAssignment {
                                name,
                                span,
                                type_annotation,
                                value_text,
                            });
                        }
                    }
                }
            }
        }
    }

    fn extract_assignment_expression(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        if let Some(left) = node.child_by_field_name("left") {
            if left.kind() == "identifier" {
                if let Some(name) = self.extract_name(&left, source) {
                    let span = node_to_span(&left);
                    variables.push(VariableAssignment {
                        name,
                        span,
                        type_annotation: None,
                        value_text: None,
                    });
                }
            }
        }
    }

    fn extract_augmented_assignment(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        if let Some(left) = node.child_by_field_name("left") {
            if left.kind() == "identifier" {
                if let Some(name) = self.extract_name(&left, source) {
                    let span = node_to_span(&left);
                    variables.push(VariableAssignment {
                        name,
                        span,
                        type_annotation: None,
                        value_text: None,
                    });
                }
            }
        }
    }
}

impl VariableExtractor for TypeScriptVariableExtractor {
    fn extract_variables(&self, block_node: &Node, source: &str) -> Vec<VariableAssignment> {
        let mut variables = Vec::new();
        self.traverse_for_assignments(block_node, source, &mut variables);
        variables
    }

    fn is_assignment(&self, node: &Node) -> bool {
        matches!(
            node.kind(),
            "variable_declaration" | "assignment_expression" | "augmented_assignment_expression"
        )
    }

    fn extract_name(&self, node: &Node, source: &str) -> Option<String> {
        match node.kind() {
            "identifier" => node
                .utf8_text(source.as_bytes())
                .ok()
                .map(|s| s.to_string()),
            _ => None,
        }
    }

    fn extract_type(&self, node: &Node, source: &str) -> Option<String> {
        node.child_by_field_name("type")
            .and_then(|t| t.utf8_text(source.as_bytes()).ok())
            .map(|s| s.to_string())
    }
}

// ========================================
// Java Variable Extractor
// ========================================

pub struct JavaVariableExtractor;

impl JavaVariableExtractor {
    pub fn new() -> Self {
        Self
    }

    fn traverse_for_assignments(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        match node.kind() {
            // Local variable declaration: int x = 10;
            "local_variable_declaration" => {
                self.extract_local_variable(node, source, variables);
            }
            // Assignment: x = 10
            "assignment_expression" => {
                self.extract_assignment(node, source, variables);
            }
            // Control flow
            "if_statement"
            | "else_clause"
            | "for_statement"
            | "enhanced_for_statement"
            | "while_statement"
            | "try_statement"
            | "catch_clause"
            | "finally_clause"
            | "switch_expression" => {
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        self.traverse_for_assignments(&child, source, variables);
                    }
                }
            }
            _ => {
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        self.traverse_for_assignments(&child, source, variables);
                    }
                }
            }
        }
    }

    fn extract_local_variable(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        // local_variable_declaration -> variable_declarator -> identifier
        let type_annotation = node
            .child_by_field_name("type")
            .and_then(|t| t.utf8_text(source.as_bytes()).ok())
            .map(|s| s.to_string());

        for i in 0..node.child_count() {
            if let Some(declarator) = node.child(i) {
                if declarator.kind() == "variable_declarator" {
                    if let Some(name_node) = declarator.child_by_field_name("name") {
                        if let Some(name) = self.extract_name(&name_node, source) {
                            let span = node_to_span(&name_node);
                            let value_text = declarator
                                .child_by_field_name("value")
                                .and_then(|v| v.utf8_text(source.as_bytes()).ok())
                                .map(|s| s.to_string());

                            variables.push(VariableAssignment {
                                name,
                                span,
                                type_annotation: type_annotation.clone(),
                                value_text,
                            });
                        }
                    }
                }
            }
        }
    }

    fn extract_assignment(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        if let Some(left) = node.child_by_field_name("left") {
            if left.kind() == "identifier" {
                if let Some(name) = self.extract_name(&left, source) {
                    let span = node_to_span(&left);
                    variables.push(VariableAssignment {
                        name,
                        span,
                        type_annotation: None,
                        value_text: None,
                    });
                }
            }
        }
    }
}

impl VariableExtractor for JavaVariableExtractor {
    fn extract_variables(&self, block_node: &Node, source: &str) -> Vec<VariableAssignment> {
        let mut variables = Vec::new();
        self.traverse_for_assignments(block_node, source, &mut variables);
        variables
    }

    fn is_assignment(&self, node: &Node) -> bool {
        matches!(
            node.kind(),
            "local_variable_declaration" | "assignment_expression"
        )
    }

    fn extract_name(&self, node: &Node, source: &str) -> Option<String> {
        if node.kind() == "identifier" {
            node.utf8_text(source.as_bytes())
                .ok()
                .map(|s| s.to_string())
        } else {
            None
        }
    }
}

// ========================================
// Kotlin Variable Extractor
// ========================================

pub struct KotlinVariableExtractor;

impl KotlinVariableExtractor {
    pub fn new() -> Self {
        Self
    }

    fn traverse_for_assignments(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        match node.kind() {
            // Property declaration: val/var
            "property_declaration" => {
                self.extract_property_declaration(node, source, variables);
            }
            // Assignment: x = 10
            "assignment" => {
                self.extract_assignment(node, source, variables);
            }
            // Control flow - recurse
            "if_expression"
            | "when_expression"
            | "when_entry"
            | "control_structure_body"
            | "for_statement"
            | "while_statement" => {
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        self.traverse_for_assignments(&child, source, variables);
                    }
                }
            }
            _ => {
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        self.traverse_for_assignments(&child, source, variables);
                    }
                }
            }
        }
    }

    fn extract_property_declaration(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        // property_declaration has variable_declaration children
        for i in 0..node.child_count() {
            if let Some(child) = node.child(i) {
                if child.kind() == "variable_declaration" {
                    // Get first simple_identifier child
                    let name_node = child.child(0);
                    if let Some(name_node) = name_node {
                        if name_node.kind() == "simple_identifier" {
                            if let Some(name) = self.extract_name(&name_node, source) {
                                let span = node_to_span(&name_node);

                                // Type annotation is after the identifier
                                let type_annotation = (0..child.child_count())
                                    .filter_map(|j| child.child(j))
                                    .find(|c| c.kind() == "user_type")
                                    .and_then(|t| t.utf8_text(source.as_bytes()).ok())
                                    .map(|s| s.to_string());

                                // Value is after '=' in parent property_declaration
                                let value_text = (0..node.child_count())
                                    .filter_map(|j| node.child(j))
                                    .skip_while(|c| c.kind() != "=")
                                    .nth(1)
                                    .and_then(|v| v.utf8_text(source.as_bytes()).ok())
                                    .map(|s| s.to_string());

                                variables.push(VariableAssignment {
                                    name,
                                    span,
                                    type_annotation,
                                    value_text,
                                });
                            }
                        }
                    }
                }
            }
        }
    }

    fn extract_assignment(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        // Kotlin assignments don't use field names, they use positional children:
        // assignment -> child(0): directly_assignable_expression -> simple_identifier
        //            -> child(1): =
        //            -> child(2): value
        if let Some(left) = node.child(0) {
            if let Some(name) = self.extract_name(&left, source) {
                let span = node_to_span(&left);
                let value_text = node
                    .child(2)
                    .and_then(|v| v.utf8_text(source.as_bytes()).ok())
                    .map(|s| s.to_string());

                variables.push(VariableAssignment {
                    name,
                    span,
                    type_annotation: None,
                    value_text,
                });
            }
        }
    }
}

impl VariableExtractor for KotlinVariableExtractor {
    fn extract_variables(&self, block_node: &Node, source: &str) -> Vec<VariableAssignment> {
        let mut variables = Vec::new();
        self.traverse_for_assignments(block_node, source, &mut variables);
        variables
    }

    fn is_assignment(&self, node: &Node) -> bool {
        matches!(node.kind(), "property_declaration" | "assignment")
    }

    fn extract_name(&self, node: &Node, source: &str) -> Option<String> {
        match node.kind() {
            "simple_identifier" => node
                .utf8_text(source.as_bytes())
                .ok()
                .map(|s| s.to_string()),
            _ => {
                // Try to find identifier child
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        if child.kind() == "simple_identifier" {
                            return child
                                .utf8_text(source.as_bytes())
                                .ok()
                                .map(|s| s.to_string());
                        }
                    }
                }
                None
            }
        }
    }
}

// ========================================
// Rust Variable Extractor
// ========================================

pub struct RustVariableExtractor;

impl RustVariableExtractor {
    pub fn new() -> Self {
        Self
    }

    fn traverse_for_assignments(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        match node.kind() {
            // Let declaration: let x = 10
            "let_declaration" => {
                self.extract_let_declaration(node, source, variables);
            }
            // Assignment: x = 10
            "assignment_expression" => {
                self.extract_assignment(node, source, variables);
            }
            // Compound assignment: x += 1
            "compound_assignment_expr" => {
                self.extract_compound_assignment(node, source, variables);
            }
            // Control flow - recurse
            "if_expression" | "match_expression" | "for_expression" | "while_expression"
            | "loop_expression" => {
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        self.traverse_for_assignments(&child, source, variables);
                    }
                }
            }
            _ => {
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        self.traverse_for_assignments(&child, source, variables);
                    }
                }
            }
        }
    }

    fn extract_let_declaration(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        if let Some(pattern) = node.child_by_field_name("pattern") {
            if let Some(name) = self.extract_name(&pattern, source) {
                let span = node_to_span(&pattern);
                let type_annotation = node
                    .child_by_field_name("type")
                    .and_then(|t| t.utf8_text(source.as_bytes()).ok())
                    .map(|s| s.to_string());
                let value_text = node
                    .child_by_field_name("value")
                    .and_then(|v| v.utf8_text(source.as_bytes()).ok())
                    .map(|s| s.to_string());

                variables.push(VariableAssignment {
                    name,
                    span,
                    type_annotation,
                    value_text,
                });
            }
        }
    }

    fn extract_assignment(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        if let Some(left) = node.child_by_field_name("left") {
            if let Some(name) = self.extract_name(&left, source) {
                let span = node_to_span(&left);
                let value_text = node
                    .child_by_field_name("right")
                    .and_then(|v| v.utf8_text(source.as_bytes()).ok())
                    .map(|s| s.to_string());

                variables.push(VariableAssignment {
                    name,
                    span,
                    type_annotation: None,
                    value_text,
                });
            }
        }
    }

    fn extract_compound_assignment(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        if let Some(left) = node.child_by_field_name("left") {
            if let Some(name) = self.extract_name(&left, source) {
                let span = node_to_span(&left);
                let value_text = node
                    .utf8_text(source.as_bytes())
                    .ok()
                    .map(|s| s.to_string());

                variables.push(VariableAssignment {
                    name,
                    span,
                    type_annotation: None,
                    value_text,
                });
            }
        }
    }
}

impl VariableExtractor for RustVariableExtractor {
    fn extract_variables(&self, block_node: &Node, source: &str) -> Vec<VariableAssignment> {
        let mut variables = Vec::new();
        self.traverse_for_assignments(block_node, source, &mut variables);
        variables
    }

    fn is_assignment(&self, node: &Node) -> bool {
        matches!(
            node.kind(),
            "let_declaration" | "assignment_expression" | "compound_assignment_expr"
        )
    }

    fn extract_name(&self, node: &Node, source: &str) -> Option<String> {
        match node.kind() {
            "identifier" => node
                .utf8_text(source.as_bytes())
                .ok()
                .map(|s| s.to_string()),
            _ => {
                // Try to find identifier child
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        if child.kind() == "identifier" {
                            return child
                                .utf8_text(source.as_bytes())
                                .ok()
                                .map(|s| s.to_string());
                        }
                    }
                }
                None
            }
        }
    }
}

// ========================================
// Go Variable Extractor
// ========================================

pub struct GoVariableExtractor;

impl GoVariableExtractor {
    pub fn new() -> Self {
        Self
    }

    fn traverse_for_assignments(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        match node.kind() {
            // var declaration: var x int
            "var_declaration" => {
                self.extract_var_declaration(node, source, variables);
            }
            // Short var declaration: x := 10
            "short_var_declaration" => {
                self.extract_short_var_declaration(node, source, variables);
            }
            // Assignment: x = 10
            "assignment_statement" => {
                self.extract_assignment(node, source, variables);
            }
            // Control flow - recurse
            "if_statement" | "for_statement" | "switch_statement" | "select_statement" => {
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        self.traverse_for_assignments(&child, source, variables);
                    }
                }
            }
            _ => {
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        self.traverse_for_assignments(&child, source, variables);
                    }
                }
            }
        }
    }

    fn extract_var_declaration(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        // var_declaration has var_spec children
        for i in 0..node.child_count() {
            if let Some(spec) = node.child(i) {
                if spec.kind() == "var_spec" {
                    // Get name
                    if let Some(name_node) = spec.child_by_field_name("name") {
                        if let Some(name) = self.extract_name(&name_node, source) {
                            let span = node_to_span(&name_node);
                            let type_annotation = spec
                                .child_by_field_name("type")
                                .and_then(|t| t.utf8_text(source.as_bytes()).ok())
                                .map(|s| s.to_string());
                            let value_text = spec
                                .child_by_field_name("value")
                                .and_then(|v| v.utf8_text(source.as_bytes()).ok())
                                .map(|s| s.to_string());

                            variables.push(VariableAssignment {
                                name,
                                span,
                                type_annotation,
                                value_text,
                            });
                        }
                    }
                }
            }
        }
    }

    fn extract_short_var_declaration(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        // short_var_declaration: x := 10
        if let Some(left) = node.child_by_field_name("left") {
            if let Some(name) = self.extract_name(&left, source) {
                let span = node_to_span(&left);
                let value_text = node
                    .child_by_field_name("right")
                    .and_then(|v| v.utf8_text(source.as_bytes()).ok())
                    .map(|s| s.to_string());

                variables.push(VariableAssignment {
                    name,
                    span,
                    type_annotation: None,
                    value_text,
                });
            }
        }
    }

    fn extract_assignment(
        &self,
        node: &Node,
        source: &str,
        variables: &mut Vec<VariableAssignment>,
    ) {
        if let Some(left) = node.child_by_field_name("left") {
            if let Some(name) = self.extract_name(&left, source) {
                let span = node_to_span(&left);
                let value_text = node
                    .child_by_field_name("right")
                    .and_then(|v| v.utf8_text(source.as_bytes()).ok())
                    .map(|s| s.to_string());

                variables.push(VariableAssignment {
                    name,
                    span,
                    type_annotation: None,
                    value_text,
                });
            }
        }
    }
}

impl VariableExtractor for GoVariableExtractor {
    fn extract_variables(&self, block_node: &Node, source: &str) -> Vec<VariableAssignment> {
        let mut variables = Vec::new();
        self.traverse_for_assignments(block_node, source, &mut variables);
        variables
    }

    fn is_assignment(&self, node: &Node) -> bool {
        matches!(
            node.kind(),
            "var_declaration" | "short_var_declaration" | "assignment_statement"
        )
    }

    fn extract_name(&self, node: &Node, source: &str) -> Option<String> {
        match node.kind() {
            "identifier" => node
                .utf8_text(source.as_bytes())
                .ok()
                .map(|s| s.to_string()),
            "expression_list" => {
                // For multiple assignments, get first identifier
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        if child.kind() == "identifier" {
                            return child
                                .utf8_text(source.as_bytes())
                                .ok()
                                .map(|s| s.to_string());
                        }
                    }
                }
                None
            }
            _ => {
                // Try to find identifier child
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i) {
                        if child.kind() == "identifier" {
                            return child
                                .utf8_text(source.as_bytes())
                                .ok()
                                .map(|s| s.to_string());
                        }
                    }
                }
                None
            }
        }
    }
}

// ========================================
// Factory for Language-Specific Extractors
// ========================================

pub fn get_variable_extractor(language: &str) -> Box<dyn VariableExtractor> {
    match language {
        "python" => Box::new(PythonVariableExtractor::new()),
        "typescript" | "javascript" => Box::new(TypeScriptVariableExtractor::new()),
        "java" => Box::new(JavaVariableExtractor::new()),
        "kotlin" => Box::new(KotlinVariableExtractor::new()),
        "rust" => Box::new(RustVariableExtractor::new()),
        "go" => Box::new(GoVariableExtractor::new()),
        _ => Box::new(PythonVariableExtractor::new()), // Fallback to Python
    }
}

// ========================================
// Utility Functions
// ========================================

fn node_to_span(node: &Node) -> Span {
    let start_pos = node.start_position();
    let end_pos = node.end_position();

    Span::new(
        start_pos.row as u32 + 1,
        start_pos.column as u32,
        end_pos.row as u32 + 1,
        end_pos.column as u32,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use tree_sitter::Parser;

    #[test]
    fn test_python_variable_extraction() {
        let code = r#"
def test():
    x = 10
    y = 20
    z = x + y
"#;
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_python::language())
            .unwrap();
        let tree = parser.parse(code, None).unwrap();

        let extractor = PythonVariableExtractor::new();
        let vars = extractor.extract_variables(&tree.root_node(), code);

        assert_eq!(vars.len(), 3);
        assert_eq!(vars[0].name, "x");
        assert_eq!(vars[1].name, "y");
        assert_eq!(vars[2].name, "z");
    }

    #[test]
    fn test_typescript_variable_extraction() {
        let code = r#"
function test() {
    let x = 10;
    const y = 20;
    var z = x + y;
}
"#;
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_typescript::language_typescript())
            .unwrap();
        let tree = parser.parse(code, None).unwrap();

        let extractor = TypeScriptVariableExtractor::new();
        let vars = extractor.extract_variables(&tree.root_node(), code);

        println!("TypeScript vars extracted: {}", vars.len());
        for var in &vars {
            println!("  - {}", var.name);
        }

        assert!(
            vars.len() >= 3,
            "Should extract at least 3 variables. Found: {}",
            vars.len()
        );
        let var_names: Vec<_> = vars.iter().map(|v| v.name.as_str()).collect();
        assert!(var_names.contains(&"x"), "Should contain 'x'");
        assert!(var_names.contains(&"y"), "Should contain 'y'");
        assert!(var_names.contains(&"z"), "Should contain 'z'");
    }

    #[test]
    fn test_java_variable_extraction() {
        let code = r#"
public class Test {
    public void test() {
        int x = 10;
        int y = 20;
        int z = x + y;
    }
}
"#;
        let mut parser = Parser::new();
        parser.set_language(&tree_sitter_java::language()).unwrap();
        let tree = parser.parse(code, None).unwrap();

        let extractor = JavaVariableExtractor::new();
        let vars = extractor.extract_variables(&tree.root_node(), code);

        assert!(vars.len() >= 3);
        let var_names: Vec<_> = vars.iter().map(|v| v.name.as_str()).collect();
        assert!(var_names.contains(&"x"));
        assert!(var_names.contains(&"y"));
        assert!(var_names.contains(&"z"));
    }

    #[test]
    fn test_kotlin_variable_extraction() {
        let code = r#"
fun test() {
    var x: Int = 10
    val y: Int = 20
    var z = x + y
}
"#;
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_kotlin::language())
            .unwrap();
        let tree = parser.parse(code, None).unwrap();

        let extractor = KotlinVariableExtractor::new();
        let vars = extractor.extract_variables(&tree.root_node(), code);

        println!("Kotlin vars extracted: {}", vars.len());
        for var in &vars {
            println!("  - {}", var.name);
        }

        assert!(
            vars.len() >= 3,
            "Should extract at least 3 variables. Found: {}",
            vars.len()
        );
        let var_names: Vec<_> = vars.iter().map(|v| v.name.as_str()).collect();
        assert!(var_names.contains(&"x"), "Should contain 'x'");
        assert!(var_names.contains(&"y"), "Should contain 'y'");
        assert!(var_names.contains(&"z"), "Should contain 'z'");
    }

    #[test]
    fn test_kotlin_when_statement_debug() {
        let code = r#"
fun whenStmt(x: Int): Int {
    var y: Int
    when (x) {
        1 -> y = 10
        2 -> y = 20
        else -> y = 0
    }
    return y
}
"#;
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_kotlin::language())
            .unwrap();
        let tree = parser.parse(code, None).unwrap();

        // Debug: Print AST
        fn print_ast(node: &Node, source: &str, depth: usize) {
            let indent = "  ".repeat(depth);
            let text = node.utf8_text(source.as_bytes()).ok().unwrap_or("");
            let text_preview = if text.len() > 60 {
                format!("{}...", &text[..60])
            } else {
                text.to_string()
            };
            println!(
                "{}{} | {}",
                indent,
                node.kind(),
                text_preview.replace('\n', "\\n")
            );

            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    print_ast(&child, source, depth + 1);
                }
            }
        }

        println!("\n=== Kotlin when_statement AST ===");
        print_ast(&tree.root_node(), code, 0);
        println!("==================================\n");

        let extractor = KotlinVariableExtractor::new();
        let vars = extractor.extract_variables(&tree.root_node(), code);

        println!("Kotlin when_statement vars extracted: {}", vars.len());
        for var in &vars {
            println!("  - {} at {:?}", var.name, var.span);
        }

        // We expect 4 assignments: var y: Int (initial) + 3 when entries
        println!(
            "Expected: 4 (initial + 3 when entries), Got: {}",
            vars.len()
        );
    }

    #[test]
    fn test_rust_variable_extraction() {
        let code = r#"
fn test() {
    let x = 10;
    let mut y = 20;
    let z = x + y;
}
"#;
        let mut parser = Parser::new();
        parser.set_language(&tree_sitter_rust::language()).unwrap();
        let tree = parser.parse(code, None).unwrap();

        // Debug: Print AST
        fn print_ast(node: &Node, source: &str, depth: usize) {
            let indent = "  ".repeat(depth);
            let text = node.utf8_text(source.as_bytes()).ok().unwrap_or("");
            let text_preview = if text.len() > 40 {
                format!("{}...", &text[..40])
            } else {
                text.to_string()
            };
            println!(
                "{}{} | {}",
                indent,
                node.kind(),
                text_preview.replace('\n', "\\n")
            );

            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    print_ast(&child, source, depth + 1);
                }
            }
        }

        println!("=== Rust AST ===");
        print_ast(&tree.root_node(), code, 0);
        println!("=================");

        let extractor = RustVariableExtractor::new();
        let vars = extractor.extract_variables(&tree.root_node(), code);

        println!("Rust vars extracted: {}", vars.len());
        for var in &vars {
            println!("  - {}", var.name);
        }

        assert!(
            vars.len() >= 3,
            "Should extract at least 3 variables. Found: {}",
            vars.len()
        );
        let var_names: Vec<_> = vars.iter().map(|v| v.name.as_str()).collect();
        assert!(var_names.contains(&"x"), "Should contain 'x'");
        assert!(var_names.contains(&"y"), "Should contain 'y'");
        assert!(var_names.contains(&"z"), "Should contain 'z'");
    }

    #[test]
    fn test_go_variable_extraction() {
        let code = r#"
func test() {
    var x int = 10
    y := 20
    z := x + y
}
"#;
        let mut parser = Parser::new();
        parser.set_language(&tree_sitter_go::language()).unwrap();
        let tree = parser.parse(code, None).unwrap();

        // Debug: Print AST
        fn print_ast(node: &Node, source: &str, depth: usize) {
            let indent = "  ".repeat(depth);
            let text = node.utf8_text(source.as_bytes()).ok().unwrap_or("");
            let text_preview = if text.len() > 40 {
                format!("{}...", &text[..40])
            } else {
                text.to_string()
            };
            println!(
                "{}{} | {}",
                indent,
                node.kind(),
                text_preview.replace('\n', "\\n")
            );

            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    print_ast(&child, source, depth + 1);
                }
            }
        }

        println!("=== Go AST ===");
        print_ast(&tree.root_node(), code, 0);
        println!("==============");

        let extractor = GoVariableExtractor::new();
        let vars = extractor.extract_variables(&tree.root_node(), code);

        println!("Go vars extracted: {}", vars.len());
        for var in &vars {
            println!("  - {}", var.name);
        }

        assert!(
            vars.len() >= 3,
            "Should extract at least 3 variables. Found: {}",
            vars.len()
        );
        let var_names: Vec<_> = vars.iter().map(|v| v.name.as_str()).collect();
        assert!(var_names.contains(&"x"), "Should contain 'x'");
        assert!(var_names.contains(&"y"), "Should contain 'y'");
        assert!(var_names.contains(&"z"), "Should contain 'z'");
    }
}
