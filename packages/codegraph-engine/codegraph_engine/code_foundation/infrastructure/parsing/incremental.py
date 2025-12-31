"""
Incremental Parser

Supports Tree-sitter incremental parsing for performance optimization.
Uses git diff information to minimize re-parsing.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Parser, Tree


@dataclass
class DiffHunk:
    """Represents a diff hunk from unified diff format"""

    old_start: int  # Starting line in old file (1-indexed)
    old_count: int  # Number of lines in old file
    new_start: int  # Starting line in new file (1-indexed)
    new_count: int  # Number of lines in new file
    lines: list[str]  # Actual diff lines


@dataclass
class Edit:
    """
    Tree-sitter edit information.

    Based on tree-sitter Edit structure.
    """

    start_byte: int
    old_end_byte: int
    new_end_byte: int
    start_row: int
    start_column: int
    old_end_row: int
    old_end_column: int
    new_end_row: int
    new_end_column: int


class DiffParser:
    """Parse unified diff format"""

    # Matches: @@ -10,5 +10,6 @@
    HUNK_HEADER_PATTERN = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    def parse_diff(self, diff_text: str) -> list[DiffHunk]:
        """
        Parse unified diff text into hunks.

        Args:
            diff_text: Unified diff string

        Returns:
            List of diff hunks
        """
        hunks = []
        lines = diff_text.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]

            # Look for hunk header
            match = self.HUNK_HEADER_PATTERN.match(line)
            if match:
                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) else 1

                # Collect hunk lines
                hunk_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith("@@"):
                    hunk_lines.append(lines[i])
                    i += 1

                hunks.append(
                    DiffHunk(
                        old_start=old_start,
                        old_count=old_count,
                        new_start=new_start,
                        new_count=new_count,
                        lines=hunk_lines,
                    )
                )
            else:
                i += 1

        return hunks


class EditCalculator:
    """Convert diff hunks to Tree-sitter edits"""

    def calculate_edits(self, old_content: str, diff_hunks: list[DiffHunk]) -> list[Edit]:
        """
        Calculate Tree-sitter edits from diff hunks.

        Args:
            old_content: Original file content
            diff_hunks: List of diff hunks

        Returns:
            List of Tree-sitter edits
        """
        edits = []
        old_lines = old_content.split("\n")

        for hunk in diff_hunks:
            # Calculate byte positions
            start_byte = self._line_col_to_byte(old_lines, hunk.old_start - 1, 0)

            # Calculate old end position
            old_end_line = hunk.old_start - 1 + hunk.old_count
            old_end_col = len(old_lines[old_end_line - 1]) if old_end_line <= len(old_lines) else 0
            old_end_byte = self._line_col_to_byte(old_lines, old_end_line - 1, old_end_col)

            # Calculate new end position by parsing the actual new content from diff
            new_lines = []
            for line in hunk.lines:
                if line.startswith("+"):
                    new_lines.append(line[1:])  # Remove '+' prefix
                elif not line.startswith("-"):
                    new_lines.append(line[1:] if len(line) > 0 else "")

            # Calculate exact byte length of new content
            new_content = "\n".join(new_lines)
            new_content_bytes = len(new_content.encode("utf-8"))
            new_end_byte = start_byte + new_content_bytes

            # Calculate new end line/column
            new_end_line = hunk.new_start - 1 + hunk.new_count
            new_end_col = len(new_lines[-1]) if new_lines else 0

            edit = Edit(
                start_byte=start_byte,
                old_end_byte=old_end_byte,
                new_end_byte=new_end_byte,
                start_row=hunk.old_start - 1,
                start_column=0,
                old_end_row=old_end_line - 1,
                old_end_column=old_end_col,
                new_end_row=new_end_line - 1,
                new_end_column=new_end_col,
            )
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


class IncrementalParser:
    """
    Incremental parser using Tree-sitter.

    Caches parse trees and applies incremental edits based on diffs.
    """

    def __init__(self):
        self._tree_cache: dict[str, Tree] = {}
        self.diff_parser = DiffParser()
        self.edit_calculator = EditCalculator()

    def parse_incremental(
        self,
        parser: "Parser",
        file_path: str,
        new_content: str,
        old_content: str | None = None,
        diff_text: str | None = None,
    ) -> "Tree":
        """
        Parse with incremental support.

        Args:
            parser: Tree-sitter parser
            file_path: Path to file (for caching)
            new_content: New file content
            old_content: Old file content (for diff calculation)
            diff_text: Optional unified diff (if not provided, full parse)

        Returns:
            Parse tree
        """
        # If we have cached tree and diff, do incremental parsing
        old_tree = self._tree_cache.get(file_path)

        if old_tree and diff_text and old_content:
            # Parse diff
            hunks = self.diff_parser.parse_diff(diff_text)

            if hunks:
                # Calculate edits
                edits = self.edit_calculator.calculate_edits(old_content, hunks)

                # Apply edits to old tree
                for edit in edits:
                    old_tree.edit(
                        start_byte=edit.start_byte,
                        old_end_byte=edit.old_end_byte,
                        new_end_byte=edit.new_end_byte,
                        start_point=(edit.start_row, edit.start_column),
                        old_end_point=(edit.old_end_row, edit.old_end_column),
                        new_end_point=(edit.new_end_row, edit.new_end_column),
                    )

                # Parse incrementally
                new_tree = parser.parse(new_content.encode("utf-8"), old_tree)
            else:
                # No changes, return old tree
                new_tree = old_tree
        else:
            # Full parse (no cache or diff)
            new_tree = parser.parse(new_content.encode("utf-8"))

        # Cache the new tree
        self._tree_cache[file_path] = new_tree

        return new_tree

    def clear_cache(self, file_path: str | None = None) -> None:
        """
        Clear cached parse tree(s).

        Args:
            file_path: Specific file to clear, or None for all
        """
        if file_path:
            self._tree_cache.pop(file_path, None)
        else:
            self._tree_cache.clear()
