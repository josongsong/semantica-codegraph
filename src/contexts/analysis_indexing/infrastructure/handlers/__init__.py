"""
Indexing Pipeline Stage Handlers

Extracted from IndexingOrchestrator for better separation of concerns.
Each handler manages a specific stage of the indexing pipeline.
"""

from src.contexts.analysis_indexing.infrastructure.handlers.base import BaseHandler, HandlerContext
from src.contexts.analysis_indexing.infrastructure.handlers.chunking import ChunkingHandler
from src.contexts.analysis_indexing.infrastructure.handlers.graph_building import GraphBuildingHandler
from src.contexts.analysis_indexing.infrastructure.handlers.indexing import IndexingHandler
from src.contexts.analysis_indexing.infrastructure.handlers.ir_building import IRBuildingHandler
from src.contexts.analysis_indexing.infrastructure.handlers.parsing import ParsingHandler

__all__ = [
    "BaseHandler",
    "HandlerContext",
    "ParsingHandler",
    "IRBuildingHandler",
    "GraphBuildingHandler",
    "ChunkingHandler",
    "IndexingHandler",
]
