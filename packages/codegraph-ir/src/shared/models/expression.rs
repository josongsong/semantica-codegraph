//! Expression IR - L1 High-Level Intermediate Representation
//!
//! SOTA Design based on:
//! - LLVM ClangIR (2024-2025): High-level semantic preservation
//! - MLIR: Progressive lowering pattern
//! - Rust-analyzer HIR: AST → semantic IR
//! - Meta Infer: Expression-level symbolic execution
//! - GitHub CodeQL: ExprNode abstraction

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

use super::Span;

/// Expression ID (unique within a file)
pub type ExprId = usize;

/// Variable ID (for data flow tracking)
pub type VarId = String;

/// Symbol ID (for cross-file resolution)
pub type SymbolId = String;

/// Expression Entity (L1: High-Level IR)
///
/// Design principles:
/// - **LLVM-style**: ID-based, SSA-friendly
/// - **CodeQL-style**: reads/defines for dataflow
/// - **Infer-style**: heap_access for separation logic
/// - **Multi-language**: Language-agnostic core, attrs for specifics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Expression {
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Identity
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Unique ID within the file
    pub id: ExprId,

    /// Expression kind (14 types, complete coverage)
    pub kind: ExprKind,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Location
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Source location
    pub span: Span,

    /// File path
    pub file_path: String,

    /// Function/method ID (optional)
    pub function_id: Option<String>,

    /// Block ID (for CFG integration)
    pub block_id: Option<String>,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Data Flow (CodeQL-style)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Operands (input expressions)
    pub reads: Vec<ExprId>,

    /// Variable defined by this expression (if any)
    pub defines: Option<VarId>,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Semantics
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Type information (from LSP or type inference)
    pub type_info: Option<TypeInfo>,

    /// Inferred type string (e.g., "int", "List[str]")
    pub inferred_type: Option<String>,

    /// Symbol ID (cross-file resolution)
    pub symbol_id: Option<SymbolId>,

    /// Fully Qualified Name
    pub symbol_fqn: Option<String>,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Heap Analysis (Infer-style)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Heap access information (for separation logic)
    pub heap_access: Option<HeapAccess>,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Expression Tree
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Parent expression
    pub parent: Option<ExprId>,

    /// Child expressions
    pub children: Vec<ExprId>,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Metadata (Language-specific attributes)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Flexible attributes for language-specific data
    pub attrs: HashMap<String, Value>,
}

/// Expression Kind (MLIR-inspired: orthogonal operations)
///
/// Design: 14 types covering Python ExprKind completely
/// (also applicable to TypeScript, Java, Kotlin, Rust, Go)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ExprKind {
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Value Access (CodeQL: ExprNode)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Variable read: `x`
    NameLoad,

    /// Field access: `obj.field`
    Attribute,

    /// Array/dict access: `arr[i]`, `dict["key"]`
    Subscript,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Operations (LLVM IR: BinaryOp, UnaryOp)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Binary operation: `a + b`, `a == b`, `a and b`
    BinOp(BinOp),

    /// Unary operation: `-a`, `not x`, `!x`
    UnaryOp(UnaryOp),

    /// Comparison: `a < b`, `a != b`
    Compare(CompOp),

    /// Boolean operation: `a and b`, `a || b`
    BoolOp(BoolOp),

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Calls (Infer-style: function call tracking)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Function call: `fn(args)`
    Call,

    /// Object instantiation: `new Class()`, `Class(...)`
    Instantiate,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Literals (LLVM IR: ConstantInt, ConstantFP)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Literal value: `42`, `"str"`, `true`, `null`
    Literal(LiteralKind),

    /// Collection literal: `[1, 2]`, `{"a": 1}`
    Collection(CollectionKind),

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Assignment (SSA phi-like)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Assignment: `x = expr`
    Assign,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Higher-order (Python/JavaScript specific)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Lambda/arrow function: `lambda x: x + 1`, `(x) => x + 1`
    Lambda,

    /// List/dict comprehension: `[x for x in lst]`
    Comprehension,

    /// Conditional expression: `a if cond else b`, `cond ? a : b`
    Conditional,
}

/// Binary Operation
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum BinOp {
    // Arithmetic
    Add,
    Sub,
    Mul,
    Div,
    Mod,
    Pow,
    FloorDiv,

    // Bitwise
    BitAnd,
    BitOr,
    BitXor,
    LShift,
    RShift,

    // Logical (short-circuit)
    And,
    Or,
}

/// Unary Operation
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum UnaryOp {
    Not,
    Neg,
    Pos,
    Invert,
}

/// Comparison Operation
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum CompOp {
    Eq,
    NotEq,
    Lt,
    LtE,
    Gt,
    GtE,
    Is,
    IsNot,
    In,
    NotIn,
}

/// Boolean Operation
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum BoolOp {
    And,
    Or,
}

/// Literal Kind
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum LiteralKind {
    Integer,
    Float,
    String,
    Boolean,
    None,
}

/// Collection Kind
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum CollectionKind {
    List,
    Tuple,
    Set,
    Dict,
    Array,
}

/// Type Information (from LSP or type inference)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TypeInfo {
    /// Type string (e.g., "int", "List[str]", "Optional[User]")
    pub type_string: String,

    /// Is nullable/optional
    pub is_nullable: bool,

    /// Generic type parameters (e.g., ["str"] for List[str])
    pub type_params: Vec<String>,
}

/// Heap Access (Infer separation logic)
///
/// Tracks memory access for field-sensitive analysis
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HeapAccess {
    /// Base object expression
    pub base: ExprId,

    /// Field name (for `obj.field`)
    pub field: Option<String>,

    /// Index expression (for `arr[index]`)
    pub index: Option<ExprId>,

    /// Access kind (read, write, call)
    pub access_kind: AccessKind,
}

/// Heap Access Kind
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum AccessKind {
    /// Read: `x = obj.field`
    Read,

    /// Write: `obj.field = x`
    Write,

    /// Method call: `obj.method()`
    Call,
}

/// Expression IR Container (per file)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExpressionIR {
    /// All expressions in this file
    pub expressions: Vec<Expression>,

    /// Type bindings (ExprId → TypeInfo)
    pub type_bindings: HashMap<ExprId, TypeInfo>,

    /// Symbol table (name → SymbolId)
    pub symbol_table: HashMap<String, SymbolId>,

    /// File path
    pub file_path: String,

    /// Module path (e.g., "myapp.auth.login")
    pub module_path: Option<String>,
}

impl Expression {
    /// Create a new expression with minimal fields
    pub fn new(id: ExprId, kind: ExprKind, span: Span, file_path: String) -> Self {
        Self {
            id,
            kind,
            span,
            file_path,
            function_id: None,
            block_id: None,
            reads: Vec::new(),
            defines: None,
            type_info: None,
            inferred_type: None,
            symbol_id: None,
            symbol_fqn: None,
            heap_access: None,
            parent: None,
            children: Vec::new(),
            attrs: HashMap::new(),
        }
    }

    /// Check if this expression reads a variable
    pub fn reads_var(&self, var_id: &str) -> bool {
        // Check if any of our operands is the variable
        // (In full implementation, would need var_id mapping)
        false // Placeholder
    }

    /// Check if this expression defines a variable
    pub fn defines_var(&self, var_id: &str) -> bool {
        self.defines.as_ref().map(|d| d == var_id).unwrap_or(false)
    }

    /// Check if this expression accesses heap memory
    pub fn is_heap_access(&self) -> bool {
        self.heap_access.is_some()
    }
}

impl ExpressionIR {
    /// Create empty Expression IR for a file
    pub fn new(file_path: String) -> Self {
        Self {
            expressions: Vec::new(),
            type_bindings: HashMap::new(),
            symbol_table: HashMap::new(),
            file_path,
            module_path: None,
        }
    }

    /// Add an expression
    pub fn add_expression(&mut self, expr: Expression) {
        self.expressions.push(expr);
    }

    /// Get expression by ID
    pub fn get_expression(&self, id: ExprId) -> Option<&Expression> {
        self.expressions.iter().find(|e| e.id == id)
    }

    /// Get expressions of a specific kind
    pub fn get_expressions_by_kind(&self, kind: &ExprKind) -> Vec<&Expression> {
        self.expressions
            .iter()
            .filter(|e| &e.kind == kind)
            .collect()
    }

    /// Get all function calls
    pub fn get_function_calls(&self) -> Vec<&Expression> {
        self.expressions
            .iter()
            .filter(|e| matches!(e.kind, ExprKind::Call))
            .collect()
    }

    /// Get all heap accesses
    pub fn get_heap_accesses(&self) -> Vec<&Expression> {
        self.expressions
            .iter()
            .filter(|e| e.is_heap_access())
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_expression_creation() {
        let span = Span {
            start_line: 1,
            start_col: 0,
            end_line: 1,
            end_col: 10,
        };

        let expr = Expression::new(0, ExprKind::NameLoad, span, "test.py".into());

        assert_eq!(expr.id, 0);
        assert_eq!(expr.kind, ExprKind::NameLoad);
        assert_eq!(expr.file_path, "test.py");
    }

    #[test]
    fn test_expression_ir() {
        let mut ir = ExpressionIR::new("test.py".into());

        let span = Span {
            start_line: 1,
            start_col: 0,
            end_line: 1,
            end_col: 10,
        };

        ir.add_expression(Expression::new(
            0,
            ExprKind::NameLoad,
            span.clone(),
            "test.py".into(),
        ));
        ir.add_expression(Expression::new(1, ExprKind::Call, span, "test.py".into()));

        assert_eq!(ir.expressions.len(), 2);
        assert_eq!(ir.get_function_calls().len(), 1);
    }
}
