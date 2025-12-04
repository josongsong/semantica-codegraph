"""
SOTA Memory Read Pipeline (Retrieval + Fusion)

Implements the read pipeline for memory retrieval:
1. Query Classification → Determine which buckets to query
2. Multi-Bucket Retrieval → Parallel query to relevant buckets
3. 3-Axis Scoring → Composite score (similarity + recency + importance)
4. Fusion → Merge and deduplicate results
5. Ranking → Final ordering

Based on patterns from:
- Generative Agents: 3-axis scoring (relevance, recency, importance)
- Mem0: Multi-source retrieval
- RAG systems: Reciprocal Rank Fusion
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Protocol

from src.common.observability import get_logger

from .models import (
    MemoryQueryResult,
    MemoryScore,
    MemoryType,
    MemoryUnit,
)

logger = get_logger(__name__)
# ============================================================
# Query Classification
# ============================================================


class QueryIntent(str, Enum):
    """Intent of memory query."""

    PROFILE = "profile"  # Who is the user?
    PREFERENCE = "preference"  # How does user like things?
    RECALL = "recall"  # What happened before?
    KNOWLEDGE = "knowledge"  # What do we know about X?
    DEBUG = "debug"  # How did we fix this before?
    GENERAL = "general"  # Search everything


@dataclass
class QueryAnalysis:
    """Result of query analysis."""

    intent: QueryIntent
    buckets: list[MemoryType]  # Which buckets to query
    filters: dict[str, Any]  # Filters to apply
    boost_factors: dict[MemoryType, float]  # Bucket-specific boosts
    keywords: list[str]  # Extracted keywords


class QueryClassifier:
    """Classify query intent and determine retrieval strategy."""

    # Intent detection patterns
    PROFILE_PATTERNS = [
        "who am i",
        "my name",
        "my role",
        "my expertise",
        "what do you know about me",
        "user info",
    ]

    PREFERENCE_PATTERNS = [
        "how do i like",
        "my preference",
        "i prefer",
        "my style",
        "how should you",
        "remember i",
    ]

    RECALL_PATTERNS = [
        "last time",
        "before",
        "previously",
        "when did",
        "what happened",
        "how did we",
        "remember when",
    ]

    DEBUG_PATTERNS = [
        "error",
        "bug",
        "fix",
        "debug",
        "exception",
        "traceback",
        "failed",
        "broken",
        "crash",
    ]

    KNOWLEDGE_PATTERNS = [
        "what is",
        "how does",
        "explain",
        "tell me about",
        "documentation",
        "api",
        "function",
        "class",
    ]

    def classify(self, query: str) -> QueryAnalysis:
        """
        Classify query and determine retrieval strategy.

        Args:
            query: Natural language query

        Returns:
            QueryAnalysis with intent and bucket selection
        """
        query_lower = query.lower()

        # Detect intent
        intent = self._detect_intent(query_lower)

        # Determine buckets based on intent
        buckets, boosts = self._select_buckets(intent)

        # Extract keywords for filtering
        keywords = self._extract_keywords(query)

        # Build filters
        filters = self._build_filters(query_lower, keywords)

        return QueryAnalysis(
            intent=intent,
            buckets=buckets,
            filters=filters,
            boost_factors=boosts,
            keywords=keywords,
        )

    def _detect_intent(self, query: str) -> QueryIntent:
        """Detect query intent from patterns."""
        scores = {
            QueryIntent.PROFILE: self._pattern_score(query, self.PROFILE_PATTERNS),
            QueryIntent.PREFERENCE: self._pattern_score(query, self.PREFERENCE_PATTERNS),
            QueryIntent.RECALL: self._pattern_score(query, self.RECALL_PATTERNS),
            QueryIntent.DEBUG: self._pattern_score(query, self.DEBUG_PATTERNS),
            QueryIntent.KNOWLEDGE: self._pattern_score(query, self.KNOWLEDGE_PATTERNS),
        }

        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        if best_score < 0.1:
            return QueryIntent.GENERAL

        return best_intent

    def _pattern_score(self, query: str, patterns: list[str]) -> float:
        """Score query against patterns."""
        matches = sum(1 for p in patterns if p in query)
        return min(1.0, matches / max(len(patterns) * 0.2, 1))

    def _select_buckets(self, intent: QueryIntent) -> tuple[list[MemoryType], dict[MemoryType, float]]:
        """Select buckets and boosts based on intent."""
        bucket_map = {
            QueryIntent.PROFILE: (
                [MemoryType.PROFILE],
                {MemoryType.PROFILE: 1.5},
            ),
            QueryIntent.PREFERENCE: (
                [MemoryType.PREFERENCE, MemoryType.PROFILE],
                {MemoryType.PREFERENCE: 1.5, MemoryType.PROFILE: 0.8},
            ),
            QueryIntent.RECALL: (
                [MemoryType.EPISODIC, MemoryType.SEMANTIC],
                {MemoryType.EPISODIC: 1.3, MemoryType.SEMANTIC: 1.0},
            ),
            QueryIntent.DEBUG: (
                [MemoryType.EPISODIC, MemoryType.FACT, MemoryType.SEMANTIC],
                {MemoryType.EPISODIC: 1.4, MemoryType.FACT: 1.2, MemoryType.SEMANTIC: 1.0},
            ),
            QueryIntent.KNOWLEDGE: (
                [MemoryType.FACT, MemoryType.SEMANTIC, MemoryType.EPISODIC],
                {MemoryType.FACT: 1.3, MemoryType.SEMANTIC: 1.2, MemoryType.EPISODIC: 0.8},
            ),
            QueryIntent.GENERAL: (
                [MemoryType.EPISODIC, MemoryType.FACT, MemoryType.SEMANTIC, MemoryType.PREFERENCE],
                {MemoryType.EPISODIC: 1.0, MemoryType.FACT: 1.0, MemoryType.SEMANTIC: 1.0, MemoryType.PREFERENCE: 0.8},
            ),
        }

        return bucket_map.get(intent, bucket_map[QueryIntent.GENERAL])

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract keywords from query."""
        import re

        # Remove common words
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "about",
            "how",
            "what",
            "when",
            "where",
            "who",
            "which",
            "this",
            "that",
            "i",
            "you",
            "we",
            "they",
            "it",
            "my",
            "your",
            "our",
            "their",
        }

        # Extract words
        words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", query.lower())

        # Filter stopwords and short words
        keywords = [w for w in words if w not in stopwords and len(w) >= 3]

        return keywords[:10]  # Limit keywords

    def _build_filters(self, query: str, keywords: list[str]) -> dict[str, Any]:
        """Build filters from query."""
        filters: dict[str, Any] = {}

        # Time-based filters
        if "today" in query:
            filters["min_date"] = datetime.now().replace(hour=0, minute=0, second=0)
        elif "yesterday" in query:
            filters["min_date"] = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0)
            filters["max_date"] = datetime.now().replace(hour=0, minute=0, second=0)
        elif "last week" in query:
            filters["min_date"] = datetime.now() - timedelta(days=7)
        elif "last month" in query:
            filters["min_date"] = datetime.now() - timedelta(days=30)

        # Error type filter
        error_types = ["typeerror", "keyerror", "valueerror", "indexerror", "attributeerror"]
        for err in error_types:
            if err in query:
                filters["error_type"] = err.title()
                break

        return filters


# ============================================================
# 3-Axis Scoring (Generative Agents style)
# ============================================================


@dataclass
class ScoringConfig:
    """Configuration for 3-axis scoring."""

    # Weights (should sum to 1.0)
    w_similarity: float = 0.5  # Semantic similarity weight
    w_recency: float = 0.3  # Time decay weight
    w_importance: float = 0.2  # Stored importance weight

    # Recency decay
    recency_half_life_hours: float = 24.0  # Time for recency to halve

    # Importance normalization
    importance_min: float = 0.0
    importance_max: float = 1.0


class ThreeAxisScorer:
    """
    3-Axis Memory Scorer (Generative Agents pattern).

    score = w_sim * similarity + w_rec * recency + w_imp * importance

    Where:
    - similarity: Embedding cosine similarity (0-1)
    - recency: Exponential decay based on time (0-1)
    - importance: Stored importance score (0-1)
    """

    def __init__(self, config: ScoringConfig | None = None):
        """
        Initialize scorer.

        Args:
            config: Scoring configuration
        """
        self.config = config or ScoringConfig()

    def score(
        self,
        memory: MemoryUnit,
        similarity: float,
        now: datetime | None = None,
    ) -> MemoryScore:
        """
        Calculate composite score for a memory.

        Args:
            memory: Memory unit to score
            similarity: Embedding similarity (0-1)
            now: Current time (default: datetime.now())

        Returns:
            MemoryScore with component scores
        """
        now = now or datetime.now()

        # Calculate recency score
        recency = self._calculate_recency(memory.created_at, now)

        # Normalize importance
        importance = self._normalize_importance(memory.importance)

        return MemoryScore(
            memory_id=memory.id,
            similarity=similarity,
            recency=recency,
            importance=importance,
            w_similarity=self.config.w_similarity,
            w_recency=self.config.w_recency,
            w_importance=self.config.w_importance,
        )

    def score_batch(
        self,
        memories: list[MemoryUnit],
        similarities: list[float],
        now: datetime | None = None,
    ) -> list[MemoryScore]:
        """Score multiple memories."""
        now = now or datetime.now()
        return [self.score(mem, sim, now) for mem, sim in zip(memories, similarities, strict=False)]

    def _calculate_recency(self, created_at: datetime, now: datetime) -> float:
        """
        Calculate recency score using exponential decay.

        recency = exp(-lambda * hours_elapsed)

        Where lambda = ln(2) / half_life
        """
        # Calculate hours elapsed
        delta = now - created_at
        hours_elapsed = delta.total_seconds() / 3600.0

        # Exponential decay
        decay_rate = math.log(2) / self.config.recency_half_life_hours
        recency = math.exp(-decay_rate * hours_elapsed)

        return max(0.0, min(1.0, recency))

    def _normalize_importance(self, importance: float) -> float:
        """Normalize importance to 0-1 range."""
        normalized = (importance - self.config.importance_min) / (
            self.config.importance_max - self.config.importance_min
        )
        return max(0.0, min(1.0, normalized))


# ============================================================
# Result Fusion
# ============================================================


class FusionStrategy(Protocol):
    """Protocol for result fusion strategies."""

    def fuse(
        self,
        results: dict[MemoryType, list[tuple[MemoryUnit, MemoryScore]]],
        bucket_boosts: dict[MemoryType, float],
    ) -> list[tuple[MemoryUnit, MemoryScore]]:
        """Fuse results from multiple buckets."""
        ...


class WeightedFusion:
    """
    Weighted fusion of multi-bucket results.

    Applies bucket-specific boosts and deduplicates.
    """

    def __init__(self, dedup_threshold: float = 0.95):
        """
        Initialize weighted fusion.

        Args:
            dedup_threshold: Similarity threshold for deduplication
        """
        self.dedup_threshold = dedup_threshold

    def fuse(
        self,
        results: dict[MemoryType, list[tuple[MemoryUnit, MemoryScore]]],
        bucket_boosts: dict[MemoryType, float],
    ) -> list[tuple[MemoryUnit, MemoryScore]]:
        """
        Fuse results from multiple buckets.

        Args:
            results: Results per bucket
            bucket_boosts: Boost factors per bucket

        Returns:
            Fused and deduplicated results
        """
        all_results: list[tuple[MemoryUnit, MemoryScore]] = []

        # Collect all results with bucket boost
        for bucket, bucket_results in results.items():
            boost = bucket_boosts.get(bucket, 1.0)

            for memory, score in bucket_results:
                # Apply bucket boost to composite score
                boosted_score = MemoryScore(
                    memory_id=score.memory_id,
                    similarity=score.similarity,
                    recency=score.recency,
                    importance=score.importance,
                    w_similarity=score.w_similarity * boost,
                    w_recency=score.w_recency,
                    w_importance=score.w_importance,
                )
                all_results.append((memory, boosted_score))

        # Deduplicate by content similarity
        deduped = self._deduplicate(all_results)

        # Sort by composite score
        deduped.sort(key=lambda x: x[1].composite_score, reverse=True)

        return deduped

    def _deduplicate(
        self,
        results: list[tuple[MemoryUnit, MemoryScore]],
    ) -> list[tuple[MemoryUnit, MemoryScore]]:
        """Deduplicate results by content."""
        seen_contents: list[str] = []
        deduped: list[tuple[MemoryUnit, MemoryScore]] = []

        for memory, score in results:
            # Check if similar content already seen
            is_dup = False
            for seen in seen_contents:
                if self._content_similar(memory.content, seen):
                    is_dup = True
                    break

            if not is_dup:
                seen_contents.append(memory.content)
                deduped.append((memory, score))

        return deduped

    def _content_similar(self, a: str, b: str) -> bool:
        """Check if two contents are similar (simple Jaccard)."""
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())

        if not words_a or not words_b:
            return a == b

        intersection = len(words_a & words_b)
        union = len(words_a | words_b)

        jaccard = intersection / union if union > 0 else 0
        return jaccard >= self.dedup_threshold


class ReciprocalRankFusion:
    """
    Reciprocal Rank Fusion (RRF) for multi-bucket results.

    RRF_score = sum(1 / (k + rank_i)) for each bucket i

    Good for combining results from different ranking systems.
    """

    def __init__(self, k: int = 60, dedup_threshold: float = 0.95):
        """
        Initialize RRF.

        Args:
            k: RRF constant (higher = less emphasis on top ranks)
            dedup_threshold: Similarity threshold for deduplication
        """
        self.k = k
        self.dedup_threshold = dedup_threshold

    def fuse(
        self,
        results: dict[MemoryType, list[tuple[MemoryUnit, MemoryScore]]],
        bucket_boosts: dict[MemoryType, float],
    ) -> list[tuple[MemoryUnit, MemoryScore]]:
        """
        Fuse using Reciprocal Rank Fusion.

        Args:
            results: Results per bucket
            bucket_boosts: Boost factors per bucket (used as weight multipliers)

        Returns:
            Fused and ranked results
        """
        # Calculate RRF scores
        rrf_scores: dict[str, float] = {}
        memory_map: dict[str, MemoryUnit] = {}
        score_map: dict[str, MemoryScore] = {}

        for bucket, bucket_results in results.items():
            boost = bucket_boosts.get(bucket, 1.0)

            for rank, (memory, score) in enumerate(bucket_results):
                # RRF contribution from this bucket
                rrf_contribution = boost / (self.k + rank + 1)

                if memory.id in rrf_scores:
                    rrf_scores[memory.id] += rrf_contribution
                else:
                    rrf_scores[memory.id] = rrf_contribution
                    memory_map[memory.id] = memory
                    score_map[memory.id] = score

        # Create fused results
        fused_results: list[tuple[MemoryUnit, MemoryScore]] = []

        for mem_id, rrf_score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True):
            memory = memory_map[mem_id]
            original_score = score_map[mem_id]

            # Create new score with RRF as similarity component
            fused_score = MemoryScore(
                memory_id=mem_id,
                similarity=rrf_score,  # Use RRF as similarity proxy
                recency=original_score.recency,
                importance=original_score.importance,
                w_similarity=0.6,  # Higher weight for RRF
                w_recency=0.25,
                w_importance=0.15,
            )

            fused_results.append((memory, fused_score))

        # Deduplicate
        return self._deduplicate(fused_results)

    def _deduplicate(
        self,
        results: list[tuple[MemoryUnit, MemoryScore]],
    ) -> list[tuple[MemoryUnit, MemoryScore]]:
        """Deduplicate results by content."""
        seen_contents: list[str] = []
        deduped: list[tuple[MemoryUnit, MemoryScore]] = []

        for memory, score in results:
            is_dup = False
            for seen in seen_contents:
                if self._content_similar(memory.content, seen):
                    is_dup = True
                    break

            if not is_dup:
                seen_contents.append(memory.content)
                deduped.append((memory, score))

        return deduped

    def _content_similar(self, a: str, b: str) -> bool:
        """Check if two contents are similar."""
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())

        if not words_a or not words_b:
            return a == b

        intersection = len(words_a & words_b)
        union = len(words_a | words_b)

        jaccard = intersection / union if union > 0 else 0
        return jaccard >= self.dedup_threshold


# ============================================================
# Read Pipeline
# ============================================================


@dataclass
class ReadPipelineConfig:
    """Configuration for read pipeline."""

    # Scoring
    scoring: ScoringConfig = field(default_factory=ScoringConfig)

    # Limits
    per_bucket_limit: int = 20
    final_limit: int = 10

    # Fusion
    fusion_strategy: str = "weighted"  # "weighted" or "rrf"
    rrf_k: int = 60

    # Deduplication
    dedup_threshold: float = 0.9


class MemoryRetrievalStore(Protocol):
    """Protocol for memory retrieval backends."""

    async def retrieve(
        self,
        query: str,
        memory_types: list[MemoryType],
        filters: dict[str, Any],
        limit: int,
    ) -> dict[MemoryType, list[tuple[MemoryUnit, float]]]:
        """
        Retrieve memories with similarity scores.

        Returns: {bucket: [(memory, similarity), ...]}
        """
        ...


class MemoryReadPipeline:
    """
    SOTA Memory Read Pipeline.

    Process:
    1. Query Classification → Determine intent and buckets
    2. Multi-Bucket Retrieval → Parallel query to relevant buckets
    3. 3-Axis Scoring → Calculate composite scores
    4. Fusion → Merge and deduplicate
    5. Ranking → Return top results
    """

    def __init__(
        self,
        retrieval_store: MemoryRetrievalStore,
        config: ReadPipelineConfig | None = None,
    ):
        """
        Initialize read pipeline.

        Args:
            retrieval_store: Backend for memory retrieval
            config: Pipeline configuration
        """
        self.store = retrieval_store
        self.config = config or ReadPipelineConfig()

        # Initialize components
        self.query_classifier = QueryClassifier()
        self.scorer = ThreeAxisScorer(self.config.scoring)

        # Select fusion strategy
        if self.config.fusion_strategy == "rrf":
            self.fusion = ReciprocalRankFusion(
                k=self.config.rrf_k,
                dedup_threshold=self.config.dedup_threshold,
            )
        else:
            self.fusion = WeightedFusion(
                dedup_threshold=self.config.dedup_threshold,
            )

    async def query(
        self,
        query: str,
        project_id: str | None = None,
        user_id: str | None = None,
        limit: int | None = None,
    ) -> MemoryQueryResult:
        """
        Execute memory query through the pipeline.

        Args:
            query: Natural language query
            project_id: Optional project filter
            user_id: Optional user filter
            limit: Override result limit

        Returns:
            MemoryQueryResult with ranked memories
        """
        import time

        start_time = time.time()

        # Step 1: Classify query
        analysis = self.query_classifier.classify(query)
        logger.debug(f"Query classified as {analysis.intent}, buckets: {analysis.buckets}")

        # Add project/user filters
        filters = analysis.filters.copy()
        if project_id:
            filters["project_id"] = project_id
        if user_id:
            filters["user_id"] = user_id

        # Step 2: Multi-bucket retrieval
        raw_results = await self.store.retrieve(
            query=query,
            memory_types=analysis.buckets,
            filters=filters,
            limit=self.config.per_bucket_limit,
        )

        # Step 3: Apply 3-axis scoring
        scored_results: dict[MemoryType, list[tuple[MemoryUnit, MemoryScore]]] = {}
        now = datetime.now()

        for bucket, bucket_results in raw_results.items():
            scored = []
            for memory, similarity in bucket_results:
                score = self.scorer.score(memory, similarity, now)
                scored.append((memory, score))
            scored_results[bucket] = scored

        # Step 4: Fusion
        fused = self.fusion.fuse(scored_results, analysis.boost_factors)

        # Step 5: Limit results
        final_limit = limit or self.config.final_limit
        final_results = fused[:final_limit]

        # Build result
        retrieval_time = (time.time() - start_time) * 1000

        return MemoryQueryResult(
            memories=[mem for mem, _ in final_results],
            scores=[score for _, score in final_results],
            query_type=analysis.buckets[0] if analysis.buckets else None,
            total_candidates=sum(len(r) for r in raw_results.values()),
            retrieval_time_ms=retrieval_time,
        )

    async def query_by_type(
        self,
        query: str,
        memory_type: MemoryType,
        project_id: str | None = None,
        limit: int = 10,
    ) -> list[tuple[MemoryUnit, MemoryScore]]:
        """
        Query specific memory bucket.

        Args:
            query: Natural language query
            memory_type: Specific bucket to query
            project_id: Optional project filter
            limit: Result limit

        Returns:
            List of (memory, score) tuples
        """
        filters = {}
        if project_id:
            filters["project_id"] = project_id

        raw_results = await self.store.retrieve(
            query=query,
            memory_types=[memory_type],
            filters=filters,
            limit=limit,
        )

        # Score results
        bucket_results = raw_results.get(memory_type, [])
        now = datetime.now()

        scored = [(mem, self.scorer.score(mem, sim, now)) for mem, sim in bucket_results]

        # Sort by composite score
        scored.sort(key=lambda x: x[1].composite_score, reverse=True)

        return scored[:limit]


# ============================================================
# Factory Functions
# ============================================================


def create_read_pipeline(
    retrieval_store: MemoryRetrievalStore,
    config: ReadPipelineConfig | None = None,
) -> MemoryReadPipeline:
    """
    Create configured read pipeline.

    Args:
        retrieval_store: Memory retrieval backend
        config: Pipeline configuration

    Returns:
        Configured MemoryReadPipeline
    """
    return MemoryReadPipeline(
        retrieval_store=retrieval_store,
        config=config or ReadPipelineConfig(),
    )


def create_scorer(
    w_similarity: float = 0.5,
    w_recency: float = 0.3,
    w_importance: float = 0.2,
    recency_half_life_hours: float = 24.0,
) -> ThreeAxisScorer:
    """
    Create configured 3-axis scorer.

    Args:
        w_similarity: Similarity weight
        w_recency: Recency weight
        w_importance: Importance weight
        recency_half_life_hours: Recency decay half-life

    Returns:
        Configured ThreeAxisScorer
    """
    config = ScoringConfig(
        w_similarity=w_similarity,
        w_recency=w_recency,
        w_importance=w_importance,
        recency_half_life_hours=recency_half_life_hours,
    )
    return ThreeAxisScorer(config)
