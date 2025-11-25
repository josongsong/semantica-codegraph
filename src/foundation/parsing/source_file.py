"""
Source File representation
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SourceFile:
    """
    Represents a source code file.

    Attributes:
        file_path: Relative path from repository root
        content: File content as string
        language: Programming language
        encoding: File encoding (default: utf-8)
    """

    file_path: str
    content: str
    language: str
    encoding: str = "utf-8"

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        repo_root: str | Path,
        language: str | None = None,
        encoding: str = "utf-8",
    ) -> "SourceFile":
        """
        Load source file from disk.

        Args:
            file_path: Absolute or relative path to file
            repo_root: Repository root directory
            language: Language override (auto-detected if None)
            encoding: File encoding

        Returns:
            SourceFile instance
        """
        file_path = Path(file_path)
        repo_root = Path(repo_root)

        # Calculate relative path
        if file_path.is_absolute():
            relative_path = file_path.relative_to(repo_root)
        else:
            relative_path = file_path

        # Read content
        abs_path = repo_root / relative_path
        content = abs_path.read_text(encoding=encoding)

        # Auto-detect language if not specified
        if language is None:
            from .parser_registry import get_registry

            registry = get_registry()
            language = registry.detect_language(abs_path)
            if language is None:
                raise ValueError(f"Could not detect language for: {abs_path}")

        return cls(
            file_path=str(relative_path),
            content=content,
            language=language,
            encoding=encoding,
        )

    @classmethod
    def from_content(
        cls,
        file_path: str,
        content: str,
        language: str,
        encoding: str = "utf-8",
    ) -> "SourceFile":
        """
        Create source file from content string.

        Args:
            file_path: Relative file path
            content: Source code content
            language: Programming language
            encoding: File encoding

        Returns:
            SourceFile instance
        """
        return cls(
            file_path=file_path,
            content=content,
            language=language,
            encoding=encoding,
        )

    def get_line(self, line_num: int) -> str:
        """
        Get specific line from source (1-indexed).

        Args:
            line_num: Line number (1-indexed)

        Returns:
            Line content (without newline)
        """
        lines = self.content.splitlines()
        if 1 <= line_num <= len(lines):
            return lines[line_num - 1]
        return ""

    def get_lines(self, start_line: int, end_line: int) -> list[str]:
        """
        Get range of lines (1-indexed, inclusive).

        Args:
            start_line: Start line number (1-indexed)
            end_line: End line number (1-indexed, inclusive)

        Returns:
            List of lines (without newlines)
        """
        lines = self.content.splitlines()
        return lines[start_line - 1 : end_line]

    def get_text(self, start_line: int, start_col: int, end_line: int, end_col: int) -> str:
        """
        Extract text from source using line/column coordinates.

        Args:
            start_line: Start line (1-indexed)
            start_col: Start column (0-indexed)
            end_line: End line (1-indexed)
            end_col: End column (0-indexed)

        Returns:
            Extracted text
        """
        lines = self.content.splitlines(keepends=True)

        if start_line == end_line:
            # Single line
            line = lines[start_line - 1] if start_line <= len(lines) else ""
            return line[start_col:end_col]

        # Multi-line
        result_lines = []

        # First line
        if start_line <= len(lines):
            result_lines.append(lines[start_line - 1][start_col:])

        # Middle lines
        for line_num in range(start_line + 1, end_line):
            if line_num <= len(lines):
                result_lines.append(lines[line_num - 1])

        # Last line
        if end_line <= len(lines):
            result_lines.append(lines[end_line - 1][:end_col])

        return "".join(result_lines)

    @property
    def line_count(self) -> int:
        """Get total number of lines"""
        return len(self.content.splitlines())

    @property
    def byte_size(self) -> int:
        """Get file size in bytes"""
        return len(self.content.encode(self.encoding))
