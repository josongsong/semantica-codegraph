"""
RFC-037: IRDocument Adapter

Infrastructure adapter implementing IRQuery port.

Hexagonal Architecture:
- Implements IRQuery (Domain port)
- Wraps IRDocument (Infrastructure)
- Enables Application → Domain dependency

SOTA: Adapter pattern for dependency inversion.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.ports.ir_query import IRQuery
    from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot
    from codegraph_engine.code_foundation.infrastructure.ir.models import (
        IRDocument,
        Edge,
        Node,
        NodeKind,
        EdgeKind,
        Occurrence,
    )


class IRDocumentAdapter:
    """
    RFC-037: Adapter for IRDocument.

    Implements IRQuery port (Domain).
    Wraps IRDocument (Infrastructure).

    Hexagonal: Infrastructure → Domain (implements port)
    """

    def __init__(self, ir_doc: "IRDocument"):
        """
        Initialize adapter.

        Args:
            ir_doc: IRDocument to wrap
        """
        self._ir_doc = ir_doc

    def get_nodes(self, kind: "NodeKind | None" = None) -> list["Node"]:
        """
        Get nodes, optionally filtered by kind.

        Implementation: IRQuery protocol.
        """
        if kind is None:
            return self._ir_doc.nodes

        return [n for n in self._ir_doc.nodes if n.kind == kind]

    def get_edges(self, kind: "EdgeKind | None" = None) -> list["Edge"]:
        """
        Get edges, optionally filtered by kind.

        Implementation: IRQuery protocol.
        """
        if kind is None:
            return self._ir_doc.edges

        return [e for e in self._ir_doc.edges if e.kind == kind]

    def get_occurrences(self, symbol: str | None = None) -> list["Occurrence"]:
        """
        Get occurrences, optionally filtered by symbol.

        Implementation: IRQuery protocol.

        Note: Occurrence uses symbol_id field, not symbol.
        """
        if symbol is None:
            return self._ir_doc.occurrences

        return [o for o in self._ir_doc.occurrences if o.symbol_id == symbol]

    def get_dfg(self) -> "DfgSnapshot | None":
        """
        Get DFG snapshot.

        Implementation: IRQuery protocol.

        Returns:
            DfgSnapshot or None if not built (BASE tier)
        """
        return self._ir_doc.dfg_snapshot

    def get_file_path(self) -> str:
        """
        Get file path.

        Implementation: IRQuery protocol.
        """
        # IRDocument doesn't have single file_path
        # Return from first node or empty
        if self._ir_doc.nodes:
            return self._ir_doc.nodes[0].file_path
        return ""

    def has_tier(self, tier: str) -> bool:
        """
        Check if specific tier data is available.

        Implementation: IRQuery protocol.

        Args:
            tier: "base", "extended", or "full"

        Returns:
            True if tier data is available
        """
        tier_lower = tier.lower()

        if tier_lower == "base":
            # BASE: Always true (has nodes/edges)
            return True

        elif tier_lower == "extended":
            # EXTENDED: Has DFG and expressions
            return self._ir_doc.dfg_snapshot is not None and len(self._ir_doc.expressions) > 0

        elif tier_lower == "full":
            # FULL: Has SSA (check dfg_snapshot for SSA contexts)
            if self._ir_doc.dfg_snapshot is None:
                return False
            # Check if SSA was built (has ssa_contexts)
            return hasattr(self._ir_doc.dfg_snapshot, "ssa_contexts")

        return False
