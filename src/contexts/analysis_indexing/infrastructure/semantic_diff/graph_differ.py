"""
Graph Differ

Compares graph structures to detect semantic changes.
"""

from dataclasses import dataclass
from typing import Any

import structlog

from .models import (
    ChangeSeverity,
    ChangeType,
    DiffContext,
    SemanticChange,
    SemanticDiff,
)

logger = structlog.get_logger(__name__)


@dataclass
class GraphDiffer:
    """
    Graph-level differ

    Detects changes by comparing graph structures:
    - Call graph changes
    - Dependency changes
    - Reachability changes
    - Error propagation paths

    Example:
        differ = GraphDiffer(context)
        diff = differ.compare_call_graphs()
    """

    context: DiffContext

    def compare_call_graphs(self) -> SemanticDiff:
        """
        Compare call graphs between old and new versions

        Returns:
            SemanticDiff with call graph changes
        """
        diff = SemanticDiff()

        if not self.context.old_call_graph or not self.context.new_call_graph:
            return diff

        # Get edges from both graphs
        old_edges = self._get_edges(self.context.old_call_graph)
        new_edges = self._get_edges(self.context.new_call_graph)

        # Edges added (new dependencies)
        added_edges = new_edges - old_edges
        for caller, callee in added_edges:
            change = SemanticChange(
                change_type=ChangeType.DEPENDENCY_ADDED,
                severity=ChangeSeverity.MODERATE,
                file_path="",
                symbol_id=caller,
                description=f"New dependency: {caller} -> {callee}",
                old_value=None,
                new_value=callee,
            )
            change.add_affected(callee)
            diff.add_change(change)

        # Edges removed (dependencies removed)
        removed_edges = old_edges - new_edges
        for caller, callee in removed_edges:
            change = SemanticChange(
                change_type=ChangeType.DEPENDENCY_REMOVED,
                severity=ChangeSeverity.MAJOR,
                file_path="",
                symbol_id=caller,
                description=f"Dependency removed: {caller} -/-> {callee}",
                old_value=callee,
                new_value=None,
            )
            change.add_affected(callee)
            diff.add_change(change)

        return diff

    def compare_reachability(self, start_symbol: str) -> SemanticDiff:
        """
        Compare reachable sets from a symbol

        Args:
            start_symbol: Starting symbol for reachability analysis

        Returns:
            SemanticDiff with reachability changes
        """
        diff = SemanticDiff()

        # Compute reachable sets
        old_reachable = self._compute_reachable(start_symbol, self.context.old_call_graph)
        new_reachable = self._compute_reachable(start_symbol, self.context.new_call_graph)

        # Reachability changed
        if old_reachable != new_reachable:
            added = new_reachable - old_reachable
            removed = old_reachable - new_reachable

            change = SemanticChange(
                change_type=ChangeType.REACHABLE_SET_CHANGED,
                severity=ChangeSeverity.MAJOR,
                file_path="",
                symbol_id=start_symbol,
                description=f"Reachable set changed (+{len(added)}, -{len(removed)})",
                old_value=list(old_reachable),
                new_value=list(new_reachable),
            )

            for symbol in added | removed:
                change.add_affected(symbol)

            diff.add_change(change)

        return diff

    def _get_edges(self, call_graph: Any) -> set[tuple[str, str]]:
        """Get edges from call graph"""
        edges = set()

        if hasattr(call_graph, "edges"):
            cg_edges = call_graph.edges
            if isinstance(cg_edges, dict):
                edges = set(cg_edges.keys())
            else:
                edges = set(cg_edges)

        return edges

    def _compute_reachable(
        self,
        start: str,
        call_graph: Any | None,
        max_depth: int = 10,
    ) -> set[str]:
        """Compute reachable symbols from start"""
        if not call_graph:
            return set()

        reachable = set()
        queue = [(start, 0)]
        visited = set()

        while queue:
            current, depth = queue.pop(0)

            if depth >= max_depth or current in visited:
                continue

            visited.add(current)
            reachable.add(current)

            # Find callees
            if hasattr(call_graph, "edges"):
                edges = call_graph.edges
                if isinstance(edges, dict):
                    for (caller, callee), _ in edges.items():
                        if caller == current:
                            queue.append((callee, depth + 1))

        return reachable

    def detect_side_effects(self, symbol_id: str) -> SemanticDiff:
        """
        Detect side effect changes

        Simplified: checks if new external calls added
        """
        diff = SemanticDiff()

        # Get old and new callees
        old_callees = self._get_callees(symbol_id, self.context.old_call_graph)
        new_callees = self._get_callees(symbol_id, self.context.new_call_graph)

        added_callees = new_callees - old_callees

        if added_callees:
            # Check if any are potential side effects
            # (Simplified: any IO, network, file operations)
            side_effect_keywords = ["write", "send", "delete", "update", "create"]

            for callee in added_callees:
                if any(keyword in callee.lower() for keyword in side_effect_keywords):
                    change = SemanticChange(
                        change_type=ChangeType.SIDE_EFFECT_ADDED,
                        severity=ChangeSeverity.MAJOR,
                        file_path="",
                        symbol_id=symbol_id,
                        description=f"Potential side effect added: {callee}",
                        old_value=None,
                        new_value=callee,
                    )
                    diff.add_change(change)

        return diff

    def _get_callees(self, symbol_id: str, call_graph: Any | None) -> set[str]:
        """Get callees of a symbol"""
        callees = set()

        if not call_graph or not hasattr(call_graph, "edges"):
            return callees

        edges = call_graph.edges
        if isinstance(edges, dict):
            for (caller, callee), _ in edges.items():
                if caller == symbol_id:
                    callees.add(callee)

        return callees

    def __repr__(self) -> str:
        return f"GraphDiffer(context={self.context})"
