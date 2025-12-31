"""
Incremental Parsing with Tree-sitter

Provides infrastructure for incremental parsing using Tree-sitter's
edit/reparse capabilities.

Status: Full implementation with diff hunk to Tree-sitter edit conversion
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from tree_sitter import Language, Parser, Tree
except ImportError:
    Language = Parser = Tree = Any  # type: ignore


@dataclass
class TextEdit:
    """
    Represents a text edit for incremental parsing.

    Attributes:
        start_byte: Starting byte offset
        old_end_byte: Old ending byte offset
        new_end_byte: New ending byte offset
        start_point: Starting (row, column) tuple
        old_end_point: Old ending (row, column) tuple
        new_end_point: New ending (row, column) tuple
    """

    start_byte: int
    old_end_byte: int
    new_end_byte: int
    start_point: tuple[int, int]
    old_end_point: tuple[int, int]
    new_end_point: tuple[int, int]


class IncrementalParser:
    """
    Incremental parser using Tree-sitter's edit/reparse functionality.

    Tree-sitter supports incremental parsing by:
    1. Storing the previous parse tree
    2. Applying edits to the tree
    3. Reparsing only the changed regions

    This can significantly speed up parsing for large files with small changes.
    """

    def __init__(self, language: Any):
        """
        Initialize incremental parser.

        Args:
            language: Tree-sitter Language object
        """
        if Parser is None:
            raise ImportError("tree-sitter is required for incremental parsing")

        self.parser = Parser()
        self.parser.set_language(language)
        self._cached_trees: dict[str, Tree] = {}  # type: ignore[valid-type]  # file_path -> previous tree

    def parse_with_edit(
        self,
        file_path: str,
        new_content: bytes,
        old_content: bytes | None = None,
        diff_hunks: list[dict] | None = None,
    ) -> Tree:  # type: ignore[valid-type]
        """
        Parse file incrementally using previous tree if available.

        Args:
            file_path: File path (used as cache key)
            new_content: New file content (bytes)
            old_content: Old file content (bytes, for edit calculation)
            diff_hunks: Optional pre-computed diff hunks

        Returns:
            Parsed tree

        Notes:
            - If no previous tree exists, performs full parse
            - If edits provided, applies them before reparsing
            - Tree-sitter automatically reuses unchanged subtrees
        """
        old_tree = self._cached_trees.get(file_path)

        if old_tree is None:
            # No previous tree - full parse
            tree = self.parser.parse(new_content)
        else:
            # Previous tree exists - incremental parse
            if old_content and diff_hunks:
                # Apply edits to tree
                edits = self._calculate_edits(old_content, new_content, diff_hunks)
                for edit in edits:
                    old_tree.edit(**edit)

            # Reparse with edit information
            # Tree-sitter will reuse unchanged subtrees
            tree = self.parser.parse(new_content, old_tree)

        # Cache for next time
        self._cached_trees[file_path] = tree
        return tree

    def _calculate_edits(
        self,
        old_content: bytes,
        new_content: bytes,
        diff_hunks: list[dict],
    ) -> list[dict[str, Any]]:
        """
        Calculate Tree-sitter edit operations from diff hunks.

        Args:
            old_content: Old file content (bytes)
            new_content: New file content (bytes)
            diff_hunks: Diff hunks from git diff parser
                Each hunk should have: old_start, old_count, new_start, new_count, lines

        Returns:
            List of edit dictionaries for tree.edit()
        """
        edits = []
        old_lines = old_content.decode("utf-8").split("\n")

        for hunk in diff_hunks:
            # Extract hunk info (support both dict and DiffHunk object)
            old_start = hunk.get("old_start") if isinstance(hunk, dict) else hunk.old_start
            old_count = hunk.get("old_count", 1) if isinstance(hunk, dict) else hunk.old_count
            new_count = hunk.get("new_count", 1) if isinstance(hunk, dict) else hunk.new_count
            lines = hunk.get("lines", []) if isinstance(hunk, dict) else hunk.lines

            # Calculate byte positions
            start_byte = self._line_col_to_byte(old_lines, old_start - 1, 0)

            # Calculate old end position
            old_end_line = old_start - 1 + old_count
            old_end_col = len(old_lines[old_end_line - 1]) if old_end_line <= len(old_lines) else 0
            old_end_byte = self._line_col_to_byte(old_lines, old_end_line - 1, old_end_col)

            # Calculate new content from diff lines
            new_lines = []
            for line in lines:
                if line.startswith("+"):
                    new_lines.append(line[1:])  # Remove '+' prefix
                elif not line.startswith("-"):
                    # Context line (starts with ' ') or empty
                    new_lines.append(line[1:] if len(line) > 0 else "")

            # Calculate exact byte length of new content
            new_content_str = "\n".join(new_lines)
            new_content_bytes = len(new_content_str.encode("utf-8"))
            new_end_byte = start_byte + new_content_bytes

            # Calculate new end line/column
            new_end_line = old_start - 1 + new_count
            new_end_col = len(new_lines[-1]) if new_lines else 0

            edit = {
                "start_byte": start_byte,
                "old_end_byte": old_end_byte,
                "new_end_byte": new_end_byte,
                "start_point": (old_start - 1, 0),
                "old_end_point": (old_end_line - 1, old_end_col),
                "new_end_point": (new_end_line - 1, new_end_col),
            }
            edits.append(edit)

        return edits

    def _line_col_to_byte(self, lines: list[str], line: int, col: int) -> int:
        """
        Convert line/column position to byte offset.

        Args:
            lines: File lines
            line: Line number (0-indexed)
            col: Column number (0-indexed)

        Returns:
            Byte offset
        """
        byte_offset = 0

        # Add bytes from all previous lines
        for i in range(min(line, len(lines))):
            byte_offset += len(lines[i].encode("utf-8")) + 1  # +1 for newline

        # Add bytes from current line up to column
        if line < len(lines):
            byte_offset += len(lines[line][:col].encode("utf-8"))

        return byte_offset

    def invalidate_cache(self, file_path: str | None = None):
        """
        Invalidate cached tree(s).

        Args:
            file_path: Specific file to invalidate (None = all)
        """
        if file_path:
            self._cached_trees.pop(file_path, None)
        else:
            self._cached_trees.clear()

    def get_cache_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache size and file count
        """
        return {
            "cached_files": len(self._cached_trees),
            "cache_keys": list(self._cached_trees.keys())[:10],  # First 10
        }


# Integration helpers for chunk incremental refresher
def create_incremental_parser(language_name: str = "python") -> IncrementalParser | None:
    """
    Create incremental parser for a language.

    Args:
        language_name: Language name (default: python)

    Returns:
        IncrementalParser instance or None if tree-sitter not available
    """
    try:
        from codegraph_engine.code_foundation.infrastructure.parsing.parser_registry import get_registry

        registry = get_registry()
        parser = registry.get_parser(language_name)

        # Extract language from parser (tree-sitter Parser has .language attribute)
        language = getattr(parser, "language", None)
        if language is None:
            return None

        return IncrementalParser(language)
    except Exception:
        return None


# Future Phase 2: Integration with chunk refresher
# class IncrementalChunkRefresher:
#     def __init__(self, incremental_parser: IncrementalParser):
#         self.parser = incremental_parser
#
#     def refresh_with_incremental_parsing(self, file_path, old_content, new_content, diff):
#         """Use incremental parsing for faster chunk generation"""
#         tree = self.parser.parse_with_edit(file_path, new_content, old_content, diff)
#         # Generate chunks from tree
#         # ...
