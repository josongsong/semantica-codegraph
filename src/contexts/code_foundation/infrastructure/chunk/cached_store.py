"""
Cached Chunk Store (3-tier)

L1: In-Memory LRU (~0.1ms)
L2: Redis (~1-2ms, shared)
L3: PostgreSQL (~10-50ms, persistent)
"""

from typing import TYPE_CHECKING, Any

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.chunk.models import Chunk
from src.infra.cache.three_tier_cache import L3DatabaseLoader, ThreeTierCache

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.chunk.store import ChunkStore

logger = get_logger(__name__)


class ChunkDBLoader(L3DatabaseLoader[Chunk]):
    """Chunk용 L3 데이터베이스 로더"""

    def __init__(self, chunk_store: "ChunkStore"):
        """
        Args:
            chunk_store: 기존 ChunkStore (PostgreSQL)
        """
        self.store = chunk_store

    async def load(self, key: str) -> Chunk | None:
        """
        DB에서 Chunk 로드.

        Args:
            key: chunk_id

        Returns:
            Chunk or None
        """
        try:
            return await self.store.get_chunk(key)
        except Exception as e:
            logger.warning("chunk_db_load_failed", chunk_id=key, error=str(e))
            return None

    async def save(self, key: str, value: Chunk) -> None:
        """
        DB에 Chunk 저장.

        Args:
            key: chunk_id
            value: Chunk
        """
        try:
            await self.store.save_chunk(value)
        except Exception as e:
            logger.error("chunk_db_save_failed", chunk_id=key, error=str(e))
            raise

    async def delete(self, key: str) -> None:
        """
        DB에서 Chunk 삭제.

        Note: ChunkStore에는 개별 삭제 메서드가 없음 (soft delete 사용)
        이 메서드는 캐시 무효화만 수행

        Args:
            key: chunk_id
        """
        # ChunkStore는 soft delete만 지원하므로 skip
        pass


class CachedChunkStore:
    """
    3-tier 캐싱이 적용된 Chunk Store.

    성능 향상:
    - L1 hit: ~0.1ms (vs 10-50ms DB 조회)
    - L2 hit: ~1-2ms
    - Expected hit rate: 40-60% (L1+L2 combined)

    Usage:
        cached_store = CachedChunkStore(
            chunk_store=postgres_chunk_store,
            redis_client=redis,
            l1_maxsize=1000,
            ttl=300
        )

        # 투명한 API (기존 ChunkStore와 동일)
        chunk = await cached_store.get_by_id(chunk_id)
        await cached_store.save(chunk)
    """

    def __init__(
        self,
        chunk_store: "ChunkStore",
        redis_client: Any | None = None,
        l1_maxsize: int = 1000,
        ttl: int = 300,
    ):
        """
        Args:
            chunk_store: 기존 ChunkStore (PostgreSQL)
            redis_client: Redis 클라이언트 (optional)
            l1_maxsize: L1 최대 크기
            ttl: TTL (초)
        """
        self.store = chunk_store
        self._cache = ThreeTierCache[Chunk](
            l1_maxsize=l1_maxsize,
            l2_redis=redis_client,
            l3_loader=ChunkDBLoader(chunk_store),
            ttl=ttl,
            namespace="chunks",
        )

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        """
        Chunk ID로 조회 (캐싱 적용).

        Args:
            chunk_id: Chunk ID

        Returns:
            Chunk or None
        """
        return await self._cache.get(chunk_id)

    async def save_chunk(self, chunk: Chunk) -> None:
        """
        Chunk 저장 (write-through).

        Args:
            chunk: Chunk to save
        """
        await self._cache.set(chunk.chunk_id, chunk, write_through=True)

    async def save_chunks(self, chunks: list[Chunk]) -> None:
        """
        여러 Chunk 저장.

        Args:
            chunks: Chunks to save
        """
        # Batch save to L3 (DB)
        await self.store.save_chunks(chunks)

        # Populate L1 (L2는 lazy)
        for chunk in chunks:
            self._cache._l1.set(chunk.chunk_id, chunk)

    async def delete_chunks_by_repo(self, repo_id: str, snapshot_id: str) -> None:
        """
        Repository의 모든 Chunk 삭제 (soft delete + 캐시 무효화).

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
        """
        # DB에서 soft delete
        await self.store.delete_chunks_by_repo(repo_id, snapshot_id)

        # 캐시 무효화
        await self.invalidate_repo(repo_id)

    async def find_chunks_by_repo(
        self, repo_id: str, snapshot_id: str | None = None, limit: int | None = None, offset: int = 0
    ) -> list[Chunk]:
        """
        레포지토리의 모든 Chunk 조회 (캐싱 없음 - bulk operation).

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID (optional)
            limit: 최대 조회 개수
            offset: 시작 오프셋

        Returns:
            List of chunks
        """
        # Bulk operation - 캐시 bypass
        return await self.store.find_chunks_by_repo(repo_id, snapshot_id, limit, offset)

    async def get_chunks_by_file(self, repo_id: str, file_path: str, snapshot_id: str | None = None) -> list[Chunk]:
        """
        파일의 모든 Chunk 조회 (캐싱 없음 - bulk operation).

        Args:
            repo_id: Repository ID
            file_path: File path
            snapshot_id: Snapshot ID (optional)

        Returns:
            List of chunks
        """
        # Bulk operation - 캐시 bypass
        return await self.store.get_chunks_by_file(repo_id, file_path, snapshot_id)

    async def get_chunks_by_files_batch(
        self, repo_id: str, file_paths: list[str], commit: str | None = None
    ) -> dict[str, list]:
        """
        여러 파일의 Chunk를 일괄 조회.

        Cache pass-through (배치 조회는 캐싱 복잡도 높음).
        """
        return await self.store.get_chunks_by_files_batch(repo_id, file_paths, commit)

    async def invalidate_repo(self, repo_id: str) -> int:
        """
        레포지토리 관련 캐시 무효화.

        Args:
            repo_id: Repository ID

        Returns:
            무효화된 항목 수
        """
        # repo_id는 chunk_id에 포함되지 않으므로 전체 캐시 클리어
        # 향후 개선: chunk_id에 repo_id 포함하거나 별도 인덱스 유지
        self._cache._l1.clear()
        if self._cache._l2:
            return await self._cache._l2.clear_namespace()
        return 0

    def stats(self) -> dict:
        """캐시 통계 조회"""
        return self._cache.stats()
