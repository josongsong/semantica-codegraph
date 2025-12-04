"""
Delete From Indexes UseCase

인덱스에서 데이터 삭제
"""

from ..domain.models import DeleteResult, IndexType
from ..domain.ports import IndexPort


class DeleteFromIndexesUseCase:
    """인덱스 삭제 UseCase"""

    def __init__(self, index: IndexPort, index_type: IndexType):
        """
        초기화

        Args:
            index: 인덱스
            index_type: 인덱스 타입
        """
        self.index = index
        self.index_type = index_type

    async def execute(self, ids: list[str], repo_id: str) -> DeleteResult:
        """
        인덱스에서 삭제

        Args:
            ids: 삭제할 ID 리스트
            repo_id: 리포지토리 ID

        Returns:
            삭제 결과
        """
        result = await self.index.delete(ids, repo_id)
        return result
