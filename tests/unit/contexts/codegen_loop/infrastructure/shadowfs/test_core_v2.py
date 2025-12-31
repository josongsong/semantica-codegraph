"""
ShadowFS Core v2 Tests

Comprehensive test coverage:
- Base Cases: Happy path
- Corner Cases: Boundary conditions
- Edge Cases: Concurrency, conflicts
- Extreme Cases: Performance, large files

Test Strategy:
    - Each test is independent (no shared state)
    - Use tmp_path fixture for isolation
    - Verify both state and side effects
"""

import asyncio
import time
from pathlib import Path

import pytest

from codegraph_runtime.codegen_loop.domain.shadowfs.events import (
    CommitError,
    ConflictError,
    ShadowFSEvent,
)
from codegraph_runtime.codegen_loop.infrastructure.shadowfs.core_v2 import (
    CoreConfig,
    ShadowFSCore,
)
from codegraph_runtime.codegen_loop.infrastructure.shadowfs.event_bus import EventBus

# ========== Fixtures ==========


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create temp workspace with sample files"""
    # Create sample structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main(): pass")
    (tmp_path / "src" / "utils.py").write_text("def util(): pass")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test(): pass")

    return tmp_path


@pytest.fixture
def event_bus() -> EventBus:
    """Create event bus"""
    return EventBus()


@pytest.fixture
def config() -> CoreConfig:
    """Create config"""
    return CoreConfig(
        max_file_size=1024 * 1024,  # 1MB for tests
        materialize_use_symlinks=True,
        txn_ttl=0,  # No TTL for tests
    )


@pytest.fixture
def core(workspace: Path, event_bus: EventBus, config: CoreConfig) -> ShadowFSCore:
    """Create ShadowFS Core"""
    return ShadowFSCore(workspace, event_bus, config)


class EventCollector:
    """Test helper: collect emitted events"""

    def __init__(self):
        self.events: list[ShadowFSEvent] = []

    async def on_event(self, event: ShadowFSEvent) -> None:
        self.events.append(event)


# ========== Base Cases (Happy Path) ==========


class TestBaseCases:
    """Happy path tests"""

    @pytest.mark.asyncio
    async def test_begin_commit_happy_path(self, core: ShadowFSCore, workspace: Path):
        """Base: begin → write → commit"""
        # Begin
        txn_id = await core.begin()
        assert txn_id is not None
        assert len(txn_id) > 0

        # Write
        await core.write("new_file.py", "def new(): pass", txn_id)

        # Commit
        await core.commit(txn_id)

        # Verify file exists
        assert (workspace / "new_file.py").exists()
        assert (workspace / "new_file.py").read_text() == "def new(): pass"

    @pytest.mark.asyncio
    async def test_begin_rollback_happy_path(self, core: ShadowFSCore, workspace: Path):
        """Base: begin → write → rollback"""
        # Begin
        txn_id = await core.begin()

        # Write
        await core.write("new_file.py", "def new(): pass", txn_id)

        # Rollback
        await core.rollback(txn_id)

        # Verify file doesn't exist
        assert not (workspace / "new_file.py").exists()

    @pytest.mark.asyncio
    async def test_read_write_read(self, core: ShadowFSCore, workspace: Path):
        """Base: read → write → read (verify change)"""
        txn_id = await core.begin()

        # Read original
        original = await core.read("src/main.py", txn_id)
        assert original == "def main(): pass"

        # Write
        await core.write("src/main.py", "def main(): return 42", txn_id)

        # Read modified
        modified = await core.read("src/main.py", txn_id)
        assert modified == "def main(): return 42"

    @pytest.mark.asyncio
    async def test_delete_commit(self, core: ShadowFSCore, workspace: Path):
        """Base: delete → commit"""
        txn_id = await core.begin()

        # Delete
        await core.delete("src/utils.py", txn_id)

        # Verify deleted in transaction
        with pytest.raises(FileNotFoundError):
            await core.read("src/utils.py", txn_id)

        # Commit
        await core.commit(txn_id)

        # Verify deleted on disk
        assert not (workspace / "src" / "utils.py").exists()

    @pytest.mark.asyncio
    async def test_event_emission(self, core: ShadowFSCore, event_bus: EventBus):
        """Base: verify events are emitted"""
        collector = EventCollector()
        event_bus.register(collector)

        txn_id = await core.begin()
        await core.write("file.py", "content", txn_id)
        await core.commit(txn_id)

        # Verify events
        assert len(collector.events) >= 2  # write + commit
        assert collector.events[0].type == "write"
        assert collector.events[0].path == "file.py"
        assert collector.events[-1].type == "commit"


# ========== Corner Cases (Boundary Conditions) ==========


class TestCornerCases:
    """Corner case tests"""

    @pytest.mark.asyncio
    async def test_begin_with_custom_id(self, core: ShadowFSCore):
        """Corner: begin with custom transaction ID"""
        txn_id = await core.begin("custom-txn-123")
        assert txn_id == "custom-txn-123"

    @pytest.mark.asyncio
    async def test_begin_duplicate_id(self, core: ShadowFSCore):
        """Corner: begin with duplicate ID → error"""
        await core.begin("txn-1")

        with pytest.raises(ValueError, match="already exists"):
            await core.begin("txn-1")

    @pytest.mark.asyncio
    async def test_write_to_nonexistent_txn(self, core: ShadowFSCore):
        """Corner: write to non-existent transaction"""
        with pytest.raises(ValueError, match="not found"):
            await core.write("file.py", "content", "invalid-txn")

    @pytest.mark.asyncio
    async def test_commit_nonexistent_txn(self, core: ShadowFSCore):
        """Corner: commit non-existent transaction"""
        with pytest.raises(ValueError, match="not found"):
            await core.commit("invalid-txn")

    @pytest.mark.asyncio
    async def test_rollback_nonexistent_txn(self, core: ShadowFSCore):
        """Corner: rollback non-existent transaction"""
        with pytest.raises(ValueError, match="not found"):
            await core.rollback("invalid-txn")

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, core: ShadowFSCore):
        """Corner: read file that doesn't exist"""
        txn_id = await core.begin()

        with pytest.raises(FileNotFoundError):
            await core.read("nonexistent.py", txn_id)

    @pytest.mark.asyncio
    async def test_read_deleted_file(self, core: ShadowFSCore):
        """Corner: read file that was deleted in transaction"""
        txn_id = await core.begin()

        await core.delete("src/main.py", txn_id)

        with pytest.raises(FileNotFoundError):
            await core.read("src/main.py", txn_id)

    @pytest.mark.asyncio
    async def test_write_then_delete(self, core: ShadowFSCore):
        """Corner: write then delete same file"""
        txn_id = await core.begin()

        await core.write("file.py", "content", txn_id)
        await core.delete("file.py", txn_id)

        # Should be deleted
        with pytest.raises(FileNotFoundError):
            await core.read("file.py", txn_id)

    @pytest.mark.asyncio
    async def test_delete_then_write(self, core: ShadowFSCore, workspace: Path):
        """Corner: delete then write same file (undelete)"""
        txn_id = await core.begin()

        await core.delete("src/main.py", txn_id)
        await core.write("src/main.py", "new content", txn_id)

        # Should be writable (undeleted)
        content = await core.read("src/main.py", txn_id)
        assert content == "new content"

        await core.commit(txn_id)
        assert (workspace / "src" / "main.py").read_text() == "new content"

    @pytest.mark.asyncio
    async def test_empty_transaction(self, core: ShadowFSCore):
        """Corner: commit empty transaction (no changes)"""
        txn_id = await core.begin()
        await core.commit(txn_id)  # Should not error

    @pytest.mark.asyncio
    async def test_read_without_transaction(self, core: ShadowFSCore):
        """Corner: read directly from workspace (no txn)"""
        content = await core.read("src/main.py", txn_id=None)
        assert content == "def main(): pass"


# ========== Edge Cases (Concurrency, Conflicts) ==========


class TestEdgeCases:
    """Edge case tests"""

    @pytest.mark.asyncio
    async def test_conflict_detection(self, core: ShadowFSCore, workspace: Path):
        """Edge: detect conflict (optimistic concurrency)"""
        # Create base file
        (workspace / "conflict.py").write_text("base content")

        # Begin transaction
        txn_id = await core.begin()

        # External change (simulating concurrent modification)
        (workspace / "conflict.py").write_text("external change")

        # Modify in transaction
        await core.write("conflict.py", "txn change", txn_id)

        # Commit should detect conflict
        with pytest.raises(ConflictError) as exc_info:
            await core.commit(txn_id)

        assert "conflict.py" in exc_info.value.conflicts

    @pytest.mark.asyncio
    async def test_multi_txn_no_conflict(self, core: ShadowFSCore, workspace: Path):
        """Edge: multiple transactions, different files (no conflict)"""
        txn1 = await core.begin()
        txn2 = await core.begin()

        # Different files
        await core.write("file1.py", "content1", txn1)
        await core.write("file2.py", "content2", txn2)

        # Both should succeed
        await core.commit(txn1)
        await core.commit(txn2)

        assert (workspace / "file1.py").read_text() == "content1"
        assert (workspace / "file2.py").read_text() == "content2"

    @pytest.mark.asyncio
    async def test_multi_txn_same_file_conflict(self, core: ShadowFSCore):
        """Edge: multiple transactions, same file → conflict"""
        txn1 = await core.begin()
        txn2 = await core.begin()

        # Same file
        await core.write("file.py", "version1", txn1)
        await core.write("file.py", "version2", txn2)

        # First commit succeeds
        await core.commit(txn1)

        # Second commit should conflict
        with pytest.raises(ConflictError):
            await core.commit(txn2)

    @pytest.mark.asyncio
    async def test_concurrent_writes_same_txn(self, core: ShadowFSCore):
        """Edge: concurrent writes to same file in same txn (race)"""
        txn_id = await core.begin()

        # Simulate race condition (100 concurrent writes)
        tasks = [core.write("file.py", f"content{i}", txn_id) for i in range(100)]

        await asyncio.gather(*tasks)

        # Should not corrupt (last write wins)
        content = await core.read("file.py", txn_id)
        assert content.startswith("content")  # Some valid content

    @pytest.mark.asyncio
    async def test_read_isolation(self, core: ShadowFSCore):
        """Edge: read isolation between transactions"""
        txn1 = await core.begin()
        txn2 = await core.begin()

        # Write in txn1
        await core.write("file.py", "txn1 content", txn1)

        # Read in txn2 should NOT see txn1 changes
        with pytest.raises(FileNotFoundError):
            await core.read("file.py", txn2)

    @pytest.mark.asyncio
    async def test_materialize_with_changes(self, core: ShadowFSCore, workspace: Path):
        """Edge: materialize with changes"""
        txn_id = await core.begin()

        # Modify existing file
        await core.write("src/main.py", "modified", txn_id)

        # Create new file
        await core.write("new.py", "new content", txn_id)

        # Delete file
        await core.delete("src/utils.py", txn_id)

        # Materialize
        async with await core.materialize(txn_id) as lease:
            # Verify modified
            assert (lease.path / "src" / "main.py").read_text() == "modified"

            # Verify new
            assert (lease.path / "new.py").read_text() == "new content"

            # Verify deleted
            assert not (lease.path / "src" / "utils.py").exists()

            # Verify unchanged (should exist)
            assert (lease.path / "tests" / "test_main.py").exists()


# ========== Extreme Cases (Performance, Limits) ==========


class TestExtremeCases:
    """Extreme case tests"""

    @pytest.mark.asyncio
    async def test_write_latency_target(self, core: ShadowFSCore):
        """Extreme: write() latency < 5ms (target)"""
        txn_id = await core.begin()

        # Warmup
        for i in range(10):
            await core.write(f"warmup{i}.py", "content", txn_id)

        # Measure
        durations = []
        for i in range(100):
            start = time.perf_counter()
            await core.write(f"file{i}.py", f"content{i}", txn_id)
            duration = time.perf_counter() - start
            durations.append(duration)

        # Stats
        avg_ms = (sum(durations) / len(durations)) * 1000
        p99_ms = sorted(durations)[98] * 1000

        print(f"\nWrite latency: avg={avg_ms:.2f}ms, p99={p99_ms:.2f}ms")

        # Verify target (relaxed for CI)
        assert avg_ms < 10.0, f"Write latency too slow: {avg_ms:.2f}ms"

    @pytest.mark.asyncio
    async def test_large_transaction(self, core: ShadowFSCore):
        """Extreme: 1000 files in single transaction"""
        txn_id = await core.begin()

        # Write 1000 files
        for i in range(1000):
            await core.write(f"file{i}.py", f"content{i}", txn_id)

        # Commit should not error
        await core.commit(txn_id)

        # Verify metrics
        metrics = core.get_metrics()
        assert metrics.files_written >= 1000

    @pytest.mark.asyncio
    async def test_many_transactions(self, core: ShadowFSCore):
        """Extreme: 100 sequential transactions"""
        for i in range(100):
            txn_id = await core.begin()
            await core.write(f"file{i}.py", f"content{i}", txn_id)
            await core.commit(txn_id)

        # Verify metrics
        metrics = core.get_metrics()
        assert metrics.txn_begun >= 100
        assert metrics.txn_committed >= 100

    @pytest.mark.asyncio
    async def test_large_file_content(self, core: ShadowFSCore):
        """Extreme: large file (1MB)"""
        txn_id = await core.begin()

        # 1MB content
        large_content = "x" * (1024 * 1024)

        await core.write("large.py", large_content, txn_id)

        # Read back
        content = await core.read("large.py", txn_id)
        assert len(content) == 1024 * 1024

    @pytest.mark.asyncio
    async def test_materialize_performance(
        self,
        core: ShadowFSCore,
        workspace: Path,
    ):
        """Extreme: materialize with 100 files should be fast"""
        # Create 100 files
        for i in range(100):
            (workspace / f"file{i}.py").write_text(f"content{i}")

        txn_id = await core.begin()
        await core.write("changed.py", "new content", txn_id)

        # Measure materialize
        start = time.perf_counter()
        async with await core.materialize(txn_id) as lease:
            duration = time.perf_counter() - start

            print(f"\nMaterialize (100 files): {duration * 1000:.2f}ms")

            # Should be fast (<1s)
            assert duration < 1.0, f"Materialize too slow: {duration}s"

    @pytest.mark.asyncio
    async def test_rollback_large_transaction(self, core: ShadowFSCore):
        """Extreme: rollback large transaction should be fast"""
        txn_id = await core.begin()

        # Write 500 files
        for i in range(500):
            await core.write(f"file{i}.py", f"content{i}", txn_id)

        # Rollback should be instant
        start = time.perf_counter()
        await core.rollback(txn_id)
        duration = time.perf_counter() - start

        print(f"\nRollback (500 files): {duration * 1000:.2f}ms")

        # Should be very fast (O(1))
        assert duration < 0.1, f"Rollback too slow: {duration}s"

    @pytest.mark.asyncio
    async def test_metrics_accuracy(self, core: ShadowFSCore):
        """Extreme: verify metrics accuracy"""
        # Perform operations
        txn1 = await core.begin()
        await core.write("f1.py", "c1", txn1)
        await core.write("f2.py", "c2", txn1)
        await core.delete("src/main.py", txn1)
        await core.commit(txn1)

        txn2 = await core.begin()
        await core.write("f3.py", "c3", txn2)
        await core.rollback(txn2)

        # Verify metrics
        metrics = core.get_metrics()
        assert metrics.txn_begun == 2
        assert metrics.txn_committed == 1
        assert metrics.txn_rolled_back == 1
        assert metrics.files_written >= 3
        assert metrics.files_deleted >= 1
        assert metrics.write_latency_avg > 0


# ========== Integration Tests ==========


class TestIntegration:
    """Integration tests (full workflows)"""

    @pytest.mark.asyncio
    async def test_full_workflow_with_events(
        self,
        core: ShadowFSCore,
        event_bus: EventBus,
        workspace: Path,
    ):
        """Integration: full workflow with event tracking"""
        collector = EventCollector()
        event_bus.register(collector)

        # Workflow
        txn_id = await core.begin()
        await core.write("file1.py", "content1", txn_id)
        await core.write("file2.py", "content2", txn_id)
        await core.delete("src/utils.py", txn_id)
        await core.commit(txn_id)

        # Verify events
        write_events = [e for e in collector.events if e.type == "write"]
        delete_events = [e for e in collector.events if e.type == "delete"]
        commit_events = [e for e in collector.events if e.type == "commit"]

        assert len(write_events) == 2
        assert len(delete_events) == 1
        assert len(commit_events) == 1

        # Verify filesystem
        assert (workspace / "file1.py").exists()
        assert (workspace / "file2.py").exists()
        assert not (workspace / "src" / "utils.py").exists()

    @pytest.mark.asyncio
    async def test_error_recovery(self, core: ShadowFSCore, workspace: Path):
        """Integration: error recovery (conflict → rollback → retry)"""
        # Create base file
        (workspace / "conflict.py").write_text("base")

        # Txn1: begin
        txn1 = await core.begin()

        # External change
        (workspace / "conflict.py").write_text("external")

        # Txn1: modify
        await core.write("conflict.py", "txn1", txn1)

        # Txn1: commit → conflict
        with pytest.raises(ConflictError):
            await core.commit(txn1)

        # Rollback (manual)
        await core.rollback(txn1)

        # Retry with new transaction
        txn2 = await core.begin()
        await core.write("conflict.py", "txn2", txn2)
        await core.commit(txn2)  # Should succeed

        # Verify
        assert (workspace / "conflict.py").read_text() == "txn2"
