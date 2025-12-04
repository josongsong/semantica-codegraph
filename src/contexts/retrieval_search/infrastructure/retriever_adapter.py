"""
Retriever Adapter

실제 RetrieverServiceV3 어댑터
"""

from ..domain.models import SearchHit, SearchQuery


class RetrieverAdapter:
    """실제 Retriever 어댑터"""

    def __init__(self, retriever_service):
        """
        초기화

        Args:
            retriever_service: RetrieverServiceV3 인스턴스
        """
        self.retriever = retriever_service

    async def search(self, query: SearchQuery) -> list[SearchHit]:
        """검색 실행"""
        try:
            # 실제 RetrieverServiceV3 호출
            hits = await self.retriever.search_with_cache(
                repo_id=query.repo_id,
                query=query.query,
                limit=query.limit,
            )

            # 도메인 모델로 변환
            return [
                SearchHit(
                    id=hit.id,
                    score=hit.score,
                    content=hit.content or "",
                    metadata=hit.metadata or {},
                )
                for hit in hits
            ]
        except Exception as e:
            # 에러 발생 시 빈 결과 반환 (로깅 포함)
            from src.common.observability import get_logger

            logger = get_logger(__name__)
            logger.warning(f"Search failed: {e}", repo_id=query.repo_id, query=query.query)
            return []
