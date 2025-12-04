"""
Chunking Layer

Symbol-first hierarchical chunking for RAG.

Hierarchy:
    Repo → Project → Module → File → Class → Function
"""

from src.contexts.code_foundation.infrastructure.chunk.boundary import BoundaryValidationError, ChunkBoundaryValidator
from src.contexts.code_foundation.infrastructure.chunk.builder import ChunkBuilder
from src.contexts.code_foundation.infrastructure.chunk.git_loader import GitFileLoader, get_file_at_commit
from src.contexts.code_foundation.infrastructure.chunk.id_generator import ChunkIdContext, ChunkIdGenerator
from src.contexts.code_foundation.infrastructure.chunk.incremental import (
    ChunkIncrementalRefresher,
    ChunkUpdateHook,
    DiffHunk,
    DiffParser,
)
from src.contexts.code_foundation.infrastructure.chunk.mapping import ChunkGraphMapper, ChunkMapper, GraphNodeFilter
from src.contexts.code_foundation.infrastructure.chunk.models import (
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
from src.contexts.code_foundation.infrastructure.chunk.store import ChunkStore, InMemoryChunkStore, PostgresChunkStore

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
