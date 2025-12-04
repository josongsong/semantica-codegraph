"""
Search Code UseCase

코드 검색
"""

from ..domain.models import SearchHit, SearchQuery
from ..domain.ports import SearchEnginePort


class SearchCodeUseCase:
    """코드 검색 UseCase"""

    def __init__(self, search_engine: SearchEnginePort):
        """
        초기화

        Args:
            search_engine: 검색 엔진
        """
        self.search_engine = search_engine

    async def execute(
        self,
        repo_id: str,
        query: str,
        limit: int = 10,
    ) -> list[SearchHit]:
        """
        코드 검색 실행

        Args:
            repo_id: 리포지토리 ID
            query: 검색 쿼리
            limit: 결과 수

        Returns:
            검색 결과 리스트
        """
        # 1. SearchQuery 생성
        search_query = SearchQuery(
            query=query,
            repo_id=repo_id,
            limit=limit,
        )

        # 2. 검색 실행
        hits = await self.search_engine.search(search_query)

        # 3. 순위 부여
        for i, hit in enumerate(hits, 1):
            hit.rank = i

        return hits
