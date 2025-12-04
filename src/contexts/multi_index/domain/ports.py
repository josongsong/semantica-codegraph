"""
Multi Index Domain Ports

다중 인덱스 관리 포트
"""

from typing import Protocol

from .models import DeleteResult, UpsertResult


class IndexPort(Protocol):
    """인덱스 포트"""

    async def upsert(self, data: list[dict], repo_id: str) -> UpsertResult:
        """데이터 업서트"""
        ...

    async def delete(self, ids: list[str], repo_id: str) -> DeleteResult:
        """데이터 삭제"""
        ...

    async def search(self, query: str, repo_id: str, limit: int) -> list[dict]:
        """검색"""
        ...
