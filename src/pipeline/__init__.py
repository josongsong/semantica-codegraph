"""
Pipeline Layer

End-to-end orchestration of parsing, IR generation, graph building,
chunking, and indexing.

Components:
- IndexingOrchestrator: Full pipeline from source files to indexed chunks
"""

from .orchestrator import IndexingOrchestrator, IndexingResult

__all__ = [
    "IndexingOrchestrator",
    "IndexingResult",
]
