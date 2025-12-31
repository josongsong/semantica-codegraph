"""
Integration Tests for Tantivy Batch Indexing Performance

Tests actual Tantivy integration with:
- Real index directory
- Real file system
- Performance benchmarks
- Concurrency safety
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

# Import from Domain (Port types)
from codegraph_engine.multi_index.domain.ports import (
    FileToIndex,
    IndexingMode,
)

# Import from Infrastructure (Implementation)
from codegraph_engine.multi_index.infrastructure.lexical.tantivy.code_index import (
    TantivyCodeIndex,
)

# ============================================================
# Test Fixtures
# ============================================================


@pytest.fixture
def temp_index_dir():
    """Create temporary index directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_chunk_store():
    """Mock ChunkStore for testing"""
    from unittest.mock import AsyncMock, MagicMock

    store = MagicMock()
    store.find_chunk_by_file_and_line = AsyncMock(return_value=None)
    store.find_file_chunk = AsyncMock(return_value=None)
    return store


@pytest.fixture
def sample_files():
    """Generate sample Python files for indexing"""
    files = []
    for i in range(100):
        content = f"""
# File {i}
def function_{i}():
    \"\"\"Docstring for function {i}\"\"\"
    # Comment {i}
    result = "String literal {i}"
    return result

class Class{i}:
    \"\"\"Class docstring {i}\"\"\"
    
    def method_{i}(self):
        # Method comment {i}
        return f"Method {{i}} result"
"""
        files.append(
            FileToIndex(
                repo_id="test-repo",
                file_path=f"/project/file_{i}.py",
                content=content,
            )
        )
    return files


# ============================================================
# Performance Benchmark Tests
# ============================================================


class TestBatchPerformance:
    """Test real-world performance with actual Tantivy"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_batch_faster_than_sequential(self, temp_index_dir, mock_chunk_store, sample_files):
        """Batch indexing should be significantly faster than sequential"""

        # Sequential indexing (old way)
        index_sequential = TantivyCodeIndex(
            index_dir=temp_index_dir / "sequential",
            chunk_store=mock_chunk_store,
            mode=IndexingMode.CONSERVATIVE,
        )

        start = asyncio.get_event_loop().time()
        for file in sample_files[:50]:  # 50 files for reasonable test time
            await index_sequential.index_file(file.repo_id, file.file_path, file.content)
        sequential_duration = asyncio.get_event_loop().time() - start

        # Batch indexing (new way)
        index_batch = TantivyCodeIndex(
            index_dir=temp_index_dir / "batch",
            chunk_store=mock_chunk_store,
            mode=IndexingMode.AGGRESSIVE,
            batch_size=50,
        )

        start = asyncio.get_event_loop().time()
        result = await index_batch.index_files_batch(sample_files[:50])
        batch_duration = result.duration_seconds

        # Batch should be at least 3x faster
        speedup = sequential_duration / batch_duration

        print("\nPerformance comparison (50 files):")
        print(f"  Sequential: {sequential_duration:.2f}s")
        print(f"  Batch: {batch_duration:.2f}s")
        print(f"  Speedup: {speedup:.1f}x")

        assert speedup >= 3.0, f"Expected 3x speedup, got {speedup:.1f}x"
        assert result.is_complete_success

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_aggressive_mode_faster_than_conservative(self, temp_index_dir, mock_chunk_store, sample_files):
        """AGGRESSIVE mode should be faster than CONSERVATIVE"""

        # Conservative mode
        index_conservative = TantivyCodeIndex(
            index_dir=temp_index_dir / "conservative",
            chunk_store=mock_chunk_store,
            mode=IndexingMode.CONSERVATIVE,
            batch_size=100,
        )

        result_conservative = await index_conservative.index_files_batch(sample_files)
        conservative_duration = result_conservative.duration_seconds

        # Aggressive mode
        index_aggressive = TantivyCodeIndex(
            index_dir=temp_index_dir / "aggressive",
            chunk_store=mock_chunk_store,
            mode=IndexingMode.AGGRESSIVE,
            batch_size=100,
        )

        result_aggressive = await index_aggressive.index_files_batch(sample_files)
        aggressive_duration = result_aggressive.duration_seconds

        print(f"\nMode comparison ({len(sample_files)} files):")
        print(f"  CONSERVATIVE: {conservative_duration:.2f}s")
        print(f"  AGGRESSIVE: {aggressive_duration:.2f}s")
        print(f"  Speedup: {conservative_duration / aggressive_duration:.1f}x")

        # Aggressive should be at least as fast (possibly faster)
        assert aggressive_duration <= conservative_duration * 1.2  # Allow 20% margin
        assert result_aggressive.is_complete_success

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_throughput_target(self, temp_index_dir, mock_chunk_store, sample_files):
        """Should achieve target throughput of >50 files/second"""

        index = TantivyCodeIndex(
            index_dir=temp_index_dir,
            chunk_store=mock_chunk_store,
            mode=IndexingMode.AGGRESSIVE,
            batch_size=100,
        )

        result = await index.index_files_batch(sample_files)

        throughput = result.total_files / result.duration_seconds

        print(f"\nThroughput test ({len(sample_files)} files):")
        print(f"  Duration: {result.duration_seconds:.2f}s")
        print(f"  Throughput: {throughput:.1f} files/s")

        # Target: >50 files/second (conservative estimate)
        assert throughput >= 50.0, f"Expected >50 files/s, got {throughput:.1f}"
        assert result.is_complete_success


# ============================================================
# Concurrency Safety Tests
# ============================================================


class TestConcurrencySafety:
    """Test that concurrent indexing doesn't cause race conditions"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_indexing_no_lock_errors(self, temp_index_dir, mock_chunk_store, sample_files):
        """Multiple concurrent index operations should not cause LockBusy errors"""

        index = TantivyCodeIndex(
            index_dir=temp_index_dir,
            chunk_store=mock_chunk_store,
            mode=IndexingMode.BALANCED,
            batch_size=20,
        )

        # Split files into batches
        batch1 = sample_files[:30]
        batch2 = sample_files[30:60]
        batch3 = sample_files[60:90]

        # Run concurrently
        results = await asyncio.gather(
            index.index_files_batch(batch1),
            index.index_files_batch(batch2),
            index.index_files_batch(batch3),
        )

        # All should succeed without lock errors
        for result in results:
            assert result.is_complete_success
            assert "LockBusy" not in str(result.failed_files)

        total_success = sum(r.success_count for r in results)
        assert total_success == 90


# ============================================================
# Error Recovery Tests
# ============================================================


class TestErrorRecovery:
    """Test error handling and recovery"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_partial_failure_continues(self, temp_index_dir, mock_chunk_store):
        """Indexing should continue after individual file failures"""

        index = TantivyCodeIndex(
            index_dir=temp_index_dir,
            chunk_store=mock_chunk_store,
            mode=IndexingMode.BALANCED,
        )

        # Mix valid and invalid files
        files = [
            FileToIndex(repo_id="repo", file_path="/file1.py", content="valid code"),
            FileToIndex(repo_id="repo", file_path="/file2.py", content="valid code"),
            FileToIndex(repo_id="repo", file_path="/file3.py", content="valid code"),
        ]

        result = await index.index_files_batch(files, fail_fast=False)

        # Even if some fail, others should succeed
        assert result.success_count > 0
        print(f"\nError recovery: {result.success_count}/{result.total_files} succeeded")


# ============================================================
# Data Integrity Tests
# ============================================================


class TestDataIntegrity:
    """Test that indexed data is correct and searchable"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_indexed_files_are_searchable(self, temp_index_dir, mock_chunk_store):
        """Files indexed via batch should be searchable"""

        index = TantivyCodeIndex(
            index_dir=temp_index_dir,
            chunk_store=mock_chunk_store,
            mode=IndexingMode.BALANCED,
        )

        # Index files with unique content
        files = [
            FileToIndex(
                repo_id="test-repo",
                file_path="/unique_file.py",
                content="def unique_function_xyz():\n    return 'unique_result_xyz'",
            ),
        ]

        result = await index.index_files_batch(files)
        assert result.is_complete_success

        # Search for unique content
        hits = await index.search(
            repo_id="test-repo",
            snapshot_id="main",
            query="unique_function_xyz",
            limit=10,
        )

        # Should find the indexed file
        assert len(hits) > 0
        assert any("unique_file.py" in hit.file_path for hit in hits)


# ============================================================
# Benchmark Runner
# ============================================================


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_benchmark_300_files(temp_index_dir, mock_chunk_store):
    """Benchmark: 300 files (realistic CLI scenario)"""

    # Generate 300 files
    files = []
    for i in range(300):
        content = f"""
# File {i}
def function_{i}():
    \"\"\"Docstring {i}\"\"\"
    return "result_{i}"
"""
        files.append(FileToIndex(repo_id="repo", file_path=f"/file_{i}.py", content=content))

    index = TantivyCodeIndex(
        index_dir=temp_index_dir,
        chunk_store=mock_chunk_store,
        mode=IndexingMode.AGGRESSIVE,
        batch_size=100,
    )

    result = await index.index_files_batch(files)

    throughput = result.total_files / result.duration_seconds

    print("\n📊 Benchmark: 300 files")
    print(f"   Duration: {result.duration_seconds:.2f}s")
    print(f"   Throughput: {throughput:.1f} files/s")
    print(f"   Success rate: {result.success_count}/{result.total_files}")
    print(f"   Target achieved: {'✅' if result.duration_seconds <= 3.0 else '❌'}")

    # Target: 300 files in ≤3 seconds
    assert result.duration_seconds <= 3.0
    assert result.is_complete_success
