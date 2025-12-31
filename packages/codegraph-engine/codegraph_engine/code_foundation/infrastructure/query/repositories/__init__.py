"""
Query Repositories

Repository pattern implementations for graph data access.

Architecture:
    GraphRepositoryPort (Interface)
        ↑ implemented by
    IndexBackedGraphRepository (Concrete)
"""

from .graph_repository import GraphRepositoryPort, IndexBackedGraphRepository

__all__ = [
    "GraphRepositoryPort",
    "IndexBackedGraphRepository",
]
