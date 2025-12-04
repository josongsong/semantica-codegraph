"""
Fake Indexing Metadata Store

테스트용 인메모리 메타데이터 저장소
"""

from ..domain.models import IndexingMetadata


class FakeIndexingMetadataStore:
    """테스트용 Fake 메타데이터 저장소"""

    def __init__(self):
        """초기화"""
        self.metadata: dict[str, IndexingMetadata] = {}

    async def save_metadata(self, metadata: IndexingMetadata) -> None:
        """메타데이터 저장"""
        key = f"{metadata.repo_id}:{metadata.snapshot_id}"
        self.metadata[key] = metadata

    async def get_metadata(self, repo_id: str, snapshot_id: str) -> IndexingMetadata | None:
        """메타데이터 조회"""
        key = f"{repo_id}:{snapshot_id}"
        return self.metadata.get(key)

    async def list_metadata(self, repo_id: str) -> list[IndexingMetadata]:
        """리포지토리의 모든 메타데이터 조회"""
        return [m for m in self.metadata.values() if m.repo_id == repo_id]

    async def delete_metadata(self, repo_id: str, snapshot_id: str) -> None:
        """메타데이터 삭제"""
        key = f"{repo_id}:{snapshot_id}"
        if key in self.metadata:
            del self.metadata[key]
