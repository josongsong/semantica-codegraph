"""
Chunk Store Adapter

In-memory chunk storage for ChunkStorePort.

WARNING: This is a placeholder. Use PostgreSQL/SQLite in production.
"""

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.models import Chunk
from codegraph_engine.code_foundation.domain.ports import ChunkStorePort

logger = get_logger(__name__)


class InMemoryChunkStoreAdapter:
    """
    ChunkStorePort adapter using in-memory storage.

    WARNING: This is a placeholder for testing.
    Production should use PostgreSQL/SQLite adapter.
    """

    def __init__(self):
        """Initialize in-memory store."""
        self._chunks: dict[str, Chunk] = {}
        logger.warning("Using InMemoryChunkStoreAdapter - NOT for production")

    async def save_chunks(self, chunks: list[Chunk], repo_id: str) -> None:
        """
        Save chunks.

        Args:
            chunks: Chunks to save
            repo_id: Repository ID
        """
        for chunk in chunks:
            self._chunks[chunk.id] = chunk
        logger.info("Saved chunks", count=len(chunks), repo_id=repo_id)

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        """
        Get chunk by ID.

        Args:
            chunk_id: Chunk ID

        Returns:
            Chunk or None
        """
        return self._chunks.get(chunk_id)

    async def get_chunks_by_file(self, file_path: str, repo_id: str) -> list[Chunk]:
        """
        Get all chunks for a file.

        Args:
            file_path: File path
            repo_id: Repository ID

        Returns:
            List of chunks
        """
        return [c for c in self._chunks.values() if c.file_path == file_path]

    async def delete_chunks(self, chunk_ids: list[str]) -> None:
        """
        Delete chunks.

        Args:
            chunk_ids: Chunk IDs to delete
        """
        for chunk_id in chunk_ids:
            self._chunks.pop(chunk_id, None)
        logger.info("Deleted chunks", count=len(chunk_ids))


def create_chunk_store_adapter() -> ChunkStorePort:
    """
    Create ChunkStorePort adapter.

    WARNING: Returns in-memory adapter by default.
    Override with production adapter in deployment.
    """
    # TODO: Replace with PostgreSQL/SQLite adapter in production
    return InMemoryChunkStoreAdapter()
