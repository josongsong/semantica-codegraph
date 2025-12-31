//! Python-specific tree-sitter configuration

/// Python node kinds for quick lookup
pub mod node_kinds {
    pub const FUNCTION_DEF: &str = "function_definition";
    pub const CLASS_DEF: &str = "class_definition";
    pub const LAMBDA: &str = "lambda";
    pub const ASSIGNMENT: &str = "assignment";
    pub const PARAMETER: &str = "parameter";
    pub const DEFAULT_PARAMETER: &str = "default_parameter";
    pub const TYPED_PARAMETER: &str = "typed_parameter";
    pub const CALL: &str = "call";
    pub const IDENTIFIER: &str = "identifier";
    pub const ATTRIBUTE: &str = "attribute";
    pub const IF_STATEMENT: &str = "if_statement";
    pub const FOR_STATEMENT: &str = "for_statement";
    pub const WHILE_STATEMENT: &str = "while_statement";
    pub const TRY_STATEMENT: &str = "try_statement";
    pub const RETURN_STATEMENT: &str = "return_statement";
    pub const IMPORT_STATEMENT: &str = "import_statement";
    pub const IMPORT_FROM_STATEMENT: &str = "import_from_statement";
    pub const DECORATOR: &str = "decorator";
    pub const STRING: &str = "string";
    pub const BLOCK: &str = "block";
    pub const MODULE: &str = "module";
}

/// Check if a node kind is a definition
pub fn is_definition(kind: &str) -> bool {
    matches!(
        kind,
        node_kinds::FUNCTION_DEF | node_kinds::CLASS_DEF | node_kinds::LAMBDA
    )
}

/// Check if a node kind is a statement
pub fn is_statement(kind: &str) -> bool {
    kind.ends_with("_statement") || kind == node_kinds::ASSIGNMENT
}

/// Check if a node kind is control flow
pub fn is_control_flow(kind: &str) -> bool {
    matches!(
        kind,
        node_kinds::IF_STATEMENT
            | node_kinds::FOR_STATEMENT
            | node_kinds::WHILE_STATEMENT
            | node_kinds::TRY_STATEMENT
            | node_kinds::RETURN_STATEMENT
            | "break_statement"
            | "continue_statement"
            | "raise_statement"
    )
}
