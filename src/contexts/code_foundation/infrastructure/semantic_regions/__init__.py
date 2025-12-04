"""
Semantic Region Index

Indexes code by semantic regions for LLM-augmented IDEs.
"""

from .models import (
    SemanticRegion,
    RegionType,
    RegionPurpose,
    TypeFlowInfo,
    ControlFlowInfo,
    RegionCollection,
)
from .segmenter import RegionSegmenter
from .annotator import SemanticAnnotator
from .index import RegionIndex

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

