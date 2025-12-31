"""
Index Registry (OCP 준수)

Open/Closed Principle을 위한 인덱스 레지스트리.
새 인덱스 추가 시 코드 수정 없이 등록만으로 확장 가능.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.multi_index.domain.ports import SearchableIndex

if TYPE_CHECKING:
    from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit

logger = get_logger(__name__)


@dataclass
class IndexEntry:
    """인덱스 레지스트리 엔트리"""

    name: str
    index: SearchableIndex  # Protocol 기반 타입
    weight: float = 1.0  # 검색 가중치
    phase: int = 1  # Two-phase indexing: 1=fast, 2=heavy
    enabled: bool = True


class IndexRegistry:
    """
    인덱스 레지스트리 (OCP 패턴).

    새 인덱스를 등록하면 자동으로 indexing/search에 포함됨.

    Usage:
        registry = IndexRegistry()
        registry.register("vector", vector_index, weight=0.3, phase=2)
        registry.register("lexical", lexical_index, weight=0.3, phase=1)

        # 모든 인덱스에 대해 인덱싱
        await registry.index_all(repo_id, snapshot_id, docs)

        # 모든 인덱스에서 검색
        hits = await registry.search_all(repo_id, snapshot_id, query)
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._entries: dict[str, IndexEntry] = {}

    def register(
        self,
        name: str,
        index: SearchableIndex,
        weight: float = 1.0,
        phase: int = 1,
        enabled: bool = True,
    ) -> None:
        """
        인덱스 등록.

        Args:
            name: 인덱스 이름 (예: "vector", "lexical")
            index: 인덱스 객체 (SearchableIndex Protocol 구현체)
            weight: 검색 가중치 (기본 1.0)
            phase: Two-phase 단계 (1=fast, 2=heavy)
            enabled: 활성화 여부

        Note:
            index는 SearchableIndex Protocol을 구현해야 합니다.
            즉, async def search(repo_id, snapshot_id, query, limit) 메서드가 필요합니다.
        """
        if index is None:
            return

        # Runtime Protocol 체크 (개발 중 오류 조기 발견)
        if not isinstance(index, SearchableIndex):
            logger.warning(f"index_not_searchable: {name} does not implement SearchableIndex protocol")

        self._entries[name] = IndexEntry(
            name=name,
            index=index,
            weight=weight,
            phase=phase,
            enabled=enabled,
        )
        logger.debug(f"index_registered: {name} (phase={phase}, weight={weight})")

    def unregister(self, name: str) -> None:
        """인덱스 등록 해제"""
        if name in self._entries:
            del self._entries[name]
            logger.debug(f"index_unregistered: {name}")

    def get(self, name: str) -> SearchableIndex | None:
        """인덱스 가져오기"""
        entry = self._entries.get(name)
        return entry.index if entry and entry.enabled else None

    def get_all(self, phase: int | None = None) -> list[IndexEntry]:
        """
        모든 인덱스 가져오기.

        Args:
            phase: 특정 phase만 필터링 (None이면 전체)

        Returns:
            IndexEntry 리스트
        """
        entries = [e for e in self._entries.values() if e.enabled]
        if phase is not None:
            entries = [e for e in entries if e.phase == phase]
        return entries

    def get_weights(self) -> dict[str, float]:
        """검색 가중치 딕셔너리 반환"""
        return {name: entry.weight for name, entry in self._entries.items() if entry.enabled}

    async def execute_all(
        self,
        operation: Callable[[str, SearchableIndex], Awaitable[None]],
        phase: int | None = None,
        parallel: bool = True,
    ) -> list[tuple[str, Exception | None]]:
        """
        모든 인덱스에 대해 작업 실행.

        Args:
            operation: async (name, index) -> None
            phase: 특정 phase만 (None이면 전체)
            parallel: 병렬 실행 여부

        Returns:
            (name, exception | None) 리스트
        """
        entries = self.get_all(phase)
        results: list[tuple[str, Exception | None]] = []

        async def _run(entry: IndexEntry) -> tuple[str, Exception | None]:
            try:
                await operation(entry.name, entry.index)
                return (entry.name, None)
            except Exception as e:
                logger.error(f"index_operation_failed: {entry.name}", exc_info=True)
                return (entry.name, e)

        if parallel:
            tasks = [_run(entry) for entry in entries]
            results = await asyncio.gather(*tasks)
        else:
            for entry in entries:
                results.append(await _run(entry))

        return list(results)

    async def search_all(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int = 100,
    ) -> list["SearchHit"]:
        """
        모든 인덱스에서 검색.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            query: 검색 쿼리
            limit: 각 인덱스별 최대 결과 수

        Returns:
            모든 인덱스의 SearchHit 리스트 (퓨전 전)
        """
        all_hits: list[SearchHit] = []
        entries = self.get_all()

        async def _search(entry: IndexEntry) -> list["SearchHit"]:
            try:
                # SearchableIndex Protocol 보장으로 hasattr 체크 불필요
                return await entry.index.search(repo_id, snapshot_id, query, limit=limit)
            except Exception as e:
                logger.error(f"search_failed: {entry.name}", error=str(e))
                return []

        # 병렬 검색
        tasks = [_search(entry) for entry in entries]
        results = await asyncio.gather(*tasks)

        for hits in results:
            all_hits.extend(hits)

        return all_hits
