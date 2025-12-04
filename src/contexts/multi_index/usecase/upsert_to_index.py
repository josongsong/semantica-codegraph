"""
Upsert To Index UseCase

인덱스에 데이터 업서트
"""

from ..domain.models import IndexType, UpsertResult
from ..domain.ports import IndexPort


class UpsertToIndexUseCase:
    """인덱스 업서트 UseCase"""

    def __init__(self, index: IndexPort, index_type: IndexType):
        """
        초기화

        Args:
            index: 인덱스
            index_type: 인덱스 타입
        """
        self.index = index
        self.index_type = index_type

    async def execute(self, data: list[dict], repo_id: str) -> UpsertResult:
        """
        인덱스 업서트 실행

        Args:
            data: 업서트할 데이터
            repo_id: 리포지토리 ID

        Returns:
            업서트 결과
        """
        result = await self.index.upsert(data, repo_id)
        return result
