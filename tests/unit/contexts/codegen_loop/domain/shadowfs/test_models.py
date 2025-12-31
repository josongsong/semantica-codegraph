"""
SOTA-Level Unit Tests for ShadowFS Domain Models

Coverage:
    - Base cases (happy path)
    - Edge cases (boundary values)
    - Corner cases (unusual combinations)
    - Extreme cases (limits, overflow)
    - Security cases (injection, traversal)
"""

import pytest

from codegraph_runtime.codegen_loop.domain.shadowfs.models import ChangeType, FilePatch, Hunk


class TestHunkBaseCase:
    """Base case: Normal, expected usage"""

    def test_create_valid_hunk(self):
        """BASE: Create hunk with valid parameters"""
        hunk = Hunk(start_line=10, end_line=11, original_lines=("line1", "line2"), new_lines=("new1", "new2", "new3"))

        assert hunk.start_line == 10
        assert hunk.end_line == 11
        assert len(hunk.original_lines) == 2
        assert len(hunk.new_lines) == 3

    def test_hunk_addition(self):
        """BASE: Hunk that adds lines (no original lines)"""
        hunk = Hunk(
            start_line=1,
            end_line=1,  # FIXED: No original lines means end_line = start_line
            original_lines=(),
            new_lines=("new line",),
        )

        assert hunk.is_addition
        assert not hunk.is_deletion
        assert not hunk.is_modification
        assert hunk.lines_added == 1

    def test_hunk_deletion(self):
        """BASE: Hunk that deletes lines"""
        hunk = Hunk(start_line=1, end_line=1, original_lines=("old line",), new_lines=())

        assert hunk.is_deletion
        assert not hunk.is_addition
        assert not hunk.is_modification
        assert hunk.lines_removed == 1


class TestHunkEdgeCase:
    """Edge case: Boundary values"""

    def test_start_line_minimum(self):
        """EDGE: start_line = 1 (minimum valid)"""
        hunk = Hunk(start_line=1, end_line=1, original_lines=("line",), new_lines=())
        assert hunk.start_line == 1

    def test_start_line_zero_rejected(self):
        """EDGE: start_line = 0 (invalid)"""
        with pytest.raises(ValueError, match="start_line must be > 0"):
            Hunk(start_line=0, end_line=1)

    def test_start_line_negative_rejected(self):
        """EDGE: start_line < 0 (invalid)"""
        with pytest.raises(ValueError, match="start_line must be > 0"):
            Hunk(start_line=-1, end_line=1)

    def test_end_line_equals_start(self):
        """EDGE: end_line = start_line (single line)"""
        hunk = Hunk(start_line=5, end_line=5, original_lines=("line",), new_lines=())
        assert hunk.end_line == hunk.start_line

    def test_end_line_less_than_start_rejected(self):
        """EDGE: end_line < start_line (invalid)"""
        with pytest.raises(ValueError, match="end_line.*must be >= start_line"):
            Hunk(start_line=10, end_line=5)


class TestHunkCornerCase:
    """Corner case: Unusual combinations"""

    def test_empty_hunk_rejected(self):
        """CORNER: Both original_lines and new_lines empty"""
        with pytest.raises(ValueError, match="At least one"):
            Hunk(start_line=1, end_line=1)

    def test_line_range_inconsistency_detected(self):
        """CORNER: end_line doesn't match original_lines length"""
        with pytest.raises(ValueError, match="end_line.*inconsistent"):
            Hunk(
                start_line=10,
                end_line=15,
                original_lines=("line1", "line2"),
                new_lines=(),  # Should be 11 (10 + 2 - 1)
            )

    def test_large_line_numbers(self):
        """CORNER: Very large line numbers"""
        hunk = Hunk(start_line=999999, end_line=999999, original_lines=("line",), new_lines=())
        assert hunk.start_line == 999999

    def test_many_lines(self):
        """CORNER: Many lines in hunk"""
        lines = tuple(f"line{i}" for i in range(1000))
        hunk = Hunk(start_line=1, end_line=1000, original_lines=lines, new_lines=())
        assert len(hunk.original_lines) == 1000


class TestFilePatchBaseCase:
    """Base case: Normal file operations"""

    def test_add_patch(self):
        """BASE: Add new file"""
        patch = FilePatch(
            path="src/new.py", change_type=ChangeType.ADD, original_content=None, new_content="print('hello')", hunks=()
        )

        assert patch.change_type == ChangeType.ADD
        assert patch.original_content is None
        assert patch.new_content is not None

    def test_modify_patch(self):
        """BASE: Modify existing file"""
        patch = FilePatch(
            path="src/old.py", change_type=ChangeType.MODIFY, original_content="old", new_content="new", hunks=()
        )

        assert patch.change_type == ChangeType.MODIFY
        assert patch.original_content == "old"
        assert patch.new_content == "new"

    def test_delete_patch(self):
        """BASE: Delete file"""
        patch = FilePatch(
            path="src/deleted.py", change_type=ChangeType.DELETE, original_content="deleted", new_content=None, hunks=()
        )

        assert patch.change_type == ChangeType.DELETE
        assert patch.original_content is not None
        assert patch.new_content is None


class TestFilePatchSecurityCase:
    """Security case: Injection and traversal attacks"""

    def test_null_byte_injection_blocked(self):
        """SECURITY: Null byte in path"""
        with pytest.raises(ValueError, match="null byte"):
            FilePatch(path="src/main.py\x00.txt", change_type=ChangeType.ADD, new_content="code")

    def test_newline_injection_blocked(self):
        """SECURITY: Newline in path"""
        with pytest.raises(ValueError, match="newline"):
            FilePatch(path="src/main.py\n../etc/passwd", change_type=ChangeType.ADD, new_content="code")

    def test_carriage_return_blocked(self):
        """SECURITY: Carriage return in path"""
        with pytest.raises(ValueError, match="newline"):
            FilePatch(path="src/main.py\r", change_type=ChangeType.ADD, new_content="code")

    def test_path_traversal_blocked(self):
        """SECURITY: Path traversal with .."""
        with pytest.raises(ValueError, match="path traversal"):
            FilePatch(path="../etc/passwd", change_type=ChangeType.ADD, new_content="code")

    def test_path_traversal_hidden_blocked(self):
        """SECURITY: Path traversal hidden in middle"""
        with pytest.raises(ValueError, match="path traversal"):
            FilePatch(path="src/../../../etc/passwd", change_type=ChangeType.ADD, new_content="code")

    def test_absolute_path_unix_blocked(self):
        """SECURITY: Absolute path (Unix)"""
        with pytest.raises(ValueError, match="must be relative"):
            FilePatch(path="/etc/passwd", change_type=ChangeType.ADD, new_content="code")

    def test_absolute_path_windows_blocked(self):
        """SECURITY: Absolute path (Windows)"""
        with pytest.raises(ValueError, match="must be relative"):
            FilePatch(path="C:\\Windows\\System32", change_type=ChangeType.ADD, new_content="code")


class TestFilePatchEdgeCase:
    """Edge case: Boundary conditions"""

    def test_empty_path_rejected(self):
        """EDGE: Empty path"""
        with pytest.raises(ValueError, match="path must be non-empty"):
            FilePatch(path="", change_type=ChangeType.ADD, new_content="code")

    def test_whitespace_in_path_rejected(self):
        """EDGE: Leading/trailing whitespace"""
        with pytest.raises(ValueError, match="whitespace"):
            FilePatch(path=" src/main.py ", change_type=ChangeType.ADD, new_content="code")

    def test_empty_new_content_allowed(self):
        """EDGE: Empty file content (valid for empty file)"""
        patch = FilePatch(
            path="src/empty.py",
            change_type=ChangeType.ADD,
            new_content="",
            hunks=(),  # Empty but not None
        )
        assert patch.new_content == ""

    def test_very_long_path(self):
        """EDGE: Very long path (4096 chars)"""
        long_path = "a/" * 2000 + "file.py"  # > 4000 chars
        patch = FilePatch(path=long_path, change_type=ChangeType.ADD, new_content="code", hunks=())
        assert len(patch.path) > 4000


class TestFilePatchCornerCase:
    """Corner case: Unusual combinations"""

    def test_add_without_new_content_rejected(self):
        """CORNER: ADD with new_content=None"""
        with pytest.raises(ValueError, match="ADD patch must have new_content"):
            FilePatch(path="src/new.py", change_type=ChangeType.ADD, new_content=None)

    def test_add_with_original_content_rejected(self):
        """CORNER: ADD with original_content set"""
        with pytest.raises(ValueError, match="ADD patch must have original_content=None"):
            FilePatch(path="src/new.py", change_type=ChangeType.ADD, original_content="something", new_content="code")

    def test_delete_without_original_rejected(self):
        """CORNER: DELETE with original_content=None"""
        with pytest.raises(ValueError, match="DELETE patch must have original_content"):
            FilePatch(path="src/deleted.py", change_type=ChangeType.DELETE, original_content=None)

    def test_delete_with_new_content_rejected(self):
        """CORNER: DELETE with new_content set"""
        with pytest.raises(ValueError, match="DELETE patch must have new_content=None"):
            FilePatch(
                path="src/deleted.py", change_type=ChangeType.DELETE, original_content="old", new_content="something"
            )

    def test_modify_identical_content_rejected(self):
        """CORNER: MODIFY with identical content"""
        with pytest.raises(ValueError, match="identical content"):
            FilePatch(path="src/file.py", change_type=ChangeType.MODIFY, original_content="same", new_content="same")

    def test_unicode_path(self):
        """CORNER: Unicode characters in path"""
        patch = FilePatch(path="src/한글파일.py", change_type=ChangeType.ADD, new_content="# 한글 코드")
        assert "한글" in patch.path

    def test_special_chars_in_path(self):
        """CORNER: Special characters (allowed)"""
        patch = FilePatch(path="src/file-name_v2.0.py", change_type=ChangeType.ADD, new_content="code")
        assert patch.path == "src/file-name_v2.0.py"


class TestFilePatchDiffGeneration:
    """Diff generation functionality"""

    def test_unified_diff_format(self):
        """BASE: Generate unified diff"""
        hunk = Hunk(start_line=1, end_line=2, original_lines=("old line 1", "old line 2"), new_lines=("new line 1",))

        patch = FilePatch(
            path="src/file.py", change_type=ChangeType.MODIFY, original_content="old", new_content="new", hunks=(hunk,)
        )

        diff = patch.to_unified_diff()

        assert "--- a/src/file.py" in diff
        assert "+++ b/src/file.py" in diff
        assert "@@" in diff
        assert "-old line 1" in diff
        assert "+new line 1" in diff


# Run with: pytest -v tests/unit/contexts/codegen_loop/domain/shadowfs/test_models.py
