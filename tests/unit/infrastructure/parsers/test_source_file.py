"""
Source File Tests

Tests for source file representation and utilities.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from src.foundation.parsing.source_file import SourceFile


class TestSourceFileBasics:
    """Test basic SourceFile functionality."""

    def test_source_file_creation(self):
        """Test SourceFile can be instantiated."""
        source = SourceFile(
            file_path="test.py",
            content="print('hello')",
            language="python",
        )

        assert source is not None
        assert source.file_path == "test.py"
        assert source.content == "print('hello')"
        assert source.language == "python"
        assert source.encoding == "utf-8"

    def test_custom_encoding(self):
        """Test SourceFile with custom encoding."""
        source = SourceFile(
            file_path="test.py",
            content="print('hello')",
            language="python",
            encoding="latin-1",
        )

        assert source.encoding == "latin-1"


class TestFromContent:
    """Test from_content class method."""

    def test_from_content_basic(self):
        """Test creating SourceFile from content string."""
        source = SourceFile.from_content(
            file_path="src/main.py",
            content="def foo():\n    pass",
            language="python",
        )

        assert source.file_path == "src/main.py"
        assert source.content == "def foo():\n    pass"
        assert source.language == "python"
        assert source.encoding == "utf-8"

    def test_from_content_with_encoding(self):
        """Test from_content with custom encoding."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="content",
            language="python",
            encoding="ascii",
        )

        assert source.encoding == "ascii"


class TestFromFile:
    """Test from_file class method."""

    def test_from_file_basic(self):
        """Test loading SourceFile from disk."""
        with TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def foo():\n    pass")

            # Load with language specified
            source = SourceFile.from_file(
                file_path=test_file,
                repo_root=tmpdir,
                language="python",
            )

            assert source.file_path == "test.py"
            assert source.content == "def foo():\n    pass"
            assert source.language == "python"

    def test_from_file_with_subdirectory(self):
        """Test loading file from subdirectory."""
        with TemporaryDirectory() as tmpdir:
            # Create subdirectory structure
            subdir = Path(tmpdir) / "src" / "utils"
            subdir.mkdir(parents=True)
            test_file = subdir / "helper.py"
            test_file.write_text("x = 1")

            source = SourceFile.from_file(
                file_path=test_file,
                repo_root=tmpdir,
                language="python",
            )

            assert source.file_path == "src/utils/helper.py"
            assert source.content == "x = 1"

    def test_from_file_with_relative_path(self):
        """Test loading file with relative path."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("content")

            # Use relative path
            source = SourceFile.from_file(
                file_path="test.py",
                repo_root=tmpdir,
                language="python",
            )

            assert source.file_path == "test.py"
            assert source.content == "content"

    @patch("src.foundation.parsing.parser_registry.get_registry")
    def test_from_file_auto_detect_language(self, mock_get_registry):
        """Test auto-detecting language from file extension."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("content")

            # Mock registry to return python language
            mock_registry = MagicMock()
            mock_registry.detect_language.return_value = "python"
            mock_get_registry.return_value = mock_registry

            # Don't specify language
            source = SourceFile.from_file(
                file_path=test_file,
                repo_root=tmpdir,
                language=None,
            )

            assert source.language == "python"
            mock_registry.detect_language.assert_called_once()

    @patch("src.foundation.parsing.parser_registry.get_registry")
    def test_from_file_unsupported_language_raises(self, mock_get_registry):
        """Test loading unsupported file raises ValueError."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.unknown"
            test_file.write_text("content")

            # Mock registry to return None (unsupported)
            mock_registry = MagicMock()
            mock_registry.detect_language.return_value = None
            mock_get_registry.return_value = mock_registry

            with pytest.raises(ValueError, match="Could not detect language"):
                SourceFile.from_file(
                    file_path=test_file,
                    repo_root=tmpdir,
                    language=None,
                )


class TestGetLine:
    """Test get_line method."""

    def test_get_line_single_line(self):
        """Test getting line from single-line file."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="print('hello')",
            language="python",
        )

        assert source.get_line(1) == "print('hello')"

    def test_get_line_multi_line(self):
        """Test getting line from multi-line file."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="line 1\nline 2\nline 3",
            language="python",
        )

        assert source.get_line(1) == "line 1"
        assert source.get_line(2) == "line 2"
        assert source.get_line(3) == "line 3"

    def test_get_line_out_of_bounds(self):
        """Test getting line outside file bounds."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="line 1\nline 2",
            language="python",
        )

        assert source.get_line(0) == ""
        assert source.get_line(3) == ""
        assert source.get_line(100) == ""


class TestGetLines:
    """Test get_lines method."""

    def test_get_lines_range(self):
        """Test getting range of lines."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="line 1\nline 2\nline 3\nline 4",
            language="python",
        )

        lines = source.get_lines(2, 3)

        assert lines == ["line 2", "line 3"]

    def test_get_lines_single_line(self):
        """Test getting single line using get_lines."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="line 1\nline 2\nline 3",
            language="python",
        )

        lines = source.get_lines(2, 2)

        assert lines == ["line 2"]

    def test_get_lines_entire_file(self):
        """Test getting all lines."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="line 1\nline 2\nline 3",
            language="python",
        )

        lines = source.get_lines(1, 3)

        assert lines == ["line 1", "line 2", "line 3"]


class TestGetText:
    """Test get_text method with coordinates."""

    def test_get_text_single_line(self):
        """Test extracting text from single line."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="def foo():",
            language="python",
        )

        text = source.get_text(1, 4, 1, 7)

        assert text == "foo"

    def test_get_text_multi_line(self):
        """Test extracting text across multiple lines."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="def foo():\n    pass\n    return",
            language="python",
        )

        text = source.get_text(1, 4, 2, 8)

        # Should extract from "foo():\n    pass"
        assert "foo" in text
        assert "pass" in text

    def test_get_text_entire_line(self):
        """Test extracting entire line."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="def foo():\n    pass",
            language="python",
        )

        text = source.get_text(1, 0, 1, 10)

        assert text == "def foo():"

    def test_get_text_out_of_bounds(self):
        """Test extracting text with out-of-bounds coordinates."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="line 1\nline 2",
            language="python",
        )

        # Beyond file end
        text = source.get_text(3, 0, 3, 10)

        assert text == ""


class TestProperties:
    """Test SourceFile properties."""

    def test_line_count_single_line(self):
        """Test line count for single-line file."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="single line",
            language="python",
        )

        assert source.line_count == 1

    def test_line_count_multi_line(self):
        """Test line count for multi-line file."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="line 1\nline 2\nline 3",
            language="python",
        )

        assert source.line_count == 3

    def test_line_count_empty(self):
        """Test line count for empty file."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="",
            language="python",
        )

        assert source.line_count == 0  # splitlines() on empty string returns []

    def test_byte_size(self):
        """Test byte size calculation."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="hello",
            language="python",
        )

        assert source.byte_size == 5

    def test_byte_size_unicode(self):
        """Test byte size with unicode characters."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="hello 世界",
            language="python",
        )

        # "hello " = 6 bytes, "世界" = 6 bytes in UTF-8
        assert source.byte_size == 12


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_content(self):
        """Test SourceFile with empty content."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="",
            language="python",
        )

        assert source.content == ""
        assert source.line_count == 0
        assert source.get_line(1) == ""

    def test_windows_line_endings(self):
        """Test handling Windows line endings."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="line 1\r\nline 2\r\nline 3",
            language="python",
        )

        assert source.line_count == 3
        assert source.get_line(1) == "line 1"
        assert source.get_line(2) == "line 2"

    def test_mixed_line_endings(self):
        """Test handling mixed line endings."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="line 1\nline 2\r\nline 3",
            language="python",
        )

        assert source.line_count == 3
