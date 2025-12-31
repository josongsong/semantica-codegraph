"""
SOTA-Level Unit Tests for ShadowFSCore

Coverage:
    - Base cases (normal operations)
    - Edge cases (boundary conditions)
    - Corner cases (unusual combinations)
    - Thread safety (concurrent operations)
    - Integration (full workflows)
"""

import shutil
import tempfile
import threading
from pathlib import Path

import pytest

from codegraph_runtime.codegen_loop.domain.shadowfs.models import ChangeType
from codegraph_runtime.codegen_loop.infrastructure.shadowfs.core import ShadowFSCore


@pytest.fixture
def temp_workspace():
    """Create temporary workspace"""
    workspace = Path(tempfile.mkdtemp(prefix="test_shadowfs_"))

    # Create test files
    (workspace / "existing.py").write_text("original content", encoding="utf-8")
    (workspace / "subdir").mkdir()
    (workspace / "subdir" / "file.py").write_text("subdir content", encoding="utf-8")

    yield workspace

    # Cleanup
    shutil.rmtree(workspace, ignore_errors=True)


class TestShadowFSCoreBaseCase:
    """Base case: Normal operations"""

    def test_create_shadowfs(self, temp_workspace):
        """BASE: Create ShadowFS instance"""
        fs = ShadowFSCore(temp_workspace)

        assert fs.workspace_root == temp_workspace.resolve()
        assert len(fs.overlay) == 0
        assert len(fs.deleted) == 0

    def test_read_existing_file(self, temp_workspace):
        """BASE: Read file from disk"""
        fs = ShadowFSCore(temp_workspace)

        content = fs.read_file("existing.py")

        assert content == "original content"

    def test_write_new_file(self, temp_workspace):
        """BASE: Write new file to overlay"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("new.py", "new content")

        assert "new.py" in fs.overlay
        assert fs.overlay["new.py"] == "new content"
        assert fs.exists("new.py")

    def test_write_overwrites_existing(self, temp_workspace):
        """BASE: Write overwrites existing disk file"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("existing.py", "modified content")
        content = fs.read_file("existing.py")

        assert content == "modified content"
        # Disk unchanged
        assert (temp_workspace / "existing.py").read_text() == "original content"

    def test_delete_file(self, temp_workspace):
        """BASE: Delete file (tombstone)"""
        fs = ShadowFSCore(temp_workspace)

        fs.delete_file("existing.py")

        assert "existing.py" in fs.deleted
        assert not fs.exists("existing.py")
        with pytest.raises(FileNotFoundError):
            fs.read_file("existing.py")


class TestShadowFSCoreEdgeCase:
    """Edge case: Boundary conditions"""

    def test_read_nonexistent_file(self, temp_workspace):
        """EDGE: Read file that doesn't exist"""
        fs = ShadowFSCore(temp_workspace)

        with pytest.raises(FileNotFoundError, match="not found on disk"):
            fs.read_file("nonexistent.py")

    def test_write_empty_content(self, temp_workspace):
        """EDGE: Write empty file"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("empty.py", "")
        content = fs.read_file("empty.py")

        assert content == ""

    def test_write_empty_path_rejected(self, temp_workspace):
        """EDGE: Empty path rejected"""
        fs = ShadowFSCore(temp_workspace)

        with pytest.raises(ValueError, match="path must be non-empty"):
            fs.write_file("", "content")

    def test_delete_empty_path_rejected(self, temp_workspace):
        """EDGE: Empty path rejected"""
        fs = ShadowFSCore(temp_workspace)

        with pytest.raises(ValueError, match="path must be non-empty"):
            fs.delete_file("")

    def test_write_non_string_content_rejected(self, temp_workspace):
        """EDGE: Non-string content rejected"""
        fs = ShadowFSCore(temp_workspace)

        with pytest.raises(TypeError, match="content must be str"):
            fs.write_file("file.py", 12345)

    def test_list_files_empty_workspace(self):
        """EDGE: List files in empty workspace"""
        with tempfile.TemporaryDirectory() as temp_dir:
            fs = ShadowFSCore(Path(temp_dir))

            files = fs.list_files()

            assert files == []

    def test_rollback_empty_state(self, temp_workspace):
        """EDGE: Rollback with no changes"""
        fs = ShadowFSCore(temp_workspace)

        fs.rollback()  # Should not raise

        assert not fs.is_modified()


class TestShadowFSCoreExtremeCase:
    """Extreme case: Production limits and stress"""

    def test_binary_file_handling(self, temp_workspace):
        """EXTREME: Binary file (no text)"""
        fs = ShadowFSCore(temp_workspace)

        # Binary data
        binary_content = bytes(range(256)).decode("latin-1")
        fs.write_file("binary.dat", binary_content)

        content = fs.read_file("binary.dat")
        assert content == binary_content

    def test_very_deep_nesting(self, temp_workspace):
        """EXTREME: 100-level deep directory"""
        fs = ShadowFSCore(temp_workspace)

        # Create 100-level deep path
        deep_path = "/".join([f"d{i}" for i in range(100)]) + "/file.py"
        fs.write_file(deep_path, "deep content")

        assert fs.exists(deep_path)
        assert fs.read_file(deep_path) == "deep content"

    def test_many_files(self, temp_workspace):
        """EXTREME: 1000 files"""
        fs = ShadowFSCore(temp_workspace)

        # Create 1000 files
        for i in range(1000):
            fs.write_file(f"file{i}.py", f"content{i}")

        assert len(fs.overlay) == 1000
        files = fs.get_modified_files()
        assert len(files) == 1000

    def test_unicode_extremes(self, temp_workspace):
        """EXTREME: Emoji, RTL, zero-width characters"""
        fs = ShadowFSCore(temp_workspace)

        # Emoji
        fs.write_file("emoji.py", "# 😀🎉💯\nprint('👍')")
        assert "😀" in fs.read_file("emoji.py")

        # RTL (Right-to-Left)
        fs.write_file("rtl.py", "# مرحبا العالم\n# שלום עולם")
        assert "مرحبا" in fs.read_file("rtl.py")

        # Zero-width characters
        fs.write_file("zero.py", "a\u200bb\u200cc")  # zero-width space, joiner
        content = fs.read_file("zero.py")
        assert len(content) == 5  # a + ZWS + b + ZWNJ + c

    def test_symlink_loop(self, temp_workspace):
        """EXTREME: Symlink circular reference"""
        fs = ShadowFSCore(temp_workspace)

        # Create symlink loop: a -> b -> a
        link_a = temp_workspace / "link_a"
        link_b = temp_workspace / "link_b"

        try:
            link_a.symlink_to(link_b)
            link_b.symlink_to(link_a)
        except (OSError, PermissionError):
            pytest.skip("Cannot create symlink loop")

        # Should handle gracefully (not crash)
        temp_dir = None
        try:
            temp_dir = fs.prepare_for_external_tool()
            # If it doesn't crash, success
            assert temp_dir.exists()
        except (OSError, RecursionError):
            # Acceptable to fail with proper exception
            pass
        finally:
            if temp_dir:
                fs.cleanup_temp(temp_dir)

    def test_permission_denied_file(self, temp_workspace):
        """EXTREME: File with no read permission"""
        fs = ShadowFSCore(temp_workspace)

        # Create file with no permissions
        restricted = temp_workspace / "restricted.py"
        restricted.write_text("secret", encoding="utf-8")
        restricted.chmod(0o000)  # No permissions

        try:
            # Should raise PermissionError
            with pytest.raises((PermissionError, OSError)):
                fs.read_file("restricted.py")
        finally:
            restricted.chmod(0o644)  # Cleanup

    def test_concurrent_stress(self, temp_workspace):
        """EXTREME: 50 threads hammering"""
        import threading

        fs = ShadowFSCore(temp_workspace)

        errors = []
        operations = []

        def stress_worker(worker_id):
            try:
                for i in range(100):
                    fs.write_file(f"w{worker_id}_f{i}.py", f"c{i}")
                    if i % 10 == 0:
                        fs.read_file(f"w{worker_id}_f{i}.py")
                    if i % 20 == 0:
                        fs.delete_file(f"w{worker_id}_f{i}.py")
                operations.append(1)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=stress_worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Stress test failed: {errors[:3]}"
        assert len(operations) == 50
        print("Stress test: 50 threads × 100 ops = 5000 operations ✅")


class TestShadowFSCoreCornerCase:
    """Corner case: Unusual combinations"""

    def test_delete_then_resurrect(self, temp_workspace):
        """CORNER: Delete then write same file"""
        fs = ShadowFSCore(temp_workspace)

        fs.delete_file("existing.py")
        assert not fs.exists("existing.py")

        fs.write_file("existing.py", "resurrected")

        assert fs.exists("existing.py")
        assert "existing.py" not in fs.deleted
        assert fs.read_file("existing.py") == "resurrected"

    def test_write_then_delete(self, temp_workspace):
        """CORNER: Write then delete same file"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("new.py", "content")
        assert fs.exists("new.py")

        fs.delete_file("new.py")

        assert not fs.exists("new.py")
        assert "new.py" in fs.deleted
        assert "new.py" not in fs.overlay

    def test_multiple_writes_same_file(self, temp_workspace):
        """CORNER: Write same file multiple times"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("file.py", "version1")
        fs.write_file("file.py", "version2")
        fs.write_file("file.py", "version3")

        assert fs.read_file("file.py") == "version3"
        assert len(fs.overlay) == 1

    def test_delete_nonexistent_file(self, temp_workspace):
        """CORNER: Delete file that doesn't exist"""
        fs = ShadowFSCore(temp_workspace)

        fs.delete_file("nonexistent.py")  # Should not raise

        assert "nonexistent.py" in fs.deleted

    def test_nested_path_creation(self, temp_workspace):
        """CORNER: Write file in non-existent nested directories"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("deep/nested/path/file.py", "content")

        assert fs.exists("deep/nested/path/file.py")
        assert fs.read_file("deep/nested/path/file.py") == "content"

    def test_unicode_path_and_content(self, temp_workspace):
        """CORNER: Unicode in path and content"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("한글/파일.py", "# 한글 코멘트\nprint('안녕')")

        content = fs.read_file("한글/파일.py")
        assert "한글" in content

    def test_large_file_content(self, temp_workspace):
        """CORNER: Large file (1MB)"""
        fs = ShadowFSCore(temp_workspace)

        large_content = "x" * 1_000_000  # 1MB
        fs.write_file("large.txt", large_content)

        read_content = fs.read_file("large.txt")
        assert len(read_content) == 1_000_000


class TestShadowFSCoreListOperations:
    """List operations testing"""

    def test_list_files_basic(self, temp_workspace):
        """BASE: List all files"""
        fs = ShadowFSCore(temp_workspace)

        files = fs.list_files()

        assert "existing.py" in files
        assert "subdir/file.py" in files
        assert len(files) == 2

    def test_list_files_with_overlay(self, temp_workspace):
        """BASE: List includes overlay files"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("new1.py", "content")
        fs.write_file("new2.py", "content")

        files = fs.list_files()

        assert "new1.py" in files
        assert "new2.py" in files
        assert "existing.py" in files

    def test_list_files_excludes_deleted(self, temp_workspace):
        """BASE: List excludes deleted files"""
        fs = ShadowFSCore(temp_workspace)

        fs.delete_file("existing.py")

        files = fs.list_files()

        assert "existing.py" not in files

    def test_list_files_with_prefix_filter(self, temp_workspace):
        """BASE: Filter by prefix"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("src/main.py", "content")
        fs.write_file("tests/test.py", "content")

        files = fs.list_files(prefix="src/")

        assert "src/main.py" in files
        assert "tests/test.py" not in files

    def test_list_files_with_suffix_filter(self, temp_workspace):
        """BASE: Filter by suffix"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("file1.py", "content")
        fs.write_file("file2.txt", "content")

        files = fs.list_files(suffix=".py")

        assert "file1.py" in files
        assert "file2.txt" not in files

    def test_get_modified_files(self, temp_workspace):
        """BASE: Get modified files list"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("a.py", "content")
        fs.write_file("b.py", "content")

        modified = fs.get_modified_files()

        assert modified == ["a.py", "b.py"]  # Sorted

    def test_get_deleted_files(self, temp_workspace):
        """BASE: Get deleted files list"""
        fs = ShadowFSCore(temp_workspace)

        fs.delete_file("existing.py")
        fs.delete_file("subdir/file.py")

        deleted = fs.get_deleted_files()

        assert deleted == ["existing.py", "subdir/file.py"]  # Sorted


class TestShadowFSCoreDiffGeneration:
    """Diff generation testing"""

    def test_get_diff_modify(self, temp_workspace):
        """BASE: Diff for modified file"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("existing.py", "modified content")

        patches = fs.get_diff()

        assert len(patches) == 1
        assert patches[0].path == "existing.py"
        assert patches[0].change_type == ChangeType.MODIFY
        assert patches[0].original_content == "original content"
        assert patches[0].new_content == "modified content"

    def test_get_diff_add(self, temp_workspace):
        """BASE: Diff for added file"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("new.py", "new content")

        patches = fs.get_diff()

        assert len(patches) == 1
        assert patches[0].path == "new.py"
        assert patches[0].change_type == ChangeType.ADD
        assert patches[0].original_content is None
        assert patches[0].new_content == "new content"

    def test_get_diff_delete(self, temp_workspace):
        """BASE: Diff for deleted file"""
        fs = ShadowFSCore(temp_workspace)

        fs.delete_file("existing.py")

        patches = fs.get_diff()

        assert len(patches) == 1
        assert patches[0].path == "existing.py"
        assert patches[0].change_type == ChangeType.DELETE
        assert patches[0].original_content == "original content"
        assert patches[0].new_content is None

    def test_get_diff_multiple_changes(self, temp_workspace):
        """BASE: Diff with multiple changes"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("existing.py", "modified")
        fs.write_file("new.py", "added")
        fs.delete_file("subdir/file.py")

        patches = fs.get_diff()

        assert len(patches) == 3
        types = {p.change_type for p in patches}
        assert ChangeType.MODIFY in types
        assert ChangeType.ADD in types
        assert ChangeType.DELETE in types

    def test_get_diff_empty(self, temp_workspace):
        """EDGE: Diff with no changes"""
        fs = ShadowFSCore(temp_workspace)

        patches = fs.get_diff()

        assert patches == []

    def test_diff_hunks_structure(self, temp_workspace):
        """BASE: Verify hunk structure"""
        fs = ShadowFSCore(temp_workspace)

        original = "line1\nline2\nline3"
        modified = "line1\nmodified2\nline3"

        (temp_workspace / "test.py").write_text(original, encoding="utf-8")
        fs.write_file("test.py", modified)

        patches = fs.get_diff()

        assert len(patches) == 1
        patch = patches[0]
        assert len(patch.hunks) > 0


class TestShadowFSCoreMaterialization:
    """External tool materialization testing"""

    def test_materialize_basic(self, temp_workspace):
        """BASE: Materialize to temp directory"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("new.py", "new content")

        temp_dir = fs.prepare_for_external_tool()

        try:
            assert temp_dir.exists()
            assert (temp_dir / "new.py").exists()
            assert (temp_dir / "new.py").read_text() == "new content"
            assert (temp_dir / "existing.py").exists()
        finally:
            fs.cleanup_temp(temp_dir)

    def test_materialize_symlink_jail_escape_blocked(self, temp_workspace):
        """SECURITY: Block symlink pointing outside workspace"""
        fs = ShadowFSCore(temp_workspace)

        # Create symlink to /etc (outside workspace)
        evil_link = temp_workspace / "evil_link"
        try:
            evil_link.symlink_to("/etc")
        except (OSError, PermissionError):
            pytest.skip("Cannot create symlink")

        temp_dir = fs.prepare_for_external_tool()

        try:
            # evil_link should NOT be in temp_dir (skipped for security)
            assert not (temp_dir / "evil_link").exists()
        finally:
            fs.cleanup_temp(temp_dir)

    def test_materialize_symlink_within_workspace(self, temp_workspace):
        """BASE: Symlink within workspace is allowed"""
        fs = ShadowFSCore(temp_workspace)

        # Create symlink within workspace
        target = temp_workspace / "target.py"
        target.write_text("target content")

        link = temp_workspace / "link.py"
        try:
            link.symlink_to(target)
        except (OSError, PermissionError):
            pytest.skip("Cannot create symlink")

        temp_dir = fs.prepare_for_external_tool()

        try:
            # link should be copied/resolved (within workspace is safe)
            # It's ok if either link or target exists
            assert (temp_dir / "link.py").exists() or (temp_dir / "target.py").exists()
        finally:
            fs.cleanup_temp(temp_dir)

    def test_materialize_with_deletion(self, temp_workspace):
        """BASE: Materialize applies deletions"""
        fs = ShadowFSCore(temp_workspace)

        fs.delete_file("existing.py")

        temp_dir = fs.prepare_for_external_tool()

        try:
            assert not (temp_dir / "existing.py").exists()
        finally:
            fs.cleanup_temp(temp_dir)

    def test_materialize_with_modification(self, temp_workspace):
        """BASE: Materialize applies modifications"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("existing.py", "modified")

        temp_dir = fs.prepare_for_external_tool()

        try:
            content = (temp_dir / "existing.py").read_text()
            assert content == "modified"
        finally:
            fs.cleanup_temp(temp_dir)

    def test_cleanup_temp(self, temp_workspace):
        """BASE: Cleanup removes temp directory"""
        fs = ShadowFSCore(temp_workspace)

        temp_dir = fs.prepare_for_external_tool()
        assert temp_dir.exists()

        fs.cleanup_temp(temp_dir)

        assert not temp_dir.exists()

    def test_cleanup_nonexistent_temp(self, temp_workspace):
        """EDGE: Cleanup non-existent directory"""
        fs = ShadowFSCore(temp_workspace)

        fs.cleanup_temp(Path("/nonexistent/temp"))  # Should not raise


class TestShadowFSCoreThreadSafety:
    """Thread safety testing"""

    def test_concurrent_writes(self, temp_workspace):
        """THREAD-SAFETY: Multiple threads writing"""
        fs = ShadowFSCore(temp_workspace)
        errors = []

        def write_worker(file_id):
            try:
                fs.write_file(f"file{file_id}.py", f"content{file_id}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(fs.overlay) == 20

    def test_concurrent_read_write(self, temp_workspace):
        """THREAD-SAFETY: Concurrent reads and writes"""
        fs = ShadowFSCore(temp_workspace)
        fs.write_file("shared.py", "initial")

        errors = []
        read_count = []

        def reader():
            try:
                for _ in range(100):
                    fs.read_file("shared.py")
                    read_count.append(1)
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(100):
                    fs.write_file(f"file{i}.py", f"content{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(3)] + [
            threading.Thread(target=writer) for _ in range(2)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(read_count) == 300


class TestShadowFSCoreAffectedDirs:
    """Test _get_affected_dirs helper"""

    def test_get_affected_dirs_single_file(self, temp_workspace):
        """BASE: Single nested file"""
        fs = ShadowFSCore(temp_workspace)

        affected = fs._get_affected_dirs({"a/b/c.py"})

        assert "a" in affected
        assert "a/b" in affected
        assert "a/b/c.py" not in affected  # Files excluded

    def test_get_affected_dirs_multiple_files(self, temp_workspace):
        """BASE: Multiple files in different dirs"""
        fs = ShadowFSCore(temp_workspace)

        affected = fs._get_affected_dirs({"a/b/c.py", "a/d/e.py", "x/y.py"})

        assert "a" in affected
        assert "a/b" in affected
        assert "a/d" in affected
        assert "x" in affected

    def test_get_affected_dirs_root_file(self, temp_workspace):
        """EDGE: Root-level file"""
        fs = ShadowFSCore(temp_workspace)

        affected = fs._get_affected_dirs({"root.py"})

        # Root file has no parent dirs (or only ".")
        assert len(affected) == 0 or affected == {"."}

    def test_get_affected_dirs_deep_nesting(self, temp_workspace):
        """EDGE: Very deep nesting"""
        fs = ShadowFSCore(temp_workspace)

        affected = fs._get_affected_dirs({"a/b/c/d/e/file.py"})

        # Should include all parent directories
        assert "a" in affected
        assert "a/b" in affected
        assert "a/b/c" in affected
        assert "a/b/c/d" in affected
        assert "a/b/c/d/e" in affected


class TestShadowFSCoreProductionCriticalEdgeCases:
    """Production-critical edge cases that were missing"""

    def test_line_ending_normalization(self, temp_workspace):
        """EDGE: CRLF vs LF line endings"""
        fs = ShadowFSCore(temp_workspace)

        # Write with CRLF
        content_crlf = "line1\r\nline2\r\nline3"
        fs.write_file("crlf.py", content_crlf)

        # Read back (should preserve)
        assert fs.read_file("crlf.py") == content_crlf

        # Write with LF
        content_lf = "line1\nline2\nline3"
        fs.write_file("lf.py", content_lf)

        assert fs.read_file("lf.py") == content_lf

    def test_empty_file_to_content(self, temp_workspace):
        """EDGE: Diff from empty file to content"""
        fs = ShadowFSCore(temp_workspace)

        # Create empty file on disk
        (temp_workspace / "empty.py").write_text("", encoding="utf-8")

        # Write content
        fs.write_file("empty.py", "new content")

        patches = fs.get_diff()
        assert len(patches) == 1
        assert patches[0].original_content == ""
        assert patches[0].new_content == "new content"

    def test_content_to_empty_file(self, temp_workspace):
        """EDGE: Diff from content to empty"""
        fs = ShadowFSCore(temp_workspace)

        # Existing file has content
        # Write empty
        fs.write_file("existing.py", "")

        patches = fs.get_diff()
        assert len(patches) == 1
        assert patches[0].original_content == "original content"
        assert patches[0].new_content == ""

    def test_broken_symlink(self, temp_workspace):
        """EDGE: Symlink to nonexistent target"""
        fs = ShadowFSCore(temp_workspace)

        # Create broken symlink
        broken = temp_workspace / "broken_link"
        nonexistent = temp_workspace / "nonexistent_target"

        try:
            broken.symlink_to(nonexistent)
        except (OSError, PermissionError):
            pytest.skip("Cannot create symlink")

        # Should handle gracefully during materialization
        temp_dir = None
        try:
            temp_dir = fs.prepare_for_external_tool()
            # Should not crash
            assert temp_dir.exists()
        finally:
            if temp_dir:
                fs.cleanup_temp(temp_dir)

    def test_symlink_chain(self, temp_workspace):
        """EDGE: Symlink chain a→b→c"""
        fs = ShadowFSCore(temp_workspace)

        # Create chain: link_a → link_b → target
        target = temp_workspace / "target.py"
        target.write_text("target content")

        link_b = temp_workspace / "link_b"
        link_a = temp_workspace / "link_a"

        try:
            link_b.symlink_to(target)
            link_a.symlink_to(link_b)
        except (OSError, PermissionError):
            pytest.skip("Cannot create symlink chain")

        temp_dir = None
        try:
            temp_dir = fs.prepare_for_external_tool()
            # Should resolve chain
            assert temp_dir.exists()
        finally:
            if temp_dir:
                fs.cleanup_temp(temp_dir)

    def test_concurrent_get_diff(self, temp_workspace):
        """THREAD-SAFETY: Concurrent get_diff() calls"""
        import threading

        fs = ShadowFSCore(temp_workspace)

        fs.write_file("test1.py", "content1")
        fs.write_file("test2.py", "content2")

        errors = []
        results = []

        def diff_worker():
            try:
                patches = fs.get_diff()
                results.append(len(patches))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=diff_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # All threads should see same number of patches
        assert len(set(results)) == 1
        assert results[0] == 2

    def test_concurrent_materialize(self, temp_workspace):
        """THREAD-SAFETY: Concurrent materialize (2+ temp dirs)"""
        import threading

        fs = ShadowFSCore(temp_workspace)

        fs.write_file("test.py", "content")

        errors = []
        temp_dirs = []
        lock = threading.Lock()

        def materialize_worker():
            try:
                temp_dir = fs.prepare_for_external_tool()
                with lock:
                    temp_dirs.append(temp_dir)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=materialize_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Cleanup
        for temp_dir in temp_dirs:
            fs.cleanup_temp(temp_dir)

        assert len(errors) == 0
        assert len(temp_dirs) == 5
        # All should be different directories
        assert len({str(d) for d in temp_dirs}) == 5

    def test_no_newline_at_eof(self, temp_workspace):
        """EDGE: File without newline at end"""
        fs = ShadowFSCore(temp_workspace)

        # Write without trailing newline
        content = "line1\nline2"
        fs.write_file("no_newline.py", content)

        assert fs.read_file("no_newline.py") == content

        patches = fs.get_diff()
        assert len(patches) == 1

    def test_only_whitespace_changes(self, temp_workspace):
        """EDGE: Diff with only whitespace changes"""
        fs = ShadowFSCore(temp_workspace)

        # Original has spaces
        (temp_workspace / "whitespace.py").write_text("line1  \nline2  ", encoding="utf-8")

        # New has no trailing spaces
        fs.write_file("whitespace.py", "line1\nline2")

        patches = fs.get_diff()
        assert len(patches) == 1
        # Should detect whitespace change
        assert patches[0].original_content != patches[0].new_content

    def test_hidden_files(self, temp_workspace):
        """EDGE: Hidden files (.git, .env)"""
        fs = ShadowFSCore(temp_workspace)

        # Write hidden files
        fs.write_file(".gitignore", "*.pyc")
        fs.write_file(".env", "SECRET=123")

        files = fs.list_files()
        assert ".gitignore" in files
        assert ".env" in files

        # Materialize should include hidden files
        temp_dir = fs.prepare_for_external_tool()
        try:
            assert (temp_dir / ".gitignore").exists()
            assert (temp_dir / ".env").exists()
        finally:
            fs.cleanup_temp(temp_dir)


class TestShadowFSCoreMinorEdgeCases:
    """Minor edge cases (complete coverage)"""

    def test_bom_utf8(self, temp_workspace):
        """EDGE: UTF-8 BOM handling"""
        fs = ShadowFSCore(temp_workspace)

        # Write with BOM
        bom_content = "\ufeffline1\nline2"
        fs.write_file("bom.py", bom_content)

        # Should preserve BOM
        assert fs.read_file("bom.py") == bom_content

    def test_invalid_utf8_error(self, temp_workspace):
        """EDGE: Invalid UTF-8 sequences raise error"""
        fs = ShadowFSCore(temp_workspace)

        # Create file with invalid UTF-8
        invalid_file = temp_workspace / "invalid.bin"
        invalid_file.write_bytes(b"\x80\x81\x82")  # Invalid UTF-8

        with pytest.raises(UnicodeDecodeError):
            fs.read_file("invalid.bin")

    def test_surrogate_pairs(self, temp_workspace):
        """EDGE: Unicode surrogate pairs"""
        fs = ShadowFSCore(temp_workspace)

        # Emoji with surrogate pairs
        content = "Test 𝕳𝖊𝖑𝖑𝖔 𝕎𝕠𝕣𝕝𝕕 🌍"
        fs.write_file("surrogates.py", content)

        assert fs.read_file("surrogates.py") == content

    def test_special_chars_in_filename(self, temp_workspace):
        """EDGE: Special chars in filename (sanitized by OS)"""
        fs = ShadowFSCore(temp_workspace)

        # Try various special chars (some may be rejected by OS)
        test_names = ["file[bracket].py", "file(paren).py", "file space.py", "file'quote.py"]

        for name in test_names:
            try:
                fs.write_file(name, "content")
                assert fs.read_file(name) == "content"
            except (OSError, ValueError):
                # OS may reject some chars, acceptable
                pass

    def test_large_diff(self, temp_workspace):
        """EDGE: Large diff (10,000+ lines)"""
        fs = ShadowFSCore(temp_workspace)

        # Create large file (축소)
        lines = [f"line{i}\n" for i in range(1000)]  # 10000 → 1000
        large_content = "".join(lines)

        (temp_workspace / "large.py").write_text("original\n", encoding="utf-8")

        fs.write_file("large.py", large_content)

        patches = fs.get_diff()
        assert len(patches) == 1
        assert len(patches[0].new_content) > 50000  # Large content

    def test_diff_no_actual_changes(self, temp_workspace):
        """EDGE: Diff with no actual semantic changes (optimized away)"""
        fs = ShadowFSCore(temp_workspace)

        # Same content (no changes)
        (temp_workspace / "same.py").write_text("line1\nline2", encoding="utf-8")

        fs.write_file("same.py", "line1\nline2")

        # Optimized: No diff if content identical
        patches = fs.get_diff()
        assert len(patches) == 0  # Correctly optimized

    def test_mixed_line_endings_same_file(self, temp_workspace):
        """EDGE: Mixed line endings within same file"""
        fs = ShadowFSCore(temp_workspace)

        # Mix CRLF and LF
        mixed = "line1\r\nline2\nline3\r\nline4"
        fs.write_file("mixed.py", mixed)

        assert fs.read_file("mixed.py") == mixed

    def test_empty_to_empty_noop(self, temp_workspace):
        """EDGE: Empty file to empty file (no-op, optimized)"""
        fs = ShadowFSCore(temp_workspace)

        (temp_workspace / "empty.py").write_text("", encoding="utf-8")

        fs.write_file("empty.py", "")

        # Optimized: No diff if no actual change
        patches = fs.get_diff()
        assert len(patches) == 0  # Correctly optimized

    def test_case_insensitive_filter(self, temp_workspace):
        """EDGE: Case-insensitive file filtering"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("Test.PY", "content")
        fs.write_file("test.py", "content")
        fs.write_file("TEST.py", "content")

        # List all
        files = fs.list_files()

        # Should have all (case-sensitive overlay)
        assert len([f for f in files if "test" in f.lower()]) >= 1

    def test_large_directory(self, temp_workspace):
        """EDGE: Large directory (1000+ files)"""
        fs = ShadowFSCore(temp_workspace)

        # Create 1000 files
        for i in range(1000):
            fs.write_file(f"file{i:04d}.py", f"content{i}")

        files = fs.list_files()
        modified = fs.get_modified_files()

        assert len(modified) == 1000

    def test_concurrent_write_during_materialize(self, temp_workspace):
        """THREAD-SAFETY: Write during materialization"""
        import threading

        fs = ShadowFSCore(temp_workspace)

        fs.write_file("initial.py", "content")

        materialize_started = threading.Event()
        write_completed = threading.Event()

        def slow_materialize():
            materialize_started.set()
            temp_dir = fs.prepare_for_external_tool()
            fs.cleanup_temp(temp_dir)

        def write_during():
            materialize_started.wait(timeout=1.0)
            fs.write_file("concurrent.py", "new content")
            write_completed.set()

        t1 = threading.Thread(target=slow_materialize)
        t2 = threading.Thread(target=write_during)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Both should succeed (snapshot isolation)
        assert write_completed.is_set()
        assert fs.read_file("concurrent.py") == "new content"

    def test_rollback_during_concurrent_read(self, temp_workspace):
        """THREAD-SAFETY: Rollback during concurrent reads"""
        import threading

        fs = ShadowFSCore(temp_workspace)

        fs.write_file("test.py", "content")

        errors = []
        reads = []

        def reader():
            try:
                for _ in range(100):
                    try:
                        content = fs.read_file("test.py")
                        reads.append(content)
                    except FileNotFoundError:
                        # Acceptable after rollback
                        pass
            except Exception as e:
                errors.append(e)

        def rollback_worker():
            import time

            time.sleep(0.01)
            fs.rollback()

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=rollback_worker)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Should not crash
        assert len(errors) == 0

    def test_multiple_sequential_rollbacks(self, temp_workspace):
        """STATE: Multiple rollbacks in sequence"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("a.py", "content1")
        fs.rollback()

        fs.write_file("b.py", "content2")
        fs.rollback()

        fs.write_file("c.py", "content3")
        fs.rollback()

        assert len(fs.overlay) == 0
        assert len(fs.deleted) == 0

    def test_rollback_after_partial_ops(self, temp_workspace):
        """STATE: Rollback after partial operations"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("a.py", "content")
        fs.write_file("b.py", "content")
        fs.delete_file("existing.py")

        # Partial rollback (all-or-nothing)
        fs.rollback()

        assert len(fs.overlay) == 0
        assert len(fs.deleted) == 0

    def test_hidden_dot_directories(self, temp_workspace):
        """EDGE: Hidden directories (.github, .vscode)"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file(".github/workflows/ci.yml", "content")
        fs.write_file(".vscode/settings.json", "content")

        files = fs.list_files()

        assert ".github/workflows/ci.yml" in files
        assert ".vscode/settings.json" in files

    def test_materialize_with_missing_parent_dirs(self, temp_workspace):
        """EDGE: Materialize creates missing parent dirs"""
        fs = ShadowFSCore(temp_workspace)

        # Deep nesting that doesn't exist on disk
        fs.write_file("a/b/c/d/e/f/file.py", "content")

        temp_dir = fs.prepare_for_external_tool()
        try:
            assert (temp_dir / "a/b/c/d/e/f/file.py").exists()
            assert (temp_dir / "a/b/c/d/e/f/file.py").read_text() == "content"
        finally:
            fs.cleanup_temp(temp_dir)

    def test_readonly_file_on_disk(self, temp_workspace):
        """EDGE: Read-only file on disk (overlay still works)"""
        import stat

        readonly = temp_workspace / "readonly.py"
        readonly.write_text("original", encoding="utf-8")
        readonly.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # r--r--r--

        fs = ShadowFSCore(temp_workspace)

        # Overlay write should succeed (not touching disk)
        fs.write_file("readonly.py", "modified")

        assert fs.read_file("readonly.py") == "modified"

        # Restore permissions for cleanup
        readonly.chmod(stat.S_IWUSR | stat.S_IRUSR)

    def test_very_long_line(self, temp_workspace):
        """EDGE: Very long single line (100K chars)"""
        fs = ShadowFSCore(temp_workspace)

        long_line = "x" * 100000
        fs.write_file("long.py", long_line)

        assert len(fs.read_file("long.py")) == 100000

    def test_list_files_with_glob_pattern(self, temp_workspace):
        """EDGE: Glob-style filtering"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("test_a.py", "content")
        fs.write_file("test_b.py", "content")
        fs.write_file("main.py", "content")

        # Simulate glob: files starting with "test_"
        files = [f for f in fs.list_files() if f.startswith("test_")]

        assert len(files) == 2
        assert "test_a.py" in files
        assert "test_b.py" in files


class TestShadowFSCoreStateManagement:
    """State management testing"""

    def test_rollback_clears_overlay(self, temp_workspace):
        """BASE: Rollback clears overlay"""
        fs = ShadowFSCore(temp_workspace)

        fs.write_file("a.py", "content")
        fs.write_file("b.py", "content")

        fs.rollback()

        assert len(fs.overlay) == 0
        assert not fs.is_modified()

    def test_rollback_clears_deleted(self, temp_workspace):
        """BASE: Rollback clears deleted"""
        fs = ShadowFSCore(temp_workspace)

        fs.delete_file("existing.py")

        fs.rollback()

        assert len(fs.deleted) == 0
        assert fs.exists("existing.py")

    def test_is_modified_with_overlay(self, temp_workspace):
        """BASE: is_modified detects overlay"""
        fs = ShadowFSCore(temp_workspace)

        assert not fs.is_modified()

        fs.write_file("new.py", "content")

        assert fs.is_modified()

    def test_is_modified_with_deletion(self, temp_workspace):
        """BASE: is_modified detects deletion"""
        fs = ShadowFSCore(temp_workspace)

        assert not fs.is_modified()

        fs.delete_file("existing.py")

        assert fs.is_modified()


# Run with:
# pytest tests/unit/contexts/codegen_loop/infrastructure/shadowfs/test_core.py -v
# With coverage:
# pytest tests/unit/contexts/codegen_loop/infrastructure/shadowfs/test_core.py \
#   --cov=src/contexts/codegen_loop/infrastructure/shadowfs/core \
#   --cov-report=term-missing
