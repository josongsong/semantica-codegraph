"""
Start Session UseCase

세션 시작
"""

from datetime import datetime
from uuid import uuid4

from ..domain.models import Session
from ..ports import SessionStorePort


class StartSessionUseCase:
    """세션 시작 UseCase"""

    def __init__(self, session_store: SessionStorePort):
        """
        초기화

        Args:
            session_store: 세션 저장소
        """
        self.session_store = session_store

    async def execute(self, repo_id: str) -> Session:
        """
        세션 시작

        Args:
            repo_id: 리포지토리 ID

        Returns:
            새 세션
        """
        session = Session(
            id=str(uuid4()),
            repo_id=repo_id,
            started_at=datetime.now(),
            ended_at=None,
        )

        await self.session_store.create(session)

        return session
