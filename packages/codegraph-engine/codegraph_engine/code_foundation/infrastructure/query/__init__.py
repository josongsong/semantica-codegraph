"""
Query Engine Infrastructure

Implementation layer for Query DSL.
Depends on IRDocument and domain models.

Public API:
- QueryEngine: Main facade for executing queries
- FileSystemCodeTraceAdapter: Code trace generation from files
- InMemoryCodeTraceAdapter: Code trace generation from memory (testing)
"""

from .adapters import FileSystemCodeTraceAdapter
from .edge_resolver import EdgeResolver
from .graph_index import UnifiedGraphIndex
from .node_matcher import NodeMatcher
from .query_engine import QueryEngine
from .query_executor import QueryExecutor
from .traversal_engine import TraversalEngine

__all__ = [
    # Public API
    "QueryEngine",
    # Adapters (CodeTraceProvider implementations)
    "FileSystemCodeTraceAdapter",
    # Internal components (for testing)
    "UnifiedGraphIndex",
    "NodeMatcher",
    "EdgeResolver",
    "TraversalEngine",
    "QueryExecutor",
]
