"""Merging Lexical Index - Base (Zoekt) + Delta (Tantivy) 융합."""

from typing import TYPE_CHECKING

from src.contexts.multi_index.infrastructure.common.documents import SearchHit
from src.contexts.multi_index.infrastructure.lexical.merge.deduplicator import Deduplicator
from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.contexts.multi_index.infrastructure.lexical.adapter_zoekt import ZoektLexicalIndex
    from src.contexts.multi_index.infrastructure.lexical.delta.delta_index import DeltaLexicalIndex

logger = get_logger(__name__)


class MergingLexicalIndex:
    """Base+Delta Merging Index.

    Zoekt (Base) + Tantivy (Delta)를 융합하여
    최신 상태의 검색 결과를 제공합니다.
    """

    def __init__(
        self,
        base_index: "ZoektLexicalIndex",
        delta_index: "DeltaLexicalIndex",
    ):
        """
        Args:
            base_index: Zoekt Base index
            delta_index: Tantivy Delta index
        """
        self.base = base_index
        self.delta = delta_index
        self.deduplicator = Deduplicator()

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int = 50,
    ) -> list[SearchHit]:
        """Base+Delta 융합 검색.

        SOTA 순서:
        1. Delta 검색 (최신)
        2. Base 검색 (대규모)
        3. Deduplication (Delta wins)
        4. Score normalization

        Args:
            repo_id: 저장소 ID
            snapshot_id: Snapshot ID
            query: 검색 쿼리
            limit: 최대 결과 수

        Returns:
            SearchHit 리스트
        """
        # Query routing (최적화)
        delta_count = await self.delta.count(repo_id)

        if delta_count == 0:
            # Delta 없음 → Base만
            logger.info("Delta empty, Base-only search")
            return await self.base.search(repo_id, snapshot_id, query, limit)

        # Delta 검색
        delta_results = await self.delta.search(repo_id, query, limit)

        # Delta hit ≥ limit이면 Base skip (성능 최적화)
        if len(delta_results) >= limit:
            logger.info(f"Delta hit sufficient ({len(delta_results)} ≥ {limit}), skipping Base")
            return self._convert_to_search_hits(delta_results, limit)

        # Base 검색
        base_results = await self.base.search(repo_id, snapshot_id, query, limit * 2)

        # Tombstone 조회
        tombstones = await self.delta.tombstone.get_tombstones(repo_id)

        # Deduplication (Delta wins)
        base_dicts = [self._search_hit_to_dict(h) for h in base_results]
        merged = self.deduplicator.deduplicate(base_dicts, delta_results, tombstones)

        # SearchHit으로 변환
        search_hits = self._convert_to_search_hits(merged, limit)

        logger.info(f"Merged search: delta={len(delta_results)}, base={len(base_results)}, merged={len(search_hits)}")

        return search_hits

    def _search_hit_to_dict(self, hit: SearchHit) -> dict:
        """SearchHit을 dict로 변환."""
        return {
            "file_path": hit.file_path,
            "score": hit.score,
            "snippet": hit.metadata.get("preview", ""),
            "source": hit.source,
            "chunk_id": hit.chunk_id,
            "symbol_id": hit.symbol_id,
        }

    def _convert_to_search_hits(
        self,
        results: list[dict],
        limit: int,
    ) -> list[SearchHit]:
        """Dict 결과를 SearchHit으로 변환.

        Args:
            results: 검색 결과 (dict)
            limit: 최대 개수

        Returns:
            SearchHit 리스트
        """
        hits = []

        for r in results[:limit]:
            # Delta 결과는 chunk_id가 없을 수 있음 (virtual)
            chunk_id = r.get("chunk_id") or f"virtual:{r['file_path']}"

            hits.append(
                SearchHit(
                    chunk_id=chunk_id,
                    file_path=r["file_path"],
                    symbol_id=r.get("symbol_id"),
                    score=r["score"],
                    source=r.get("source", "merged"),
                    metadata={
                        "preview": r.get("snippet", ""),
                        "mapped": bool(r.get("chunk_id")),
                    },
                )
            )

        return hits

    async def reindex_file(
        self,
        repo_id: str,
        file_path: str,
        content: str,
        base_version_id: int | None = None,
    ) -> bool:
        """파일 인덱싱 (Delta에만).

        Args:
            repo_id: 저장소 ID
            file_path: 파일 경로
            content: 파일 내용
            base_version_id: Base snapshot ID

        Returns:
            성공 여부
        """
        return await self.delta.index_file(repo_id, file_path, content, base_version_id)

    async def delete_file(
        self,
        repo_id: str,
        file_path: str,
        base_version_id: int | None = None,
    ) -> None:
        """파일 삭제 (Tombstone 생성).

        Args:
            repo_id: 저장소 ID
            file_path: 파일 경로
            base_version_id: Base snapshot ID
        """
        await self.delta.delete_file(repo_id, file_path, base_version_id)

    async def get_delta_size(self, repo_id: str) -> int:
        """Delta 크기 조회.

        Args:
            repo_id: 저장소 ID

        Returns:
            Delta 파일 개수
        """
        return await self.delta.count(repo_id)
