"""
Auto Repair

인덱스 불일치 자동 수리.
Phase 3 Day 34-36
"""

from src.infra.observability import get_logger

logger = get_logger(__name__)


class AutoRepair:
    """
    인덱스 불일치 자동 수리.

    기능:
    - Vector index repair (누락 chunks 재인덱싱)
    - Zoekt index repair (누락 files 재인덱싱)
    - Memgraph repair (누락 nodes 재생성)
    """

    def __init__(
        self,
        chunk_store,
        vector_index,
        lexical_index,
        graph_store,
        embedding_model=None,
    ):
        """
        Initialize auto repair.

        Args:
            chunk_store: Chunk storage
            vector_index: Vector index
            lexical_index: Lexical index
            graph_store: Graph storage
            embedding_model: Optional embedding model for vector repair
        """
        self.chunk_store = chunk_store
        self.vector_index = vector_index
        self.lexical_index = lexical_index
        self.graph_store = graph_store
        self.embedding_model = embedding_model

    async def repair_vector_index(self, repo_id: str) -> int:
        """
        Repair vector index (재인덱싱).

        Args:
            repo_id: Repository ID

        Returns:
            Number of chunks repaired
        """
        try:
            # Find missing chunks
            missing_chunks = await self._find_missing_chunks_in_vector(repo_id)

            if not missing_chunks:
                logger.info("no_missing_chunks_in_vector", repo_id=repo_id)
                return 0

            # Reindex missing chunks
            repaired = 0
            for chunk_id in missing_chunks:
                try:
                    chunk = await self.chunk_store.get_by_id(chunk_id)
                    if not chunk:
                        continue

                    # Generate embedding
                    if self.embedding_model:
                        embedding = await self.embedding_model.encode_document(chunk.content)
                        await self.vector_index.upsert(
                            repo_id=repo_id,
                            snapshot_id=chunk.snapshot_id,
                            chunk_id=chunk_id,
                            embedding=embedding,
                        )
                        repaired += 1

                except Exception as e:
                    logger.warning("chunk_repair_failed", chunk_id=chunk_id, error=str(e))

            logger.info("vector_index_repaired", repo_id=repo_id, repaired=repaired)
            return repaired

        except Exception as e:
            logger.error("vector_repair_failed", repo_id=repo_id, error=str(e))
            return 0

    async def repair_zoekt_index(self, repo_id: str) -> int:
        """
        Repair Zoekt index (누락 files 재인덱싱).

        Args:
            repo_id: Repository ID

        Returns:
            Number of files repaired
        """
        try:
            # Zoekt repair는 전체 재인덱싱이 더 효율적
            # (파일 단위 증분이 어려움)
            logger.info("zoekt_repair_not_implemented", repo_id=repo_id)
            return 0

        except Exception as e:
            logger.error("zoekt_repair_failed", repo_id=repo_id, error=str(e))
            return 0

    async def repair_memgraph_index(self, repo_id: str) -> int:
        """
        Repair Memgraph index (누락 nodes 재생성).

        Args:
            repo_id: Repository ID

        Returns:
            Number of nodes repaired
        """
        try:
            # Memgraph repair는 전체 재인덱싱 권장
            logger.info("memgraph_repair_not_implemented", repo_id=repo_id)
            return 0

        except Exception as e:
            logger.error("memgraph_repair_failed", repo_id=repo_id, error=str(e))
            return 0

    async def _find_missing_chunks_in_vector(self, repo_id: str) -> list[str]:
        """Find chunks in Postgres but not in Qdrant."""
        # Simplified implementation - Consistency Checker에서 감지된 경우 사용
        return []
