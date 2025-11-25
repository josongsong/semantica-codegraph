"""
Chunking Layer

Symbol-first hierarchical chunking for RAG.

Hierarchy:
    Repo → Project → Module → File → Class → Function
"""

from .boundary import BoundaryValidationError, ChunkBoundaryValidator
from .builder import ChunkBuilder
from .git_loader import GitFileLoader, get_file_at_commit
from .id_generator import ChunkIdContext, ChunkIdGenerator
from .incremental import (
    ChunkIncrementalRefresher,
    ChunkUpdateHook,
    DiffHunk,
    DiffParser,
)
from .mapping import ChunkGraphMapper, ChunkMapper, GraphNodeFilter
from .models import (
    Chunk,
    ChunkDiffType,
    ChunkHierarchy,
    ChunkId,
    ChunkRefreshResult,
    ChunkToGraph,
    ChunkToIR,
    GraphNodeId,
    IRNodeId,
)
from .store import ChunkStore, InMemoryChunkStore, PostgresChunkStore

__all__ = [
    "Chunk",
    "ChunkBuilder",
    "ChunkBoundaryValidator",
    "BoundaryValidationError",
    "ChunkIdContext",
    "ChunkIdGenerator",
    "ChunkIncrementalRefresher",
    "ChunkUpdateHook",
    "DiffHunk",
    "DiffParser",
    "ChunkMapper",
    "ChunkGraphMapper",
    "GraphNodeFilter",
    "ChunkId",
    "GraphNodeId",
    "IRNodeId",
    "ChunkToGraph",
    "ChunkToIR",
    "ChunkHierarchy",
    "ChunkDiffType",
    "ChunkRefreshResult",
    "ChunkStore",
    "InMemoryChunkStore",
    "PostgresChunkStore",
    "GitFileLoader",
    "get_file_at_commit",
]
