"""
Expression IR Models

Expression entities for CFG/DFG construction.
"""

from dataclasses import dataclass, field
from enum import Enum

from src.contexts.code_foundation.infrastructure.ir.models import Span


class ExprKind(str, Enum):
    """Expression types"""

    # Value access
    NAME_LOAD = "NameLoad"  # Variable read: x
    ATTRIBUTE = "Attribute"  # Attribute access: obj.attr
    SUBSCRIPT = "Subscript"  # Index: arr[i]

    # Operations
    BIN_OP = "BinOp"  # Binary operation: a + b
    UNARY_OP = "UnaryOp"  # Unary operation: -a, not x
    COMPARE = "Compare"  # Comparison: a < b
    BOOL_OP = "BoolOp"  # Boolean operation: a and b

    # Calls/Creation
    CALL = "Call"  # Function call: fn(x)
    INSTANTIATE = "Instantiate"  # Object creation: Class()

    # Literals
    LITERAL = "Literal"  # Constant: 1, "str", True
    COLLECTION = "Collection"  # Collection: [1,2], {a:b}

    # Assignment
    ASSIGN = "Assign"  # Assignment target: a = b (left side)

    # Special
    LAMBDA = "Lambda"  # Lambda expression
    COMPREHENSION = "Comprehension"  # List/dict/set comprehension


@dataclass
class Expression:
    """
    Expression entity (value-level node for DFG).

    Represents a single expression in the AST that produces or consumes values.

    ID format: expr:{repo_id}:{file_path}:{line}:{col}
    """

    # [Required] Identity
    id: str
    kind: ExprKind
    repo_id: str
    file_path: str
    function_fqn: str | None  # None = module-level expression

    # [Required] Location
    span: Span

    # [Optional] DFG connections
    reads_vars: list[str] = field(default_factory=list)  # VariableEntity IDs
    defines_var: str | None = None  # VariableEntity ID (for assignment targets)

    # [Optional] Type information
    type_id: str | None = None  # TypeEntity ID (from annotation or inference)
    inferred_type: str | None = None  # Pyright hover result
    inferred_type_id: str | None = None  # TypeEntity ID for inferred type

    # [Optional] Symbol linking (cross-file resolution)
    symbol_id: str | None = None  # IR Node ID of the symbol definition
    symbol_fqn: str | None = None  # Fully qualified name of the symbol

    # [Optional] Expression tree structure
    parent_expr_id: str | None = None  # Parent expression ID
    child_expr_ids: list[str] = field(default_factory=list)  # Child expression IDs

    # [Optional] CFG block reference
    block_id: str | None = None  # CFGBlock ID where this expression appears

    # [Optional] Expression-specific attributes
    attrs: dict = field(default_factory=dict)
    # attrs examples:
    # - BinOp: {"operator": "+", "left_expr_id": "...", "right_expr_id": "..."}
    # - Call: {"callee_id": "...", "arg_expr_ids": [...], "callee_name": "fn"}
    # - Attribute: {"base_expr_id": "...", "attr_name": "field"}
    # - Literal: {"value": 42, "value_type": "int"}
    # - NAME_LOAD: {"var_name": "x"}
    # - definition_file: file path of symbol definition (from Pyright)
    # - definition_line: line number of symbol definition
    # - definition_fqn: fully qualified name of symbol definition
