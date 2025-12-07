"""
Lost-in-the-Middle Mitigation

Addresses position bias in retrieved contexts where LLMs perform worse
on information in the middle of long contexts.

References:
- Lost in the Middle (Liu et al., 2023)
- https://arxiv.org/abs/2307.03172

Key Finding:
LLMs attend more to beginning and end of context, missing middle content.
Solution: Reorder results to place important info at edges.
"""

from dataclasses import dataclass
from typing import Any

from src.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class RankedChunk:
    """Chunk with ranking information."""

    chunk_id: str
    content: str
    score: float
    original_rank: int
    metadata: dict[str, Any]


class PositionBiasReorderer:
    """
    Reorders chunks to mitigate Lost-in-the-Middle effect.

    Strategy: Place highest-scoring chunks at beginning and end,
    lower-scoring chunks in middle.

    Pattern: [Best, 3rd, 5th, ..., 6th, 4th, 2nd]

    Features:
    - Alternating placement (start/end)
    - Preserves relative importance
    - Configurable strategies
    """

    def __init__(
        self,
        strategy: str = "alternating",  # alternating|bookends|preserve
        min_chunks_for_reorder: int = 5,
    ):
        """
        Initialize position bias reorderer.

        Args:
            strategy: Reordering strategy
                - alternating: Best at edges, alternate placement
                - bookends: Best at start/end only
                - preserve: No reordering (baseline)
            min_chunks_for_reorder: Minimum chunks to apply reordering
        """
        self.strategy = strategy
        self.min_chunks_for_reorder = min_chunks_for_reorder

    def reorder(self, chunks: list[RankedChunk]) -> list[RankedChunk]:
        """
        Reorder chunks to mitigate position bias.

        Args:
            chunks: List of chunks sorted by score (best first)

        Returns:
            Reordered chunks optimized for LLM attention
        """
        # Skip reordering for short lists
        if len(chunks) < self.min_chunks_for_reorder:
            logger.debug(
                "position_bias_skip_too_few",
                num_chunks=len(chunks),
                threshold=self.min_chunks_for_reorder,
            )
            return chunks

        if self.strategy == "preserve":
            return chunks
        elif self.strategy == "bookends":
            return self._bookends_reorder(chunks)
        elif self.strategy == "alternating":
            return self._alternating_reorder(chunks)
        else:
            logger.warning(f"Unknown strategy: {self.strategy}, using alternating")
            return self._alternating_reorder(chunks)

    def _alternating_reorder(self, chunks: list[RankedChunk]) -> list[RankedChunk]:
        """
        Alternating placement: [1st, 3rd, 5th, ..., 6th, 4th, 2nd]

        Pattern:
        - Odd ranks (1, 3, 5, ...) at beginning
        - Even ranks (2, 4, 6, ...) at end (reversed)

        Example for 6 chunks:
        Original:  [1, 2, 3, 4, 5, 6]
        Reordered: [1, 3, 5, 6, 4, 2]

        Args:
            chunks: Sorted chunks

        Returns:
            Reordered chunks
        """
        odd_chunks = []  # positions 0, 2, 4, ... (1st, 3rd, 5th, ...)
        even_chunks = []  # positions 1, 3, 5, ... (2nd, 4th, 6th, ...)

        for i, chunk in enumerate(chunks):
            if i % 2 == 0:
                odd_chunks.append(chunk)
            else:
                even_chunks.append(chunk)

        # Odd chunks at start, even chunks at end (reversed)
        reordered = odd_chunks + list(reversed(even_chunks))

        logger.info(
            "position_bias_alternating",
            num_chunks=len(chunks),
            num_odd=len(odd_chunks),
            num_even=len(even_chunks),
        )

        return reordered

    def _bookends_reorder(self, chunks: list[RankedChunk]) -> list[RankedChunk]:
        """
        Bookends strategy: Best chunks at start and end only.

        Pattern:
        - Top 20% at start
        - Middle 60% in middle (unchanged)
        - Top 20% at end

        Example for 10 chunks:
        Original:  [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        Reordered: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]  # with best spread to edges

        Args:
            chunks: Sorted chunks

        Returns:
            Reordered chunks
        """
        n = len(chunks)
        top_k = max(1, n // 5)  # Top 20%

        # Split into top and rest
        top_chunks = chunks[:top_k]
        middle_chunks = chunks[top_k:]

        if len(top_chunks) < 2:
            return chunks  # Not enough to split

        # Place first half of top at start, second half at end
        start_chunks = top_chunks[: len(top_chunks) // 2]
        end_chunks = top_chunks[len(top_chunks) // 2 :]

        reordered = start_chunks + middle_chunks + end_chunks

        logger.info(
            "position_bias_bookends",
            num_chunks=n,
            num_start=len(start_chunks),
            num_end=len(end_chunks),
        )

        return reordered


class PositionAwareRanker:
    """
    Position-aware ranking that considers both relevance and position.

    Assigns position-based weights to adjust final scores.
    """

    def __init__(
        self,
        use_position_weights: bool = True,
        edge_boost: float = 1.2,  # Boost for edges
        middle_penalty: float = 0.9,  # Penalty for middle
    ):
        """
        Initialize position-aware ranker.

        Args:
            use_position_weights: Enable position weighting
            edge_boost: Score multiplier for edge positions
            middle_penalty: Score multiplier for middle positions
        """
        self.use_position_weights = use_position_weights
        self.edge_boost = edge_boost
        self.middle_penalty = middle_penalty

    def get_position_weight(self, position: int, total: int) -> float:
        """
        Get position-based weight.

        Pattern: High at edges, low in middle

        Args:
            position: Item position (0-indexed)
            total: Total items

        Returns:
            Position weight (0.5-1.5)
        """
        if not self.use_position_weights:
            return 1.0

        if total < 3:
            return 1.0

        # Normalize position to 0-1
        norm_pos = position / (total - 1)

        # U-shaped weight: high at 0 and 1, low at 0.5
        # Using quadratic: weight = 1 - 4*(norm_pos - 0.5)^2 * penalty
        distance_from_edge = abs(norm_pos - 0.5)

        if distance_from_edge < 0.25:  # Middle 50%
            weight = self.middle_penalty
        else:  # Edges
            weight = self.edge_boost

        return weight

    def apply_position_weights(
        self,
        chunks: list[RankedChunk],
    ) -> list[RankedChunk]:
        """
        Apply position weights to chunk scores.

        Args:
            chunks: Ordered chunks

        Returns:
            Chunks with position-adjusted scores
        """
        if not self.use_position_weights:
            return chunks

        weighted_chunks = []
        total = len(chunks)

        for i, chunk in enumerate(chunks):
            pos_weight = self.get_position_weight(i, total)
            weighted_score = chunk.score * pos_weight

            # Create new chunk with adjusted score
            weighted_chunk = RankedChunk(
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                score=weighted_score,
                original_rank=chunk.original_rank,
                metadata={
                    **chunk.metadata,
                    "position_weight": pos_weight,
                    "original_score": chunk.score,
                },
            )
            weighted_chunks.append(weighted_chunk)

        logger.debug(
            "position_weights_applied",
            num_chunks=total,
            avg_weight=sum(self.get_position_weight(i, total) for i in range(total)) / total,
        )

        return weighted_chunks


def mitigate_lost_in_middle(
    chunks: list[dict[str, Any]],
    strategy: str = "alternating",
    apply_weights: bool = False,
) -> list[dict[str, Any]]:
    """
    Convenience function to mitigate Lost-in-the-Middle effect.

    Args:
        chunks: List of chunk dicts with 'id', 'content', 'score'
        strategy: Reordering strategy (alternating/bookends/preserve)
        apply_weights: Whether to apply position weights

    Returns:
        Reordered chunks
    """
    # Convert to RankedChunk
    ranked_chunks = [
        RankedChunk(
            chunk_id=chunk.get("id", f"chunk_{i}"),
            content=chunk.get("content", ""),
            score=chunk.get("score", 0.0),
            original_rank=i,
            metadata=chunk.get("metadata", {}),
        )
        for i, chunk in enumerate(chunks)
    ]

    # Reorder
    reorderer = PositionBiasReorderer(strategy=strategy)
    reordered = reorderer.reorder(ranked_chunks)

    # Apply weights if requested
    if apply_weights:
        ranker = PositionAwareRanker()
        reordered = ranker.apply_position_weights(reordered)

    # Convert back to dict
    result = [
        {
            "id": chunk.chunk_id,
            "content": chunk.content,
            "score": chunk.score,
            "original_rank": chunk.original_rank,
            "metadata": chunk.metadata,
        }
        for chunk in reordered
    ]

    logger.info(
        "lost_in_middle_mitigation_complete",
        num_chunks=len(result),
        strategy=strategy,
        apply_weights=apply_weights,
    )

    return result
