"""
Get Indexing Status UseCase

인덱싱 상태 조회
"""

from ..domain.models import IndexingMetadata
from ..domain.ports import IndexingMetadataStorePort


class GetIndexingStatusUseCase:
    """인덱싱 상태 조회 UseCase"""

    def __init__(self, metadata_store: IndexingMetadataStorePort):
        """
        초기화

        Args:
            metadata_store: 인덱싱 메타데이터 저장소
        """
        self.metadata_store = metadata_store

    async def execute(
        self,
        repo_id: str,
        snapshot_id: str = "main",
    ) -> IndexingMetadata | None:
        """
        인덱싱 상태 조회

        Args:
            repo_id: 리포지토리 ID
            snapshot_id: 스냅샷 ID

        Returns:
            인덱싱 메타데이터 (없으면 None)
        """
        metadata = await self.metadata_store.get_metadata(repo_id, snapshot_id)
        return metadata
