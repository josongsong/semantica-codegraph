"""
Fake Chunk Store for Testing

Minimal stub implementation of ChunkStore interface for unit tests.
"""

from dataclasses import dataclass


@dataclass
class FakeChunk:
    """Fake chunk with minimal required attributes."""

    file_path: str = "test.py"
    start_line: int = 1
    end_line: int = 10
    language: str = "python"
    content_hash: str = "fake_hash"
    content: str = "def test_func():\n    pass"


class FakeChunkStore:
    """
    Fake ChunkStore that returns deterministic chunks.

    Supports async interface to match real ChunkStore.

    Usage:
        store = FakeChunkStore()
        chunk = await store.get_chunk("chunk:1")
    """

    def __init__(
        self,
        content_hash: str | None = None,
        content: str = "def test_func():\n    pass",
    ):
        """
        Initialize FakeChunkStore.

        Args:
            content_hash: Fixed hash for all chunks (None = use chunk_id based hash)
            content: Content to return for chunks
        """
        self._fixed_hash = content_hash
        self._content = content
        self._chunks: dict[str, FakeChunk] = {}

    async def get_chunk(self, chunk_id: str) -> FakeChunk:
        """
        Get a fake chunk by ID.

        Args:
            chunk_id: Chunk identifier

        Returns:
            FakeChunk with test data
        """
        if chunk_id in self._chunks:
            return self._chunks[chunk_id]

        content_hash = self._fixed_hash or f"hash_{chunk_id}"
        return FakeChunk(
            content_hash=content_hash,
            content=self._content,
        )

    def set_chunk(self, chunk_id: str, chunk: FakeChunk) -> None:
        """Set a specific chunk for testing."""
        self._chunks[chunk_id] = chunk
