"""
Control Flow Graph (CFG) Models

CFGBlock, CFGEdge, CFGGraph
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from ...ir.models.core import Span


class CFGBlockKind(str, Enum):
    """Control Flow Graph block types"""

    ENTRY = "Entry"
    EXIT = "Exit"
    BLOCK = "Block"
    CONDITION = "Condition"
    LOOP_HEADER = "LoopHeader"
    TRY = "Try"
    CATCH = "Catch"
    FINALLY = "Finally"


class CFGEdgeKind(str, Enum):
    """Control Flow Graph edge types"""

    NORMAL = "NORMAL"
    TRUE_BRANCH = "TRUE_BRANCH"
    FALSE_BRANCH = "FALSE_BRANCH"
    EXCEPTION = "EXCEPTION"
    LOOP_BACK = "LOOP_BACK"


@dataclass
class ControlFlowBlock:
    """CFG Basic Block"""

    # [Required] Identity
    id: str  # e.g., "cfg:plan:block:1"
    kind: CFGBlockKind
    function_node_id: str  # Node.id (Function/Method)

    # [Optional] Location
    span: Optional[Span] = None

    # [Optional] Data Flow (for DFG)
    defined_variable_ids: list[str] = field(default_factory=list)  # Node.id (Variable/Field)
    used_variable_ids: list[str] = field(default_factory=list)  # Node.id


@dataclass
class ControlFlowEdge:
    """CFG Edge between blocks"""

    source_block_id: str
    target_block_id: str
    kind: CFGEdgeKind


@dataclass
class ControlFlowGraph:
    """Control Flow Graph for a single function/method"""

    # [Required] Identity
    id: str  # e.g., "cfg:HybridRetriever.plan"
    function_node_id: str  # Node.id (Function/Method)

    # [Required] Structure
    entry_block_id: str
    exit_block_id: str
    blocks: list[ControlFlowBlock] = field(default_factory=list)
    edges: list[ControlFlowEdge] = field(default_factory=list)
