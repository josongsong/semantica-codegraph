"""
Analysis Indexing Domain Ports

인덱싱 도메인의 포트 인터페이스 (Protocol)
"""

from typing import Protocol

from .models import FileHash, IndexingMetadata


class IndexingMetadataStorePort(Protocol):
    """인덱싱 메타데이터 저장소 포트"""

    async def save_metadata(self, metadata: IndexingMetadata) -> None:
        """메타데이터 저장 (Upsert)"""
        ...

    async def get_metadata(self, repo_id: str, snapshot_id: str) -> IndexingMetadata | None:
        """메타데이터 조회"""
        ...

    async def list_metadata(self, repo_id: str) -> list[IndexingMetadata]:
        """리포지토리의 모든 메타데이터 조회"""
        ...

    async def delete_metadata(self, repo_id: str, snapshot_id: str) -> None:
        """메타데이터 삭제"""
        ...


class FileHashStorePort(Protocol):
    """파일 해시 저장소 포트"""

    async def save_hash(self, file_hash: FileHash) -> None:
        """파일 해시 저장"""
        ...

    async def get_hash(self, repo_id: str, file_path: str) -> FileHash | None:
        """파일 해시 조회"""
        ...

    async def get_all_hashes(self, repo_id: str) -> dict[str, str]:
        """리포지토리의 모든 파일 해시 조회 (file_path -> hash)"""
        ...

    async def get_changed_files(self, repo_id: str, current_hashes: dict[str, str]) -> list[str]:
        """변경된 파일 목록 조회"""
        ...

    async def delete_all(self, repo_id: str) -> None:
        """리포지토리의 모든 해시 삭제"""
        ...
