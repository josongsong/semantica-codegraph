"""
Minimal IR models needed for parsing.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Span:
    """
    Source code location (immutable).

    Attributes:
        start_line: Starting line number (1-indexed)
        start_col: Starting column (0-indexed)
        end_line: Ending line number (1-indexed)
        end_col: Ending column (0-indexed)
    """

    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def overlaps(self, other: "Span") -> bool:
        """Check if this span overlaps with another"""
        return not (self.end_line < other.start_line or other.end_line < self.start_line)

    def contains_line(self, line: int) -> bool:
        """Check if span contains the given line"""
        return self.start_line <= line <= self.end_line
