"""
Graph Store Port

Abstract interface for graph database operations.
Implementations: Neo4j, NetworkX (in-memory), etc.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from ..domain.graph import BaseSemanticaNode, RelationshipType


class GraphStorePort(ABC):
    """
    Port for graph database operations.

    Responsibilities:
    - Store nodes and relationships
    - Query graph structure
    - Traverse relationships
    """

    @abstractmethod
    async def create_node(self, node: BaseSemanticaNode) -> None:
        """Create a node in the graph."""
        pass

    @abstractmethod
    async def create_relationship(
        self,
        source_id: str,
        target_id: str,
        rel_type: RelationshipType,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Create a relationship between two nodes."""
        pass

    @abstractmethod
    async def get_node(self, node_id: str) -> Optional[BaseSemanticaNode]:
        """Retrieve a node by ID."""
        pass

    @abstractmethod
    async def get_neighbors(
        self,
        node_id: str,
        rel_type: Optional[RelationshipType] = None,
        direction: str = "outgoing",
        depth: int = 1,
    ) -> list[BaseSemanticaNode]:
        """
        Get neighboring nodes.

        Args:
            node_id: Starting node ID
            rel_type: Filter by relationship type (optional)
            direction: "outgoing", "incoming", or "both"
            depth: Traversal depth

        Returns:
            List of neighboring nodes
        """
        pass

    @abstractmethod
    async def query_path(
        self,
        start_id: str,
        end_id: str,
        max_depth: int = 5,
    ) -> list[list[str]]:
        """
        Find paths between two nodes.

        Returns:
            List of paths (each path is a list of node IDs)
        """
        pass

    @abstractmethod
    async def delete_node(self, node_id: str) -> None:
        """Delete a node and its relationships."""
        pass

    @abstractmethod
    async def query(
        self,
        query: str,
        parameters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a custom graph query.

        Args:
            query: Query string (e.g., Cypher for Neo4j)
            parameters: Query parameters

        Returns:
            Query results
        """
        pass
