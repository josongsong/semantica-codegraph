"""
Semantic IR Context - Snapshot, Delta, Index

Defines the data structures for semantic IR lifecycle:
- Snapshot: Full semantic IR state
- Delta: Incremental changes
- Index: Fast lookups (Structural IR ↔ Semantic IR mapping)
"""

from dataclasses import dataclass, field

from ..dfg.models import DfgSnapshot
from .bfg.models import BasicFlowBlock, BasicFlowGraph
from .cfg.models import ControlFlowBlock, ControlFlowEdge, ControlFlowGraph
from .signature.models import SignatureEntity
from .typing.models import TypeEntity

# ============================================================
# Snapshot
# ============================================================


@dataclass
class SemanticIrSnapshot:
    """
    Complete semantic IR state.

    Phase 1: types, signatures
    Phase 2: + BFG (basic blocks) + CFG (control flow edges)
    Phase 3: + DFG (data flow graph)
    """

    # Phase 1: Type + Signature
    types: list[TypeEntity] = field(default_factory=list)
    signatures: list[SignatureEntity] = field(default_factory=list)

    # Phase 2a: BFG (Basic Flow Graph - blocks without edges)
    bfg_graphs: list[BasicFlowGraph] = field(default_factory=list)
    bfg_blocks: list[BasicFlowBlock] = field(default_factory=list)

    # Phase 2b: CFG (Control Flow Graph - blocks with edges)
    cfg_graphs: list[ControlFlowGraph] = field(default_factory=list)
    cfg_blocks: list[ControlFlowBlock] = field(default_factory=list)
    cfg_edges: list[ControlFlowEdge] = field(default_factory=list)

    # Phase 3: DFG (Data Flow Graph)
    dfg_snapshot: DfgSnapshot | None = None


# ============================================================
# Delta
# ============================================================


@dataclass
class SemanticIrDelta:
    """
    Incremental changes to semantic IR.

    For efficient updates without full rebuild.
    """

    added: SemanticIrSnapshot
    updated: SemanticIrSnapshot
    deleted_ids: dict[str, list[str]]  # entity_type -> [ids]


# ============================================================
# Index (Structural ↔ Semantic mapping)
# ============================================================


@dataclass
class TypeIndex:
    """
    Fast lookup: Structural IR → Type System

    Maps function/variable nodes to their resolved types.
    """

    # Function node_id -> parameter type IDs (in order)
    function_to_param_type_ids: dict[str, list[str]] = field(default_factory=dict)

    # Function node_id -> return type ID
    function_to_return_type_id: dict[str, str | None] = field(default_factory=dict)

    # Variable node_id -> declared type ID
    variable_to_type_id: dict[str, str | None] = field(default_factory=dict)


@dataclass
class SignatureIndex:
    """
    Fast lookup: Function node_id → SignatureEntity.id
    """

    # Function/Method node_id -> Signature ID
    function_to_signature: dict[str, str] = field(default_factory=dict)


@dataclass
class SemanticIndex:
    """
    Unified semantic index (all layers).

    Provides fast lookups from Structural IR to Semantic IR.
    """

    type_index: TypeIndex = field(default_factory=TypeIndex)
    signature_index: SignatureIndex = field(default_factory=SignatureIndex)

    # Phase 2: CFG Index
    # function_to_cfg: dict[str, str] = field(default_factory=dict)

    # Phase 3: DFG Index
    # variable_struct_to_semantic: dict[str, str] = field(default_factory=dict)

    def merge(self, other: "SemanticIndex") -> "SemanticIndex":
        """Merge another index into this one"""
        merged = SemanticIndex()

        # Merge type index
        merged.type_index.function_to_param_type_ids = {
            **self.type_index.function_to_param_type_ids,
            **other.type_index.function_to_param_type_ids,
        }
        merged.type_index.function_to_return_type_id = {
            **self.type_index.function_to_return_type_id,
            **other.type_index.function_to_return_type_id,
        }
        merged.type_index.variable_to_type_id = {
            **self.type_index.variable_to_type_id,
            **other.type_index.variable_to_type_id,
        }

        # Merge signature index
        merged.signature_index.function_to_signature = {
            **self.signature_index.function_to_signature,
            **other.signature_index.function_to_signature,
        }

        return merged
