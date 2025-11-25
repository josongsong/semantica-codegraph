"""
Fusion Engine

Fuses multi-index search results using weighted scores and deduplication.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.index.common.documents import SearchHit
from src.retriever.intent.models import QueryIntent

from .normalizer import ScoreNormalizer
from .weights import (
    PRIORITY_FUSED_WEIGHT,
    PRIORITY_REPOMAP_WEIGHT,
    PRIORITY_SYMBOL_WEIGHT,
    get_weights_for_intent,
)

if TYPE_CHECKING:
    from src.retriever.multi_index.orchestrator import MultiIndexResult

logger = logging.getLogger(__name__)


@dataclass
class FusedHit:
    """
    Fused search hit with combined scores.

    Attributes:
        chunk_id: Chunk identifier
        file_path: File path
        symbol_id: Symbol identifier (if any)
        fused_score: Weighted fusion of all source scores
        priority_score: Priority score for token packing
        sources: Dict of source → score
        metadata: Combined metadata
        primary_source: Primary source with highest contribution
    """

    chunk_id: str
    file_path: str | None
    symbol_id: str | None
    fused_score: float
    priority_score: float
    sources: dict[str, float] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    primary_source: str = "lexical"

    def to_search_hit(self) -> SearchHit:
        """Convert to SearchHit for compatibility."""
        return SearchHit(
            chunk_id=self.chunk_id,
            file_path=self.file_path,
            symbol_id=self.symbol_id,
            score=self.fused_score,
            source="fused",  # type: ignore
            metadata={
                **self.metadata,
                "fused_score": self.fused_score,
                "priority_score": self.priority_score,
                "sources": self.sources,
                "primary_source": self.primary_source,
            },
        )


class FusionEngine:
    """
    Fuses multi-index search results using weighted scoring.

    Combines hits from different sources (lexical, vector, symbol, graph)
    using intent-based weights and calculates priority scores for ranking.
    """

    def __init__(self, enable_dedup: bool = True):
        """
        Initialize fusion engine.

        Args:
            enable_dedup: Enable deduplication of overlapping chunks
        """
        self.normalizer = ScoreNormalizer()
        self.enable_dedup = enable_dedup

    def fuse(
        self,
        multi_result: "MultiIndexResult",
        intent: QueryIntent,
        repomap_importance: dict[str, float] | None = None,
    ) -> list[FusedHit]:
        """
        Fuse multi-index results into ranked list.

        Args:
            multi_result: Results from multiple indexes
            intent: Query intent
            repomap_importance: Dict mapping chunk_id → importance (0-1)

        Returns:
            List of FusedHit sorted by priority_score (descending)
        """
        # Get weights for this intent
        weights = get_weights_for_intent(intent.kind)

        # Normalize scores for each source
        normalized_results = {
            "lexical": self.normalizer.normalize_hits(multi_result.lexical_hits, "lexical"),
            "vector": self.normalizer.normalize_hits(multi_result.vector_hits, "vector"),
            "symbol": self.normalizer.normalize_hits(multi_result.symbol_hits, "symbol"),
            "graph": self.normalizer.normalize_hits(multi_result.graph_hits, "graph"),
        }

        # Group hits by chunk_id
        chunk_hits: dict[str, dict[str, SearchHit]] = defaultdict(dict)

        for source, hits in normalized_results.items():
            for hit in hits:
                chunk_hits[hit.chunk_id][source] = hit

        # Calculate fused scores
        fused_hits = []

        for chunk_id, source_hits in chunk_hits.items():
            # Calculate weighted fusion score
            fused_score = 0.0
            sources = {}

            for source, hit in source_hits.items():
                weight = weights.get(source, 0.0)
                contribution = hit.score * weight
                fused_score += contribution
                sources[source] = hit.score

            # Determine primary source (highest contribution)
            primary_source = max(sources, key=lambda s: sources[s] * weights.get(s, 0.0))

            # Get representative hit (from primary source)
            representative_hit = source_hits[primary_source]

            # Calculate priority score for token packing
            priority_score = self._calculate_priority_score(
                chunk_id=chunk_id,
                fused_score=fused_score,
                source_hits=source_hits,
                repomap_importance=repomap_importance,
            )

            # Create fused hit
            fused_hit = FusedHit(
                chunk_id=chunk_id,
                file_path=representative_hit.file_path,
                symbol_id=representative_hit.symbol_id,
                fused_score=fused_score,
                priority_score=priority_score,
                sources=sources,
                metadata=representative_hit.metadata,
                primary_source=primary_source,
            )

            fused_hits.append(fused_hit)

        # Sort by priority score
        fused_hits.sort(key=lambda h: h.priority_score, reverse=True)

        logger.info(
            f"Fusion complete: {len(chunk_hits)} unique chunks, "
            f"intent={intent.kind.value}, "
            f"avg_fused_score={sum(h.fused_score for h in fused_hits) / len(fused_hits):.3f}"
        )

        return fused_hits

    def _calculate_priority_score(
        self,
        chunk_id: str,
        fused_score: float,
        source_hits: dict[str, SearchHit],
        repomap_importance: dict[str, float] | None,
    ) -> float:
        """
        Calculate priority score for token packing.

        PriorityScore = 0.55 * fused_score
                      + 0.30 * repomap_importance
                      + 0.15 * symbol_confidence

        Args:
            chunk_id: Chunk identifier
            fused_score: Fused score from weighted combination
            source_hits: Hits from each source for this chunk
            repomap_importance: RepoMap importance scores

        Returns:
            Priority score (0-1)
        """
        # Component 1: Fused score (55%)
        priority = PRIORITY_FUSED_WEIGHT * fused_score

        # Component 2: RepoMap importance (30%)
        if repomap_importance and chunk_id in repomap_importance:
            importance = repomap_importance[chunk_id]
            priority += PRIORITY_REPOMAP_WEIGHT * importance

        # Component 3: Symbol confidence (15%)
        # If symbol index returned this hit with high score → high confidence
        if "symbol" in source_hits:
            symbol_score = source_hits["symbol"].score
            priority += PRIORITY_SYMBOL_WEIGHT * symbol_score

        # Clamp to 0-1
        priority = max(0.0, min(1.0, priority))

        return priority
