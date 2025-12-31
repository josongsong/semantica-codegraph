"""
Git-aware Ranker

Reranks search results based on git history metrics and intent.
"""

import time
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger, record_histogram
from codegraph_search.infrastructure.fusion.engine import FusedHit
from codegraph_search.infrastructure.intent.models import IntentKind

if TYPE_CHECKING:
    from codegraph_search.infrastructure.intent.models import QueryIntent

logger = get_logger(__name__)


class GitAwareRanker:
    """
    Reranks search results using git history metrics.

    Intent-based git boosting:
    - FLOW_TRACE: Boost recently modified code (+20%)
    - CODE_SEARCH: Penalize hotspots (-10%, prefer stable code)
    - SYMBOL_NAV: Boost primary author code (+15%)
    - CONCEPT_SEARCH: Boost low-churn code (+10%, prefer stable docs)
    """

    def __init__(self, recency_days_threshold: int = 30, hotspot_penalty: float = 0.1):
        """
        Initialize git-aware ranker.

        Args:
            recency_days_threshold: Days threshold for recency boost (default: 30)
            hotspot_penalty: Penalty factor for hotspots (default: 0.1 = -10%)
        """
        self.recency_days_threshold = recency_days_threshold
        self.hotspot_penalty = hotspot_penalty

    def rerank(self, hits: list[FusedHit], intent: "QueryIntent") -> list[FusedHit]:
        """
        Rerank hits based on git metrics and intent.

        Args:
            hits: Fused hits to rerank
            intent: Query intent

        Returns:
            Reranked hits (sorted by adjusted priority_score)
        """
        if not hits:
            return hits

        start_time = time.perf_counter()

        # Apply intent-based git boosting
        for hit in hits:
            boost = self._calculate_git_boost(hit, intent.kind)
            if boost != 0.0:
                # Apply multiplicative boost to priority score
                hit.priority_score *= 1 + boost

                # Store boost in metadata for debugging
                hit.metadata["git_boost"] = round(boost, 3)

        # Re-sort by adjusted priority score
        hits.sort(key=lambda h: h.priority_score, reverse=True)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        record_histogram("retrieval_git_rerank_latency_ms", elapsed_ms)

        logger.debug(f"Git reranking complete in {elapsed_ms:.1f}ms")

        return hits

    def _calculate_git_boost(self, hit: FusedHit, intent_kind: IntentKind) -> float:
        """
        Calculate git-based boost factor for a hit.

        Args:
            hit: Fused hit
            intent_kind: Intent type

        Returns:
            Boost factor (e.g., 0.2 = +20%, -0.1 = -10%)
        """
        boost = 0.0

        # Extract git metrics from metadata
        last_modified_days = hit.metadata.get("git_last_modified_days", 9999)
        is_hotspot = hit.metadata.get("git_is_hotspot", False)
        churn_score = hit.metadata.get("git_churn_score", 0.0)

        # Intent-based boosting strategies

        if intent_kind == IntentKind.FLOW_TRACE:
            # FLOW_TRACE: Prefer recently modified code
            if last_modified_days <= 7:
                boost += 0.20  # Very recent: +20%
            elif last_modified_days <= self.recency_days_threshold:
                # Sigmoid boost: 7 days = +20%, 30 days = +5%
                boost += 0.20 * (1 / (1 + ((last_modified_days - 7) / 10)))

        elif intent_kind == IntentKind.CODE_SEARCH:
            # CODE_SEARCH: Penalize hotspots (prefer stable, simple code)
            if is_hotspot:
                boost -= self.hotspot_penalty
            elif churn_score < 0.3:
                # Stable code boost
                boost += 0.05

        elif intent_kind == IntentKind.SYMBOL_NAV:
            # SYMBOL_NAV: Neutral on git metrics (symbol match dominates)
            # But slightly prefer non-hotspots
            if is_hotspot:
                boost -= 0.05

        elif intent_kind == IntentKind.CONCEPT_SEARCH:
            # CONCEPT_SEARCH: Prefer stable, well-documented code
            if churn_score < 0.3:
                boost += 0.10  # Low churn = stable docs
            elif is_hotspot:
                boost -= 0.05  # Hotspot = may have outdated docs

        elif intent_kind == IntentKind.REPO_OVERVIEW:
            # REPO_OVERVIEW: Slight recency preference
            if last_modified_days <= 90:
                boost += 0.05

        return boost

    def get_recency_score(self, days_since_last_change: int) -> float:
        """
        Calculate recency score (0-1).

        Args:
            days_since_last_change: Days since last modification

        Returns:
            Recency score (1.0 = today, 0.0 = very old)
        """
        if days_since_last_change == 0:
            return 1.0

        # Exponential decay: half-life = 90 days
        import math

        return math.exp(-days_since_last_change / 90)
