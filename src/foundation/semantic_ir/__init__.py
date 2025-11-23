"""
Semantic IR

Semantic analysis layer on top of Structural IR.

Phases:
- Phase 1: Type System + Signatures 
- Phase 2: CFG (Control Flow Graph)
- Phase 3: DFG (Data Flow Graph)
"""

from .builder import DefaultSemanticIrBuilder, SemanticIrBuilder
from .context import (
    SemanticIndex,
    SemanticIrDelta,
    SemanticIrSnapshot,
    SignatureIndex,
    TypeIndex,
)

# Sub-layers
from .cfg.builder import CfgIrBuilder
from .cfg.models import (
    CFGBlockKind,
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
    ControlFlowGraph,
)
from .signature.builder import SignatureIrBuilder
from .signature.models import SignatureEntity, Visibility
from .typing.builder import TypeIrBuilder
from .typing.models import TypeEntity, TypeFlavor, TypeResolutionLevel

__all__ = [
    # Builder
    "SemanticIrBuilder",
    "DefaultSemanticIrBuilder",
    "TypeIrBuilder",
    "SignatureIrBuilder",
    "CfgIrBuilder",
    # Context
    "SemanticIrSnapshot",
    "SemanticIrDelta",
    "SemanticIndex",
    "TypeIndex",
    "SignatureIndex",
    # Models
    "TypeEntity",
    "TypeFlavor",
    "TypeResolutionLevel",
    "SignatureEntity",
    "Visibility",
    "CFGBlockKind",
    "CFGEdgeKind",
    "ControlFlowBlock",
    "ControlFlowEdge",
    "ControlFlowGraph",
]
