"""
Session Query Handler

세션 조회 쿼리 처리기 (CQRS Read Side)
"""

from ...domain.aggregates.indexing_session import IndexingSession
from ...domain.repositories.session_repository import SessionRepository
from ..queries.get_session_query import GetSessionQuery, GetSessionsByRepoQuery


class SessionQueryHandler:
    """세션 조회 쿼리 처리기"""

    def __init__(self, session_repository: SessionRepository):
        """
        초기화

        Args:
            session_repository: 세션 리포지토리
        """
        self.session_repository = session_repository

    async def handle_get_session(self, query: GetSessionQuery) -> IndexingSession | None:
        """
        세션 조회

        Args:
            query: 세션 조회 쿼리

        Returns:
            세션 또는 None
        """
        return await self.session_repository.find_by_id(query.session_id)

    async def handle_get_sessions_by_repo(self, query: GetSessionsByRepoQuery) -> list[IndexingSession]:
        """
        리포지토리별 세션 조회

        Args:
            query: 리포지토리별 세션 조회 쿼리

        Returns:
            세션 리스트
        """
        return await self.session_repository.find_by_repo(query.repo_id)
