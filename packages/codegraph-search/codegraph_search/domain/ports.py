"""
Retrieval Search Domain Ports

검색 도메인의 포트 인터페이스
"""

from typing import Protocol

from .models import Intent, SearchHit, SearchQuery


class SearchEnginePort(Protocol):
    """검색 엔진 포트"""

    async def search(self, query: SearchQuery) -> list[SearchHit]:
        """검색 실행"""
        ...


class IntentAnalyzerPort(Protocol):
    """인텐트 분석 포트"""

    async def analyze(self, query: str) -> Intent:
        """쿼리 인텐트 분석"""
        ...


class FusionEnginePort(Protocol):
    """결과 융합 포트"""

    async def fuse(
        self,
        results: dict[str, list[SearchHit]],
        intent: Intent | None = None,
    ) -> list[SearchHit]:
        """여러 검색 결과를 융합"""
        ...


class RerankerPort(Protocol):
    """재순위화 포트"""

    async def rerank(
        self,
        query: str,
        hits: list[SearchHit],
    ) -> list[SearchHit]:
        """검색 결과 재순위화"""
        ...
