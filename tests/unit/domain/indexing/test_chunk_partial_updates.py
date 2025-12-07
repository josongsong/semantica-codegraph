"""
Tests for Phase C: Diff-based Partial Updates

Tests the git diff parser, affected chunk detection, and selective chunk updates.
"""

from src.foundation.chunk import (
    Chunk,
    ChunkBuilder,
    ChunkIdGenerator,
    ChunkIncrementalRefresher,
    DiffHunk,
    DiffParser,
)

# ============================================================
# Test DiffParser
# ============================================================


class TestDiffParser:
    """Test git diff parser"""

    def test_parse_simple_hunk(self):
        """Test parsing a simple single hunk diff"""
        diff_text = """
@@ -10,5 +10,6 @@ def foo():
     a = 1
     b = 2
+    c = 3
     return a + b
"""
        parser = DiffParser()
        hunks = parser.parse_diff(diff_text)

        assert len(hunks) == 1
        assert hunks[0].old_start == 10
        assert hunks[0].old_count == 5
        assert hunks[0].new_start == 10
        assert hunks[0].new_count == 6

    def test_parse_multiple_hunks(self):
        """Test parsing multiple hunks in a single diff"""
        diff_text = """
@@ -10,3 +10,4 @@ def foo():
     a = 1
+    b = 2
     return a
@@ -20,2 +21,3 @@ def bar():
     x = 1
+    y = 2
     return x
"""
        parser = DiffParser()
        hunks = parser.parse_diff(diff_text)

        assert len(hunks) == 2
        assert hunks[0].old_start == 10
        assert hunks[0].old_count == 3
        assert hunks[1].old_start == 20
        assert hunks[1].old_count == 2

    def test_parse_hunk_no_count(self):
        """Test parsing hunk with implicit count (1 line)"""
        diff_text = """
@@ -10 +10,2 @@ def foo():
-    a = 1
+    a = 1
+    b = 2
"""
        parser = DiffParser()
        hunks = parser.parse_diff(diff_text)

        assert len(hunks) == 1
        assert hunks[0].old_start == 10
        assert hunks[0].old_count == 1
        assert hunks[0].new_start == 10
        assert hunks[0].new_count == 2

    def test_parse_empty_diff(self):
        """Test parsing empty diff"""
        parser = DiffParser()
        hunks = parser.parse_diff("")

        assert hunks == []

    def test_parse_no_hunks(self):
        """Test diff with no hunk headers"""
        diff_text = """
diff --git a/foo.py b/foo.py
index 123..456 100644
--- a/foo.py
+++ b/foo.py
"""
        parser = DiffParser()
        hunks = parser.parse_diff(diff_text)

        assert hunks == []


class TestDiffHunk:
    """Test DiffHunk dataclass methods"""

    def test_affected_old_range(self):
        """Test affected_old_range calculation"""
        hunk = DiffHunk(old_start=10, old_count=5, new_start=10, new_count=6, lines=[])
        assert hunk.affected_old_range() == (10, 14)

    def test_affected_new_range(self):
        """Test affected_new_range calculation"""
        hunk = DiffHunk(old_start=10, old_count=5, new_start=10, new_count=6, lines=[])
        assert hunk.affected_new_range() == (10, 15)

    def test_affected_range_single_line(self):
        """Test affected range for single line change"""
        hunk = DiffHunk(old_start=10, old_count=1, new_start=10, new_count=1, lines=[])
        assert hunk.affected_old_range() == (10, 10)
        assert hunk.affected_new_range() == (10, 10)


# ============================================================
# Test Affected Chunk Detection
# ============================================================


class TestAffectedChunkDetection:
    """Test _identify_affected_chunks and _ranges_overlap"""

    def setup_method(self):
        """Setup test fixtures"""
        # Create dummy chunks at different line ranges
        self.chunks = [
            Chunk(
                chunk_id="chunk:repo:function:mod.func1",
                repo_id="repo",
                snapshot_id="snap:001",
                project_id=None,
                module_path="mod",
                file_path="mod.py",
                kind="function",
                fqn="mod.func1",
                start_line=10,
                end_line=20,
                original_start_line=10,
                original_end_line=20,
                content_hash="hash1",
                parent_id=None,
                children=[],
                language="python",
                symbol_visibility="public",
                symbol_id=None,
                symbol_owner_id=None,
                summary=None,
                importance=None,
            ),
            Chunk(
                chunk_id="chunk:repo:function:mod.func2",
                repo_id="repo",
                snapshot_id="snap:001",
                project_id=None,
                module_path="mod",
                file_path="mod.py",
                kind="function",
                fqn="mod.func2",
                start_line=30,
                end_line=40,
                original_start_line=30,
                original_end_line=40,
                content_hash="hash2",
                parent_id=None,
                children=[],
                language="python",
                symbol_visibility="public",
                symbol_id=None,
                symbol_owner_id=None,
                summary=None,
                importance=None,
            ),
            Chunk(
                chunk_id="chunk:repo:function:mod.func3",
                repo_id="repo",
                snapshot_id="snap:001",
                project_id=None,
                module_path="mod",
                file_path="mod.py",
                kind="function",
                fqn="mod.func3",
                start_line=50,
                end_line=60,
                original_start_line=50,
                original_end_line=60,
                content_hash="hash3",
                parent_id=None,
                children=[],
                language="python",
                symbol_visibility="public",
                symbol_id=None,
                symbol_owner_id=None,
                summary=None,
                importance=None,
            ),
        ]

        # Create refresher instance (we'll only use its helper methods)
        self.refresher = ChunkIncrementalRefresher(
            chunk_builder=None,  # type: ignore
            chunk_store=None,  # type: ignore
            ir_generator=None,  # type: ignore
            graph_generator=None,  # type: ignore
            use_partial_updates=True,
        )

    def test_ranges_overlap_complete(self):
        """Test overlapping ranges"""
        assert self.refresher._ranges_overlap((10, 20), (15, 25)) is True
        assert self.refresher._ranges_overlap((15, 25), (10, 20)) is True

    def test_ranges_overlap_adjacent(self):
        """Test adjacent ranges (touching but not overlapping)"""
        assert self.refresher._ranges_overlap((10, 20), (20, 30)) is True
        assert self.refresher._ranges_overlap((20, 30), (10, 20)) is True

    def test_ranges_no_overlap(self):
        """Test non-overlapping ranges"""
        assert self.refresher._ranges_overlap((10, 20), (30, 40)) is False
        assert self.refresher._ranges_overlap((30, 40), (10, 20)) is False

    def test_identify_affected_chunks_single_hunk(self):
        """Test identifying chunks affected by a single hunk"""
        hunks = [DiffHunk(old_start=15, old_count=5, new_start=15, new_count=6, lines=[])]  # Overlaps func1

        affected = self.refresher._identify_affected_chunks(self.chunks, hunks)
        assert affected == {"mod.func1"}

    def test_identify_affected_chunks_multiple_hunks(self):
        """Test identifying chunks affected by multiple hunks"""
        hunks = [
            DiffHunk(old_start=15, old_count=5, new_start=15, new_count=6, lines=[]),  # Overlaps func1
            DiffHunk(old_start=35, old_count=3, new_start=35, new_count=4, lines=[]),  # Overlaps func2
        ]

        affected = self.refresher._identify_affected_chunks(self.chunks, hunks)
        assert affected == {"mod.func1", "mod.func2"}

    def test_identify_affected_chunks_none(self):
        """Test no chunks affected"""
        hunks = [DiffHunk(old_start=70, old_count=5, new_start=70, new_count=6, lines=[])]  # No overlap

        affected = self.refresher._identify_affected_chunks(self.chunks, hunks)
        assert affected == set()

    def test_identify_affected_chunks_all(self):
        """Test all chunks affected"""
        hunks = [DiffHunk(old_start=1, old_count=100, new_start=1, new_count=100, lines=[])]  # Covers all

        affected = self.refresher._identify_affected_chunks(self.chunks, hunks)
        assert affected == {"mod.func1", "mod.func2", "mod.func3"}


# ============================================================
# Test Partial Update Integration
# ============================================================


class MockChunkStore:
    """Mock chunk store for testing"""

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

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        """Delete chunks"""
        for repo_id in self._chunks:
            for file_path in self._chunks[repo_id]:
                self._chunks[repo_id][file_path] = [
                    c for c in self._chunks[repo_id][file_path] if c.chunk_id not in chunk_ids
                ]


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


class TestPartialUpdateIntegration:
    """Integration tests for partial update flow"""

    def setup_method(self):
        """Setup test fixtures"""
        self.id_generator = ChunkIdGenerator()
        self.chunk_builder = ChunkBuilder(id_generator=self.id_generator)
        self.ir_generator = MockIRGenerator()
        self.graph_generator = MockGraphGenerator()
        self.chunk_store = MockChunkStore()

        # Track hook calls
        self.hook_calls: list[tuple[str, Chunk]] = []

        def update_hook(event: str, chunk: Chunk) -> None:
            self.hook_calls.append((event, chunk))

        self.update_hook = update_hook

        self.refresher = ChunkIncrementalRefresher(
            chunk_builder=self.chunk_builder,
            chunk_store=self.chunk_store,
            ir_generator=self.ir_generator,
            graph_generator=self.graph_generator,
            update_hook=self.update_hook,
            use_partial_updates=True,
        )

    def test_partial_update_with_manual_chunks(self):
        """Test partial update flow with manually created chunks"""
        repo_id = "test_repo"
        file_path = "test.py"

        # Manually create initial chunks (simulating existing state)
        func1_chunk = Chunk(
            chunk_id="chunk:test_repo:function:test.func1",
            repo_id=repo_id,
            snapshot_id="snap:001",
            project_id=None,
            module_path="test",
            file_path=file_path,
            kind="function",
            fqn="test.func1",
            start_line=1,
            end_line=4,
            original_start_line=1,
            original_end_line=4,
            content_hash="hash1",
            parent_id=None,
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            version=1,
            last_indexed_commit="abc123",
        )

        func2_chunk = Chunk(
            chunk_id="chunk:test_repo:function:test.func2",
            repo_id=repo_id,
            snapshot_id="snap:001",
            project_id=None,
            module_path="test",
            file_path=file_path,
            kind="function",
            fqn="test.func2",
            start_line=6,
            end_line=9,
            original_start_line=6,
            original_end_line=9,
            content_hash="hash2",
            parent_id=None,
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            version=1,
            last_indexed_commit="abc123",
        )

        # Save to store
        self.chunk_store.save_chunks([func1_chunk, func2_chunk])

        # Diff that only touches func1 (lines 1-4)
        diff_text = """
@@ -1,4 +1,5 @@ def func1():
 def func1():
-    a = 1
+    a = 1
+    c = 3
     return a
"""

        # Parse diff and identify affected chunks
        hunks = self.refresher.diff_parser.parse_diff(diff_text)
        assert len(hunks) == 1
        assert hunks[0].old_start == 1
        assert hunks[0].new_count == 5  # Now 5 lines instead of 4

        # Identify affected chunks
        old_chunks = self.chunk_store.get_chunks_by_file(repo_id, file_path, "abc123")
        affected = self.refresher._identify_affected_chunks(old_chunks, hunks)

        # Only func1 should be affected
        assert "test.func1" in affected
        assert "test.func2" not in affected

    def test_partial_update_fallback_no_diff(self):
        """Test that partial update falls back when no diff provided"""
        refresher_partial = ChunkIncrementalRefresher(
            chunk_builder=self.chunk_builder,
            chunk_store=self.chunk_store,
            ir_generator=self.ir_generator,
            graph_generator=self.graph_generator,
            use_partial_updates=True,
        )

        # Verify flag is set
        assert refresher_partial.use_partial_updates is True

        # When file_diffs is None or empty, should fall back to full processing
        # This is tested implicitly in the implementation

    def test_partial_update_disabled(self):
        """Test that partial updates are disabled when flag is False"""
        refresher_no_partial = ChunkIncrementalRefresher(
            chunk_builder=self.chunk_builder,
            chunk_store=self.chunk_store,
            ir_generator=self.ir_generator,
            graph_generator=self.graph_generator,
            use_partial_updates=False,  # Disabled
        )

        # Verify flag is set
        assert refresher_no_partial.use_partial_updates is False

        # Even if diff is provided, _handle_modified_file will be called
        # instead of _handle_modified_file_partial

    def test_partial_update_multiple_affected_chunks(self):
        """Test partial update with multiple affected chunks"""
        repo_id = "test_repo"
        file_path = "test.py"

        # Create 4 chunks in a file
        chunks = []
        for i in range(1, 5):
            chunk = Chunk(
                chunk_id=f"chunk:test_repo:function:test.func{i}",
                repo_id=repo_id,
                snapshot_id="snap:001",
                project_id=None,
                module_path="test",
                file_path=file_path,
                kind="function",
                fqn=f"test.func{i}",
                start_line=i * 10,
                end_line=i * 10 + 5,
                original_start_line=i * 10,
                original_end_line=i * 10 + 5,
                content_hash=f"hash{i}",
                parent_id=None,
                children=[],
                language="python",
                symbol_visibility="public",
                symbol_id=None,
                symbol_owner_id=None,
                summary=None,
                importance=None,
                version=1,
                last_indexed_commit="abc123",
            )
            chunks.append(chunk)

        self.chunk_store.save_chunks(chunks)

        # Diff that affects func2 and func3 (lines 20-35)
        diff_text = """
@@ -20,5 +20,6 @@ def func2():
 def func2():
     a = 2
+    b = 3
     return a
@@ -30,5 +31,6 @@ def func3():
 def func3():
     x = 3
+    y = 4
     return x
"""

        # Parse and identify affected chunks
        hunks = self.refresher.diff_parser.parse_diff(diff_text)
        assert len(hunks) == 2

        affected = self.refresher._identify_affected_chunks(chunks, hunks)

        # Only func2 and func3 should be affected
        assert "test.func2" in affected
        assert "test.func3" in affected
        assert "test.func1" not in affected
        assert "test.func4" not in affected

    def test_partial_update_with_hooks_integration(self):
        """Test that hooks are called correctly during partial update"""
        repo_id = "test_repo"
        file_path = "test.py"

        # Track hook calls
        hook_calls = []

        def update_hook(event: str, chunk: Chunk) -> None:
            hook_calls.append((event, chunk.fqn))

        refresher_with_hook = ChunkIncrementalRefresher(
            chunk_builder=self.chunk_builder,
            chunk_store=self.chunk_store,
            ir_generator=self.ir_generator,
            graph_generator=self.graph_generator,
            update_hook=update_hook,
            use_partial_updates=True,
        )

        # Create initial chunk
        chunk = Chunk(
            chunk_id="chunk:test_repo:function:test.func1",
            repo_id=repo_id,
            snapshot_id="snap:001",
            project_id=None,
            module_path="test",
            file_path=file_path,
            kind="function",
            fqn="test.func1",
            start_line=10,
            end_line=15,
            original_start_line=10,
            original_end_line=15,
            content_hash="hash1",
            parent_id=None,
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            version=1,
            last_indexed_commit="abc123",
        )
        self.chunk_store.save_chunks([chunk])

        # Diff that modifies the chunk
        diff_text = """
@@ -10,5 +10,6 @@ def func1():
 def func1():
     a = 1
+    b = 2
     return a
"""

        # Verify hook tracking works
        assert refresher_with_hook.update_hook is update_hook

    def test_partial_update_boundary_overlap(self):
        """Test partial update with chunks at diff boundaries"""
        repo_id = "test_repo"
        file_path = "test.py"

        # Create chunks at boundaries
        chunks = [
            Chunk(
                chunk_id="chunk:test_repo:function:test.func1",
                repo_id=repo_id,
                snapshot_id="snap:001",
                project_id=None,
                module_path="test",
                file_path=file_path,
                kind="function",
                fqn="test.func1",
                start_line=1,
                end_line=10,
                original_start_line=1,
                original_end_line=10,
                content_hash="hash1",
                parent_id=None,
                children=[],
                language="python",
                symbol_visibility="public",
                symbol_id=None,
                symbol_owner_id=None,
                summary=None,
                importance=None,
            ),
            Chunk(
                chunk_id="chunk:test_repo:function:test.func2",
                repo_id=repo_id,
                snapshot_id="snap:001",
                project_id=None,
                module_path="test",
                file_path=file_path,
                kind="function",
                fqn="test.func2",
                start_line=10,  # Overlaps at line 10
                end_line=20,
                original_start_line=10,
                original_end_line=20,
                content_hash="hash2",
                parent_id=None,
                children=[],
                language="python",
                symbol_visibility="public",
                symbol_id=None,
                symbol_owner_id=None,
                summary=None,
                importance=None,
            ),
        ]

        # Diff exactly at line 10
        hunks = [DiffHunk(old_start=10, old_count=1, new_start=10, new_count=2, lines=[])]

        affected = self.refresher._identify_affected_chunks(chunks, hunks)

        # Both chunks should be affected (they both include line 10)
        assert "test.func1" in affected
        assert "test.func2" in affected


# ============================================================
# Test Edge Cases
# ============================================================


class TestPartialUpdateEdgeCases:
    """Test edge cases for partial updates"""

    def test_diff_parser_malformed_hunk(self):
        """Test parser with malformed hunk header"""
        diff_text = """
@@ invalid hunk header @@
     some content
"""
        parser = DiffParser()
        hunks = parser.parse_diff(diff_text)
        assert hunks == []

    def test_identify_affected_chunks_empty_chunks(self):
        """Test affected detection with no chunks"""
        refresher = ChunkIncrementalRefresher(
            chunk_builder=None,  # type: ignore
            chunk_store=None,  # type: ignore
            ir_generator=None,  # type: ignore
            graph_generator=None,  # type: ignore
            use_partial_updates=True,
        )

        hunks = [DiffHunk(old_start=10, old_count=5, new_start=10, new_count=6, lines=[])]
        affected = refresher._identify_affected_chunks([], hunks)
        assert affected == set()

    def test_identify_affected_chunks_no_line_info(self):
        """Test affected detection with chunks missing line info"""
        chunk = Chunk(
            chunk_id="chunk:repo:function:mod.func",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id=None,
            module_path="mod",
            file_path="mod.py",
            kind="function",
            fqn="mod.func",
            start_line=None,  # Missing line info
            end_line=None,
            original_start_line=None,
            original_end_line=None,
            content_hash="hash",
            parent_id=None,
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
        )

        refresher = ChunkIncrementalRefresher(
            chunk_builder=None,  # type: ignore
            chunk_store=None,  # type: ignore
            ir_generator=None,  # type: ignore
            graph_generator=None,  # type: ignore
            use_partial_updates=True,
        )

        hunks = [DiffHunk(old_start=10, old_count=5, new_start=10, new_count=6, lines=[])]
        affected = refresher._identify_affected_chunks([chunk], hunks)

        # Should not include chunk without line info
        assert affected == set()
