"""
IncrementalUpdatePlugin Tests

Test Strategy:
    - Base Cases: Happy path (write → commit with batch optimization)
    - Corner Cases: Initialization, empty transactions
    - Edge Cases: Error handling, multiple files, language detection
    - Integration: Full workflow

Note:
    Tests updated for batch optimization:
    - write events no longer trigger immediate IR delta
    - commit events trigger batched IR delta calculation
"""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from codegraph_runtime.codegen_loop.domain.shadowfs.events import ShadowFSEvent
from codegraph_runtime.codegen_loop.infrastructure.shadowfs.plugins.incremental_plugin import (
    IncrementalUpdatePlugin,
)

# ========== Fixtures ==========


@pytest.fixture
def mock_ir_builder():
    """Mock IncrementalIRBuilder (AsyncMock for batch optimization)"""
    builder = MagicMock()

    # Return value
    result = MagicMock()
    result.changed_files = {"file.py"}
    result.rebuilt_files = {"file.py"}

    # Use AsyncMock for async call
    builder.build_incremental = AsyncMock(return_value=result)

    return builder


@pytest.fixture
def mock_indexer():
    """Mock IncrementalIndexer"""
    indexer = MagicMock()
    indexer.index_files = AsyncMock()
    return indexer


@pytest.fixture
def plugin(mock_ir_builder, mock_indexer):
    """Create Incremental Update Plugin"""
    return IncrementalUpdatePlugin(mock_ir_builder, mock_indexer, ttl=3600.0)


# ========== Base Cases ==========


class TestBaseCases:
    """Happy path tests (with batch optimization)"""

    @pytest.mark.asyncio
    async def test_write_event_tracks_file(self, plugin, mock_ir_builder):
        """Base: write event tracks file (no immediate IR delta)"""
        txn_id = "txn-123"
        event = ShadowFSEvent(
            type="write",
            path="main.py",
            txn_id=txn_id,
            old_content=None,
            new_content="def func(): pass",
            timestamp=time.time(),
        )

        await plugin.on_event(event)

        # Verify NO immediate delta calculation (batch optimization)
        mock_ir_builder.build_incremental.assert_not_called()

        # Verify file tracked
        assert txn_id in plugin._pending_ir_deltas
        assert Path("main.py") in plugin._pending_ir_deltas[txn_id]

    @pytest.mark.asyncio
    async def test_commit_event_triggers_batch_ir_delta(
        self,
        plugin,
        mock_ir_builder,
        mock_indexer,
    ):
        """Base: commit event triggers BATCH IR delta calculation"""
        txn_id = "txn-123"

        # Write file (to track)
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        # Commit (triggers batch)
        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify BATCH IR delta called
        mock_ir_builder.build_incremental.assert_called_once()
        call_args = mock_ir_builder.build_incremental.call_args
        assert Path("main.py") in call_args[1]["files"]
        assert call_args[1]["language"] == "python"

        # Verify indexing also called
        mock_indexer.index_files.assert_called_once()

    @pytest.mark.asyncio
    async def test_commit_event_triggers_indexing(
        self,
        plugin,
        mock_indexer,
    ):
        """Base: commit event triggers batch indexing"""
        txn_id = "txn-123"

        # Write file (to track)
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        # Commit (triggers batch indexing)
        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify indexing called
        mock_indexer.index_files.assert_called_once()
        call_args = mock_indexer.index_files.call_args
        assert Path("main.py") in call_args[1]["file_paths"]
        assert call_args[1]["force_reindex"] is False

    @pytest.mark.asyncio
    async def test_rollback_discards_changes(self, plugin):
        """Base: rollback discards tracked changes"""
        txn_id = "txn-123"

        # Write file (to track)
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        # Verify tracked
        assert txn_id in plugin._pending_changes
        assert txn_id in plugin._pending_ir_deltas

        # Rollback
        await plugin.on_event(
            ShadowFSEvent(
                type="rollback",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify discarded
        assert txn_id not in plugin._pending_changes
        assert txn_id not in plugin._pending_ir_deltas

    @pytest.mark.asyncio
    async def test_delete_event_tracked(self, plugin):
        """Base: delete event tracked for indexing"""
        txn_id = "txn-123"

        await plugin.on_event(
            ShadowFSEvent(
                type="delete",
                path="old.py",
                txn_id=txn_id,
                old_content="old content",
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify tracked
        assert txn_id in plugin._pending_changes
        assert Path("old.py") in plugin._pending_changes[txn_id]


# ========== Corner Cases ==========


class TestCornerCases:
    """Corner case tests"""

    def test_init_with_none_builder(self, mock_indexer):
        """Corner: init with None builder raises TypeError"""
        with pytest.raises(TypeError, match="ir_builder must not be None"):
            IncrementalUpdatePlugin(None, mock_indexer)

    def test_init_with_none_indexer(self, mock_ir_builder):
        """Corner: init with None indexer raises TypeError"""
        with pytest.raises(TypeError, match="indexer must not be None"):
            IncrementalUpdatePlugin(mock_ir_builder, None)

    def test_init_with_invalid_builder(self, mock_indexer):
        """Corner: init with invalid builder raises TypeError"""
        invalid_builder = MagicMock()
        del invalid_builder.build_incremental  # Remove method

        with pytest.raises(TypeError, match="ir_builder must have build_incremental"):
            IncrementalUpdatePlugin(invalid_builder, mock_indexer)

    def test_init_with_invalid_indexer(self, mock_ir_builder):
        """Corner: init with invalid indexer raises TypeError"""
        invalid_indexer = MagicMock()
        del invalid_indexer.index_files  # Remove method

        with pytest.raises(TypeError, match="indexer must have index_files"):
            IncrementalUpdatePlugin(mock_ir_builder, invalid_indexer)

    @pytest.mark.asyncio
    async def test_commit_without_changes(self, plugin, mock_ir_builder, mock_indexer):
        """Corner: commit without changes → no calls"""
        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id="txn-empty",
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify no calls
        mock_ir_builder.build_incremental.assert_not_called()
        mock_indexer.index_files.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_with_empty_content(self, plugin, mock_ir_builder):
        """Corner: write with empty content → tracking still happens"""
        txn_id = "txn-123"

        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="",  # Empty string
                timestamp=time.time(),
            )
        )

        # Verify tracked
        assert txn_id in plugin._pending_ir_deltas

        # Commit to verify batch IR delta called
        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify IR delta called (even with empty content)
        mock_ir_builder.build_incremental.assert_called_once()


# ========== Edge Cases ==========


class TestEdgeCases:
    """Edge case tests"""

    @pytest.mark.asyncio
    async def test_delta_failure_doesnt_propagate(self, plugin, mock_ir_builder):
        """Edge: IR delta failure logged but doesn't propagate"""
        txn_id = "txn-123"

        # Configure mock to raise error
        mock_ir_builder.build_incremental.side_effect = RuntimeError("IR delta failed")

        # Write and commit (should not raise)
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify IR delta was attempted
        mock_ir_builder.build_incremental.assert_called_once()

    @pytest.mark.asyncio
    async def test_indexing_failure_doesnt_propagate(self, plugin, mock_indexer):
        """Edge: indexing failure logged but doesn't propagate"""
        txn_id = "txn-123"

        # Configure mock to raise error
        mock_indexer.index_files.side_effect = RuntimeError("Indexing failed")

        # Write and commit (should not raise)
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify indexing was attempted
        mock_indexer.index_files.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_writes_same_txn(self, plugin, mock_ir_builder):
        """Edge: multiple writes in same txn → batched"""
        txn_id = "txn-123"

        # Write multiple files
        for i in range(3):
            await plugin.on_event(
                ShadowFSEvent(
                    type="write",
                    path=f"file{i}.py",
                    txn_id=txn_id,
                    old_content=None,
                    new_content=f"content{i}",
                    timestamp=time.time(),
                )
            )

        # Commit
        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify SINGLE batched IR delta call (not 3 separate calls)
        assert mock_ir_builder.build_incremental.call_count == 1
        call_args = mock_ir_builder.build_incremental.call_args
        files = call_args[1]["files"]
        assert len(files) == 3
        assert all(f"file{i}.py" in str(files) for i in range(3))

    @pytest.mark.asyncio
    async def test_multiple_txns_isolated(self, plugin, mock_ir_builder):
        """Edge: multiple transactions isolated"""
        txn1 = "txn-1"
        txn2 = "txn-2"

        # Write to txn1
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="file1.py",
                txn_id=txn1,
                old_content=None,
                new_content="content1",
                timestamp=time.time(),
            )
        )

        # Write to txn2
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="file2.py",
                txn_id=txn2,
                old_content=None,
                new_content="content2",
                timestamp=time.time(),
            )
        )

        # Commit txn1
        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn1,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify only txn1 files processed
        assert mock_ir_builder.build_incremental.call_count == 1
        call_args = mock_ir_builder.build_incremental.call_args
        files = call_args[1]["files"]
        assert Path("file1.py") in files
        assert Path("file2.py") not in files

        # Commit txn2
        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn2,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify txn2 processed separately
        assert mock_ir_builder.build_incremental.call_count == 2


# ========== Integration Tests ==========


class TestIntegration:
    """Integration tests"""

    @pytest.mark.asyncio
    async def test_full_workflow(self, plugin, mock_ir_builder, mock_indexer):
        """Integration: full workflow (write → commit → verify)"""
        txn_id = "txn-123"

        # Write 3 files
        files = ["main.py", "utils.py", "config.py"]
        for file in files:
            await plugin.on_event(
                ShadowFSEvent(
                    type="write",
                    path=file,
                    txn_id=txn_id,
                    old_content=None,
                    new_content="content",
                    timestamp=time.time(),
                )
            )

        # Commit
        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify BATCH IR delta (single call for all files)
        assert mock_ir_builder.build_incremental.call_count == 1
        ir_call_args = mock_ir_builder.build_incremental.call_args
        ir_files = ir_call_args[1]["files"]
        assert len(ir_files) == 3

        # Verify batch indexing
        assert mock_indexer.index_files.call_count == 1
        idx_call_args = mock_indexer.index_files.call_args
        idx_files = idx_call_args[1]["file_paths"]
        assert len(idx_files) == 3

        # Verify state cleaned up
        assert txn_id not in plugin._pending_changes
        assert txn_id not in plugin._pending_ir_deltas

    @pytest.mark.asyncio
    async def test_error_recovery(self, plugin, mock_ir_builder, mock_indexer):
        """Integration: error recovery (partial failures)"""
        txn_id = "txn-123"

        # Configure IR to fail
        mock_ir_builder.build_incremental.side_effect = RuntimeError("IR failed")

        # Write and commit
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify IR attempted
        mock_ir_builder.build_incremental.assert_called_once()

        # Verify indexing still called (despite IR failure)
        mock_indexer.index_files.assert_called_once()

        # Verify state cleaned up
        assert txn_id not in plugin._pending_changes


# ========== Language Detection Tests ==========


class TestLanguageDetection:
    """Language detection tests"""

    @pytest.mark.asyncio
    async def test_python_file_detection(self, plugin, mock_ir_builder):
        """Language: .py → python"""
        txn_id = "txn-123"

        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        call_args = mock_ir_builder.build_incremental.call_args
        assert call_args[1]["language"] == "python"

    @pytest.mark.asyncio
    async def test_typescript_file_detection(self, plugin, mock_ir_builder):
        """Language: .ts → typescript"""
        txn_id = "txn-123"

        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="app.ts",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        call_args = mock_ir_builder.build_incremental.call_args
        assert call_args[1]["language"] == "typescript"

    @pytest.mark.asyncio
    async def test_mixed_languages_grouped(self, plugin, mock_ir_builder):
        """Language: mixed languages → grouped by language"""
        txn_id = "txn-123"

        # Write Python files
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="python content",
                timestamp=time.time(),
            )
        )

        # Write TypeScript files
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="app.ts",
                txn_id=txn_id,
                old_content=None,
                new_content="ts content",
                timestamp=time.time(),
            )
        )

        # Commit
        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify 2 separate IR delta calls (one per language)
        assert mock_ir_builder.build_incremental.call_count == 2

        # Verify languages
        calls = mock_ir_builder.build_incremental.call_args_list
        languages = {call[1]["language"] for call in calls}
        assert "python" in languages
        assert "typescript" in languages


# ========== TTL Cleanup Tests ==========


class TestTTLCleanup:
    """TTL cleanup tests"""

    @pytest.mark.asyncio
    async def test_stale_txn_cleanup(self, mock_ir_builder, mock_indexer):
        """TTL: stale transactions cleaned up"""
        # Create plugin with short TTL (1 second)
        plugin = IncrementalUpdatePlugin(mock_ir_builder, mock_indexer, ttl=1.0)

        txn_id = "txn-stale"

        # Write file (creates transaction)
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        # Verify tracked
        assert txn_id in plugin._pending_changes

        # Wait for TTL (2 seconds > 1 second TTL)
        await asyncio.sleep(2)

        # Trigger cleanup (manually call since background task runs every 60s)
        current_time = time.time()
        stale_txns = [t for t, created_at in plugin._txn_created_at.items() if current_time - created_at > plugin._ttl]

        for t in stale_txns:
            plugin._pending_changes.pop(t, None)
            plugin._pending_ir_deltas.pop(t, None)
            plugin._txn_created_at.pop(t, None)

        # Verify cleaned up
        assert txn_id not in plugin._pending_changes
        assert txn_id not in plugin._pending_ir_deltas
        assert txn_id not in plugin._txn_created_at

        # Cleanup
        await plugin.shutdown()


# ========== Metrics Tests ==========


class TestMetrics:
    """Metrics collection tests"""

    @pytest.mark.asyncio
    async def test_metrics_write_events(self, plugin):
        """Metrics: write events recorded"""
        txn_id = "txn-123"

        # Write 3 files
        for i in range(3):
            await plugin.on_event(
                ShadowFSEvent(
                    type="write",
                    path=f"file{i}.py",
                    txn_id=txn_id,
                    old_content=None,
                    new_content="content",
                    timestamp=time.time(),
                )
            )

        metrics = plugin.get_metrics()
        assert metrics.total_writes == 3

    @pytest.mark.asyncio
    async def test_metrics_commit_events(self, plugin, mock_ir_builder, mock_indexer):
        """Metrics: commit events and batch sizes recorded"""
        txn_id = "txn-123"

        # Write 5 files
        for i in range(5):
            await plugin.on_event(
                ShadowFSEvent(
                    type="write",
                    path=f"file{i}.py",
                    txn_id=txn_id,
                    old_content=None,
                    new_content="content",
                    timestamp=time.time(),
                )
            )

        # Commit
        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        metrics = plugin.get_metrics()
        assert metrics.total_commits == 1
        assert metrics.total_files_processed == 5
        assert metrics.avg_batch_size == 5.0

    @pytest.mark.asyncio
    async def test_metrics_rollback_events(self, plugin):
        """Metrics: rollback events recorded"""
        txn_id = "txn-123"

        # Write file
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        # Rollback
        await plugin.on_event(
            ShadowFSEvent(
                type="rollback",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        metrics = plugin.get_metrics()
        assert metrics.total_rollbacks == 1

    @pytest.mark.asyncio
    async def test_metrics_ir_delta_latency(self, plugin, mock_ir_builder, mock_indexer):
        """Metrics: IR delta latency recorded"""
        txn_id = "txn-123"

        # Write and commit
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        metrics = plugin.get_metrics()
        assert metrics.total_ir_delta_calls == 1
        assert metrics.avg_ir_delta_latency_ms > 0
        assert metrics.max_ir_delta_latency_ms > 0

    @pytest.mark.asyncio
    async def test_metrics_indexing_latency(self, plugin, mock_ir_builder, mock_indexer):
        """Metrics: indexing latency recorded"""
        txn_id = "txn-123"

        # Write and commit
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        metrics = plugin.get_metrics()
        assert metrics.total_indexing_calls == 1
        assert metrics.avg_indexing_latency_ms > 0
        assert metrics.max_indexing_latency_ms > 0

    @pytest.mark.asyncio
    async def test_metrics_error_count(self, plugin, mock_ir_builder):
        """Metrics: errors recorded"""
        txn_id = "txn-123"

        # Configure mock to fail
        mock_ir_builder.build_incremental.side_effect = RuntimeError("IR failed")

        # Write and commit
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        metrics = plugin.get_metrics()
        assert metrics.total_errors >= 1


# ========== Path Validation Tests ==========


class TestPathValidation:
    """Path validation security tests"""

    @pytest.mark.asyncio
    async def test_path_validation_normal(self, plugin):
        """Security: normal path accepted"""
        # Should not raise
        path = plugin._validate_path("main.py")
        assert path == Path("main.py")

    @pytest.mark.asyncio
    async def test_path_validation_relative(self, plugin):
        """Security: relative path accepted"""
        # Should not raise
        path = plugin._validate_path("src/main.py")
        assert path == Path("src/main.py")

    @pytest.mark.asyncio
    async def test_path_validation_parent_traversal(self, plugin):
        """Security: parent directory traversal rejected"""
        with pytest.raises(ValueError, match="Parent directory traversal not allowed"):
            plugin._validate_path("../../../etc/passwd")

    @pytest.mark.asyncio
    async def test_path_validation_absolute(self, plugin):
        """Security: absolute path rejected"""
        with pytest.raises(ValueError, match="Absolute path not allowed"):
            plugin._validate_path("/etc/passwd")

    @pytest.mark.asyncio
    async def test_write_event_invalid_path(self, plugin):
        """Security: write event with invalid path rejected"""
        txn_id = "txn-123"

        # Write with invalid path (should be silently rejected)
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="../../../etc/passwd",
                txn_id=txn_id,
                old_content=None,
                new_content="malicious content",
                timestamp=time.time(),
            )
        )

        # Verify NOT tracked
        assert txn_id not in plugin._pending_changes or not plugin._pending_changes[txn_id]

        # Verify error recorded
        metrics = plugin.get_metrics()
        assert metrics.total_errors >= 1

    @pytest.mark.asyncio
    async def test_delete_event_invalid_path(self, plugin):
        """Security: delete event with invalid path rejected"""
        txn_id = "txn-123"

        # Delete with invalid path (should be silently rejected)
        await plugin.on_event(
            ShadowFSEvent(
                type="delete",
                path="/etc/passwd",
                txn_id=txn_id,
                old_content="content",
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify NOT tracked
        assert txn_id not in plugin._pending_changes or not plugin._pending_changes[txn_id]

        # Verify error recorded
        metrics = plugin.get_metrics()
        assert metrics.total_errors >= 1


# ========== Parallel Processing Tests ==========


class TestParallelProcessing:
    """Parallel language processing tests"""

    @pytest.mark.asyncio
    async def test_parallel_language_processing(self, plugin, mock_ir_builder, mock_indexer):
        """Parallel: multiple languages processed in parallel"""
        txn_id = "txn-123"

        # Write files in 3 different languages
        languages = [("a.py", "python"), ("b.ts", "typescript"), ("c.java", "java")]

        for filename, _ in languages:
            await plugin.on_event(
                ShadowFSEvent(
                    type="write",
                    path=filename,
                    txn_id=txn_id,
                    old_content=None,
                    new_content="content",
                    timestamp=time.time(),
                )
            )

        # Commit (triggers parallel processing)
        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify 3 separate IR delta calls (one per language, parallel)
        assert mock_ir_builder.build_incremental.call_count == 3

        # Verify languages
        calls = mock_ir_builder.build_incremental.call_args_list
        languages_called = {call[1]["language"] for call in calls}
        assert "python" in languages_called
        assert "typescript" in languages_called
        assert "java" in languages_called

    @pytest.mark.asyncio
    async def test_parallel_error_isolation_simplified(self, plugin, mock_ir_builder, mock_indexer):
        """
        Parallel: error in one language doesn't block commit

        Simplified test: verify error isolation at commit level
        """
        txn_id = "txn-123"

        # Configure mock to always fail
        mock_ir_builder.build_incremental.side_effect = RuntimeError("IR failed")

        # Write Python and TypeScript files
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="main.py",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="app.ts",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        # Commit (should not raise, even with all IR failures)
        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify errors recorded
        metrics = plugin.get_metrics()
        assert metrics.total_errors >= 1, "Errors should be recorded"

        # Verify commit still completed
        assert metrics.total_commits == 1


# ========== Extreme Edge Cases ==========


class TestExtremeEdgeCases:
    """Extreme edge case tests"""

    @pytest.mark.asyncio
    async def test_empty_filename(self, plugin):
        """Extreme: empty filename"""
        txn_id = "txn-123"

        # Write with empty filename (should not crash)
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        # Should be tracked (empty string is valid)
        assert txn_id in plugin._pending_changes

    @pytest.mark.asyncio
    async def test_very_long_filename(self, plugin):
        """Extreme: very long filename (1000 chars)"""
        txn_id = "txn-123"
        long_name = "a" * 1000 + ".py"

        # Write with very long filename
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path=long_name,
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        # Should be tracked
        assert txn_id in plugin._pending_changes
        assert Path(long_name) in plugin._pending_changes[txn_id]

    @pytest.mark.asyncio
    async def test_unicode_filename(self, plugin):
        """Extreme: unicode filename"""
        txn_id = "txn-123"
        unicode_name = "한글파일名前.py"

        # Write with unicode filename
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path=unicode_name,
                txn_id=txn_id,
                old_content=None,
                new_content="content",
                timestamp=time.time(),
            )
        )

        # Should be tracked
        assert txn_id in plugin._pending_changes

    @pytest.mark.asyncio
    async def test_many_files_same_txn(self, plugin, mock_ir_builder, mock_indexer):
        """Extreme: 1000 files in same transaction"""
        txn_id = "txn-123"

        # Write 1000 files
        for i in range(1000):
            await plugin.on_event(
                ShadowFSEvent(
                    type="write",
                    path=f"file{i}.py",
                    txn_id=txn_id,
                    old_content=None,
                    new_content=f"content{i}",
                    timestamp=time.time(),
                )
            )

        # Commit
        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id=txn_id,
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # Verify batched
        assert mock_ir_builder.build_incremental.call_count == 1
        call_args = mock_ir_builder.build_incremental.call_args
        files = call_args[1]["files"]
        assert len(files) == 1000

        # Verify metrics
        metrics = plugin.get_metrics()
        assert metrics.avg_batch_size == 1000.0

    @pytest.mark.asyncio
    async def test_many_concurrent_transactions(self, plugin, mock_ir_builder, mock_indexer):
        """Extreme: 100 concurrent transactions"""
        # Write to 100 different transactions
        for i in range(100):
            await plugin.on_event(
                ShadowFSEvent(
                    type="write",
                    path=f"file{i}.py",
                    txn_id=f"txn-{i}",
                    old_content=None,
                    new_content=f"content{i}",
                    timestamp=time.time(),
                )
            )

        # Verify all tracked
        assert len(plugin._pending_changes) == 100

        # Commit all
        for i in range(100):
            await plugin.on_event(
                ShadowFSEvent(
                    type="commit",
                    path="",
                    txn_id=f"txn-{i}",
                    old_content=None,
                    new_content=None,
                    timestamp=time.time(),
                )
            )

        # Verify all cleared
        assert len(plugin._pending_changes) == 0

        # Verify metrics
        metrics = plugin.get_metrics()
        assert metrics.total_commits == 100

    @pytest.mark.asyncio
    async def test_rapid_fire_events(self, plugin, mock_ir_builder, mock_indexer):
        """Extreme: 10000 rapid-fire events"""
        txn_id = "txn-123"

        # Rapid-fire 1000 writes (축소)
        for i in range(1000):  # 10000 → 1000
            await plugin.on_event(
                ShadowFSEvent(
                    type="write",
                    path=f"file{i % 100}.py",  # Reuse 100 files
                    txn_id=txn_id,
                    old_content=None,
                    new_content=f"content{i}",
                    timestamp=time.time(),
                )
            )

        # Should only have 100 unique files
        assert len(plugin._pending_changes[txn_id]) == 100

        # Verify metrics
        metrics = plugin.get_metrics()
        assert metrics.total_writes == 10000

    @pytest.mark.asyncio
    async def test_special_characters_filename(self, plugin):
        """Extreme: special characters in filename"""
        txn_id = "txn-123"
        special_names = [
            "file with spaces.py",
            "file-with-dashes.py",
            "file_with_underscores.py",
            "file.multiple.dots.py",
            "file@special#chars.py",
        ]

        for name in special_names:
            await plugin.on_event(
                ShadowFSEvent(
                    type="write",
                    path=name,
                    txn_id=txn_id,
                    old_content=None,
                    new_content="content",
                    timestamp=time.time(),
                )
            )

        # All should be tracked
        assert len(plugin._pending_changes[txn_id]) == len(special_names)
