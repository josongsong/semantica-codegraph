"""
Data models for Retriever v3.

Defines all data structures used in the v3 retrieval pipeline.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntentProbability:
    """
    Multi-label intent probability distribution.

    Attributes:
        symbol: Probability of symbol navigation intent (0-1)
        flow: Probability of flow/trace intent (0-1)
        concept: Probability of concept search intent (0-1)
        code: Probability of code search intent (0-1)
        balanced: Probability of balanced search intent (0-1)
    """

    symbol: float = 0.0
    flow: float = 0.0
    concept: float = 0.0
    code: float = 0.0
    balanced: float = 0.0

    def __post_init__(self):
        """Validate that probabilities sum to ~1.0."""
        total = self.symbol + self.flow + self.concept + self.code + self.balanced
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Intent probabilities must sum to 1.0, got {total}")

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "flow": self.flow,
            "concept": self.concept,
            "code": self.code,
            "balanced": self.balanced,
        }

    def dominant_intent(self) -> str:
        """Get the intent with highest probability."""
        intents = self.to_dict()
        return max(intents, key=intents.get)  # type: ignore


@dataclass
class RankedHit:
    """
    Single hit from a retrieval strategy with rank information.

    Attributes:
        chunk_id: Chunk identifier
        strategy: Strategy name (vector, lexical, symbol, graph)
        rank: Rank position (0-based, 0 is best)
        raw_score: Original score from the strategy (optional, not used in fusion)
        file_path: File path (optional)
        symbol_id: Symbol identifier (optional)
        metadata: Additional metadata
    """

    chunk_id: str
    strategy: str
    rank: int
    raw_score: float = 0.0
    file_path: str | None = None
    symbol_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConsensusStats:
    """
    Consensus statistics for a chunk across multiple strategies.

    Attributes:
        num_strategies: Number of strategies that returned this chunk
        ranks: Dict of strategy → rank
        best_rank: Best (lowest) rank across all strategies
        avg_rank: Average rank across all strategies
        quality_factor: Quality factor based on average rank (0-1)
        consensus_factor: Final consensus boost factor (0-1.5)
    """

    num_strategies: int
    ranks: dict[str, int]
    best_rank: int
    avg_rank: float
    quality_factor: float
    consensus_factor: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "num_strategies": self.num_strategies,
            "ranks": self.ranks,
            "best_rank": self.best_rank,
            "avg_rank": self.avg_rank,
            "quality_factor": self.quality_factor,
            "consensus_factor": self.consensus_factor,
        }


@dataclass
class FeatureVector:
    """
    LTR-ready feature vector for a chunk.

    Contains all features used for ranking, suitable for Learning-to-Rank models.

    Attributes:
        chunk_id: Chunk identifier
        rank_vec: Rank from vector strategy (None if not present)
        rank_lex: Rank from lexical strategy (None if not present)
        rank_sym: Rank from symbol strategy (None if not present)
        rank_graph: Rank from graph strategy (None if not present)
        rrf_vec: RRF score from vector strategy
        rrf_lex: RRF score from lexical strategy
        rrf_sym: RRF score from symbol strategy
        rrf_graph: RRF score from graph strategy
        weight_vec: Intent-based weight for vector
        weight_lex: Intent-based weight for lexical
        weight_sym: Intent-based weight for symbol
        weight_graph: Intent-based weight for graph
        num_strategies: Number of strategies that returned this chunk
        best_rank: Best rank across all strategies
        avg_rank: Average rank across all strategies
        consensus_factor: Consensus boost factor
        chunk_size: Size of chunk in characters (if available)
        file_depth: Directory depth of file (if available)
        symbol_type: Symbol type (if available)
        metadata: Additional metadata
    """

    chunk_id: str

    # Strategy ranks
    rank_vec: int | None = None
    rank_lex: int | None = None
    rank_sym: int | None = None
    rank_graph: int | None = None

    # RRF scores
    rrf_vec: float = 0.0
    rrf_lex: float = 0.0
    rrf_sym: float = 0.0
    rrf_graph: float = 0.0

    # Intent weights
    weight_vec: float = 0.0
    weight_lex: float = 0.0
    weight_sym: float = 0.0
    weight_graph: float = 0.0

    # Consensus features
    num_strategies: int = 0
    best_rank: int = 999999
    avg_rank: float = 999999.0
    consensus_factor: float = 1.0

    # Metadata features
    chunk_size: int = 0
    file_depth: int = 0
    symbol_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_array(self) -> list[float]:
        """
        Convert to feature array for ML models.

        Returns:
            List of numeric features
        """
        return [
            float(self.rank_vec if self.rank_vec is not None else 999999),
            float(self.rank_lex if self.rank_lex is not None else 999999),
            float(self.rank_sym if self.rank_sym is not None else 999999),
            float(self.rank_graph if self.rank_graph is not None else 999999),
            self.rrf_vec,
            self.rrf_lex,
            self.rrf_sym,
            self.rrf_graph,
            self.weight_vec,
            self.weight_lex,
            self.weight_sym,
            self.weight_graph,
            float(self.num_strategies),
            float(self.best_rank),
            float(self.avg_rank),
            self.consensus_factor,
            float(self.chunk_size),
            float(self.file_depth),
        ]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "ranks": {
                "vector": self.rank_vec,
                "lexical": self.rank_lex,
                "symbol": self.rank_sym,
                "graph": self.rank_graph,
            },
            "rrf_scores": {
                "vector": self.rrf_vec,
                "lexical": self.rrf_lex,
                "symbol": self.rrf_sym,
                "graph": self.rrf_graph,
            },
            "weights": {
                "vector": self.weight_vec,
                "lexical": self.weight_lex,
                "symbol": self.weight_sym,
                "graph": self.weight_graph,
            },
            "consensus": {
                "num_strategies": self.num_strategies,
                "best_rank": self.best_rank,
                "avg_rank": self.avg_rank,
                "consensus_factor": self.consensus_factor,
            },
            "metadata": {
                "chunk_size": self.chunk_size,
                "file_depth": self.file_depth,
                "symbol_type": self.symbol_type,
            },
        }


@dataclass
class FusedResultV3:
    """
    Final fused result with ranking and explainability.

    Attributes:
        chunk_id: Chunk identifier
        file_path: File path
        symbol_id: Symbol identifier (if any)
        final_score: Final weighted + consensus score
        feature_vector: Full feature vector for this result
        consensus_stats: Consensus statistics
        metadata: Combined metadata
        explanation: Human-readable explanation of why this was ranked here
    """

    chunk_id: str
    file_path: str | None
    symbol_id: str | None
    final_score: float
    feature_vector: FeatureVector
    consensus_stats: ConsensusStats
    metadata: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "file_path": self.file_path,
            "symbol_id": self.symbol_id,
            "final_score": self.final_score,
            "feature_vector": self.feature_vector.to_dict(),
            "consensus_stats": self.consensus_stats.to_dict(),
            "metadata": self.metadata,
            "explanation": self.explanation,
        }
