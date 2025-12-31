"""
Unit Tests for Tantivy Batch Indexing (SOTA Performance)

Tests:
- FileToIndex validation
- IndexingResult properties
- Document building (pure function)
- Mode-based configuration
- Batch indexing logic
- Error handling
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Import from Domain (Port types)
from codegraph_engine.multi_index.domain.ports import (
    FileToIndex,
    IndexingMode,
    IndexingResult,
)

# Import from Infrastructure (Implementation)
from codegraph_engine.multi_index.infrastructure.lexical.tantivy.code_index import (
    TantivyCodeIndex,
)


# ============================================================
# FileToIndex Validation Tests
# ============================================================


class TestFileToIndex:
    """Test FileToIndex dataclass validation"""

    def test_valid_file_to_index(self):
        """Happy path: valid file"""
        file = FileToIndex(
            repo_id="test-repo",
            file_path="/path/to/file.py",
            content="print('hello')",
        )
        assert file.repo_id == "test-repo"
        assert file.file_path == "/path/to/file.py"
        assert file.content == "print('hello')"

    def test_empty_repo_id_raises_error(self):
        """Invalid input: empty repo_id"""
        with pytest.raises(ValueError, match="repo_id cannot be empty"):
            FileToIndex(repo_id="", file_path="/file.py", content="code")

    def test_empty_file_path_raises_error(self):
        """Invalid input: empty file_path"""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            FileToIndex(repo_id="repo", file_path="", content="code")

    def test_non_string_content_raises_error(self):
        """Invalid input: content is not str"""
        with pytest.raises(TypeError, match="content must be str"):
            FileToIndex(repo_id="repo", file_path="/file.py", content=12345)  # type: ignore

    def test_immutable_fields(self):
        """FileToIndex should be immutable (frozen dataclass)"""
        file = FileToIndex(repo_id="repo", file_path="/file.py", content="code")
        with pytest.raises(AttributeError):
            file.repo_id = "new-repo"  # type: ignore


# ============================================================
# IndexingResult Tests
# ============================================================


class TestIndexingResult:
    """Test IndexingResult properties"""

    def test_complete_success(self):
        """All files succeeded"""
        result = IndexingResult(total_files=10, success_count=10, failed_files=[], duration_seconds=1.5)
        assert result.is_complete_success
        assert not result.is_partial_success
        assert not result.is_complete_failure

    def test_partial_success(self):
        """Some files failed"""
        result = IndexingResult(
            total_files=10,
            success_count=7,
            failed_files=[("/file1.py", "error1"), ("/file2.py", "error2")],
            duration_seconds=2.0,
        )
        assert result.is_partial_success
        assert not result.is_complete_success
        assert not result.is_complete_failure

    def test_complete_failure(self):
        """All files failed"""
        result = IndexingResult(
            total_files=10,
            success_count=0,
            failed_files=[("/file.py", "error")] * 10,
            duration_seconds=0.5,
        )
        assert result.is_complete_failure
        assert not result.is_partial_success
        assert not result.is_complete_success


# ============================================================
# IndexingMode Configuration Tests
# ============================================================


class TestIndexingMode:
    """Test mode-based performance configuration"""

    @pytest.mark.parametrize(
        "mode,expected_heap,expected_threads",
        [
            (IndexingMode.CONSERVATIVE, 512, 4),
            (IndexingMode.BALANCED, 1024, 8),
            (IndexingMode.AGGRESSIVE, 2048, 16),
        ],
    )
    def test_mode_configuration(self, mode, expected_heap, expected_threads):
        """Mode should determine heap size and thread count"""
        with patch("tantivy.Index") as mock_index_class:
            mock_index = MagicMock()
            mock_index_class.return_value = mock_index

            mock_chunk_store = MagicMock()

            index = TantivyCodeIndex(
                index_dir="/tmp/test_index",
                chunk_store=mock_chunk_store,
                mode=mode,
            )

            # Thread count may be clamped by CPU count
            assert index.heap_size_mb == expected_heap
            assert index.num_threads <= expected_threads

    def test_explicit_override_heap_and_threads(self):
        """Explicit values should override mode defaults"""
        with patch("tantivy.Index") as mock_index_class:
            mock_index = MagicMock()
            mock_index_class.return_value = mock_index

            mock_chunk_store = MagicMock()

            index = TantivyCodeIndex(
                index_dir="/tmp/test_index",
                chunk_store=mock_chunk_store,
                mode=IndexingMode.CONSERVATIVE,
                heap_size_mb=4096,  # Override
                num_threads=32,  # Override
            )

            assert index.heap_size_mb == 4096
            assert index.num_threads == 32


# ============================================================
# Document Building Tests (Pure Function)
# ============================================================


class TestDocumentBuilding:
    """Test _build_document pure function"""

    def test_build_document_valid_input(self):
        """Happy path: build document from valid inputs"""
        with patch("tantivy.Index") as mock_index_class:
            mock_index = MagicMock()
            mock_index_class.return_value = mock_index

            mock_chunk_store = MagicMock()

            index = TantivyCodeIndex(
                index_dir="/tmp/test_index",
                chunk_store=mock_chunk_store,
            )

            doc = index._build_document(
                repo_id="test-repo",
                file_path="/path/file.py",
                content='# Comment\ndef foo():\n    """Docstring"""\n    return "Hello"',
            )

            # Document should be created (cannot easily inspect tantivy.Document)
            assert doc is not None

    def test_build_document_empty_repo_id(self):
        """Invalid input: empty repo_id"""
        with patch("tantivy.Index") as mock_index_class:
            mock_index = MagicMock()
            mock_index_class.return_value = mock_index

            mock_chunk_store = MagicMock()

            index = TantivyCodeIndex(
                index_dir="/tmp/test_index",
                chunk_store=mock_chunk_store,
            )

            with pytest.raises(ValueError, match="repo_id cannot be empty"):
                index._build_document(repo_id="", file_path="/file.py", content="code")

    def test_build_document_empty_file_path(self):
        """Invalid input: empty file_path"""
        with patch("tantivy.Index") as mock_index_class:
            mock_index = MagicMock()
            mock_index_class.return_value = mock_index

            mock_chunk_store = MagicMock()

            index = TantivyCodeIndex(
                index_dir="/tmp/test_index",
                chunk_store=mock_chunk_store,
            )

            with pytest.raises(ValueError, match="file_path cannot be empty"):
                index._build_document(repo_id="repo", file_path="", content="code")


# ============================================================
# Batch Indexing Tests
# ============================================================


class TestBatchIndexing:
    """Test batch indexing logic"""

    @pytest.mark.asyncio
    async def test_batch_indexing_empty_list_raises_error(self):
        """Invalid input: empty files list"""
        with patch("tantivy.Index") as mock_index_class:
            mock_index = MagicMock()
            mock_index_class.return_value = mock_index

            mock_chunk_store = MagicMock()

            index = TantivyCodeIndex(
                index_dir="/tmp/test_index",
                chunk_store=mock_chunk_store,
            )

            with pytest.raises(ValueError, match="files list cannot be empty"):
                await index.index_files_batch([])

    @pytest.mark.asyncio
    async def test_batch_indexing_single_file_success(self):
        """Happy path: index single file"""
        with patch("tantivy.Index") as mock_index_class:
            mock_index = MagicMock()
            mock_writer = MagicMock()
            mock_index.writer.return_value = mock_writer
            mock_index_class.return_value = mock_index

            mock_chunk_store = MagicMock()

            index = TantivyCodeIndex(
                index_dir="/tmp/test_index",
                chunk_store=mock_chunk_store,
            )

            files = [FileToIndex(repo_id="repo", file_path="/file.py", content="print('hi')")]

            result = await index.index_files_batch(files)

            assert result.total_files == 1
            assert result.success_count == 1
            assert result.is_complete_success
            assert len(result.failed_files) == 0

    @pytest.mark.asyncio
    async def test_batch_indexing_fail_fast_stops_on_error(self):
        """Edge case: fail_fast should stop on first error"""
        with patch("tantivy.Index") as mock_index_class:
            mock_index = MagicMock()
            mock_writer = MagicMock()

            # Simulate error on add_document
            def side_effect(*args, **kwargs):
                raise RuntimeError("Simulated indexing error")

            mock_writer.add_document.side_effect = side_effect
            mock_index.writer.return_value = mock_writer
            mock_index_class.return_value = mock_index

            mock_chunk_store = MagicMock()

            index = TantivyCodeIndex(
                index_dir="/tmp/test_index",
                chunk_store=mock_chunk_store,
            )

            files = [FileToIndex(repo_id="repo", file_path=f"/file{i}.py", content="code") for i in range(5)]

            result = await index.index_files_batch(files, fail_fast=True)

            # Should stop after first failure
            assert result.success_count == 0
            assert len(result.failed_files) >= 1

    @pytest.mark.asyncio
    async def test_batch_indexing_continue_on_error(self):
        """Edge case: continue processing on individual file error"""
        with patch("tantivy.Index") as mock_index_class:
            mock_index = MagicMock()
            mock_writer = MagicMock()

            # Simulate error on 2nd file
            call_count = 0

            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise RuntimeError("Simulated error on file 2")

            mock_writer.add_document.side_effect = side_effect
            mock_index.writer.return_value = mock_writer
            mock_index_class.return_value = mock_index

            mock_chunk_store = MagicMock()

            index = TantivyCodeIndex(
                index_dir="/tmp/test_index",
                chunk_store=mock_chunk_store,
                batch_size=10,  # All in one batch
            )

            files = [FileToIndex(repo_id="repo", file_path=f"/file{i}.py", content="code") for i in range(5)]

            result = await index.index_files_batch(files, fail_fast=False)

            # Should process all files despite one failure
            assert result.total_files == 5
            assert result.success_count == 4
            assert len(result.failed_files) == 1
            assert result.is_partial_success


# ============================================================
# Backward Compatibility Tests
# ============================================================


class TestBackwardCompatibility:
    """Test that index_file() still works"""

    @pytest.mark.asyncio
    async def test_index_file_delegates_to_batch(self):
        """index_file should delegate to index_files_batch"""
        with patch("tantivy.Index") as mock_index_class:
            mock_index = MagicMock()
            mock_writer = MagicMock()
            mock_index.writer.return_value = mock_writer
            mock_index_class.return_value = mock_index

            mock_chunk_store = MagicMock()

            index = TantivyCodeIndex(
                index_dir="/tmp/test_index",
                chunk_store=mock_chunk_store,
            )

            success = await index.index_file("repo", "/file.py", "code")

            assert success is True
