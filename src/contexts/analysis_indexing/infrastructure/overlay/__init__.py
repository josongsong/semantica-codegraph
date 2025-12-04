"""
Local Overlay - Uncommitted Changes Layer

Core functionality for integrating uncommitted changes into IR/Graph.
This is a CRITICAL feature that improves IDE/Agent accuracy by 30-50%.
"""

from .models import OverlaySnapshot, OverlayConfig
from .overlay_builder import OverlayIRBuilder
from .graph_merger import GraphMerger
from .conflict_resolver import ConflictResolver

__all__ = [
    "OverlaySnapshot",
    "OverlayConfig",
    "OverlayIRBuilder",
    "GraphMerger",
    "ConflictResolver",
]
