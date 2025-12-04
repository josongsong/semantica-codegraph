"""
Agent Utilities

Shared utilities for agent modes including file I/O operations.
"""

from pathlib import Path

from src.common.observability import get_logger

logger = get_logger(__name__)


class FileReadError(Exception):
    """Raised when file reading fails."""

    pass


def read_file(file_path: str, max_lines: int | None = None) -> str:
    """
    Read entire file or up to max_lines.

    Args:
        file_path: Path to file to read
        max_lines: Maximum number of lines to read (None = all)

    Returns:
        File content as string

    Raises:
        FileReadError: If file cannot be read
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise FileReadError(f"File not found: {file_path}")

        if not path.is_file():
            raise FileReadError(f"Not a file: {file_path}")

        with open(path, encoding="utf-8") as f:
            if max_lines is None:
                return f.read()
            else:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line)
                return "".join(lines)

    except FileReadError:
        raise
    except UnicodeDecodeError as e:
        raise FileReadError(f"Cannot decode file as UTF-8: {file_path}") from e
    except PermissionError as e:
        raise FileReadError(f"Permission denied: {file_path}") from e
    except Exception as e:
        raise FileReadError(f"Error reading file {file_path}: {e}") from e


def read_file_lines(file_path: str, start_line: int, end_line: int | None = None, context_lines: int = 0) -> str:
    """
    Read specific line range from file with optional context.

    Args:
        file_path: Path to file to read
        start_line: Starting line number (1-indexed)
        end_line: Ending line number (1-indexed, None = until EOF)
        context_lines: Number of context lines before/after range

    Returns:
        Selected lines as string with line numbers

    Raises:
        FileReadError: If file cannot be read
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise FileReadError(f"File not found: {file_path}")

        if not path.is_file():
            raise FileReadError(f"Not a file: {file_path}")

        # Calculate actual range with context
        actual_start = max(1, start_line - context_lines)
        actual_end = end_line + context_lines if end_line else None

        with open(path, encoding="utf-8") as f:
            lines = f.readlines()

        # Adjust for 0-indexed list
        start_idx = actual_start - 1
        end_idx = actual_end if actual_end is None else min(actual_end, len(lines))

        # Build output with line numbers
        result = []
        for i in range(start_idx, end_idx if end_idx is not None else len(lines)):
            line_num = i + 1
            result.append(f"{line_num:4d} | {lines[i]}")

        return "".join(result)

    except FileReadError:
        raise
    except UnicodeDecodeError as e:
        raise FileReadError(f"Cannot decode file as UTF-8: {file_path}") from e
    except PermissionError as e:
        raise FileReadError(f"Permission denied: {file_path}") from e
    except Exception as e:
        raise FileReadError(f"Error reading file {file_path}: {e}") from e


def read_multiple_files(file_paths: list[str], max_lines_per_file: int | None = None) -> str:
    """
    Read multiple files and concatenate with separators.

    Args:
        file_paths: List of file paths to read
        max_lines_per_file: Maximum lines per file (None = all)

    Returns:
        Concatenated file contents with separators

    Note:
        Continues reading other files if one fails, logs errors
    """
    results = []

    for file_path in file_paths:
        try:
            content = read_file(file_path, max_lines=max_lines_per_file)
            separator = f"\n{'=' * 80}\n# File: {file_path}\n{'=' * 80}\n"
            results.append(separator + content)
        except FileReadError as e:
            logger.warning(f"Failed to read file {file_path}: {e}")
            results.append(f"\n# File: {file_path} (ERROR: {e})\n")

    return "\n".join(results) if results else ""


def safe_read_file(file_path: str, fallback: str = "") -> str:
    """
    Read file with fallback on error.

    Args:
        file_path: Path to file to read
        fallback: Value to return on error

    Returns:
        File content or fallback value
    """
    try:
        return read_file(file_path)
    except FileReadError as e:
        logger.warning(f"Failed to read {file_path}: {e}")
        return fallback


def get_file_context(file_path: str, line_number: int, context_lines: int = 5) -> str:
    """
    Get context around a specific line in a file.

    Convenience function for error context extraction.

    Args:
        file_path: Path to file
        line_number: Line number to center context on
        context_lines: Lines before/after to include

    Returns:
        Context with line numbers
    """
    try:
        return read_file_lines(
            file_path,
            start_line=line_number,
            end_line=line_number,
            context_lines=context_lines,
        )
    except FileReadError as e:
        logger.warning(f"Failed to get context from {file_path}:{line_number}: {e}")
        return f"# Error reading {file_path}:{line_number}\n# {e}\n"
