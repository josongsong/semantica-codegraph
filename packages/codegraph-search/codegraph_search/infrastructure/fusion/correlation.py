"""
Correlation-aware Fusion v2

Enhances fusion by considering correlations between different search sources.
"""

from typing import TYPE_CHECKING

from codegraph_search.infrastructure.fusion.engine import FusedHit
from codegraph_search.infrastructure.fusion.weights import get_weights_for_intent
from codegraph_search.infrastructure.intent.models import QueryIntent

if TYPE_CHECKING:
    from codegraph_search.infrastructure.multi_index.orchestrator import MultiIndexResult
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class CorrelationAwareFusion:
    """
    Correlation-aware fusion engine.

    Boosts or penalizes scores based on source correlations:
    - Lexical + Symbol both high → boost (likely correct symbol)
    - Vector-only high, others low → penalty (semantic drift risk)
    - Symbol + Graph both high → boost (structural consistency)
    """

    # Correlation rules: (source1, source2) → boost/penalty
    CORRELATION_RULES = {
        ("lexical", "symbol"): +0.15,  # Both high → boost
        ("symbol", "graph"): +0.10,  # Both high → boost (structural)
        ("vector", "!lexical"): -0.10,  # Vector-only → penalty
        ("vector", "!symbol"): -0.05,  # Vector without symbol → mild penalty
    }

    # Thresholds for "high" scores
    HIGH_SCORE_THRESHOLD = 0.7

    # Semantic drift penalty (when vector-only is very high)
    SEMANTIC_DRIFT_PENALTY = 0.6  # Multiply score by this

    def __init__(self):
        """Initialize correlation-aware fusion."""
        pass

    def fuse(
        self,
        multi_result: "MultiIndexResult",
        intent: QueryIntent,
        repomap_importance: dict[str, float] | None = None,
    ) -> list[FusedHit]:
        """
        Fuse multi-index results with correlation awareness.

        Args:
            multi_result: Results from multiple indexes
            intent: Query intent
            repomap_importance: RepoMap importance scores

        Returns:
            List of FusedHit with correlation-adjusted scores
        """
        from collections import defaultdict

        from codegraph_search.infrastructure.fusion.normalizer import ScoreNormalizer

        # Get weights for this intent
        weights = get_weights_for_intent(intent.kind)

        # Normalize scores
        normalizer = ScoreNormalizer()
        normalized_results = {
            "lexical": normalizer.normalize_hits(multi_result.lexical_hits, "lexical"),
            "vector": normalizer.normalize_hits(multi_result.vector_hits, "vector"),
            "symbol": normalizer.normalize_hits(multi_result.symbol_hits, "symbol"),
            "graph": normalizer.normalize_hits(multi_result.graph_hits, "graph"),
        }

        # Group by chunk_id
        from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit

        chunk_hits: dict[str, dict[str, SearchHit]] = defaultdict(dict)

        for source, hits in normalized_results.items():
            for hit in hits:
                chunk_hits[hit.chunk_id][source] = hit

        # Calculate fused scores with correlation adjustments
        fused_hits = []

        for chunk_id, source_hits in chunk_hits.items():
            # Base weighted fusion
            base_score = 0.0
            sources = {}

            for source, hit in source_hits.items():
                weight = weights.get(source, 0.0)
                contribution = hit.score * weight
                base_score += contribution
                sources[source] = hit.score

            # Apply correlation adjustments
            adjusted_score = self._apply_correlation_adjustments(base_score, sources)

            # Primary source
            primary_source = max(sources, key=lambda s: sources[s] * weights.get(s, 0.0))
            representative_hit = source_hits[primary_source]

            # Priority score (same as Phase 1)
            from codegraph_search.infrastructure.fusion.weights import (
                PRIORITY_FUSED_WEIGHT,
                PRIORITY_REPOMAP_WEIGHT,
                PRIORITY_SYMBOL_WEIGHT,
            )

            priority_score = PRIORITY_FUSED_WEIGHT * adjusted_score

            if repomap_importance and chunk_id in repomap_importance:
                priority_score += PRIORITY_REPOMAP_WEIGHT * repomap_importance[chunk_id]

            if "symbol" in source_hits:
                priority_score += PRIORITY_SYMBOL_WEIGHT * source_hits["symbol"].score

            priority_score = max(0.0, min(1.0, priority_score))

            # Create fused hit
            fused_hit = FusedHit(
                chunk_id=chunk_id,
                file_path=representative_hit.file_path,
                symbol_id=representative_hit.symbol_id,
                fused_score=adjusted_score,
                priority_score=priority_score,
                sources=sources,
                metadata={
                    **representative_hit.metadata,
                    "base_score": base_score,
                    "correlation_adjustment": adjusted_score - base_score,
                },
                primary_source=primary_source,
            )

            fused_hits.append(fused_hit)

        # Sort by priority score
        fused_hits.sort(key=lambda h: h.priority_score, reverse=True)

        logger.info(
            f"Correlation-aware fusion: {len(chunk_hits)} unique chunks, "
            f"avg correlation adjustment: "
            f"{sum(h.metadata.get('correlation_adjustment', 0) for h in fused_hits) / len(fused_hits):.3f}"
        )

        return fused_hits

    def _apply_correlation_adjustments(self, base_score: float, sources: dict[str, float]) -> float:
        """
        Apply correlation-based score adjustments.

        Args:
            base_score: Base weighted fusion score
            sources: Dict of source → normalized score

        Returns:
            Adjusted score
        """
        adjusted_score = base_score

        # Rule 1: Lexical + Symbol both high → boost
        if (
            sources.get("lexical", 0) >= self.HIGH_SCORE_THRESHOLD
            and sources.get("symbol", 0) >= self.HIGH_SCORE_THRESHOLD
        ):
            adjusted_score += 0.15
            logger.debug("Correlation boost: lexical + symbol both high (+0.15)")

        # Rule 2: Symbol + Graph both high → boost
        if (
            sources.get("symbol", 0) >= self.HIGH_SCORE_THRESHOLD
            and sources.get("graph", 0) >= self.HIGH_SCORE_THRESHOLD
        ):
            adjusted_score += 0.10
            logger.debug("Correlation boost: symbol + graph both high (+0.10)")

        # Rule 3: Vector-only high (semantic drift risk)
        vector_score = sources.get("vector", 0)
        lexical_score = sources.get("lexical", 0)
        symbol_score = sources.get("symbol", 0)

        if vector_score >= 0.85:
            # Very high vector score
            other_scores_low = max(lexical_score, symbol_score) < 0.2

            if other_scores_low:
                # Semantic drift penalty
                adjusted_score *= self.SEMANTIC_DRIFT_PENALTY
                logger.debug(
                    f"Semantic drift penalty: vector={vector_score:.2f}, others<0.2 (*{self.SEMANTIC_DRIFT_PENALTY})"
                )

        # Rule 4: Vector without lexical → mild penalty
        if vector_score >= self.HIGH_SCORE_THRESHOLD and lexical_score < 0.3:
            adjusted_score -= 0.05
            logger.debug("Correlation penalty: vector without lexical (-0.05)")

        # Clamp to 0-1
        adjusted_score = max(0.0, min(1.0, adjusted_score))

        return adjusted_score
