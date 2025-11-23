"""
IR Models - Re-export all models

Backward compatibility layer for existing imports.
"""

# Structural IR
from .core import (
    ControlFlowSummary,
    Edge,
    EdgeKind,
    Node,
    NodeKind,
    Span,
)

# IR Document
from .document import IRDocument

# Re-export semantic IR models for convenience
from ...semantic_ir.typing.models import (
    TypeEntity,
    TypeFlavor,
    TypeResolutionLevel,
)
from ...semantic_ir.signature.models import (
    SignatureEntity,
    Visibility,
)
from ...semantic_ir.cfg.models import (
    CFGBlockKind,
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
    ControlFlowGraph,
)

__all__ = [
    # Structural IR
    "Node",
    "NodeKind",
    "Edge",
    "EdgeKind",
    "Span",
    "ControlFlowSummary",
    "IRDocument",
    # Type System
    "TypeEntity",
    "TypeFlavor",
    "TypeResolutionLevel",
    # Signature
    "SignatureEntity",
    "Visibility",
    # CFG
    "CFGBlockKind",
    "CFGEdgeKind",
    "ControlFlowBlock",
    "ControlFlowEdge",
    "ControlFlowGraph",
]
