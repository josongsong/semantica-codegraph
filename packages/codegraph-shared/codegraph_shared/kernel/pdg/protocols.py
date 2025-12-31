"""
PDG Protocols - Interface Definitions

Purpose: Define contracts for PDG builders without implementation
"""

from typing import Any, Protocol

from .models import PDGEdge, PDGNode


class PDGBuilderPort(Protocol):
    """
    PDG Builder Protocol.

    Implementations:
    - reasoning_engine.infrastructure.pdg.pdg_builder.PDGBuilder
    """

    nodes: dict[str, PDGNode]
    edges: list[PDGEdge]

    def add_node(self, node: PDGNode) -> None:
        """Add PDG node"""
        ...

    def add_edge(self, edge: PDGEdge) -> None:
        """Add PDG edge"""
        ...

    def build(
        self, cfg_nodes: list[Any], cfg_edges: list[Any], dfg_edges: list[Any]
    ) -> tuple[dict[str, PDGNode], list[PDGEdge]]:
        """Build PDG from CFG and DFG"""
        ...
