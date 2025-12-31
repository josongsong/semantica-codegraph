"""
Semantic Region Index

Indexes code by semantic regions for LLM-augmented IDEs.
"""

from .annotator import SemanticAnnotator
from .index import RegionIndex
from .models import (
    ControlFlowInfo,
    RegionCollection,
    RegionPurpose,
    RegionType,
    SemanticRegion,
    TypeFlowInfo,
)
from .segmenter import RegionSegmenter

__all__ = [
    "SemanticRegion",
    "RegionType",
    "RegionPurpose",
    "TypeFlowInfo",
    "ControlFlowInfo",
    "RegionCollection",
    "RegionSegmenter",
    "SemanticAnnotator",
    "RegionIndex",
]
