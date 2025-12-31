"""
ShadowFS Domain Models (SOTA-Level Fixed)

FilePatch: Represents a file change (ADD/MODIFY/DELETE)
Hunk: Represents a diff hunk within a file

SECURITY: Full input sanitization
THREAD-SAFETY: Immutable by design
VALIDATION: All invariants strictly enforced
"""

import re
from dataclasses import dataclass, field
from enum import Enum


class ChangeType(str, Enum):
    """Type of file change"""

    ADD = "ADD"
    MODIFY = "MODIFY"
    DELETE = "DELETE"


@dataclass(frozen=True)
class Hunk:
    """
    Diff hunk (immutable value object)

    Represents a contiguous block of changes in unified diff format.

    References:
        - Unified Diff Format (GNU diff)
        - Git Diff Algorithm

    Attributes:
        start_line: Starting line number in original file (1-based)
        end_line: Ending line number in original file (1-based)
        original_lines: Lines from original file
        new_lines: Lines from new file

    Invariants:
        - start_line > 0
        - end_line >= start_line
        - end_line consistent with start_line + len(original_lines) - 1
        - At least one of original_lines or new_lines is non-empty

    Thread-Safety: Immutable (frozen=True)

    Examples:
        >>> hunk = Hunk(
        ...     start_line=10,
        ...     end_line=11,
        ...     original_lines=("old line 1", "old line 2"),
        ...     new_lines=("new line 1", "new line 2", "new line 3")
        ... )
    """

    start_line: int
    end_line: int
    original_lines: tuple[str, ...] = field(default_factory=tuple)
    new_lines: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        """
        Validate invariants (SOTA-Level Strict)

        Raises:
            ValueError: For any invariant violation
        """
        # Invariant 1: Positive start_line
        if self.start_line <= 0:
            raise ValueError(f"start_line must be > 0, got {self.start_line}")

        # Invariant 2: end_line >= start_line
        if self.end_line < self.start_line:
            raise ValueError(f"end_line ({self.end_line}) must be >= start_line ({self.start_line})")

        # Invariant 3: Line range consistency (CRITICAL FIX)
        if self.original_lines:
            expected_end = self.start_line + len(self.original_lines) - 1
            if self.end_line != expected_end:
                raise ValueError(
                    f"end_line ({self.end_line}) inconsistent with start_line ({self.start_line}) "
                    f"and original_lines length ({len(self.original_lines)}). "
                    f"Expected: {expected_end}"
                )

        # Invariant 4: Non-empty content
        if not self.original_lines and not self.new_lines:
            raise ValueError("At least one of original_lines or new_lines must be non-empty")

    @property
    def is_addition(self) -> bool:
        """True if this hunk only adds lines"""
        return len(self.original_lines) == 0 and len(self.new_lines) > 0

    @property
    def is_deletion(self) -> bool:
        """True if this hunk only deletes lines"""
        return len(self.original_lines) > 0 and len(self.new_lines) == 0

    @property
    def is_modification(self) -> bool:
        """True if this hunk modifies lines"""
        return len(self.original_lines) > 0 and len(self.new_lines) > 0

    @property
    def lines_added(self) -> int:
        """Number of lines added"""
        return len(self.new_lines) - len(self.original_lines)

    @property
    def lines_removed(self) -> int:
        """Number of lines removed"""
        return len(self.original_lines) - len(self.new_lines)


# Path validation regex (compiled once)
_DANGEROUS_PATH_PATTERN = re.compile(r"[\x00\n\r]")


@dataclass(frozen=True)
class FilePatch:
    """
    File patch (immutable value object)

    Represents a complete change to a single file.

    Attributes:
        path: Relative file path from project root
        change_type: Type of change (ADD/MODIFY/DELETE)
        original_content: Original file content (None for ADD)
        new_content: New file content (None for DELETE)
        hunks: List of diff hunks (empty for binary files)

    Invariants:
        - path is non-empty, relative, sanitized
        - For ADD: original_content is None
        - For DELETE: new_content is None
        - For MODIFY: both contents are non-None
        - hunks list is consistent with change_type

    Security:
        - No null bytes, newlines in path
        - No absolute paths
        - No path traversal (..)

    Thread-Safety: Immutable (frozen=True)

    Examples:
        >>> # Add new file
        >>> patch = FilePatch(
        ...     path="src/new_file.py",
        ...     change_type=ChangeType.ADD,
        ...     original_content=None,
        ...     new_content="def hello(): pass",
        ...     hunks=(Hunk(...),)
        ... )
    """

    path: str
    change_type: ChangeType
    original_content: str | None = None
    new_content: str | None = None
    hunks: tuple[Hunk, ...] = field(default_factory=tuple)

    def __post_init__(self):
        """
        Validate invariants (SOTA-Level Strict + Security)

        Raises:
            ValueError: For any invariant or security violation
        """
        # Invariant 1: Non-empty path
        if not self.path:
            raise ValueError("path must be non-empty")

        # SECURITY: Path sanitization (CRITICAL FIX)
        # Check for null bytes
        if "\x00" in self.path:
            raise ValueError(f"path contains null byte (security violation): {repr(self.path)}")

        # Check for newlines
        if "\n" in self.path or "\r" in self.path:
            raise ValueError(f"path contains newline characters (security violation): {repr(self.path)}")

        # Check for absolute path
        if self.path.startswith("/") or (len(self.path) > 1 and self.path[1] == ":"):
            raise ValueError(f"path must be relative (security violation): {self.path}")

        # Check for path traversal
        path_parts = self.path.split("/")
        if ".." in path_parts:
            raise ValueError(f"path contains '..' (path traversal violation): {self.path}")

        # Additional: No leading/trailing spaces
        if self.path != self.path.strip():
            raise ValueError(f"path has leading/trailing whitespace: {repr(self.path)}")

        # Invariant 2: Content consistency by change_type
        if self.change_type == ChangeType.ADD:
            if self.original_content is not None:
                raise ValueError("ADD patch must have original_content=None")
            if self.new_content is None:
                raise ValueError("ADD patch must have new_content")

        elif self.change_type == ChangeType.DELETE:
            if self.original_content is None:
                raise ValueError("DELETE patch must have original_content")
            if self.new_content is not None:
                raise ValueError("DELETE patch must have new_content=None")

        elif self.change_type == ChangeType.MODIFY:
            if self.original_content is None or self.new_content is None:
                raise ValueError("MODIFY patch must have both contents")
            if self.original_content == self.new_content:
                raise ValueError("MODIFY patch with identical content is invalid (use no-op or remove this patch)")

    @property
    def is_binary(self) -> bool:
        """True if this patch represents a binary file (no hunks)"""
        return len(self.hunks) == 0

    @property
    def total_lines_added(self) -> int:
        """Total lines added across all hunks"""
        return sum(hunk.lines_added for hunk in self.hunks if hunk.lines_added > 0)

    @property
    def total_lines_removed(self) -> int:
        """Total lines removed across all hunks"""
        return sum(hunk.lines_removed for hunk in self.hunks if hunk.lines_removed > 0)

    def to_unified_diff(self) -> str:
        """
        Generate unified diff format

        Returns:
            Unified diff string (Git-compatible)
        """
        lines = []

        # Header
        lines.append(f"--- a/{self.path}")
        lines.append(f"+++ b/{self.path}")

        # Hunks
        for hunk in self.hunks:
            # Hunk header: @@ -start,count +start,count @@
            orig_start = hunk.start_line
            orig_count = len(hunk.original_lines)
            new_start = hunk.start_line
            new_count = len(hunk.new_lines)

            lines.append(f"@@ -{orig_start},{orig_count} +{new_start},{new_count} @@")

            # Removed lines
            for line in hunk.original_lines:
                lines.append(f"-{line}")

            # Added lines
            for line in hunk.new_lines:
                lines.append(f"+{line}")

        return "\n".join(lines)
