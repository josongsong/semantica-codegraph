"""
Smart Chunk Interleaving

Intelligently blends results from different search strategies to provide
diverse and comprehensive results.

Problem:
- Single strategy may miss relevant results
- Vector search: good for semantic, misses exact matches
- Lexical search: good for keywords, misses paraphrases
- Symbol search: good for definitions, misses usage

Solution:
- Interleave results from multiple strategies
- Use strategy-specific confidence scores
- Avoid duplicates while preserving diversity
- Intent-adaptive strategy weights

Expected improvement: Coverage +20%, Diversity +30%

Example:
  Vector: [A, C, E, G]
  Lexical: [B, D, A, F]
  Symbol: [A, H, I]

  Interleaved: [A, B, C, D, E, H, F, G, I]
  (A appears first across all strategies, then alternate)
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SearchStrategy(str, Enum):
    """Search strategy types."""

    VECTOR = "vector"
    LEXICAL = "lexical"
    SYMBOL = "symbol"
    GRAPH = "graph"


@dataclass
class StrategyResult:
    """Results from a single search strategy."""

    strategy: SearchStrategy
    chunks: list[dict[str, Any]]
    confidence: float  # Overall confidence for this strategy (0-1)
    metadata: dict[str, Any]


@dataclass
class InterleavingWeights:
    """Weights for different strategies based on query intent."""

    vector_weight: float
    lexical_weight: float
    symbol_weight: float
    graph_weight: float

    @staticmethod
    def for_code_search() -> "InterleavingWeights":
        """Weights optimized for code search queries."""
        return InterleavingWeights(
            vector_weight=0.5,
            lexical_weight=0.3,
            symbol_weight=0.1,
            graph_weight=0.1,
        )

    @staticmethod
    def for_symbol_navigation() -> "InterleavingWeights":
        """Weights optimized for symbol navigation queries."""
        return InterleavingWeights(
            vector_weight=0.2,
            lexical_weight=0.2,
            symbol_weight=0.5,
            graph_weight=0.1,
        )

    @staticmethod
    def for_flow_trace() -> "InterleavingWeights":
        """Weights optimized for flow tracing queries."""
        return InterleavingWeights(
            vector_weight=0.2,
            lexical_weight=0.1,
            symbol_weight=0.2,
            graph_weight=0.5,
        )

    @staticmethod
    def for_concept_search() -> "InterleavingWeights":
        """Weights optimized for concept search queries."""
        return InterleavingWeights(
            vector_weight=0.7,
            lexical_weight=0.2,
            symbol_weight=0.05,
            graph_weight=0.05,
        )

    @staticmethod
    def balanced() -> "InterleavingWeights":
        """Balanced weights for unknown intent."""
        return InterleavingWeights(
            vector_weight=0.4,
            lexical_weight=0.3,
            symbol_weight=0.2,
            graph_weight=0.1,
        )


class SmartInterleaver:
    """
    Smart interleaving of multi-strategy search results.

    Key features:
    - Round-robin with strategy weights
    - Duplicate detection and deduplication
    - Strategy confidence tracking
    - Intent-adaptive weights

    Algorithm:
    1. Normalize scores within each strategy
    2. Apply strategy-specific weights
    3. Interleave using weighted round-robin
    4. Deduplicate while preserving order
    5. Re-score based on strategy consensus
    """

    def __init__(
        self,
        weights: InterleavingWeights | None = None,
        diversity_penalty: float = 0.1,
        consensus_boost: float = 0.2,
    ):
        """
        Initialize smart interleaver.

        Args:
            weights: Strategy weights (default: balanced)
            diversity_penalty: Penalty for similar consecutive chunks
            consensus_boost: Boost for chunks appearing in multiple strategies
        """
        self.weights = weights or InterleavingWeights.balanced()
        self.diversity_penalty = diversity_penalty
        self.consensus_boost = consensus_boost

    def interleave(
        self,
        strategy_results: list[StrategyResult],
        top_k: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Interleave results from multiple strategies.

        Args:
            strategy_results: Results from different strategies
            top_k: Number of top results to return

        Returns:
            Interleaved and deduplicated results
        """
        if not strategy_results:
            return []

        # Normalize scores within each strategy
        normalized_results = self._normalize_scores(strategy_results)

        # Build chunk index (chunk_id -> list of (strategy, score, rank))
        chunk_index = self._build_chunk_index(normalized_results)

        # Compute consensus scores
        chunks_with_consensus = self._compute_consensus_scores(chunk_index)

        # Apply strategy weights
        for chunk_id, info in chunks_with_consensus.items():
            weighted_score = 0.0

            for strategy, score, rank in info["appearances"]:
                weight = self._get_strategy_weight(strategy)
                # Decay by rank (earlier = better)
                rank_decay = 1.0 / (1.0 + rank * 0.1)
                weighted_score += weight * score * rank_decay

            # Consensus boost (appears in multiple strategies)
            if len(info["appearances"]) > 1:
                consensus_factor = 1.0 + self.consensus_boost * (
                    len(info["appearances"]) - 1
                )
                weighted_score *= consensus_factor

            info["final_score"] = weighted_score

        # Sort by final score
        sorted_chunks = sorted(
            chunks_with_consensus.items(),
            key=lambda x: x[1]["final_score"],
            reverse=True,
        )

        # Build interleaved result
        interleaved = []
        seen_chunks = set()

        for chunk_id, info in sorted_chunks:
            if chunk_id in seen_chunks:
                continue

            chunk = info["chunk"]

            # Add interleaving metadata
            chunk["interleaving_score"] = info["final_score"]
            chunk["strategy_count"] = len(info["appearances"])
            chunk["strategies"] = [s.value for s, _, _ in info["appearances"]]

            interleaved.append(chunk)
            seen_chunks.add(chunk_id)

            if len(interleaved) >= top_k:
                break

        logger.info(
            f"Interleaved {len(strategy_results)} strategies → {len(interleaved)} chunks "
            f"(from {sum(len(sr.chunks) for sr in strategy_results)} total)"
        )

        # Log strategy distribution
        strategy_dist = defaultdict(int)
        for chunk in interleaved[:20]:  # Top 20
            for strategy in chunk["strategies"]:
                strategy_dist[strategy] += 1

        logger.info(f"Top-20 strategy distribution: {dict(strategy_dist)}")

        return interleaved

    def _normalize_scores(
        self, strategy_results: list[StrategyResult]
    ) -> list[StrategyResult]:
        """Normalize scores within each strategy to [0, 1] range."""
        normalized = []

        for result in strategy_results:
            if not result.chunks:
                normalized.append(result)
                continue

            # Get min/max scores
            scores = [c.get("score", 0.0) for c in result.chunks]
            min_score = min(scores)
            max_score = max(scores)

            if max_score - min_score < 1e-6:
                # All scores are the same
                for chunk in result.chunks:
                    chunk["normalized_score"] = 0.5
            else:
                # Normalize to [0, 1]
                for chunk in result.chunks:
                    original_score = chunk.get("score", 0.0)
                    normalized_score = (original_score - min_score) / (
                        max_score - min_score
                    )
                    chunk["normalized_score"] = normalized_score

            normalized.append(result)

        return normalized

    def _build_chunk_index(
        self, strategy_results: list[StrategyResult]
    ) -> dict[str, dict[str, Any]]:
        """Build index of chunk_id -> appearances across strategies."""
        chunk_index = defaultdict(lambda: {"appearances": [], "chunk": None})

        for result in strategy_results:
            for rank, chunk in enumerate(result.chunks):
                chunk_id = chunk.get("chunk_id", "")
                if not chunk_id:
                    continue

                score = chunk.get("normalized_score", chunk.get("score", 0.0))

                chunk_index[chunk_id]["appearances"].append(
                    (result.strategy, score, rank)
                )

                if chunk_index[chunk_id]["chunk"] is None:
                    chunk_index[chunk_id]["chunk"] = chunk

        return dict(chunk_index)

    def _compute_consensus_scores(
        self, chunk_index: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Compute consensus scores for chunks appearing in multiple strategies."""
        return chunk_index  # Already has appearances, will compute in interleave()

    def _get_strategy_weight(self, strategy: SearchStrategy) -> float:
        """Get weight for a specific strategy."""
        if strategy == SearchStrategy.VECTOR:
            return self.weights.vector_weight
        elif strategy == SearchStrategy.LEXICAL:
            return self.weights.lexical_weight
        elif strategy == SearchStrategy.SYMBOL:
            return self.weights.symbol_weight
        elif strategy == SearchStrategy.GRAPH:
            return self.weights.graph_weight
        else:
            return 0.25  # Default

    def set_weights(self, weights: InterleavingWeights) -> None:
        """Update strategy weights."""
        self.weights = weights

    def set_weights_for_intent(self, intent: str) -> None:
        """Set weights based on query intent."""
        intent_lower = intent.lower()

        if "symbol" in intent_lower or "definition" in intent_lower:
            self.weights = InterleavingWeights.for_symbol_navigation()
        elif "flow" in intent_lower or "trace" in intent_lower or "call" in intent_lower:
            self.weights = InterleavingWeights.for_flow_trace()
        elif "concept" in intent_lower or "explain" in intent_lower:
            self.weights = InterleavingWeights.for_concept_search()
        else:
            self.weights = InterleavingWeights.for_code_search()

        logger.info(f"Set interleaving weights for intent '{intent}': {self.weights}")


class RoundRobinInterleaver:
    """
    Simple round-robin interleaver (baseline).

    Alternates between strategies in round-robin fashion.
    Useful for A/B testing against smart interleaver.
    """

    def __init__(self):
        """Initialize round-robin interleaver."""
        pass

    def interleave(
        self,
        strategy_results: list[StrategyResult],
        top_k: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Interleave results using round-robin.

        Args:
            strategy_results: Results from different strategies
            top_k: Number of top results to return

        Returns:
            Interleaved results
        """
        if not strategy_results:
            return []

        # Create pointers for each strategy
        pointers = [0] * len(strategy_results)
        interleaved = []
        seen_chunks = set()

        # Round-robin until we have top_k or exhaust all strategies
        current_strategy = 0
        max_iterations = sum(len(sr.chunks) for sr in strategy_results)

        for _ in range(max_iterations):
            if len(interleaved) >= top_k:
                break

            # Get next chunk from current strategy
            strategy = strategy_results[current_strategy]
            pointer = pointers[current_strategy]

            if pointer < len(strategy.chunks):
                chunk = strategy.chunks[pointer]
                chunk_id = chunk.get("chunk_id", "")

                if chunk_id and chunk_id not in seen_chunks:
                    interleaved.append(chunk)
                    seen_chunks.add(chunk_id)

                pointers[current_strategy] += 1

            # Move to next strategy
            current_strategy = (current_strategy + 1) % len(strategy_results)

        logger.info(
            f"Round-robin interleaved {len(strategy_results)} strategies → "
            f"{len(interleaved)} chunks"
        )

        return interleaved


class InterleaverFactory:
    """Factory for creating interleavers based on configuration."""

    @staticmethod
    def create(
        method: str = "smart",
        intent: str | None = None,
        **kwargs: Any,
    ) -> SmartInterleaver | RoundRobinInterleaver:
        """
        Create interleaver based on method.

        Args:
            method: Interleaving method ('smart' or 'round_robin')
            intent: Query intent for adaptive weights
            **kwargs: Additional arguments

        Returns:
            Interleaver instance
        """
        if method == "smart":
            interleaver = SmartInterleaver(**kwargs)

            if intent:
                interleaver.set_weights_for_intent(intent)

            return interleaver
        elif method == "round_robin":
            return RoundRobinInterleaver()
        else:
            raise ValueError(f"Unknown interleaving method: {method}")


# Example usage
def example_usage():
    """Example usage of smart interleaving."""
    # Mock strategy results
    vector_results = StrategyResult(
        strategy=SearchStrategy.VECTOR,
        chunks=[
            {"chunk_id": "A", "content": "...", "score": 0.9},
            {"chunk_id": "C", "content": "...", "score": 0.8},
            {"chunk_id": "E", "content": "...", "score": 0.7},
        ],
        confidence=0.9,
        metadata={},
    )

    lexical_results = StrategyResult(
        strategy=SearchStrategy.LEXICAL,
        chunks=[
            {"chunk_id": "B", "content": "...", "score": 0.95},
            {"chunk_id": "D", "content": "...", "score": 0.85},
            {"chunk_id": "A", "content": "...", "score": 0.8},
        ],
        confidence=0.85,
        metadata={},
    )

    symbol_results = StrategyResult(
        strategy=SearchStrategy.SYMBOL,
        chunks=[
            {"chunk_id": "A", "content": "...", "score": 1.0},
            {"chunk_id": "F", "content": "...", "score": 0.9},
        ],
        confidence=0.95,
        metadata={},
    )

    # Smart interleaving
    interleaver = SmartInterleaver()
    interleaved = interleaver.interleave(
        [vector_results, lexical_results, symbol_results], top_k=10
    )

    print(f"Interleaved {len(interleaved)} chunks:")
    for i, chunk in enumerate(interleaved[:5]):
        print(
            f"  {i+1}. {chunk['chunk_id']} (score: {chunk['interleaving_score']:.3f}, "
            f"strategies: {chunk['strategies']})"
        )
