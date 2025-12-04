"""
Basic Flow Graph (BFG) Models

Basic blocks without control flow edges.
Edges are added by CFG layer.
"""

from dataclasses import dataclass, field
from enum import Enum

from src.contexts.code_foundation.infrastructure.ir.models.core import Span


class BFGBlockKind(str, Enum):
    """Basic Flow Graph block types"""

    ENTRY = "Entry"
    EXIT = "Exit"
    STATEMENT = "Statement"  # Regular sequential statements
    CONDITION = "Condition"  # if/elif/else condition check
    LOOP_HEADER = "LoopHeader"  # for/while condition
    TRY = "Try"
    CATCH = "Catch"
    FINALLY = "Finally"


@dataclass
class BasicFlowBlock:
    """
    Basic Block - maximal sequence of statements with single entry/exit.

    ID format: bfg:{function_node_id}:block:{index}
    """

    # [Required] Identity
    id: str
    kind: BFGBlockKind
    function_node_id: str  # IR Node.id (Function/Method)

    # [Optional] Location
    span: Span | None = None

    # [Optional] AST metadata (for CFG edge generation)
    ast_node_type: str | None = None  # e.g., "if_statement", "for_statement"
    ast_has_alternative: bool = False  # Has else/elif branch

    # [Optional] Statement content (for later analysis)
    statement_count: int = 0  # Number of statements in this block

    # [Optional] Data Flow (for DFG)
    defined_variable_ids: list[str] = field(default_factory=list)  # Variables written in this block
    used_variable_ids: list[str] = field(default_factory=list)  # Variables read in this block

    # [Optional] Control Flow Metadata (for accurate CFG edge generation)
    # Added 2025-11-25: Support for break/continue/return statements
    is_break: bool = False  # True if this block ends with break statement
    is_continue: bool = False  # True if this block ends with continue statement
    is_return: bool = False  # True if this block ends with return statement
    target_loop_id: str | None = None  # For break/continue: target loop header block ID (supports nested loops)


@dataclass
class BasicFlowGraph:
    """
    Basic Flow Graph for a single function/method.

    Contains blocks but no edges.
    CFG layer adds edges based on block kinds and AST metadata.
    """

    # [Required] Identity
    id: str  # bfg:{function_node_id}
    function_node_id: str  # IR Node.id (Function/Method)

    # [Required] Structure
    entry_block_id: str
    exit_block_id: str
    blocks: list[BasicFlowBlock] = field(default_factory=list)

    # [Optional] Metadata
    total_statements: int = 0  # Total statements in function
