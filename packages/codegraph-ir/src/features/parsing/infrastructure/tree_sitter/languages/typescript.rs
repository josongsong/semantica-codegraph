//! TypeScript-specific tree-sitter configuration
//!
//! This module provides constants, type definitions, and helper functions
//! for TypeScript AST parsing and symbol extraction.
//!
//! Design principles:
//! - No magic strings: All tree-sitter node types defined as constants
//! - No hardcoding: Configuration-driven approach
//! - Type safety: Strongly typed helpers

use lazy_static::lazy_static;
use std::collections::HashSet;

/// TypeScript tree-sitter node kinds
///
/// These constants match the exact node type names from tree-sitter-typescript grammar.
/// Source: https://github.com/tree-sitter/tree-sitter-typescript/blob/master/common/define-grammar.js
pub mod node_kinds {
    // Program structure
    pub const PROGRAM: &str = "program";
    pub const MODULE: &str = "module";

    // Declarations
    pub const CLASS_DECLARATION: &str = "class_declaration";
    pub const INTERFACE_DECLARATION: &str = "interface_declaration";
    pub const FUNCTION_DECLARATION: &str = "function_declaration";
    pub const METHOD_DEFINITION: &str = "method_definition";
    pub const VARIABLE_DECLARATION: &str = "variable_declaration";
    pub const ENUM_DECLARATION: &str = "enum_declaration";
    pub const TYPE_ALIAS_DECLARATION: &str = "type_alias_declaration";

    // Class members
    pub const PUBLIC_FIELD_DEFINITION: &str = "public_field_definition";
    pub const PROPERTY_SIGNATURE: &str = "property_signature";
    pub const METHOD_SIGNATURE: &str = "method_signature";
    pub const CONSTRUCTOR: &str = "constructor";
    pub const ABSTRACT_METHOD_SIGNATURE: &str = "abstract_method_signature";

    // Functions
    pub const ARROW_FUNCTION: &str = "arrow_function";
    pub const FUNCTION_EXPRESSION: &str = "function_expression";
    pub const GENERATOR_FUNCTION: &str = "generator_function";
    pub const GENERATOR_FUNCTION_DECLARATION: &str = "generator_function_declaration";

    // Parameters
    pub const FORMAL_PARAMETERS: &str = "formal_parameters";
    pub const REQUIRED_PARAMETER: &str = "required_parameter";
    pub const OPTIONAL_PARAMETER: &str = "optional_parameter";
    pub const REST_PARAMETER: &str = "rest_parameter";

    // Import/Export
    pub const IMPORT_STATEMENT: &str = "import_statement";
    pub const IMPORT_CLAUSE: &str = "import_clause";
    pub const NAMED_IMPORTS: &str = "named_imports";
    pub const IMPORT_SPECIFIER: &str = "import_specifier";
    pub const NAMESPACE_IMPORT: &str = "namespace_import";
    pub const EXPORT_STATEMENT: &str = "export_statement";
    pub const EXPORT_CLAUSE: &str = "export_clause";

    // Types
    pub const TYPE_ANNOTATION: &str = "type_annotation";
    pub const TYPE_PARAMETERS: &str = "type_parameters";
    pub const TYPE_PARAMETER: &str = "type_parameter";
    pub const TYPE_IDENTIFIER: &str = "type_identifier";
    pub const PREDEFINED_TYPE: &str = "predefined_type";
    pub const GENERIC_TYPE: &str = "generic_type";
    pub const UNION_TYPE: &str = "union_type";
    pub const INTERSECTION_TYPE: &str = "intersection_type";
    pub const TUPLE_TYPE: &str = "tuple_type";
    pub const ARRAY_TYPE: &str = "array_type";
    pub const FUNCTION_TYPE: &str = "function_type";
    pub const OBJECT_TYPE: &str = "object_type";

    // Modifiers
    pub const ACCESSIBILITY_MODIFIER: &str = "accessibility_modifier";
    pub const READONLY: &str = "readonly";
    pub const STATIC: &str = "static";
    pub const ASYNC: &str = "async";
    pub const ABSTRACT: &str = "abstract";

    // Decorators
    pub const DECORATOR: &str = "decorator";

    // Expressions
    pub const CALL_EXPRESSION: &str = "call_expression";
    pub const MEMBER_EXPRESSION: &str = "member_expression";
    pub const IDENTIFIER: &str = "identifier";
    pub const STRING: &str = "string";

    // Control flow
    pub const IF_STATEMENT: &str = "if_statement";
    pub const FOR_STATEMENT: &str = "for_statement";
    pub const WHILE_STATEMENT: &str = "while_statement";
    pub const DO_STATEMENT: &str = "do_statement";
    pub const TRY_STATEMENT: &str = "try_statement";
    pub const RETURN_STATEMENT: &str = "return_statement";
    pub const THROW_STATEMENT: &str = "throw_statement";
    pub const SWITCH_STATEMENT: &str = "switch_statement";

    // JSX/TSX (React)
    pub const JSX_ELEMENT: &str = "jsx_element";
    pub const JSX_SELF_CLOSING_ELEMENT: &str = "jsx_self_closing_element";
    pub const JSX_OPENING_ELEMENT: &str = "jsx_opening_element";
}

/// TypeScript built-in types
///
/// Comprehensive list of TypeScript's built-in types.
/// No hardcoding - all defined as configuration.
lazy_static! {
    pub static ref BUILTIN_TYPES: HashSet<&'static str> = {
        let mut set = HashSet::new();

        // Primitive types
        set.insert("string");
        set.insert("number");
        set.insert("boolean");
        set.insert("symbol");
        set.insert("bigint");
        set.insert("void");
        set.insert("null");
        set.insert("undefined");

        // Special types
        set.insert("any");
        set.insert("unknown");
        set.insert("never");
        set.insert("object");

        // Built-in utility types
        set.insert("Array");
        set.insert("ReadonlyArray");
        set.insert("Map");
        set.insert("Set");
        set.insert("WeakMap");
        set.insert("WeakSet");
        set.insert("Promise");
        set.insert("Date");
        set.insert("RegExp");
        set.insert("Error");
        set.insert("Function");

        // Utility types
        set.insert("Partial");
        set.insert("Required");
        set.insert("Readonly");
        set.insert("Record");
        set.insert("Pick");
        set.insert("Omit");
        set.insert("Exclude");
        set.insert("Extract");
        set.insert("NonNullable");
        set.insert("ReturnType");
        set.insert("InstanceType");
        set.insert("Parameters");
        set.insert("ConstructorParameters");

        set
    };
}

/// React Hook patterns
///
/// List of common React hooks for detection and analysis.
/// This enables React-specific SOTA features.
lazy_static! {
    pub static ref REACT_HOOKS: HashSet<&'static str> = {
        let mut set = HashSet::new();

        // Core hooks
        set.insert("useState");
        set.insert("useEffect");
        set.insert("useContext");
        set.insert("useReducer");
        set.insert("useCallback");
        set.insert("useMemo");
        set.insert("useRef");
        set.insert("useImperativeHandle");
        set.insert("useLayoutEffect");
        set.insert("useDebugValue");

        // React 18 hooks
        set.insert("useId");
        set.insert("useTransition");
        set.insert("useDeferredValue");
        set.insert("useSyncExternalStore");
        set.insert("useInsertionEffect");

        set
    };
}

/// Common TypeScript decorators
///
/// Used for decorator detection and classification.
lazy_static! {
    pub static ref COMMON_DECORATORS: HashSet<&'static str> = {
        let mut set = HashSet::new();

        // Angular decorators
        set.insert("Component");
        set.insert("NgModule");
        set.insert("Injectable");
        set.insert("Input");
        set.insert("Output");
        set.insert("ViewChild");
        set.insert("HostListener");

        // NestJS decorators
        set.insert("Controller");
        set.insert("Get");
        set.insert("Post");
        set.insert("Put");
        set.insert("Delete");
        set.insert("Patch");
        set.insert("Injectable");
        set.insert("Module");

        // TypeORM decorators
        set.insert("Entity");
        set.insert("Column");
        set.insert("PrimaryGeneratedColumn");
        set.insert("ManyToOne");
        set.insert("OneToMany");

        // TypeScript experimental decorators
        set.insert("sealed");
        set.insert("override");
        set.insert("deprecated");

        set
    };
}

/// Node kind predicates
///
/// Type-safe helpers to classify tree-sitter nodes.
/// No magic strings in main code!

/// Check if a node represents a class-like declaration
pub fn is_class_like(kind: &str) -> bool {
    matches!(
        kind,
        node_kinds::CLASS_DECLARATION | node_kinds::INTERFACE_DECLARATION
    )
}

/// Check if a node represents a function-like declaration
pub fn is_function_like(kind: &str) -> bool {
    matches!(
        kind,
        node_kinds::FUNCTION_DECLARATION
            | node_kinds::METHOD_DEFINITION
            | node_kinds::ARROW_FUNCTION
            | node_kinds::FUNCTION_EXPRESSION
            | node_kinds::GENERATOR_FUNCTION
            | node_kinds::GENERATOR_FUNCTION_DECLARATION
    )
}

/// Check if a node represents a type declaration
pub fn is_type_declaration(kind: &str) -> bool {
    matches!(
        kind,
        node_kinds::TYPE_ALIAS_DECLARATION | node_kinds::INTERFACE_DECLARATION
    )
}

/// Check if a node represents an import/export statement
pub fn is_import_export(kind: &str) -> bool {
    matches!(
        kind,
        node_kinds::IMPORT_STATEMENT | node_kinds::EXPORT_STATEMENT
    )
}

/// Check if a node represents control flow
pub fn is_control_flow(kind: &str) -> bool {
    matches!(
        kind,
        node_kinds::IF_STATEMENT
            | node_kinds::FOR_STATEMENT
            | node_kinds::WHILE_STATEMENT
            | node_kinds::DO_STATEMENT
            | node_kinds::TRY_STATEMENT
            | node_kinds::RETURN_STATEMENT
            | node_kinds::THROW_STATEMENT
            | node_kinds::SWITCH_STATEMENT
            | "break_statement"
            | "continue_statement"
    )
}

/// Check if a node represents a loop construct
pub fn is_loop(kind: &str) -> bool {
    matches!(
        kind,
        node_kinds::FOR_STATEMENT | node_kinds::WHILE_STATEMENT | node_kinds::DO_STATEMENT
    )
}

/// Check if a node represents JSX/TSX (React)
pub fn is_jsx(kind: &str) -> bool {
    matches!(
        kind,
        node_kinds::JSX_ELEMENT
            | node_kinds::JSX_SELF_CLOSING_ELEMENT
            | node_kinds::JSX_OPENING_ELEMENT
    )
}

/// Check if a name matches a React hook pattern
pub fn is_react_hook(name: &str) -> bool {
    REACT_HOOKS.contains(name) || name.starts_with("use")
}

/// Check if a type is a builtin TypeScript type
pub fn is_builtin_type(type_name: &str) -> bool {
    BUILTIN_TYPES.contains(type_name)
}

/// Check if a decorator is a known common decorator
pub fn is_common_decorator(name: &str) -> bool {
    COMMON_DECORATORS.contains(name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_builtin_types_contains_primitives() {
        assert!(is_builtin_type("string"));
        assert!(is_builtin_type("number"));
        assert!(is_builtin_type("boolean"));
        assert!(is_builtin_type("any"));
        assert!(!is_builtin_type("MyCustomType"));
    }

    #[test]
    fn test_react_hooks_detection() {
        assert!(is_react_hook("useState"));
        assert!(is_react_hook("useEffect"));
        assert!(is_react_hook("useMemo"));
        assert!(is_react_hook("useCustomHook")); // Custom hook pattern
        assert!(!is_react_hook("customFunction"));
    }

    #[test]
    fn test_common_decorators() {
        assert!(is_common_decorator("Component"));
        assert!(is_common_decorator("Injectable"));
        assert!(is_common_decorator("Controller"));
        assert!(!is_common_decorator("MyCustomDecorator"));
    }

    #[test]
    fn test_class_like_predicate() {
        assert!(is_class_like(node_kinds::CLASS_DECLARATION));
        assert!(is_class_like(node_kinds::INTERFACE_DECLARATION));
        assert!(!is_class_like(node_kinds::FUNCTION_DECLARATION));
    }

    #[test]
    fn test_function_like_predicate() {
        assert!(is_function_like(node_kinds::FUNCTION_DECLARATION));
        assert!(is_function_like(node_kinds::ARROW_FUNCTION));
        assert!(is_function_like(node_kinds::METHOD_DEFINITION));
        assert!(!is_function_like(node_kinds::CLASS_DECLARATION));
    }

    #[test]
    fn test_control_flow_predicate() {
        assert!(is_control_flow(node_kinds::IF_STATEMENT));
        assert!(is_control_flow(node_kinds::FOR_STATEMENT));
        assert!(is_control_flow(node_kinds::RETURN_STATEMENT));
        assert!(!is_control_flow(node_kinds::CLASS_DECLARATION));
    }

    #[test]
    fn test_jsx_predicate() {
        assert!(is_jsx(node_kinds::JSX_ELEMENT));
        assert!(is_jsx(node_kinds::JSX_SELF_CLOSING_ELEMENT));
        assert!(!is_jsx(node_kinds::CLASS_DECLARATION));
    }
}
