"""
Chunk Storage Adapter

청크 저장소 어댑터
"""


class ChunkStorageAdapter:
    """청크 저장소 어댑터"""

    def __init__(self, chunk_store):
        """
        초기화

        Args:
            chunk_store: Chunk Store
        """
        self.chunk_store = chunk_store

    async def save_chunks(self, repo_id: str, chunks: list) -> None:
        """
        청크 저장

        Args:
            repo_id: 리포지토리 ID
            chunks: 청크 리스트
        """
        await self.chunk_store.save_chunks(
            repo_id=repo_id,
            chunks=chunks,
        )

    async def delete_chunks(self, repo_id: str, chunk_ids: list[str]) -> None:
        """
        청크 삭제

        Args:
            repo_id: 리포지토리 ID
            chunk_ids: 삭제할 청크 ID 리스트
        """
        await self.chunk_store.delete_chunks(chunk_ids)
