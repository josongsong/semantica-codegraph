"""
Query Memory UseCase

메모리 조회
"""

from ..domain.models import Memory
from ..ports import MemoryStorePort


class QueryMemoryUseCase:
    """메모리 조회 UseCase"""

    def __init__(self, memory_store: MemoryStorePort):
        """
        초기화

        Args:
            memory_store: 메모리 저장소
        """
        self.memory_store = memory_store

    async def execute(self, session_id: str, limit: int = 10) -> list[Memory]:
        """
        메모리 조회

        Args:
            session_id: 세션 ID
            limit: 결과 수

        Returns:
            메모리 리스트
        """
        memories = await self.memory_store.retrieve(session_id, limit)
        return memories
