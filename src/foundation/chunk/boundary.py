"""
Chunk Boundary Validator

Validates chunk boundaries to ensure:
1. No overlaps between sibling chunks
2. No gaps between sibling chunks (optional warning)
3. Large class flatten mode (optional)
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Chunk

logger = logging.getLogger(__name__)


class BoundaryValidationError(Exception):
    """Raised when chunk boundaries are invalid"""

    pass


class ChunkBoundaryValidator:
    """
    Validates chunk boundaries for consistency.

    Rules:
    1. Overlap: Sibling chunks must not overlap (raises error)
    2. Gap: Sibling chunks should not have gaps (logs warning)
    3. Line order: start_line <= end_line for all chunks

    Usage:
        validator = ChunkBoundaryValidator(allow_gaps=True)
        validator.validate(chunks)
    """

    def __init__(self, allow_gaps: bool = True, large_class_threshold: int = 5000):
        """
        Initialize boundary validator.

        Args:
            allow_gaps: If False, raises error on gaps between siblings
            large_class_threshold: Token count threshold for large class flatten mode
        """
        self.allow_gaps = allow_gaps
        self.large_class_threshold = large_class_threshold

    def validate(self, chunks: list["Chunk"]) -> None:
        """
        Validate chunk boundaries.

        Args:
            chunks: List of all chunks to validate

        Raises:
            BoundaryValidationError: If validation fails
        """
        # Group chunks by parent
        by_parent: dict[str | None, list[Chunk]] = {}
        for chunk in chunks:
            by_parent.setdefault(chunk.parent_id, []).append(chunk)

        # Validate each sibling group
        for parent_id, siblings in by_parent.items():
            self._validate_sibling_group(parent_id, siblings)

    def _validate_sibling_group(self, parent_id: str | None, siblings: list["Chunk"]) -> None:
        """
        Validate a group of sibling chunks.

        Args:
            parent_id: Parent chunk ID (or None for root)
            siblings: List of sibling chunks

        Raises:
            BoundaryValidationError: If validation fails
        """
        # Filter chunks with line ranges
        chunks_with_lines = [c for c in siblings if c.start_line is not None]

        if not chunks_with_lines:
            return  # No line ranges to validate

        # Sort by start line
        sorted_chunks = sorted(chunks_with_lines, key=lambda c: c.start_line or 0)

        # Validate line order within each chunk
        for chunk in sorted_chunks:
            assert chunk.start_line is not None
            assert chunk.end_line is not None
            if chunk.start_line > chunk.end_line:
                raise BoundaryValidationError(
                    f"Invalid line range in chunk {chunk.chunk_id}: "
                    f"start_line ({chunk.start_line}) > end_line ({chunk.end_line})"
                )

        # Validate sibling relationships
        prev_chunk = None
        for current_chunk in sorted_chunks:
            if prev_chunk is None:
                prev_chunk = current_chunk
                continue

            # Type narrowing for line numbers
            assert prev_chunk.start_line is not None
            assert prev_chunk.end_line is not None
            assert current_chunk.start_line is not None
            assert current_chunk.end_line is not None

            # Check for overlap
            if current_chunk.start_line <= prev_chunk.end_line:
                raise BoundaryValidationError(
                    f"Chunk overlap detected:\n"
                    f"  Previous: {prev_chunk.chunk_id} "
                    f"(lines {prev_chunk.start_line}-{prev_chunk.end_line})\n"
                    f"  Current:  {current_chunk.chunk_id} "
                    f"(lines {current_chunk.start_line}-{current_chunk.end_line})"
                )

            # Check for gap
            if current_chunk.start_line > prev_chunk.end_line + 1:
                gap_size = current_chunk.start_line - prev_chunk.end_line - 1
                msg = (
                    f"Gap detected between chunks:\n"
                    f"  Previous: {prev_chunk.chunk_id} "
                    f"(ends at line {prev_chunk.end_line})\n"
                    f"  Current:  {current_chunk.chunk_id} "
                    f"(starts at line {current_chunk.start_line})\n"
                    f"  Gap size: {gap_size} lines"
                )

                if self.allow_gaps:
                    logger.warning(msg)
                else:
                    raise BoundaryValidationError(msg)

            prev_chunk = current_chunk

    def check_large_class_flatten(self, chunks: list["Chunk"]) -> list[str]:
        """
        Check for large classes that should be flattened.

        Args:
            chunks: List of all chunks

        Returns:
            List of class chunk IDs that exceed the threshold
        """
        large_classes = []

        for chunk in chunks:
            if chunk.kind != "class":
                continue

            if chunk.start_line is None or chunk.end_line is None:
                continue

            # Estimate tokens (rough approximation: 1 token per 4 characters)
            line_count = chunk.end_line - chunk.start_line + 1
            estimated_tokens = line_count * 20  # ~20 tokens per line average

            if estimated_tokens > self.large_class_threshold:
                large_classes.append(chunk.chunk_id)
                logger.info(
                    f"Large class detected: {chunk.chunk_id} " f"({line_count} lines, ~{estimated_tokens} tokens)"
                )

        return large_classes
