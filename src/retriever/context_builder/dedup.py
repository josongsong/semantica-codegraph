"""
Deduplication

Removes overlapping chunks to prevent redundant context.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.retriever.fusion.engine import FusedHit

logger = logging.getLogger(__name__)


class Deduplicator:
    """
    Deduplicates chunks to prevent overlapping content in context.

    Strategy:
    1. Sort chunks by priority_score (descending)
    2. For each chunk, check if it overlaps with already-selected chunks
    3. If overlap exists, apply penalty or drop
    """

    def __init__(
        self,
        overlap_threshold: float = 0.5,
        overlap_penalty: float = 0.5,
        drop_on_full_overlap: bool = True,
    ):
        """
        Initialize deduplicator.

        Args:
            overlap_threshold: Fraction of overlap to consider as duplicate (0-1)
            overlap_penalty: Score penalty for overlapping chunks
            drop_on_full_overlap: Drop chunk if fully contained in another
        """
        self.overlap_threshold = overlap_threshold
        self.overlap_penalty = overlap_penalty
        self.drop_on_full_overlap = drop_on_full_overlap

    def deduplicate(self, fused_hits: "list[FusedHit]") -> "list[FusedHit]":
        """
        Deduplicate fused hits by removing/penalizing overlaps.

        Args:
            fused_hits: List of fused hits (assumed sorted by priority_score)

        Returns:
            Deduplicated list of fused hits
        """
        if not fused_hits:
            return []

        # Track selected chunks by file → [(start, end, chunk_id), ...]
        selected_ranges: dict[str, list[tuple[int, int, str]]] = {}

        deduplicated = []
        dropped_count = 0
        penalized_count = 0

        for hit in fused_hits:
            file_path = hit.file_path
            if not file_path:
                # No file path → can't check overlap, keep it
                deduplicated.append(hit)
                continue

            # Get line range
            start_line = hit.metadata.get("start_line")
            end_line = hit.metadata.get("end_line")

            if start_line is None or end_line is None:
                # No line info → can't check overlap, keep it
                deduplicated.append(hit)
                continue

            # Check for overlap with existing chunks in same file
            if file_path in selected_ranges:
                overlap_ratio = self._calculate_max_overlap(
                    start_line, end_line, selected_ranges[file_path]
                )

                if overlap_ratio >= 1.0 and self.drop_on_full_overlap:
                    # Fully contained in another chunk → drop
                    logger.debug(
                        f"Dropping fully overlapping chunk: {hit.chunk_id} "
                        f"({file_path}:{start_line}-{end_line})"
                    )
                    dropped_count += 1
                    continue

                if overlap_ratio >= self.overlap_threshold:
                    # Significant overlap → apply penalty
                    hit.priority_score *= self.overlap_penalty
                    hit.metadata["dedup_penalty"] = self.overlap_penalty
                    hit.metadata["overlap_ratio"] = overlap_ratio
                    penalized_count += 1
                    logger.debug(
                        f"Penalizing overlapping chunk: {hit.chunk_id} "
                        f"(overlap={overlap_ratio:.2f})"
                    )

            # Add to selected ranges
            if file_path not in selected_ranges:
                selected_ranges[file_path] = []
            selected_ranges[file_path].append((start_line, end_line, hit.chunk_id))

            deduplicated.append(hit)

        logger.info(
            f"Deduplication: {len(fused_hits)} → {len(deduplicated)} chunks "
            f"(dropped={dropped_count}, penalized={penalized_count})"
        )

        # Re-sort by priority_score after penalties
        deduplicated.sort(key=lambda h: h.priority_score, reverse=True)

        return deduplicated

    def _calculate_max_overlap(
        self, start: int, end: int, existing_ranges: list[tuple[int, int, str]]
    ) -> float:
        """
        Calculate maximum overlap ratio with existing ranges.

        Args:
            start: Start line of new chunk
            end: End line of new chunk
            existing_ranges: List of (start, end, chunk_id) for existing chunks

        Returns:
            Maximum overlap ratio (0-1, >1 if fully contained)
        """
        max_overlap = 0.0
        chunk_size = end - start + 1

        for existing_start, existing_end, _ in existing_ranges:
            # Calculate overlap
            overlap_start = max(start, existing_start)
            overlap_end = min(end, existing_end)

            if overlap_start <= overlap_end:
                overlap_size = overlap_end - overlap_start + 1
                overlap_ratio = overlap_size / chunk_size
                max_overlap = max(max_overlap, overlap_ratio)

        return max_overlap
