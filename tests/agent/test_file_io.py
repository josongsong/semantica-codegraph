"""Tests for file I/O utilities."""

import os
import tempfile

import pytest

from src.agent.utils import (
    FileReadError,
    get_file_context,
    read_file,
    read_file_lines,
    read_multiple_files,
    safe_read_file,
)


class TestReadFile:
    """Tests for read_file function."""

    def test_read_existing_file(self):
        """Test reading an existing file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("line 1\nline 2\nline 3\n")
            temp_path = f.name

        try:
            content = read_file(temp_path)
            assert content == "line 1\nline 2\nline 3\n"
        finally:
            os.unlink(temp_path)

    def test_read_file_with_max_lines(self):
        """Test reading file with line limit."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("line 1\nline 2\nline 3\nline 4\nline 5\n")
            temp_path = f.name

        try:
            content = read_file(temp_path, max_lines=3)
            assert content == "line 1\nline 2\nline 3\n"
        finally:
            os.unlink(temp_path)

    def test_read_nonexistent_file(self):
        """Test error when file doesn't exist."""
        with pytest.raises(FileReadError, match="File not found"):
            read_file("/nonexistent/file.py")

    def test_read_directory(self):
        """Test error when path is a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(FileReadError, match="Not a file"):
                read_file(tmpdir)


class TestReadFileLines:
    """Tests for read_file_lines function."""

    def test_read_specific_lines(self):
        """Test reading specific line range."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("line 1\nline 2\nline 3\nline 4\nline 5\n")
            temp_path = f.name

        try:
            # Read lines 2-4
            content = read_file_lines(temp_path, start_line=2, end_line=4)
            assert "   2 | line 2\n" in content
            assert "   3 | line 3\n" in content
            assert "   4 | line 4\n" in content
            assert "line 1" not in content
            assert "line 5" not in content
        finally:
            os.unlink(temp_path)

    def test_read_lines_with_context(self):
        """Test reading lines with context."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("line 1\nline 2\nline 3\nline 4\nline 5\nline 6\nline 7\n")
            temp_path = f.name

        try:
            # Read line 4 with 2 lines of context
            content = read_file_lines(temp_path, start_line=4, end_line=4, context_lines=2)
            # Should include lines 2-6 (4 ± 2)
            assert "   2 | line 2\n" in content
            assert "   3 | line 3\n" in content
            assert "   4 | line 4\n" in content
            assert "   5 | line 5\n" in content
            assert "   6 | line 6\n" in content
            assert "line 1" not in content
            assert "line 7" not in content
        finally:
            os.unlink(temp_path)

    def test_read_lines_until_eof(self):
        """Test reading from line to EOF."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("line 1\nline 2\nline 3\nline 4\n")
            temp_path = f.name

        try:
            # Read from line 2 to end
            content = read_file_lines(temp_path, start_line=2, end_line=None)
            assert "   2 | line 2\n" in content
            assert "   3 | line 3\n" in content
            assert "   4 | line 4\n" in content
            assert "line 1" not in content
        finally:
            os.unlink(temp_path)


class TestReadMultipleFiles:
    """Tests for read_multiple_files function."""

    def test_read_multiple_files(self):
        """Test reading multiple files."""
        temp_files = []
        try:
            # Create test files
            for i in range(3):
                with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
                    f.write(f"# File {i+1}\ncode here\n")
                    temp_files.append(f.name)

            content = read_multiple_files(temp_files)

            # Check all files are included
            assert "# File 1" in content
            assert "# File 2" in content
            assert "# File 3" in content

            # Check separators exist
            assert "=" * 80 in content
            assert temp_files[0] in content
            assert temp_files[1] in content
            assert temp_files[2] in content

        finally:
            for path in temp_files:
                os.unlink(path)

    def test_read_multiple_files_with_limit(self):
        """Test reading multiple files with line limit."""
        temp_files = []
        try:
            # Create test file with many lines
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
                f.write("\n".join([f"line {i}" for i in range(100)]))
                temp_files.append(f.name)

            content = read_multiple_files(temp_files, max_lines_per_file=5)

            # Should only have first 5 lines
            assert "line 0" in content
            assert "line 4" in content
            assert "line 50" not in content

        finally:
            for path in temp_files:
                os.unlink(path)

    def test_read_multiple_files_with_errors(self):
        """Test that read_multiple_files continues on errors."""
        temp_files = []
        try:
            # Create one valid file
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
                f.write("# Valid file\n")
                temp_files.append(f.name)

            # Add a nonexistent file
            nonexistent = "/nonexistent/file.py"

            content = read_multiple_files([temp_files[0], nonexistent])

            # Should have valid file
            assert "# Valid file" in content

            # Should have error message for invalid file
            assert "ERROR" in content
            assert nonexistent in content

        finally:
            for path in temp_files:
                os.unlink(path)


class TestSafeReadFile:
    """Tests for safe_read_file function."""

    def test_safe_read_existing_file(self):
        """Test safe read of existing file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("content here")
            temp_path = f.name

        try:
            content = safe_read_file(temp_path)
            assert content == "content here"
        finally:
            os.unlink(temp_path)

    def test_safe_read_nonexistent_file(self):
        """Test safe read returns fallback on error."""
        content = safe_read_file("/nonexistent/file.py", fallback="# No file")
        assert content == "# No file"

    def test_safe_read_default_fallback(self):
        """Test safe read with default empty fallback."""
        content = safe_read_file("/nonexistent/file.py")
        assert content == ""


class TestGetFileContext:
    """Tests for get_file_context function."""

    def test_get_file_context(self):
        """Test getting context around a line."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("\n".join([f"line {i}" for i in range(1, 21)]))
            temp_path = f.name

        try:
            # Get context around line 10
            content = get_file_context(temp_path, line_number=10, context_lines=3)

            # Should have lines 7-13 (10 ± 3)
            assert "line 7" in content
            assert "line 10" in content
            assert "line 13" in content
            assert "line 5" not in content
            assert "line 15" not in content

        finally:
            os.unlink(temp_path)

    def test_get_file_context_near_start(self):
        """Test getting context near file start."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("\n".join([f"line {i}" for i in range(1, 11)]))
            temp_path = f.name

        try:
            # Get context around line 2 with 5 lines context
            # Should start at line 1 (max(1, 2-5))
            content = get_file_context(temp_path, line_number=2, context_lines=5)

            assert "   1 |" in content
            assert "   2 |" in content

        finally:
            os.unlink(temp_path)

    def test_get_file_context_error(self):
        """Test getting context from nonexistent file."""
        content = get_file_context("/nonexistent/file.py", line_number=10)
        assert "Error reading" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
