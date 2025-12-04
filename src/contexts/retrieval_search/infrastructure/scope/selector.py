"""
Scope Selector

Selects search scope based on query intent and RepoMap.
"""

from typing import TYPE_CHECKING

from src.contexts.retrieval_search.infrastructure.intent.models import IntentKind, QueryIntent
from src.contexts.retrieval_search.infrastructure.scope.models import ScopeResult
from src.contexts.retrieval_search.infrastructure.scope.validator import RepoMapValidator

if TYPE_CHECKING:
    from src.contexts.repo_structure.infrastructure.models import RepoMapNode, RepoMapSnapshot
    from src.ports import RepoMapPort
from src.common.observability import get_logger

logger = get_logger(__name__)


class ScopeSelector:
    """
    Selects search scope based on intent and RepoMap.

    Narrows search to relevant parts of the codebase using RepoMap
    importance metrics and query hints.
    """

    def __init__(
        self,
        repomap_port: "RepoMapPort",
        default_top_k: int = 20,
        max_chunk_ids: int = 500,
    ):
        """
        Initialize scope selector.

        Args:
            repomap_port: RepoMap query port
            default_top_k: Default number of top-importance nodes
            max_chunk_ids: Maximum chunk IDs to include in scope
        """
        self.repomap_port = repomap_port
        self.default_top_k = default_top_k
        self.max_chunk_ids = max_chunk_ids

        self.validator = RepoMapValidator(repomap_port)

    def select_scope(
        self,
        repo_id: str,
        snapshot_id: str,
        intent: QueryIntent,
    ) -> ScopeResult:
        """
        Select search scope based on intent and RepoMap.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            intent: Query intent

        Returns:
            ScopeResult with selected scope
        """
        # Validate RepoMap freshness
        status, can_use = self.validator.validate_or_warn(repo_id, snapshot_id)

        if not can_use:
            logger.info(f"RepoMap not usable (status={status.value}) - using full-repo scope")
            return ScopeResult(
                scope_type="full_repo",
                reason=f"repomap_{status.value}",
                metadata={"repomap_status": status.value},
            )

        # Get RepoMap snapshot
        repomap = self.validator.get_snapshot(repo_id, snapshot_id)
        if repomap is None:
            return ScopeResult(
                scope_type="full_repo",
                reason="repomap_missing",
            )

        # Select focus nodes based on intent
        focus_nodes = self._select_focus_nodes(repomap, intent)

        if not focus_nodes:
            logger.info("No focus nodes selected - using full-repo scope")
            return ScopeResult(
                scope_type="full_repo",
                reason="no_focus_nodes",
                metadata={"repomap_status": status.value},
            )

        # Calculate chunk scope
        chunk_ids = self._calculate_chunk_scope(repomap, focus_nodes)

        logger.info(f"Scope selected: {len(focus_nodes)} nodes, {len(chunk_ids)} chunks (intent={intent.kind.value})")

        return ScopeResult(
            scope_type="focused",
            reason=f"intent_{intent.kind.value}",
            focus_nodes=focus_nodes,
            chunk_ids=chunk_ids,
            metadata={
                "repomap_status": status.value,
                "intent_kind": intent.kind.value,
                "node_count": len(focus_nodes),
                "chunk_count": len(chunk_ids),
            },
        )

    def _select_focus_nodes(
        self,
        repomap: "RepoMapSnapshot",
        intent: QueryIntent,
    ) -> list["RepoMapNode"]:
        """
        Select focus nodes based on intent.

        Args:
            repomap: RepoMap snapshot
            intent: Query intent

        Returns:
            List of focus RepoMap nodes
        """
        focus_nodes = []

        # Strategy 1: Symbol-based selection
        if intent.symbol_names:
            logger.debug(f"Selecting nodes by symbols: {intent.symbol_names}")
            for symbol_name in intent.symbol_names:
                nodes = self._find_nodes_by_symbol(repomap, symbol_name)
                focus_nodes.extend(nodes)

        # Strategy 2: Path-based selection
        if intent.file_paths:
            logger.debug(f"Selecting nodes by paths: {intent.file_paths}")
            for path in intent.file_paths:
                nodes = self.repomap_port.get_nodes_by_path(repomap.repo_id, repomap.snapshot_id, path)
                focus_nodes.extend(nodes)

        # Strategy 3: Module-based selection
        if intent.module_paths:
            logger.debug(f"Selecting nodes by modules: {intent.module_paths}")
            for module_path in intent.module_paths:
                nodes = self._find_nodes_by_module(repomap, module_path)
                focus_nodes.extend(nodes)

        # Strategy 4: Intent-based selection
        if not focus_nodes:
            logger.debug(f"No specific hints - using intent-based selection: {intent.kind.value}")
            focus_nodes = self._select_by_intent_kind(repomap, intent.kind)

        # Expand to include subtrees
        expanded_nodes = self._expand_with_subtrees(repomap, focus_nodes)

        # Limit to reasonable size
        if len(expanded_nodes) > 100:
            # Sort by importance and take top N
            expanded_nodes.sort(key=lambda n: n.metrics.importance, reverse=True)
            expanded_nodes = expanded_nodes[:100]
            logger.debug("Limited expanded nodes to top 100 by importance")

        return expanded_nodes

    def _find_nodes_by_symbol(self, repomap: "RepoMapSnapshot", symbol_name: str) -> list["RepoMapNode"]:
        """Find nodes matching symbol name."""
        matching_nodes = []

        for node in repomap.nodes:
            # Exact match on name
            if node.name == symbol_name:
                matching_nodes.append(node)
                continue

            # FQN contains symbol
            if node.fqn and symbol_name in node.fqn:
                matching_nodes.append(node)
                continue

        return matching_nodes

    def _find_nodes_by_module(self, repomap: "RepoMapSnapshot", module_path: str) -> list["RepoMapNode"]:
        """Find nodes matching module path."""
        matching_nodes = []

        for node in repomap.nodes:
            if node.kind in ["module", "dir"]:
                # Check if module path matches
                if node.path and module_path in node.path:
                    matching_nodes.append(node)

                # Check FQN for Python modules
                if node.fqn and module_path in node.fqn:
                    matching_nodes.append(node)

        return matching_nodes

    def _select_by_intent_kind(self, repomap: "RepoMapSnapshot", intent_kind: IntentKind) -> list["RepoMapNode"]:
        """
        Select focus nodes based on intent kind with specialized strategies.

        Strategies:
        - REPO_OVERVIEW: Entrypoints, top-level structure
        - CONCEPT_SEARCH: High-importance nodes, exclude tests
        - CODE_SEARCH: Implementation nodes, exclude interfaces
        - SYMBOL_NAV: Specific symbols, their usages
        - FLOW_TRACE: High-degree nodes, call graphs
        """
        if intent_kind == IntentKind.REPO_OVERVIEW:
            # Entrypoints and top-level modules for overview
            nodes = [n for n in repomap.nodes if n.is_entrypoint or n.depth <= 2]
            nodes.sort(key=lambda n: n.metrics.importance, reverse=True)
            return nodes[: self.default_top_k]

        if intent_kind == IntentKind.CONCEPT_SEARCH:
            # High-importance nodes, exclude tests for concept understanding
            nodes = [n for n in repomap.nodes if not n.is_test and n.metrics.importance > 0.0]
            nodes.sort(key=lambda n: n.metrics.importance, reverse=True)
            return nodes[: self.default_top_k]

        if intent_kind == IntentKind.CODE_SEARCH:
            # Implementation code: functions/classes with actual logic
            nodes = [
                n for n in repomap.nodes if n.kind in ["function", "class"] and not n.is_test and n.metrics.loc > 10
            ]  # Has substantial code
            nodes.sort(key=lambda n: n.metrics.importance, reverse=True)
            return nodes[: self.default_top_k]

        if intent_kind == IntentKind.SYMBOL_NAV:
            # Symbols with high connectivity (important in graph)
            nodes = [n for n in repomap.nodes if n.metrics.edge_degree > 0 or n.is_entrypoint]
            nodes.sort(key=lambda n: (n.metrics.pagerank or 0.0), reverse=True)
            return nodes[: self.default_top_k]

        if intent_kind == IntentKind.FLOW_TRACE:
            # High-degree nodes for flow tracing
            nodes = [n for n in repomap.nodes if n.metrics.edge_degree > 2]
            nodes.sort(key=lambda n: n.metrics.edge_degree, reverse=True)
            return nodes[: self.default_top_k]

        # Default: top-K by importance
        return self.repomap_port.get_topk_by_importance(repomap.repo_id, repomap.snapshot_id, k=self.default_top_k)

    def _expand_with_subtrees(self, repomap: "RepoMapSnapshot", nodes: list["RepoMapNode"]) -> list["RepoMapNode"]:
        """
        Expand nodes to include their subtrees (optimized).

        Uses dict-based lookup for O(1) node access instead of O(n) iteration.
        """
        # Build node lookup dict once
        node_dict = {n.id: n for n in repomap.nodes}
        expanded_ids = set()

        for node in nodes:
            subtree = repomap.get_subtree(node.id)
            for subtree_node in subtree:
                expanded_ids.add(subtree_node.id)

        # Convert back to list using dict lookup
        result = [node_dict[nid] for nid in expanded_ids if nid in node_dict]

        return result

    def _calculate_chunk_scope(self, repomap: "RepoMapSnapshot", focus_nodes: list["RepoMapNode"]) -> set[str]:
        """
        Calculate chunk IDs within scope.

        Args:
            repomap: RepoMap snapshot
            focus_nodes: Focus nodes

        Returns:
            Set of chunk IDs
        """
        chunk_ids = set()

        for node in focus_nodes:
            chunk_ids.update(node.chunk_ids)

        # Limit to max size
        if len(chunk_ids) > self.max_chunk_ids:
            logger.warning(f"Chunk scope too large ({len(chunk_ids)} chunks), limiting to {self.max_chunk_ids}")
            chunk_ids = set(list(chunk_ids)[: self.max_chunk_ids])

        return chunk_ids
