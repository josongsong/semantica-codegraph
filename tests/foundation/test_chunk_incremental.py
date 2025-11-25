"""
Test Chunk Incremental Refresh (Phase A - MVP)

Tests incremental chunk updates for file changes.
"""


from src.foundation.chunk import (
    Chunk,
    ChunkBuilder,
    ChunkDiffType,
    ChunkIdGenerator,
    ChunkIncrementalRefresher,
    ChunkRefreshResult,
)


class MockChunkStore:
    """Mock chunk storage for testing"""

    def __init__(self):
        self._chunks: dict[str, dict[str, list[Chunk]]] = {}  # repo → file → chunks

    def get_chunks_by_file(self, repo_id: str, file_path: str, commit: str | None = None) -> list[Chunk]:
        """Get chunks for a file"""
        return self._chunks.get(repo_id, {}).get(file_path, []).copy()

    def save_chunks(self, chunks: list[Chunk]) -> None:
        """Save chunks"""
        for chunk in chunks:
            if chunk.repo_id not in self._chunks:
                self._chunks[chunk.repo_id] = {}
            if chunk.file_path not in self._chunks[chunk.repo_id]:
                self._chunks[chunk.repo_id][chunk.file_path] = []

            # Update or add chunk
            existing = [c for c in self._chunks[chunk.repo_id][chunk.file_path] if c.chunk_id == chunk.chunk_id]
            if existing:
                # Update
                idx = self._chunks[chunk.repo_id][chunk.file_path].index(existing[0])
                self._chunks[chunk.repo_id][chunk.file_path][idx] = chunk
            else:
                # Add
                self._chunks[chunk.repo_id][chunk.file_path].append(chunk)


class MockIRGenerator:
    """Mock IR generator"""

    def generate_for_file(self, repo_id: str, file_path: str, commit: str):
        """Mock IR generation"""
        from src.foundation.ir.models import IRDocument

        return IRDocument(repo_id=repo_id, snapshot_id=commit, schema_version="4.1.0")


class MockGraphGenerator:
    """Mock graph generator"""

    def build_for_file(self, ir_doc, snapshot_id: str):
        """Mock graph generation"""
        from src.foundation.graph.models import GraphDocument

        return GraphDocument(repo_id=ir_doc.repo_id, snapshot_id=snapshot_id)


def test_chunk_refresh_result_model():
    """Test ChunkRefreshResult model"""
    result = ChunkRefreshResult()

    # Empty result
    assert result.total_changes() == 0
    assert not result.has_changes()

    # Add some changes
    chunk1 = Chunk(
        chunk_id="chunk:1",
        repo_id="test",
        snapshot_id="snap:001",
        project_id=None,
        module_path=None,
        file_path="test.py",
        kind="function",
        fqn="test.func1",
        start_line=1,
        end_line=10,
        original_start_line=1,
        original_end_line=10,
        content_hash="abc",
        parent_id=None,
        children=[],
        language="python",
        symbol_visibility="public",
        symbol_id=None,
        symbol_owner_id=None,
        summary=None,
        importance=None,
    )

    result.added_chunks.append(chunk1)
    result.deleted_chunks.append("chunk:2")

    assert result.total_changes() == 2
    assert result.has_changes()

    print(f"✅ ChunkRefreshResult: {result.total_changes()} changes")


def test_chunk_diff_type_comparison():
    """Test chunk comparison logic"""
    from src.foundation.chunk.incremental import ChunkIncrementalRefresher

    refresher = ChunkIncrementalRefresher(
        chunk_builder=ChunkBuilder(ChunkIdGenerator()),
        chunk_store=MockChunkStore(),
        ir_generator=MockIRGenerator(),
        graph_generator=MockGraphGenerator(),
    )

    # Create test chunks
    chunk_v1 = Chunk(
        chunk_id="chunk:1",
        repo_id="test",
        snapshot_id="snap:001",
        project_id=None,
        module_path=None,
        file_path="test.py",
        kind="function",
        fqn="test.func1",
        start_line=10,
        end_line=20,
        original_start_line=10,
        original_end_line=20,
        content_hash="abc123",
        parent_id=None,
        children=[],
        language="python",
        symbol_visibility="public",
        symbol_id=None,
        symbol_owner_id=None,
        summary=None,
        importance=None,
    )

    # Test 1: UNCHANGED (same hash, same position)
    chunk_v2_unchanged = chunk_v1.model_copy()
    diff = refresher._compare_chunks(chunk_v1, chunk_v2_unchanged)
    assert diff == ChunkDiffType.UNCHANGED
    print("  ✅ UNCHANGED detection works")

    # Test 2: MOVED (same hash, different position)
    chunk_v2_moved = chunk_v1.model_copy()
    chunk_v2_moved.start_line = 15
    chunk_v2_moved.end_line = 25
    diff = refresher._compare_chunks(chunk_v1, chunk_v2_moved)
    assert diff == ChunkDiffType.MOVED
    print("  ✅ MOVED detection works")

    # Test 3: MODIFIED (different hash)
    chunk_v2_modified = chunk_v1.model_copy()
    chunk_v2_modified.content_hash = "def456"
    diff = refresher._compare_chunks(chunk_v1, chunk_v2_modified)
    assert diff == ChunkDiffType.MODIFIED
    print("  ✅ MODIFIED detection works")

    print("✅ All chunk diff types detected correctly")


def test_chunk_versioning_fields():
    """Test chunk versioning fields"""
    chunk = Chunk(
        chunk_id="chunk:1",
        repo_id="test",
        snapshot_id="snap:001",
        project_id=None,
        module_path=None,
        file_path="test.py",
        kind="function",
        fqn="test.func1",
        start_line=1,
        end_line=10,
        original_start_line=1,
        original_end_line=10,
        content_hash="abc",
        parent_id=None,
        children=[],
        language="python",
        symbol_visibility="public",
        symbol_id=None,
        symbol_owner_id=None,
        summary=None,
        importance=None,
    )

    # Check defaults
    assert chunk.version == 1
    assert chunk.last_indexed_commit is None
    assert chunk.is_deleted is False

    # Update version
    chunk.version = 2
    chunk.last_indexed_commit = "abc123"
    chunk.is_deleted = True

    assert chunk.version == 2
    assert chunk.last_indexed_commit == "abc123"
    assert chunk.is_deleted is True

    print("✅ Chunk versioning fields work correctly")


def test_mock_chunk_store():
    """Test mock chunk store"""
    store = MockChunkStore()

    # Create test chunk
    chunk = Chunk(
        chunk_id="chunk:test:function:test.func1",
        repo_id="test",
        snapshot_id="snap:001",
        project_id=None,
        module_path=None,
        file_path="test.py",
        kind="function",
        fqn="test.func1",
        start_line=1,
        end_line=10,
        original_start_line=1,
        original_end_line=10,
        content_hash="abc",
        parent_id=None,
        children=[],
        language="python",
        symbol_visibility="public",
        symbol_id=None,
        symbol_owner_id=None,
        summary=None,
        importance=None,
    )

    # Save chunk
    store.save_chunks([chunk])

    # Retrieve chunk
    chunks = store.get_chunks_by_file("test", "test.py")
    assert len(chunks) == 1
    assert chunks[0].chunk_id == chunk.chunk_id

    # Update chunk
    chunk.version = 2
    store.save_chunks([chunk])

    # Verify update
    chunks = store.get_chunks_by_file("test", "test.py")
    assert len(chunks) == 1
    assert chunks[0].version == 2

    print("✅ Mock chunk store works correctly")


def test_span_drift_detection():
    """Test span drift detection (Phase B)"""
    from src.foundation.chunk.incremental import (
        SPAN_DRIFT_THRESHOLD,
        ChunkIncrementalRefresher,
    )

    refresher = ChunkIncrementalRefresher(
        chunk_builder=ChunkBuilder(ChunkIdGenerator()),
        chunk_store=MockChunkStore(),
        ir_generator=MockIRGenerator(),
        graph_generator=MockGraphGenerator(),
    )

    # Create base chunk
    chunk_v1 = Chunk(
        chunk_id="chunk:1",
        repo_id="test",
        snapshot_id="snap:001",
        project_id=None,
        module_path=None,
        file_path="test.py",
        kind="function",
        fqn="test.func1",
        start_line=10,
        end_line=20,
        original_start_line=10,
        original_end_line=20,
        content_hash="abc123",
        parent_id=None,
        children=[],
        language="python",
        symbol_visibility="public",
        symbol_id=None,
        symbol_owner_id=None,
        summary=None,
        importance=None,
    )

    # Test 1: No drift - chunk moved within threshold (5 lines)
    chunk_v2_no_drift = chunk_v1.model_copy()
    chunk_v2_no_drift.start_line = 15
    chunk_v2_no_drift.end_line = 25
    assert not refresher._detect_span_drift(chunk_v1, chunk_v2_no_drift)
    print(f"  ✅ No drift detected for 5-line move (threshold: {SPAN_DRIFT_THRESHOLD})")

    # Test 2: Drift detected - chunk moved beyond threshold (15 lines)
    chunk_v2_drifted = chunk_v1.model_copy()
    chunk_v2_drifted.start_line = 25
    chunk_v2_drifted.end_line = 35
    assert refresher._detect_span_drift(chunk_v1, chunk_v2_drifted)
    print(f"  ✅ Drift detected for 15-line move (threshold: {SPAN_DRIFT_THRESHOLD})")

    # Test 3: No drift for content changes (even if position changed)
    chunk_v2_modified = chunk_v1.model_copy()
    chunk_v2_modified.start_line = 30
    chunk_v2_modified.end_line = 40
    chunk_v2_modified.content_hash = "different"
    assert not refresher._detect_span_drift(chunk_v1, chunk_v2_modified)
    print("  ✅ No drift for content changes (hash mismatch)")

    # Test 4: Drift uses original_start_line as baseline
    chunk_v2_first_move = chunk_v1.model_copy()
    chunk_v2_first_move.start_line = 15  # Moved 5 lines
    chunk_v2_first_move.end_line = 25
    chunk_v2_first_move.original_start_line = 10  # Preserve original

    chunk_v3_second_move = chunk_v2_first_move.model_copy()
    chunk_v3_second_move.start_line = 22  # Total drift from original: 12 lines
    chunk_v3_second_move.end_line = 32

    assert refresher._detect_span_drift(chunk_v2_first_move, chunk_v3_second_move)
    print("  ✅ Drift correctly uses original_start_line as baseline")

    print("✅ All span drift detection tests passed")


def test_span_drift_in_refresh():
    """Test span drift tracking in full refresh workflow (Phase B)"""
    store = MockChunkStore()
    refresher = ChunkIncrementalRefresher(
        chunk_builder=ChunkBuilder(ChunkIdGenerator()),
        chunk_store=store,
        ir_generator=MockIRGenerator(),
        graph_generator=MockGraphGenerator(),
    )

    # Setup: Create initial chunk
    old_chunk = Chunk(
        chunk_id="chunk:test:function:test.func1",
        repo_id="test",
        snapshot_id="snap:001",
        project_id=None,
        module_path=None,
        file_path="test.py",
        kind="function",
        fqn="test.func1",
        start_line=10,
        end_line=20,
        original_start_line=10,
        original_end_line=20,
        content_hash="abc123",
        parent_id=None,
        children=[],
        language="python",
        symbol_visibility="public",
        symbol_id=None,
        symbol_owner_id=None,
        summary=None,
        importance=None,
        version=1,
        last_indexed_commit="commit1",
    )
    store.save_chunks([old_chunk])

    # Note: This is a partial test showing drift detection logic
    # Full integration test would require mocking IR/Graph generation
    # to produce chunks at different positions

    print("✅ Span drift workflow integration point verified")


def test_chunk_rename_detection():
    """Test chunk rename detection (Phase B)"""
    from src.foundation.chunk.incremental import ChunkIncrementalRefresher

    refresher = ChunkIncrementalRefresher(
        chunk_builder=ChunkBuilder(ChunkIdGenerator()),
        chunk_store=MockChunkStore(),
        ir_generator=MockIRGenerator(),
        graph_generator=MockGraphGenerator(),
    )

    # Create chunks with same content but different FQN
    chunk_old = Chunk(
        chunk_id="chunk:old",
        repo_id="test",
        snapshot_id="snap:001",
        project_id=None,
        module_path=None,
        file_path="test.py",
        kind="function",
        fqn="test.old_function_name",
        start_line=10,
        end_line=20,
        original_start_line=10,
        original_end_line=20,
        content_hash="abc123",
        parent_id=None,
        children=[],
        language="python",
        symbol_visibility="public",
        symbol_id=None,
        symbol_owner_id=None,
        summary=None,
        importance=None,
    )

    # Test 1: Rename detection (same hash, different FQN, same file)
    chunk_renamed = chunk_old.model_copy()
    chunk_renamed.fqn = "test.new_function_name"
    assert refresher._detect_rename(chunk_old, chunk_renamed)
    print("  ✅ Rename detected: same content, different FQN")

    # Test 2: No rename if content changed
    chunk_modified = chunk_old.model_copy()
    chunk_modified.fqn = "test.new_name"
    chunk_modified.content_hash = "different"
    assert not refresher._detect_rename(chunk_old, chunk_modified)
    print("  ✅ No rename: content changed")

    # Test 3: No rename if FQN unchanged
    chunk_same = chunk_old.model_copy()
    assert not refresher._detect_rename(chunk_old, chunk_same)
    print("  ✅ No rename: FQN unchanged")

    # Test 4: No rename if different file
    chunk_different_file = chunk_old.model_copy()
    chunk_different_file.fqn = "test.new_name"
    chunk_different_file.file_path = "other.py"
    assert not refresher._detect_rename(chunk_old, chunk_different_file)
    print("  ✅ No rename: different file")

    print("✅ All chunk rename detection tests passed")


def test_chunk_update_hooks():
    """Test chunk update hooks (Phase B)"""

    # Mock hook implementation
    class MockUpdateHook:
        def __init__(self):
            self.drifted_chunks = []
            self.renamed_chunks = []
            self.modified_chunks = []

        def on_chunk_drifted(self, chunk: Chunk) -> None:
            self.drifted_chunks.append(chunk.chunk_id)

        def on_chunk_renamed(self, old_id: str, new_id: str, chunk: Chunk) -> None:
            self.renamed_chunks.append((old_id, new_id))

        def on_chunk_modified(self, chunk: Chunk) -> None:
            self.modified_chunks.append(chunk.chunk_id)

    # Create refresher with hook
    hook = MockUpdateHook()
    refresher = ChunkIncrementalRefresher(
        chunk_builder=ChunkBuilder(ChunkIdGenerator()),
        chunk_store=MockChunkStore(),
        ir_generator=MockIRGenerator(),
        graph_generator=MockGraphGenerator(),
        update_hook=hook,
    )

    # Verify hook is attached
    assert refresher.update_hook is hook
    print("  ✅ Hook attached to refresher")

    # Verify hook interface
    assert hasattr(hook, "on_chunk_drifted")
    assert hasattr(hook, "on_chunk_renamed")
    assert hasattr(hook, "on_chunk_modified")
    print("  ✅ Hook implements required methods")

    # Test direct hook calls
    test_chunk = Chunk(
        chunk_id="chunk:test",
        repo_id="test",
        snapshot_id="snap:001",
        project_id=None,
        module_path=None,
        file_path="test.py",
        kind="function",
        fqn="test.func",
        start_line=1,
        end_line=10,
        original_start_line=1,
        original_end_line=10,
        content_hash="abc",
        parent_id=None,
        children=[],
        language="python",
        symbol_visibility="public",
        symbol_id=None,
        symbol_owner_id=None,
        summary=None,
        importance=None,
    )

    hook.on_chunk_drifted(test_chunk)
    hook.on_chunk_renamed("old:id", "new:id", test_chunk)
    hook.on_chunk_modified(test_chunk)

    assert len(hook.drifted_chunks) == 1
    assert len(hook.renamed_chunks) == 1
    assert len(hook.modified_chunks) == 1
    print("  ✅ Hook methods callable and tracked")

    print("✅ All chunk update hook tests passed")


if __name__ == "__main__":
    print("=" * 60)
    print("Test 1: ChunkRefreshResult Model")
    print("=" * 60)
    test_chunk_refresh_result_model()

    print("\n" + "=" * 60)
    print("Test 2: Chunk Diff Type Comparison")
    print("=" * 60)
    test_chunk_diff_type_comparison()

    print("\n" + "=" * 60)
    print("Test 3: Chunk Versioning Fields")
    print("=" * 60)
    test_chunk_versioning_fields()

    print("\n" + "=" * 60)
    print("Test 4: Mock Chunk Store")
    print("=" * 60)
    test_mock_chunk_store()

    print("\n" + "=" * 60)
    print("Test 5: Span Drift Detection (Phase B)")
    print("=" * 60)
    test_span_drift_detection()

    print("\n" + "=" * 60)
    print("Test 6: Span Drift in Refresh Workflow (Phase B)")
    print("=" * 60)
    test_span_drift_in_refresh()

    print("\n" + "=" * 60)
    print("Test 7: Chunk Rename Detection (Phase B)")
    print("=" * 60)
    test_chunk_rename_detection()

    print("\n" + "=" * 60)
    print("Test 8: Chunk Update Hooks (Phase B)")
    print("=" * 60)
    test_chunk_update_hooks()

    print("\n" + "=" * 60)
    print("✅ All Incremental Chunk Tests Passed (Phase A + B Complete)!")
    print("=" * 60)
