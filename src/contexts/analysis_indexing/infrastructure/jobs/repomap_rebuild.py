"""
RepoMap Rebuild Job

RepoMap을 재계산하는 백그라운드 작업.
PageRank, 파일 구조 등을 갱신합니다.
"""

from pathlib import Path

from src.common.observability import get_logger

logger = get_logger(__name__)


class RepoMapRebuildJob:
    """RepoMap 재계산 작업"""

    def __init__(
        self,
        repomap_store,
        chunk_store,
        graph_store,
        config=None,
    ):
        """
        Initialize RepoMap rebuild job.

        Args:
            repomap_store: RepoMapStore instance
            chunk_store: ChunkStore instance
            graph_store: GraphStore instance
            config: RepoMapBuildConfig (optional)
        """
        self.repomap_store = repomap_store
        self.chunk_store = chunk_store
        self.graph_store = graph_store
        self.config = config

    async def run(self, repo_id: str, snapshot_id: str, repo_path: Path | None = None) -> dict:
        """
        RepoMap rebuild 작업 실행.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            repo_path: Repository path (optional)

        Returns:
            실행 결과 dict
        """
        logger.info(
            "repomap_rebuild_job_started",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
        )

        try:
            # 1. Load chunks for this repo/snapshot
            chunks = await self._load_chunks(repo_id, snapshot_id)

            if not chunks:
                logger.warning("repomap_rebuild_no_chunks", repo_id=repo_id)
                return {
                    "status": "skipped",
                    "reason": "no_chunks",
                }

            # 2. Load graph
            graph_doc = await self.graph_store.load_graph(repo_id, snapshot_id)

            if not graph_doc:
                logger.warning("repomap_rebuild_no_graph", repo_id=repo_id)
                return {
                    "status": "skipped",
                    "reason": "no_graph",
                }

            # 3. Build RepoMap
            from src.contexts.repo_structure.infrastructure.builder import RepoMapBuilder
            from src.contexts.repo_structure.infrastructure.models import RepoMapBuildConfig

            config = self.config or RepoMapBuildConfig(
                pagerank_enabled=True,
                summary_enabled=False,  # Disable LLM summaries for background job
                include_tests=False,
                min_loc=10,
                max_depth=10,
            )

            builder = RepoMapBuilder(
                store=self.repomap_store,
                config=config,
                llm=None,  # No LLM for background job
                chunk_store=self.chunk_store,
                repo_path=str(repo_path) if repo_path else None,
            )

            snapshot = await builder.build_async(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                chunks=chunks,
                graph_doc=graph_doc,
            )

            logger.info(
                "repomap_rebuild_job_completed",
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                nodes=len(snapshot.nodes),
                summaries=sum(1 for n in snapshot.nodes if n.summary_body),
            )

            return {
                "status": "success",
                "nodes": len(snapshot.nodes),
                "summaries": sum(1 for n in snapshot.nodes if n.summary_body),
            }

        except Exception as e:
            logger.error(
                "repomap_rebuild_job_failed",
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                error=str(e),
                exc_info=True,
            )

            return {
                "status": "failed",
                "error": str(e),
            }

    async def _load_chunks(self, repo_id: str, snapshot_id: str) -> list:
        """
        특정 repo/snapshot의 모든 chunk 로드.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            Chunk 리스트
        """
        try:
            # ChunkStore 인터페이스에 따라 다름
            # PostgresChunkStore의 경우
            if hasattr(self.chunk_store, "get_chunks_by_repo"):
                return await self.chunk_store.get_chunks_by_repo(repo_id, snapshot_id)

            # Fallback: 개별 로드 (비효율적이지만 호환성)
            logger.warning("chunk_store_no_batch_method_using_fallback")
            return []

        except Exception as e:
            logger.error("failed_to_load_chunks", error=str(e))
            return []

    async def get_last_rebuild_time(self, repo_id: str, snapshot_id: str) -> str | None:
        """
        마지막 rebuild 시간 조회.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            ISO timestamp or None
        """
        try:
            # RepoMapStore에서 snapshot 조회
            snapshot = await self.repomap_store.load_snapshot(repo_id, snapshot_id)

            if snapshot and hasattr(snapshot, "created_at"):
                return snapshot.created_at

            return None

        except Exception:
            return None
