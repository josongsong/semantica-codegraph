"""
Session Repository Interface

애그리게이트 루트 영속화 인터페이스
"""

from typing import Protocol

from ..aggregates.indexing_session import IndexingSession


class SessionRepository(Protocol):
    """세션 리포지토리 인터페이스"""

    async def save(self, session: IndexingSession) -> None:
        """
        세션 저장

        Args:
            session: 인덱싱 세션
        """
        ...

    async def find_by_id(self, session_id: str) -> IndexingSession | None:
        """
        ID로 세션 조회

        Args:
            session_id: 세션 ID

        Returns:
            세션 또는 None
        """
        ...

    async def find_by_repo(self, repo_id: str) -> list[IndexingSession]:
        """
        리포지토리 ID로 세션 조회

        Args:
            repo_id: 리포지토리 ID

        Returns:
            세션 리스트
        """
        ...

    async def delete(self, session_id: str) -> None:
        """
        세션 삭제

        Args:
            session_id: 세션 ID
        """
        ...
