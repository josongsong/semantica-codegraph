"""
RFC-037: IR Query Port

Domain port for querying IR information.

Hexagonal Architecture:
- Domain defines interface (this file)
- Infrastructure implements (IRDocumentAdapter)
- Application depends on interface (RefactorPrimitives)

SOTA: Dependency inversion for clean architecture.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot
    from codegraph_engine.code_foundation.infrastructure.ir.models import Edge, Node, NodeKind, EdgeKind, Occurrence


@runtime_checkable
class IRQuery(Protocol):
    """
    IR query port for application layer.

    Provides read-only access to IR information without exposing
    concrete IRDocument implementation.

    Hexagonal: Port (Domain) ← Application
    """

    def get_nodes(self, kind: "NodeKind | None" = None) -> list["Node"]:
        """
        Get nodes, optionally filtered by kind.

        Args:
            kind: NodeKind filter (None = all nodes)

        Returns:
            List of nodes

        Examples:
            get_nodes(NodeKind.FUNCTION)
            get_nodes()  # All nodes
        """
        ...

    def get_edges(self, kind: "EdgeKind | None" = None) -> list["Edge"]:
        """
        Get edges, optionally filtered by kind.

        Args:
            kind: EdgeKind filter (None = all edges)

        Returns:
            List of edges
        """
        ...

    def get_occurrences(self, symbol: str | None = None) -> list["Occurrence"]:
        """
        Get occurrences, optionally filtered by symbol.

        Args:
            symbol: Symbol filter (None = all occurrences)

        Returns:
            List of occurrences
        """
        ...

    def get_dfg(self) -> "DfgSnapshot | None":
        """
        Get DFG snapshot.

        Returns:
            DfgSnapshot or None if not built

        Note:
            Requires EXTENDED or FULL tier
        """
        ...

    def get_file_path(self) -> str:
        """
        Get file path of this IR document.

        Returns:
            File path
        """
        ...

    def has_tier(self, tier: str) -> bool:
        """
        Check if specific tier data is available.

        Args:
            tier: "base", "extended", or "full"

        Returns:
            True if tier data is available

        Examples:
            has_tier("extended")  # True if DFG built
        """
        ...
