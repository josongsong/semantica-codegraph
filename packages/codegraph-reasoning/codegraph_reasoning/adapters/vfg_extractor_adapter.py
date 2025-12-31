"""
VFGExtractor Adapter

Infrastructure MemgraphVFGExtractor를 Port로 래핑
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codegraph_shared.infra.graph.memgraph import MemgraphGraphStore


class VFGExtractorAdapter:
    """
    VFGExtractor Adapter

    Infrastructure → Port 브릿지

    Example:
        adapter = VFGExtractorAdapter(memgraph_store)
        vfg_data = adapter.extract_vfg(repo_id, snapshot_id)
        sources_sinks = adapter.extract_sources_and_sinks(repo_id, snapshot_id)
    """

    def __init__(self, memgraph_store: "MemgraphGraphStore"):
        """
        Initialize adapter

        Args:
            memgraph_store: MemgraphGraphStore instance
        """
        from ..infrastructure.engine.memgraph_extractor import MemgraphVFGExtractor

        self._extractor = MemgraphVFGExtractor(memgraph_store)

    def extract_vfg(
        self,
        repo_id: str | None = None,
        snapshot_id: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """
        VFG 노드/엣지 추출 (Port 메서드)

        Args:
            repo_id: Optional repo filter
            snapshot_id: Optional snapshot filter
            limit: Optional result limit

        Returns:
            {
                "nodes": [...],
                "edges": [...],
                "stats": {...}
            }
        """
        return self._extractor.extract_vfg(repo_id, snapshot_id, limit)

    def extract_sources_and_sinks(
        self,
        repo_id: str | None = None,
        snapshot_id: str | None = None,
    ) -> dict[str, list[str]]:
        """
        Source/Sink 노드 추출 (Port 메서드)

        Args:
            repo_id: Optional repo filter
            snapshot_id: Optional snapshot filter

        Returns:
            {"sources": [...], "sinks": [...]}
        """
        return self._extractor.extract_sources_and_sinks(repo_id, snapshot_id)

    def get_affected_nodes(
        self,
        file_paths: list[str],
        repo_id: str,
        snapshot_id: str,
    ) -> list[str]:
        """
        변경 영향받는 노드 조회 (Port 메서드)

        Args:
            file_paths: List of changed file paths
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            List of affected node IDs
        """
        return self._extractor.get_affected_nodes(file_paths, repo_id, snapshot_id)
