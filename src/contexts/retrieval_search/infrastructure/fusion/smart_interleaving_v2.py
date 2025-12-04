"""
Smart Chunk Interleaving v2

Improvements over v1:
1. Weighted RRF (Reciprocal Rank Fusion) instead of score-based fusion
   - Solves score calibration problem across different indexes
   - More robust to score distribution differences
2. Quality-aware consensus boosting
   - Boosts only when component scores are strong
   - Prevents weak multi-strategy agreement from dominating
3. Multi-label intent support
   - Intent is not mutually exclusive
   - Linear combination of weight profiles
4. Configurable rank decay strength per intent

Key differences from v1:
- v1: weighted_score = weight * score * rank_decay
- v2: rrf_score = weight / (k + rank)  ← Rank-based only

Expected improvements:
- More stable across different index types
- Better handling of score distribution differences
- More nuanced intent handling
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from src.common.observability import get_logger
from src.contexts.retrieval_search.infrastructure.fusion.models import SearchStrategy, StrategyResult

logger = get_logger(__name__)


@dataclass
class InterleavingWeightsV2:
    """Weights for different strategies (v2 with multi-label support)."""

    vector_weight: float
    lexical_weight: float
    symbol_weight: float
    graph_weight: float

    def normalize(self) -> "InterleavingWeightsV2":
        """Normalize weights to sum to 1.0."""
        total = self.vector_weight + self.lexical_weight + self.symbol_weight + self.graph_weight
        if total < 1e-6:
            # Fallback to balanced
            return InterleavingWeightsV2(0.25, 0.25, 0.25, 0.25)

        return InterleavingWeightsV2(
            vector_weight=self.vector_weight / total,
            lexical_weight=self.lexical_weight / total,
            symbol_weight=self.symbol_weight / total,
            graph_weight=self.graph_weight / total,
        )

    @staticmethod
    def linear_combination(profiles: list[tuple["InterleavingWeightsV2", float]]) -> "InterleavingWeightsV2":
        """
        Combine multiple weight profiles with coefficients.

        Args:
            profiles: List of (weight_profile, coefficient) tuples

        Returns:
            Combined weight profile

        Example:
            # Query: "User class definition explain" (symbol 0.6, concept 0.4)
            combined = InterleavingWeightsV2.linear_combination([
                (InterleavingWeightsV2.for_symbol_navigation(), 0.6),
                (InterleavingWeightsV2.for_concept_search(), 0.4),
            ])
        """
        vector_sum = sum(p.vector_weight * c for p, c in profiles)
        lexical_sum = sum(p.lexical_weight * c for p, c in profiles)
        symbol_sum = sum(p.symbol_weight * c for p, c in profiles)
        graph_sum = sum(p.graph_weight * c for p, c in profiles)

        combined = InterleavingWeightsV2(
            vector_weight=vector_sum,
            lexical_weight=lexical_sum,
            symbol_weight=symbol_sum,
            graph_weight=graph_sum,
        )

        return combined.normalize()

    @staticmethod
    def for_code_search() -> "InterleavingWeightsV2":
        """Weights optimized for code search queries."""
        return InterleavingWeightsV2(vector_weight=0.5, lexical_weight=0.3, symbol_weight=0.1, graph_weight=0.1)

    @staticmethod
    def for_symbol_navigation() -> "InterleavingWeightsV2":
        """Weights optimized for symbol navigation queries."""
        return InterleavingWeightsV2(vector_weight=0.2, lexical_weight=0.2, symbol_weight=0.5, graph_weight=0.1)

    @staticmethod
    def for_flow_trace() -> "InterleavingWeightsV2":
        """Weights optimized for flow tracing queries."""
        return InterleavingWeightsV2(vector_weight=0.2, lexical_weight=0.1, symbol_weight=0.2, graph_weight=0.5)

    @staticmethod
    def for_concept_search() -> "InterleavingWeightsV2":
        """Weights optimized for concept search queries."""
        return InterleavingWeightsV2(vector_weight=0.7, lexical_weight=0.2, symbol_weight=0.05, graph_weight=0.05)

    @staticmethod
    def balanced() -> "InterleavingWeightsV2":
        """Balanced weights for unknown intent."""
        return InterleavingWeightsV2(vector_weight=0.4, lexical_weight=0.3, symbol_weight=0.2, graph_weight=0.1)


@dataclass
class IntentScore:
    """Multi-label intent scores."""

    symbol_like: float = 0.0  # 0-1
    flow_like: float = 0.0  # 0-1
    concept_like: float = 0.0  # 0-1
    code_search_like: float = 0.0  # 0-1

    def to_weights(self) -> InterleavingWeightsV2:
        """Convert intent scores to interleaving weights."""
        profiles = []

        if self.symbol_like > 0:
            profiles.append((InterleavingWeightsV2.for_symbol_navigation(), self.symbol_like))
        if self.flow_like > 0:
            profiles.append((InterleavingWeightsV2.for_flow_trace(), self.flow_like))
        if self.concept_like > 0:
            profiles.append((InterleavingWeightsV2.for_concept_search(), self.concept_like))
        if self.code_search_like > 0:
            profiles.append((InterleavingWeightsV2.for_code_search(), self.code_search_like))

        if not profiles:
            return InterleavingWeightsV2.balanced()

        return InterleavingWeightsV2.linear_combination(profiles)


class SmartInterleaverV2:
    """
    Smart interleaving v2 with Weighted RRF and quality-aware consensus.

    Key improvements:
    1. Weighted RRF: component_score = weight / (k + rank)
       - Rank-based only, no raw scores
       - Robust to score distribution differences
    2. Quality-aware consensus boost:
       - Full boost only when max component score is strong
       - Prevents weak multi-strategy noise
    3. Multi-label intent support
    4. Configurable RRF k parameter
    """

    def __init__(
        self,
        weights: InterleavingWeightsV2 | None = None,
        rrf_k: int = 60,
        consensus_boost_base: float = 0.15,
        consensus_max_strategies: int = 3,
        strong_component_threshold: float = 0.01,  # For RRF, small value
    ):
        """
        Initialize smart interleaver v2.

        Args:
            weights: Strategy weights (default: balanced)
            rrf_k: RRF k parameter (typical: 60)
            consensus_boost_base: Base boost per additional strategy (0.15)
            consensus_max_strategies: Max strategies counted for boost (3)
            strong_component_threshold: Min component score for full boost
        """
        self.weights = weights or InterleavingWeightsV2.balanced()
        self.rrf_k = rrf_k
        self.consensus_boost_base = consensus_boost_base
        self.consensus_max_strategies = consensus_max_strategies
        self.strong_component_threshold = strong_component_threshold

    def interleave(
        self,
        strategy_results: list[StrategyResult],
        top_k: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Interleave results using Weighted RRF.

        Args:
            strategy_results: Results from different strategies
            top_k: Number of top results to return

        Returns:
            Interleaved and deduplicated results
        """
        if not strategy_results:
            return []

        # Build chunk index (chunk_id -> list of (strategy, score, rank))
        chunk_index = self._build_chunk_index(strategy_results)

        # Compute RRF scores with quality-aware consensus
        chunks_with_scores = self._compute_rrf_scores(chunk_index)

        # Sort by final score
        sorted_chunks = sorted(
            chunks_with_scores.items(),
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
            chunk["rrf_components"] = info["rrf_components"]  # For debugging/analysis

            interleaved.append(chunk)
            seen_chunks.add(chunk_id)

            if len(interleaved) >= top_k:
                break

        logger.info(
            f"Interleaved (v2 RRF) {len(strategy_results)} strategies → {len(interleaved)} chunks "
            f"(from {sum(len(sr.chunks) for sr in strategy_results)} total)"
        )

        # Log strategy distribution in top-20
        strategy_dist = defaultdict(int)
        for chunk in interleaved[:20]:
            for strategy in chunk["strategies"]:
                strategy_dist[strategy] += 1

        logger.info(f"Top-20 strategy distribution: {dict(strategy_dist)}")

        return interleaved

    def _build_chunk_index(self, strategy_results: list[StrategyResult]) -> dict[str, dict[str, Any]]:
        """Build index of chunk_id -> appearances across strategies."""
        chunk_index = defaultdict(lambda: {"appearances": [], "chunk": None, "original_scores": []})

        for result in strategy_results:
            for rank, chunk in enumerate(result.chunks):
                chunk_id = chunk.get("chunk_id", "")
                if not chunk_id:
                    continue

                original_score = chunk.get("score", 0.0)

                chunk_index[chunk_id]["appearances"].append((result.strategy, original_score, rank))
                chunk_index[chunk_id]["original_scores"].append(original_score)

                if chunk_index[chunk_id]["chunk"] is None:
                    chunk_index[chunk_id]["chunk"] = chunk

        return dict(chunk_index)

    def _compute_rrf_scores(self, chunk_index: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """
        Compute Weighted RRF scores with quality-aware consensus.

        RRF formula: component_score = weight / (k + rank)
        """
        chunks_with_scores = {}

        for chunk_id, info in chunk_index.items():
            rrf_sum = 0.0
            rrf_components = []
            max_component_score = 0.0

            # Compute RRF components
            for strategy, original_score, rank in info["appearances"]:
                weight = self._get_strategy_weight(strategy)

                # Weighted RRF
                rrf_component = weight / (self.rrf_k + rank)
                rrf_sum += rrf_component

                rrf_components.append(
                    {
                        "strategy": strategy.value,
                        "rank": rank,
                        "weight": weight,
                        "rrf_component": rrf_component,
                        "original_score": original_score,
                    }
                )

                # Direct comparison instead of max() function call
                if rrf_component > max_component_score:
                    max_component_score = rrf_component

            # Quality-aware consensus boost
            num_strategies = len(info["appearances"])
            consensus_factor = self._compute_consensus_factor(num_strategies, max_component_score)

            final_score = rrf_sum * consensus_factor

            chunks_with_scores[chunk_id] = {
                "chunk": info["chunk"],
                "appearances": info["appearances"],
                "rrf_sum": rrf_sum,
                "consensus_factor": consensus_factor,
                "final_score": final_score,
                "rrf_components": rrf_components,
            }

        return chunks_with_scores

    def _compute_consensus_factor(self, num_strategies: int, max_component_score: float) -> float:
        """
        Compute quality-aware consensus boost.

        Args:
            num_strategies: Number of strategies that found this chunk
            max_component_score: Maximum RRF component score

        Returns:
            Consensus factor (>= 1.0)
        """
        if num_strategies == 1:
            return 1.0

        # Cap at max_strategies for boost calculation
        effective_strategies = min(num_strategies, self.consensus_max_strategies)

        # Base factor: sqrt growth instead of linear
        # 2 strategies: 1 + 0.15 * 1 = 1.15
        # 3 strategies: 1 + 0.15 * sqrt(2) ≈ 1.21
        # 4 strategies: 1 + 0.15 * sqrt(3) ≈ 1.26
        import math

        base_factor = 1.0 + self.consensus_boost_base * math.sqrt(effective_strategies - 1)

        # Quality check: full boost only if max component is strong
        if max_component_score >= self.strong_component_threshold:
            return base_factor
        else:
            # Weak agreement: only 50% of boost
            return 1.0 + (base_factor - 1.0) * 0.5

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

    def set_weights(self, weights: InterleavingWeightsV2) -> None:
        """Update strategy weights."""
        self.weights = weights.normalize()

    def set_weights_for_intent(self, intent: str) -> None:
        """Set weights based on query intent (simple string-based for v1 compat)."""
        intent_lower = intent.lower()

        if "symbol" in intent_lower or "definition" in intent_lower:
            self.weights = InterleavingWeightsV2.for_symbol_navigation()
        elif "flow" in intent_lower or "trace" in intent_lower or "call" in intent_lower:
            self.weights = InterleavingWeightsV2.for_flow_trace()
        elif "concept" in intent_lower or "explain" in intent_lower:
            self.weights = InterleavingWeightsV2.for_concept_search()
        else:
            self.weights = InterleavingWeightsV2.for_code_search()

        logger.info(f"Set interleaving weights for intent '{intent}': {self.weights}")

    def set_weights_for_multi_intent(self, intent_scores: IntentScore) -> None:
        """Set weights based on multi-label intent scores."""
        self.weights = intent_scores.to_weights()
        logger.info(f"Set interleaving weights for multi-intent: {self.weights}")


class InterleaverFactoryV2:
    """Factory for creating v2 interleavers."""

    @staticmethod
    def create(
        method: str = "weighted_rrf",
        intent: str | None = None,
        intent_scores: IntentScore | None = None,
        **kwargs: Any,
    ) -> SmartInterleaverV2:
        """
        Create interleaver v2.

        Args:
            method: Interleaving method ('weighted_rrf')
            intent: Simple intent string (for v1 compat)
            intent_scores: Multi-label intent scores
            **kwargs: Additional arguments

        Returns:
            Interleaver instance
        """
        if method == "weighted_rrf":
            interleaver = SmartInterleaverV2(**kwargs)

            if intent_scores:
                # Multi-label intent (preferred)
                interleaver.set_weights_for_multi_intent(intent_scores)
            elif intent:
                # Simple intent string (v1 compat)
                interleaver.set_weights_for_intent(intent)

            return interleaver
        else:
            raise ValueError(f"Unknown interleaving method: {method}")


# Example usage
def example_usage():
    """Example usage of smart interleaving v2."""
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
            {"chunk_id": "B", "content": "...", "score": 25.0},  # BM25 score
            {"chunk_id": "D", "content": "...", "score": 18.0},
            {"chunk_id": "A", "content": "...", "score": 15.0},
        ],
        confidence=0.85,
        metadata={},
    )

    symbol_results = StrategyResult(
        strategy=SearchStrategy.SYMBOL,
        chunks=[
            {"chunk_id": "A", "content": "...", "score": 1.0},  # Exact match
            {"chunk_id": "F", "content": "...", "score": 0.9},
        ],
        confidence=0.95,
        metadata={},
    )

    # Example 1: Simple intent
    print("Example 1: Simple intent (symbol_nav)")
    interleaver = SmartInterleaverV2()
    interleaver.set_weights_for_intent("symbol_nav")

    interleaved = interleaver.interleave([vector_results, lexical_results, symbol_results], top_k=10)

    print(f"Interleaved {len(interleaved)} chunks:")
    for i, chunk in enumerate(interleaved[:5]):
        print(
            f"  {i + 1}. {chunk['chunk_id']} "
            f"(final_score: {chunk['interleaving_score']:.4f}, "
            f"strategies: {chunk['strategies']}, "
            f"strategy_count: {chunk['strategy_count']})"
        )

    # Example 2: Multi-label intent
    print("\nExample 2: Multi-label intent (symbol 0.6, concept 0.4)")
    intent_scores = IntentScore(symbol_like=0.6, concept_like=0.4)

    interleaver2 = InterleaverFactoryV2.create(method="weighted_rrf", intent_scores=intent_scores)

    interleaved2 = interleaver2.interleave([vector_results, lexical_results, symbol_results], top_k=10)

    print(f"Interleaved {len(interleaved2)} chunks:")
    for i, chunk in enumerate(interleaved2[:5]):
        print(
            f"  {i + 1}. {chunk['chunk_id']} "
            f"(final_score: {chunk['interleaving_score']:.4f}, "
            f"strategies: {chunk['strategies']})"
        )


if __name__ == "__main__":
    example_usage()
