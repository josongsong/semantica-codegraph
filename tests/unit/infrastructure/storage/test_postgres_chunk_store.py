"""
Integration tests for PostgresChunkStore

These tests require a running PostgreSQL database.
Set POSTGRES_TEST_URL environment variable to run these tests:

    export POSTGRES_TEST_URL="postgresql://user:pass@localhost:5432/test_db"
    pytest tests/foundation/test_postgres_chunk_store.py
"""

import os

import pytest
from src.foundation.chunk import Chunk, PostgresChunkStore

# Skip all tests if POSTGRES_TEST_URL not set
pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_URL"),
    reason="POSTGRES_TEST_URL environment variable not set",
)


@pytest.fixture
async def postgres_store():
    """Create PostgresChunkStore connected to test database"""
    conn_string = os.getenv("POSTGRES_TEST_URL")
    if not conn_string:
        pytest.skip("POSTGRES_TEST_URL not set")

    store = PostgresChunkStore(conn_string)

    # Setup: Ensure chunks table exists (run migration if needed)
    pool = await store._get_pool()
    async with pool.acquire() as conn:
        # Create table if not exists (simplified version for testing)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                project_id TEXT,
                module_path TEXT,
                file_path TEXT,
                parent_id TEXT,
                kind TEXT NOT NULL,
                fqn TEXT NOT NULL,
                language TEXT,
                symbol_visibility TEXT,
                symbol_id TEXT,
                symbol_owner_id TEXT,
                start_line INTEGER,
                end_line INTEGER,
                original_start_line INTEGER,
                original_end_line INTEGER,
                content_hash TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                last_indexed_commit TEXT,
                summary TEXT,
                importance REAL DEFAULT 0.0,
                attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

    yield store

    # Teardown: Clean up test data
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM chunks WHERE repo_id = 'test_repo'")

    await store.close()


@pytest.fixture
def sample_chunk():
    """Create a sample chunk for testing"""
    return Chunk(
        chunk_id="chunk:test_repo:function:main",
        repo_id="test_repo",
        snapshot_id="abc123",
        project_id="chunk:test_repo:project:default",
        module_path="src",
        file_path="src/main.py",
        kind="function",
        fqn="main",
        start_line=10,
        end_line=20,
        original_start_line=10,
        original_end_line=20,
        content_hash="hash123",
        parent_id="chunk:test_repo:file:src.main",
        children=[],
        language="python",
        symbol_visibility="public",
        symbol_id="sym_main",
        symbol_owner_id="sym_main",
        summary="Main function",
        importance=0.8,
        attrs={"test": "value"},
        version=1,
        last_indexed_commit="abc123",
        is_deleted=False,
    )


class TestPostgresChunkStore:
    """Integration tests for PostgresChunkStore"""

    @pytest.mark.asyncio
    async def test_save_and_get_chunk(self, postgres_store, sample_chunk):
        """Test saving and retrieving a chunk"""
        # Save chunk
        await postgres_store.save_chunk(sample_chunk)

        # Retrieve chunk
        retrieved = await postgres_store.get_chunk(sample_chunk.chunk_id)

        assert retrieved is not None
        assert retrieved.chunk_id == sample_chunk.chunk_id
        assert retrieved.repo_id == sample_chunk.repo_id
        assert retrieved.fqn == sample_chunk.fqn
        assert retrieved.kind == sample_chunk.kind
        assert retrieved.start_line == sample_chunk.start_line
        assert retrieved.end_line == sample_chunk.end_line
        assert retrieved.content_hash == sample_chunk.content_hash

    @pytest.mark.asyncio
    async def test_save_chunk_upsert(self, postgres_store, sample_chunk):
        """Test that save_chunk does UPSERT (update on conflict)"""
        # Save initial chunk
        await postgres_store.save_chunk(sample_chunk)

        # Modify and save again
        sample_chunk.summary = "Updated summary"
        sample_chunk.version = 2
        await postgres_store.save_chunk(sample_chunk)

        # Retrieve and verify update
        retrieved = await postgres_store.get_chunk(sample_chunk.chunk_id)
        assert retrieved.summary == "Updated summary"
        assert retrieved.version == 2

    @pytest.mark.asyncio
    async def test_save_chunks_batch(self, postgres_store):
        """Test batch saving multiple chunks"""
        chunks = [
            Chunk(
                chunk_id=f"chunk:test_repo:function:func{i}",
                repo_id="test_repo",
                snapshot_id="abc123",
                project_id=None,
                module_path=None,
                file_path=f"src/file{i}.py",
                kind="function",
                fqn=f"func{i}",
                start_line=i * 10,
                end_line=i * 10 + 5,
                original_start_line=i * 10,
                original_end_line=i * 10 + 5,
                content_hash=f"hash{i}",
                parent_id=None,
                children=[],
                language="python",
                symbol_visibility="public",
                symbol_id=f"sym_{i}",
                symbol_owner_id=f"sym_{i}",
                summary=None,
                importance=None,
                attrs={},
            )
            for i in range(5)
        ]

        # Save all chunks
        await postgres_store.save_chunks(chunks)

        # Verify all saved
        for chunk in chunks:
            retrieved = await postgres_store.get_chunk(chunk.chunk_id)
            assert retrieved is not None
            assert retrieved.chunk_id == chunk.chunk_id

    @pytest.mark.asyncio
    async def test_find_chunks_by_repo(self, postgres_store, sample_chunk):
        """Test finding all chunks by repository"""
        # Save multiple chunks with different snapshots
        chunk1 = sample_chunk
        await postgres_store.save_chunk(chunk1)

        chunk2 = sample_chunk.model_copy()
        chunk2.chunk_id = "chunk:test_repo:function:other"
        chunk2.fqn = "other"
        chunk2.snapshot_id = "def456"
        await postgres_store.save_chunk(chunk2)

        # Find all chunks for repo
        all_chunks = await postgres_store.find_chunks_by_repo("test_repo")
        assert len(all_chunks) >= 2

        # Find chunks for specific snapshot
        snapshot_chunks = await postgres_store.find_chunks_by_repo("test_repo", "abc123")
        assert len(snapshot_chunks) >= 1
        assert all(c.snapshot_id == "abc123" for c in snapshot_chunks)

    @pytest.mark.asyncio
    async def test_get_chunks_by_file(self, postgres_store, sample_chunk):
        """Test getting all chunks for a specific file"""
        # Save chunks for the same file
        await postgres_store.save_chunk(sample_chunk)

        chunk2 = sample_chunk.model_copy()
        chunk2.chunk_id = "chunk:test_repo:function:helper"
        chunk2.fqn = "helper"
        chunk2.start_line = 30
        chunk2.end_line = 40
        await postgres_store.save_chunk(chunk2)

        # Get all chunks for file
        file_chunks = await postgres_store.get_chunks_by_file("test_repo", "src/main.py", "abc123")

        assert len(file_chunks) == 2
        assert all(c.file_path == "src/main.py" for c in file_chunks)

    @pytest.mark.asyncio
    async def test_find_chunk_by_file_and_line(self, postgres_store, sample_chunk):
        """Test Zoekt integration: file+line → chunk mapping"""
        # Save chunks with different line ranges
        file_chunk = sample_chunk.model_copy()
        file_chunk.chunk_id = "chunk:test_repo:file:src.main"
        file_chunk.kind = "file"
        file_chunk.start_line = 1
        file_chunk.end_line = 100
        await postgres_store.save_chunk(file_chunk)

        func_chunk = sample_chunk  # Lines 10-20
        await postgres_store.save_chunk(func_chunk)

        # Query line within function (should return function chunk)
        result = await postgres_store.find_chunk_by_file_and_line("test_repo", "src/main.py", 15)
        assert result is not None
        assert result.kind == "function"
        assert result.chunk_id == func_chunk.chunk_id

        # Query line outside function (should return file chunk)
        result = await postgres_store.find_chunk_by_file_and_line("test_repo", "src/main.py", 50)
        assert result is not None
        assert result.kind == "file"
        assert result.chunk_id == file_chunk.chunk_id

    @pytest.mark.asyncio
    async def test_find_file_chunk(self, postgres_store, sample_chunk):
        """Test finding file-level chunk"""
        # Save file chunk
        file_chunk = sample_chunk.model_copy()
        file_chunk.chunk_id = "chunk:test_repo:file:src.main"
        file_chunk.kind = "file"
        await postgres_store.save_chunk(file_chunk)

        # Find file chunk
        result = await postgres_store.find_file_chunk("test_repo", "src/main.py")
        assert result is not None
        assert result.kind == "file"
        assert result.chunk_id == file_chunk.chunk_id

    @pytest.mark.asyncio
    async def test_delete_chunks_by_repo(self, postgres_store, sample_chunk):
        """Test soft delete of repository chunks"""
        # Save chunk
        await postgres_store.save_chunk(sample_chunk)

        # Verify it exists
        chunk = await postgres_store.get_chunk(sample_chunk.chunk_id)
        assert chunk is not None
        assert not chunk.is_deleted

        # Soft delete
        await postgres_store.delete_chunks_by_repo("test_repo", "abc123")

        # Verify chunk is marked as deleted
        pool = await postgres_store._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT is_deleted, version FROM chunks WHERE chunk_id = $1",
                sample_chunk.chunk_id,
            )
            assert row["is_deleted"] is True
            assert row["version"] == 2  # Version incremented

    @pytest.mark.asyncio
    async def test_chunk_priority_ordering(self, postgres_store):
        """Test that chunk priority ordering works (function > class > file)"""
        # Create overlapping chunks with different kinds
        base_chunk = Chunk(
            chunk_id="temp",
            repo_id="test_repo",
            snapshot_id="abc123",
            project_id=None,
            module_path=None,
            file_path="src/test.py",
            kind="file",
            fqn="test",
            start_line=1,
            end_line=100,
            original_start_line=1,
            original_end_line=100,
            content_hash="hash",
            parent_id=None,
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id="sym",
            symbol_owner_id="sym",
            summary=None,
            importance=None,
            attrs={},
        )

        # File chunk (1-100)
        file_chunk = base_chunk.model_copy()
        file_chunk.chunk_id = "chunk:test_repo:file:test"
        file_chunk.kind = "file"
        await postgres_store.save_chunk(file_chunk)

        # Class chunk (10-50)
        class_chunk = base_chunk.model_copy()
        class_chunk.chunk_id = "chunk:test_repo:class:Test"
        class_chunk.kind = "class"
        class_chunk.start_line = 10
        class_chunk.end_line = 50
        await postgres_store.save_chunk(class_chunk)

        # Function chunk (20-30)
        func_chunk = base_chunk.model_copy()
        func_chunk.chunk_id = "chunk:test_repo:function:test_func"
        func_chunk.kind = "function"
        func_chunk.start_line = 20
        func_chunk.end_line = 30
        await postgres_store.save_chunk(func_chunk)

        # Query line 25 - should return function (highest priority)
        result = await postgres_store.find_chunk_by_file_and_line("test_repo", "src/test.py", 25)
        assert result.kind == "function"

        # Query line 15 - should return class (second priority)
        result = await postgres_store.find_chunk_by_file_and_line("test_repo", "src/test.py", 15)
        assert result.kind == "class"

        # Query line 5 - should return file (lowest priority)
        result = await postgres_store.find_chunk_by_file_and_line("test_repo", "src/test.py", 5)
        assert result.kind == "file"
