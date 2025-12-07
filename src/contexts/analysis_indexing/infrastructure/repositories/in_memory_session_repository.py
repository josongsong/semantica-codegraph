"""
In-Memory Session Repository

메모리 기반 세션 리포지토리 (테스트/개발용)
"""

from ...domain.aggregates.indexing_session import IndexingSession


class InMemorySessionRepository:
    """인메모리 세션 리포지토리"""

    def __init__(self):
        """초기화"""
        self._sessions: dict[str, IndexingSession] = {}

    async def save(self, session: IndexingSession) -> None:
        """
        세션 저장

        Args:
            session: 인덱싱 세션
        """
        self._sessions[session.session_id] = session

    async def find_by_id(self, session_id: str) -> IndexingSession | None:
        """
        ID로 세션 조회

        Args:
            session_id: 세션 ID

        Returns:
            세션 또는 None
        """
        return self._sessions.get(session_id)

    async def find_by_repo(self, repo_id: str) -> list[IndexingSession]:
        """
        리포지토리 ID로 세션 조회

        Args:
            repo_id: 리포지토리 ID

        Returns:
            세션 리스트
        """
        return [s for s in self._sessions.values() if s.repo_id == repo_id]

    async def delete(self, session_id: str) -> None:
        """
        세션 삭제

        Args:
            session_id: 세션 ID
        """
        self._sessions.pop(session_id, None)

    def clear(self) -> None:
        """모든 세션 삭제 (테스트용)"""
        self._sessions.clear()
