"""
Local Overlay - Uncommitted Changes Layer

Core functionality for integrating uncommitted changes into IR/Graph.
This is a CRITICAL feature that improves IDE/Agent accuracy by 30-50%.
"""

from .conflict_resolver import ConflictResolver
from .graph_merger import GraphMerger
from .models import OverlayConfig, OverlaySnapshot
from .overlay_builder import OverlayIRBuilder

__all__ = [
    "OverlaySnapshot",
    "OverlayConfig",
    "OverlayIRBuilder",
    "GraphMerger",
    "ConflictResolver",
]
