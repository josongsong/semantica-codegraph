"""
Observability Models

Models for explaining and tracing retrieval results.
"""

from dataclasses import dataclass, field


@dataclass
class SourceBreakdown:
    """
    Breakdown of scores from a single source.

    Attributes:
        source: Source name (lexical, vector, symbol, etc.)
        score: Score from this source (0-1)
        contribution: Contribution to final score
        details: Source-specific details
    """

    source: str
    score: float
    contribution: float
    details: dict = field(default_factory=dict)


@dataclass
class Explanation:
    """
    Explanation for a single search result.

    Attributes:
        chunk_id: Chunk identifier
        final_score: Final fused/priority score
        breakdown: Score breakdown by source
        reasoning: Human-readable reasoning
        metadata: Additional metadata
    """

    chunk_id: str
    final_score: float
    breakdown: list[SourceBreakdown] = field(default_factory=list)
    reasoning: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class RetrievalTrace:
    """
    Complete trace of retrieval process.

    Attributes:
        query: Original query
        intent: Detected intent
        scope_type: Scope selection type
        num_sources_queried: Number of sources queried
        source_results: Results per source
        fusion_method: Fusion method used
        reranking_applied: Whether reranking was applied
        total_latency_ms: Total latency
        stage_latencies: Latency per stage
    """

    query: str
    intent: str
    scope_type: str
    num_sources_queried: int = 0
    source_results: dict = field(default_factory=dict)
    fusion_method: str = "weighted"
    reranking_applied: bool = False
    total_latency_ms: float = 0
    stage_latencies: dict = field(default_factory=dict)
