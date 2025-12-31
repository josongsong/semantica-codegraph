"""
Query Layer Ports - Hexagonal Architecture

Port interfaces that infrastructure implements.
Domain depends on ports, infrastructure implements them.

Architecture:
    Domain (query/)
        ↓ depends on
    Ports (this file)
        ↑ implemented by
    Infrastructure (infrastructure/query/)
"""

from typing import Protocol

from .results import PathResult, UnifiedEdge, UnifiedNode
from .selectors import EdgeSelector, NodeSelector
from .types import EdgeType


class GraphIndexPort(Protocol):
    """
    Port for graph index operations

    Implemented by: UnifiedGraphIndex
    """

    def get_node(self, node_id: str) -> UnifiedNode | None:
        """Get node by ID"""
        ...

    def get_edges_from(self, node_id: str, edge_type: EdgeType | str | None = None) -> list[UnifiedEdge]:
        """Get outgoing edges from node"""
        ...

    def get_edges_to(self, node_id: str, edge_type: EdgeType | str | None = None) -> list[UnifiedEdge]:
        """Get incoming edges to node"""
        ...

    def find_vars_by_name(self, name: str) -> list[UnifiedNode]:
        """Find variables by name"""
        ...

    def find_funcs_by_name(self, name: str) -> list[UnifiedNode]:
        """Find functions by name"""
        ...

    def find_classes_by_name(self, name: str) -> list[UnifiedNode]:
        """Find classes by name"""
        ...

    def find_call_sites_by_name(self, callee_name: str) -> list[UnifiedNode]:
        """Find call sites by callee name"""
        ...

    def get_all_nodes(self) -> list[UnifiedNode]:
        """Get all nodes (expensive!)"""
        ...

    def get_stats(self) -> dict:
        """Get index statistics"""
        ...


class NodeMatcherPort(Protocol):
    """
    Port for node matching operations

    Implemented by: NodeMatcher
    """

    def match(self, selector: NodeSelector) -> list[UnifiedNode]:
        """Match nodes by selector"""
        ...


class EdgeResolverPort(Protocol):
    """
    Port for edge resolution operations

    Implemented by: EdgeResolver
    """

    def resolve(self, from_node_id: str, edge_selector: EdgeSelector, backward: bool = False) -> list[UnifiedEdge]:
        """Resolve edges from node"""
        ...


class TraversalPort(Protocol):
    """
    Port for graph traversal operations

    Implemented by: TraversalEngine
    """

    def find_paths(
        self,
        source_selector: NodeSelector,
        target_selector: NodeSelector,
        edge_selector: EdgeSelector,
        direction: str,
        max_depth: int,
        max_paths: int,
        max_nodes: int,
        timeout_ms: int | None = None,
        start_time: float | None = None,
    ) -> list[PathResult]:
        """Find paths from source to target"""
        ...


class CodeTraceProvider(Protocol):
    """
    Port for code trace operations

    Provides source code context for paths.
    Implemented by infrastructure layer with IR access.
    """

    def get_trace(self, path: PathResult, context_lines: int = 2) -> str:
        """
        Get code trace with context

        Args:
            path: Path result
            context_lines: Lines of context before/after

        Returns:
            Formatted code trace
        """
        ...

    def get_node_source(self, node: UnifiedNode, context_lines: int = 2) -> str:
        """
        Get source code for a node

        Args:
            node: Unified node
            context_lines: Lines of context

        Returns:
            Source code snippet
        """
        ...
