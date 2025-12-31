"""
Fake Index

테스트용 인메모리 인덱스
"""

from ..domain.models import DeleteResult, IndexType, UpsertResult


class FakeIndex:
    """테스트용 Fake 인덱스"""

    def __init__(self, index_type: IndexType):
        """
        초기화

        Args:
            index_type: 인덱스 타입
        """
        self.index_type = index_type
        self.data: dict[str, dict] = {}

    async def upsert(self, data: list[dict], repo_id: str) -> UpsertResult:
        """데이터 업서트"""
        count = 0
        errors = []

        for item in data:
            try:
                item_id = item.get("id", f"{repo_id}-{count}")
                self.data[item_id] = {**item, "repo_id": repo_id}
                count += 1
            except Exception as e:
                errors.append(str(e))

        return UpsertResult(
            index_type=self.index_type,
            success=len(errors) == 0,
            count=count,
            errors=errors,
        )

    async def delete(self, ids: list[str], repo_id: str) -> DeleteResult:
        """데이터 삭제"""
        deleted = 0

        for item_id in ids:
            if item_id in self.data:
                del self.data[item_id]
                deleted += 1

        return DeleteResult(
            index_type=self.index_type,
            deleted_count=deleted,
        )

    async def search(self, query: str, repo_id: str, limit: int) -> list[dict]:
        """검색"""
        results = []

        for item in self.data.values():
            if item.get("repo_id") == repo_id:
                content = str(item.get("content", ""))
                if query.lower() in content.lower():
                    results.append(item)

        return results[:limit]
