"""
Basic Flow Graph (BFG) Models

Basic blocks without control flow edges.
Edges are added by CFG layer.
"""

from dataclasses import dataclass, field
from enum import Enum

from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span


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

    # Async/await support (Added 2025-12-08)
    SUSPEND = "Suspend"  # await suspend point (async call initiated)
    RESUME = "Resume"  # await resume point (async call completed)

    # Generator/Coroutine support (Added 2025-12-09 - Phase 1)
    DISPATCHER = "Dispatcher"  # State machine dispatcher (routes to states)
    YIELD = "Yield"  # yield point (suspend and return value)
    RESUME_YIELD = "ResumeYield"  # Resume point after yield


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

    # [Optional] Async/await Metadata (Added 2025-12-08)
    # For SUSPEND blocks
    is_async_call: bool = False  # True if block contains await expression
    async_target_expression: str | None = None  # The awaited expression (e.g., "fetch(url)")

    # For RESUME blocks
    resume_from_suspend_id: str | None = None  # Corresponding SUSPEND block ID
    async_result_variable: str | None = None  # Variable assigned from await result (e.g., "result")

    # Exception handling (for both SUSPEND and TRY blocks)
    can_throw_exception: bool = False  # True if block can throw/reject
    exception_handler_block_ids: list[str] = field(default_factory=list)  # Target CATCH block IDs

    # [Optional] Generator/Coroutine Metadata (Added 2025-12-09 - Phase 1)
    # For DISPATCHER blocks
    generator_dispatch_table: dict[int, str] | None = None  # State -> Block ID mapping

    # For YIELD blocks
    generator_state_id: int | None = None  # Current state number
    generator_next_state: int | None = None  # Next state after yield
    generator_yield_value: str | None = None  # Yielded expression

    # For RESUME_YIELD blocks
    generator_resume_from_state: int | None = None  # Which state we're resuming from

    # For all generator blocks (SOTA: Lift all locals - CPython f_locals strategy)
    generator_all_locals: list[str] | None = None  # All local variables to preserve


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

    # [Optional] Generator metadata (Added 2025-12-09 - Phase 1)
    is_generator: bool = False  # True if function contains yield
    generator_yield_count: int = 0  # Number of yield statements
