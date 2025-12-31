"""
Search Fusion Service

검색 결과 퓨전 담당 (Single Responsibility).

Responsibilities:
- 다중 인덱스 검색 조정
- 가중치 기반 결과 퓨전
- 점수 정규화
"""

from typing import Any, Literal, cast

from codegraph_shared.common.observability import get_logger
from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit
from codegraph_engine.multi_index.infrastructure.service.index_registry import IndexRegistry

# SearchHit.source의 Literal 타입 정의
SourceType = Literal["lexical", "vector", "symbol", "fuzzy", "domain", "runtime", "fused"]

logger = get_logger(__name__)


class SearchFusion:
    """
    검색 결과 퓨전 서비스.

    다중 인덱스의 검색 결과를 가중치 기반으로 퓨전합니다.

    Usage:
        fusion = SearchFusion(registry)
        hits = await fusion.search(repo_id, snapshot_id, query, limit=50)
    """

    # 기본 가중치
    DEFAULT_WEIGHTS = {
        "lexical": 0.3,
        "vector": 0.3,
        "symbol": 0.2,
        "fuzzy": 0.1,
        "domain": 0.1,
    }

    def __init__(self, registry: IndexRegistry):
        """
        Args:
            registry: 인덱스 레지스트리
        """
        self._registry = registry

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int = 50,
        weights: dict[str, float] | None = None,
    ) -> list[SearchHit]:
        """
        통합 검색.

        모든 등록된 인덱스에서 검색 후 가중치 기반 퓨전.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            query: 검색 쿼리
            limit: 최대 결과 수
            weights: 소스별 가중치 (None이면 레지스트리 설정 사용)

        Returns:
            퓨전된 SearchHit 리스트 (점수 내림차순)
        """
        # 가중치 결정
        if weights is None:
            weights = self._registry.get_weights()
            if not weights:
                weights = self.DEFAULT_WEIGHTS

        # 모든 인덱스에서 검색
        raw_hits = await self._registry.search_all(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            limit=100,  # 퓨전 전 충분한 결과
        )

        if not raw_hits:
            logger.warning(f"search_no_results: query={query[:50]}")
            return []

        # SearchHit로 변환 (타입 안전성)
        all_hits = self._normalize_hits(raw_hits)

        if not all_hits:
            return []

        # 퓨전
        fused_hits = self._fuse_hits(all_hits, weights)

        sources_count = len({h.source for h in all_hits})
        logger.info(f"search_fused: {len(all_hits)} hits from {sources_count} sources -> {len(fused_hits)} results")

        return fused_hits[:limit]

    # 유효한 source 값
    VALID_SOURCES = {"lexical", "vector", "symbol", "fuzzy", "domain", "runtime", "fused"}

    def _normalize_hits(self, raw_hits: list[Any]) -> list[SearchHit]:
        """
        Raw 검색 결과를 SearchHit로 정규화.

        다양한 인덱스에서 반환되는 결과를 통일된 형식으로 변환.
        """
        normalized: list[SearchHit] = []

        for hit in raw_hits:
            # 이미 SearchHit인 경우
            if isinstance(hit, SearchHit):
                normalized.append(hit)
                continue

            # dict인 경우 변환 시도
            if isinstance(hit, dict):
                try:
                    normalized.append(SearchHit(**hit))
                except Exception:
                    logger.debug(f"skip_invalid_hit_dict: {type(hit)}")
                continue

            # chunk_id, score, source 속성이 있는 객체
            if hasattr(hit, "chunk_id") and hasattr(hit, "score"):
                try:
                    source_raw = getattr(hit, "source", "fused")
                    # source 값 검증 후 타입 안전하게 변환
                    if source_raw not in self.VALID_SOURCES:
                        # Log warning for invalid source instead of silent fallback
                        logger.warning(
                            "invalid_search_hit_source",
                            source=source_raw,
                            chunk_id=getattr(hit, "chunk_id", "unknown"),
                            valid_sources=list(self.VALID_SOURCES),
                        )
                        source_raw = "fused"
                    source: SourceType = cast(SourceType, source_raw)

                    normalized.append(
                        SearchHit(
                            chunk_id=hit.chunk_id,
                            score=hit.score,
                            source=source,
                            file_path=getattr(hit, "file_path", None),
                            symbol_id=getattr(hit, "symbol_id", None),
                            metadata=getattr(hit, "metadata", {}),
                        )
                    )
                except Exception:
                    logger.debug(f"skip_invalid_hit_obj: {type(hit)}")

        return normalized

    def _fuse_hits(
        self,
        hits: list[SearchHit],
        weights: dict[str, float],
    ) -> list[SearchHit]:
        """
        가중치 기반 결과 퓨전.

        동일 chunk_id에 대해 가중 평균 점수 계산.

        Performance:
            - Grouping: O(n)
            - Fusion calculation: O(n)
            - Final sorting: O(n log n)
            - Total: O(n log n)

        Args:
            hits: 모든 검색 결과 (정렬 불필요)
            weights: 소스별 가중치

        Returns:
            퓨전 및 정렬된 결과
        """
        # chunk_id별 그룹핑
        hit_groups: dict[str, list[SearchHit]] = {}
        for hit in hits:
            if hit.chunk_id not in hit_groups:
                hit_groups[hit.chunk_id] = []
            hit_groups[hit.chunk_id].append(hit)

        # 퓨전 점수 계산
        fused: list[SearchHit] = []
        for chunk_id, chunk_hits in hit_groups.items():
            weighted_score = 0.0
            total_weight = 0.0
            representative = chunk_hits[0]

            for hit in chunk_hits:
                weight = weights.get(hit.source, 0.0)
                weighted_score += hit.score * weight
                total_weight += weight

            final_score = weighted_score / total_weight if total_weight > 0 else 0.0

            # 메타데이터 구성
            if len(chunk_hits) == 1:
                metadata = representative.metadata.copy()
            else:
                metadata = {
                    **representative.metadata,
                    "sources": [h.source for h in chunk_hits],
                    "original_scores": {h.source: h.score for h in chunk_hits},
                }

            fused.append(
                SearchHit(
                    chunk_id=chunk_id,
                    file_path=representative.file_path,
                    symbol_id=representative.symbol_id,
                    score=final_score,
                    source=representative.source,
                    metadata=metadata,
                )
            )

        # 점수 내림차순 정렬
        fused.sort(key=lambda h: h.score, reverse=True)
        return fused
