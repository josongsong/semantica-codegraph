"""
Score Normalizer

Normalizes scores from different indexes to a common scale (0-1).
"""

from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class ScoreNormalizer:
    """
    Normalizes scores from different sources to 0-1 range.

    Different indexes return scores in different ranges:
    - Lexical (Tantivy): BM25-based positive scores
    - Vector (Qdrant): cosine similarity (0-1) or distance metrics
    - Symbol (Memgraph): binary or count-based scores
    - Graph: depth-based scores (already 0-1 in our implementation)
    """

    def __init__(self, virtual_chunk_penalty: float = 0.8):
        """
        Initialize score normalizer.

        Args:
            virtual_chunk_penalty: Penalty multiplier for virtual chunks (0-1)
        """
        self.virtual_chunk_penalty = virtual_chunk_penalty

    def normalize_hits(self, hits: list[SearchHit], source: str) -> list[SearchHit]:
        """
        Normalize scores for a list of hits.

        Args:
            hits: List of search hits
            source: Source index name ("lexical", "vector", "symbol", "graph")

        Returns:
            List of hits with normalized scores
        """
        if not hits:
            return []

        # Different normalization strategies by source
        if source == "lexical":
            return self._normalize_lexical(hits)
        elif source == "vector":
            return self._normalize_vector(hits)
        elif source == "symbol":
            return self._normalize_symbol(hits)
        elif source == "graph":
            return self._normalize_graph(hits)
        else:
            # Unknown source - apply default min-max normalization
            logger.warning(
                f"Unknown source '{source}', applying default min-max normalization. "
                f"Consider adding explicit support for this source."
            )
            return self._normalize_lexical(hits)  # Use lexical normalization as fallback

    def _normalize_lexical(self, hits: list[SearchHit]) -> list[SearchHit]:
        """
        Normalize lexical scores using min-max normalization.

        Tantivy returns BM25 scores (positive floats).
        """
        if not hits:
            return []

        scores = [hit.score for hit in hits]
        max_score = max(scores)
        min_score = min(scores)

        # Avoid division by zero
        score_range = max_score - min_score
        if score_range == 0:
            score_range = 1.0

        normalized = []
        for hit in hits:
            normalized_score = (hit.score - min_score) / score_range

            # Apply virtual chunk penalty
            if self._is_virtual_chunk(hit):
                normalized_score *= self.virtual_chunk_penalty

            # Create new hit with normalized score
            normalized_hit = hit.model_copy(update={"score": normalized_score})
            normalized.append(normalized_hit)

        return normalized

    def _normalize_vector(self, hits: list[SearchHit]) -> list[SearchHit]:
        """
        Normalize vector scores.

        Qdrant typically returns cosine similarity (0-1) or distance metrics.
        Assuming scores are already in 0-1 range (cosine similarity).
        """
        normalized = []
        for hit in hits:
            # Assume score is already 0-1 (cosine similarity)
            normalized_score = hit.score

            # Clamp to 0-1
            normalized_score = max(0.0, min(1.0, normalized_score))

            # Apply virtual chunk penalty
            if self._is_virtual_chunk(hit):
                normalized_score *= self.virtual_chunk_penalty

            normalized_hit = hit.model_copy(update={"score": normalized_score})
            normalized.append(normalized_hit)

        return normalized

    def _normalize_symbol(self, hits: list[SearchHit]) -> list[SearchHit]:
        """
        Normalize symbol scores.

        Symbol index may return:
        - Binary scores (1.0 for exact match)
        - Count-based scores (number of references)
        - Confidence scores (0-1)
        """
        if not hits:
            return []

        scores = [hit.score for hit in hits]
        max_score = max(scores)

        # If all scores are <= 1.0, assume already normalized
        if max_score <= 1.0:
            return hits

        # Otherwise, normalize by max
        normalized = []
        for hit in hits:
            normalized_score = hit.score / max_score

            # Apply virtual chunk penalty
            if self._is_virtual_chunk(hit):
                normalized_score *= self.virtual_chunk_penalty

            normalized_hit = hit.model_copy(update={"score": normalized_score})
            normalized.append(normalized_hit)

        return normalized

    def _normalize_graph(self, hits: list[SearchHit]) -> list[SearchHit]:
        """
        Normalize graph expansion scores.

        Graph scores are already 0-1 in our implementation (depth-based).
        """
        # Graph scores are already normalized (0-1)
        # Just apply virtual chunk penalty if needed
        normalized = []
        for hit in hits:
            normalized_score = hit.score

            if self._is_virtual_chunk(hit):
                normalized_score *= self.virtual_chunk_penalty

            normalized_hit = hit.model_copy(update={"score": normalized_score})
            normalized.append(normalized_hit)

        return normalized

    def _is_virtual_chunk(self, hit: SearchHit) -> bool:
        """
        Check if hit corresponds to a virtual chunk.

        Virtual chunks are file-level or class-level chunks that
        don't have actual code content.

        Args:
            hit: Search hit

        Returns:
            True if virtual chunk
        """
        # Check metadata for virtual chunk indicator
        is_virtual = hit.metadata.get("is_virtual", False)

        # Alternatively, check chunk kind
        chunk_kind = hit.metadata.get("kind", "")
        if chunk_kind in ["file", "module"]:
            is_virtual = True

        return is_virtual
