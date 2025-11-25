"""
IR Models - Core structural IR models

Contains Node, Edge, Span, and IRDocument definitions.
"""

from .core import (
    ControlFlowSummary,
    Edge,
    EdgeKind,
    Node,
    NodeKind,
    Span,
)
from .document import IRDocument

__all__ = [
    # Structural IR
    "Node",
    "NodeKind",
    "Edge",
    "EdgeKind",
    "Span",
    "ControlFlowSummary",
    "IRDocument",
]
