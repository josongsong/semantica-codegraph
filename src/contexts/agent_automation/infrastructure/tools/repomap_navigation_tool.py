"""
RepoMap Navigation Tool

RepoMap 계층 구조 탐색 도구.

기능:
- 중요도 높은 노드 찾기 (top_nodes)
- 경로로 노드 검색 (search_path)
- 자식 노드 조회 (get_children)
- 조상 노드 조회 (get_ancestors)
"""

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.schemas import (
    RepoMapNavigationInput,
    RepoMapNavigationOutput,
    RepoMapNodeInfo,
)
from src.contexts.agent_automation.infrastructure.tools.base import BaseTool
from src.contexts.repo_structure.infrastructure.models import RepoMapNode
from src.contexts.repo_structure.infrastructure.storage import RepoMapStore

logger = get_logger(__name__)


class RepoMapNavigationTool(BaseTool[RepoMapNavigationInput, RepoMapNavigationOutput]):
    """
    RepoMap 탐색 도구.

    RepoMapStore를 사용하여 코드베이스 구조를 탐색합니다.
    """

    name = "repomap_navigate"
    description = "Navigate repository structure using RepoMap"
    input_schema = RepoMapNavigationInput
    output_schema = RepoMapNavigationOutput

    def __init__(
        self,
        store: RepoMapStore | None = None,
        repo_id: str = "default",
        snapshot_id: str = "main",
    ):
        """
        Initialize RepoMap navigation tool.

        Args:
            store: RepoMapStore instance
            repo_id: Repository ID
            snapshot_id: Snapshot ID
        """
        super().__init__()
        self.store = store
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id

    def set_store(self, store: RepoMapStore, repo_id: str, snapshot_id: str) -> None:
        """Set RepoMap store and identifiers."""
        self.store = store
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id

    async def _execute(self, input_data: RepoMapNavigationInput) -> RepoMapNavigationOutput:
        """
        Execute RepoMap navigation.

        Args:
            input_data: Navigation parameters

        Returns:
            Navigation results with nodes
        """
        if not self.store:
            return RepoMapNavigationOutput(
                success=False,
                error="RepoMap store not initialized",
            )

        try:
            # Execute query based on type
            if input_data.query_type == "top_nodes":
                nodes = await self._get_top_nodes(input_data.limit, input_data.min_importance)
            elif input_data.query_type == "search_path":
                if not input_data.path:
                    return RepoMapNavigationOutput(
                        success=False,
                        error="path parameter required for search_path query",
                    )
                nodes = await self._search_by_path(input_data.path, input_data.limit)
            elif input_data.query_type == "get_children":
                if not input_data.node_id:
                    return RepoMapNavigationOutput(
                        success=False,
                        error="node_id parameter required for get_children query",
                    )
                nodes = await self._get_children(input_data.node_id)
            elif input_data.query_type == "get_ancestors":
                if not input_data.node_id:
                    return RepoMapNavigationOutput(
                        success=False,
                        error="node_id parameter required for get_ancestors query",
                    )
                nodes = await self._get_ancestors(input_data.node_id)
            else:
                return RepoMapNavigationOutput(
                    success=False,
                    error=f"Unknown query type: {input_data.query_type}",
                )

            # Convert to output format
            node_infos = [self._node_to_info(node) for node in nodes]

            return RepoMapNavigationOutput(
                success=True,
                nodes=node_infos,
                total_found=len(node_infos),
            )

        except Exception as e:
            logger.error(f"RepoMap navigation failed: {e}", exc_info=True)
            return RepoMapNavigationOutput(
                success=False,
                error=str(e),
            )

    async def _get_top_nodes(self, limit: int, min_importance: float) -> list[RepoMapNode]:
        """Get top N most important nodes."""
        if not self.store:
            return []

        # Get snapshot
        snapshot = await self.store.get_snapshot(self.repo_id, self.snapshot_id)
        if not snapshot:
            return []

        # Get all nodes
        nodes = await self.store.get_nodes(self.repo_id, self.snapshot_id)

        # Filter by importance and sort
        filtered_nodes = [node for node in nodes if node.metrics.importance_score >= min_importance]

        # Sort by importance descending
        sorted_nodes = sorted(
            filtered_nodes,
            key=lambda n: n.metrics.importance_score,
            reverse=True,
        )

        return sorted_nodes[:limit]

    async def _search_by_path(self, path: str, limit: int) -> list[RepoMapNode]:
        """Search nodes by file/directory path."""
        if not self.store:
            return []

        # Get all nodes
        nodes = await self.store.get_nodes(self.repo_id, self.snapshot_id)

        # Filter by path
        matching_nodes = [node for node in nodes if node.path and path in node.path]

        # Sort by importance
        sorted_nodes = sorted(
            matching_nodes,
            key=lambda n: n.metrics.importance_score,
            reverse=True,
        )

        return sorted_nodes[:limit]

    async def _get_children(self, node_id: str) -> list[RepoMapNode]:
        """Get child nodes."""
        if not self.store:
            return []

        # Get parent node
        parent_node = await self.store.get_node(node_id)
        if not parent_node:
            return []

        # Get children
        children = []
        for child_id in parent_node.children_ids:
            child = await self.store.get_node(child_id)
            if child:
                children.append(child)

        # Sort by importance
        children.sort(key=lambda n: n.metrics.importance_score, reverse=True)

        return children

    async def _get_ancestors(self, node_id: str) -> list[RepoMapNode]:
        """Get ancestor nodes (path to root)."""
        if not self.store:
            return []

        ancestors = []
        current_node = await self.store.get_node(node_id)

        while current_node and current_node.parent_id:
            parent = await self.store.get_node(current_node.parent_id)
            if parent:
                ancestors.append(parent)
                current_node = parent
            else:
                break

        return ancestors

    def _node_to_info(self, node: RepoMapNode) -> RepoMapNodeInfo:
        """Convert RepoMapNode to RepoMapNodeInfo."""
        return RepoMapNodeInfo(
            node_id=node.id,
            kind=node.kind,
            name=node.name,
            path=node.path,
            importance_score=node.metrics.importance_score,
            summary=node.summary_overview or node.summary_detailed,
            children_count=len(node.children_ids),
        )
