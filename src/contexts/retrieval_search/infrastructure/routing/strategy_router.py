"""
Strategy Path Router for Intent-Based Retrieval.

Routes queries to optimal retrieval strategies based on intent classification.

Key features:
1. Explicit strategy paths: Primary → Fallback → Enrichment
2. Cost-aware execution: Tracks strategy latency/cost
3. Early stopping: Skip remaining strategies if sufficient results
4. Intent-based routing: Different paths for different intents
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

from src.common.observability import get_logger
from src.contexts.retrieval_search.infrastructure.v3.models import IntentProbability, RankedHit

logger = get_logger(__name__)
T = TypeVar("T")


class StrategyType(str, Enum):
    """Available retrieval strategies."""

    VECTOR = "vector"
    LEXICAL = "lexical"
    SYMBOL = "symbol"
    GRAPH = "graph"


@dataclass
class StrategyConfig:
    """Configuration for a single strategy."""

    name: StrategyType
    timeout_ms: int = 5000
    """Maximum execution time in milliseconds"""

    priority: int = 1
    """Lower = higher priority (1 = primary)"""

    min_results: int = 5
    """Minimum results to consider strategy successful"""

    cost_weight: float = 1.0
    """Relative computational cost (for resource management)"""


@dataclass
class StrategyPath:
    """
    Defines an ordered path of strategies to execute.

    Strategies are executed in priority order. Execution can stop early
    if sufficient results are obtained.
    """

    primary: list[StrategyType]
    """Primary strategies - always executed (in parallel if possible)"""

    fallback: list[StrategyType] = field(default_factory=list)
    """Fallback strategies - executed if primary insufficient"""

    enrichment: list[StrategyType] = field(default_factory=list)
    """Enrichment strategies - always run for result enhancement"""

    early_stop_threshold: int = 20
    """Stop after primary if >= this many results"""

    parallel_primary: bool = True
    """Execute primary strategies in parallel"""


# Pre-defined strategy paths for each intent
INTENT_STRATEGY_PATHS: dict[str, StrategyPath] = {
    "symbol": StrategyPath(
        primary=[StrategyType.SYMBOL, StrategyType.LEXICAL],
        fallback=[StrategyType.VECTOR],
        enrichment=[],
        early_stop_threshold=15,
        parallel_primary=True,
    ),
    "flow": StrategyPath(
        primary=[StrategyType.GRAPH, StrategyType.SYMBOL],
        fallback=[StrategyType.LEXICAL, StrategyType.VECTOR],
        enrichment=[],
        early_stop_threshold=10,
        parallel_primary=True,
    ),
    "concept": StrategyPath(
        primary=[StrategyType.VECTOR],
        fallback=[StrategyType.LEXICAL],
        enrichment=[StrategyType.SYMBOL],
        early_stop_threshold=30,
        parallel_primary=False,  # Vector alone is usually sufficient
    ),
    "code": StrategyPath(
        primary=[StrategyType.LEXICAL, StrategyType.VECTOR],
        fallback=[StrategyType.SYMBOL],
        enrichment=[StrategyType.GRAPH],
        early_stop_threshold=25,
        parallel_primary=True,
    ),
    "balanced": StrategyPath(
        primary=[StrategyType.VECTOR, StrategyType.LEXICAL, StrategyType.SYMBOL],
        fallback=[StrategyType.GRAPH],
        enrichment=[],
        early_stop_threshold=20,
        parallel_primary=True,
    ),
}


@dataclass
class StrategyResult:
    """Result from a single strategy execution."""

    strategy: StrategyType
    hits: list[RankedHit]
    latency_ms: float
    success: bool
    error: str | None = None


@dataclass
class RoutingResult:
    """Complete result from strategy routing."""

    hits_by_strategy: dict[str, list[RankedHit]]
    strategy_results: list[StrategyResult]
    total_latency_ms: float
    strategies_executed: list[str]
    early_stopped: bool = False
    path_used: StrategyPath | None = None


class StrategyRouter:
    """
    Routes queries to optimal retrieval strategies based on intent.

    Executes strategies in a defined order with early stopping and fallback logic.
    """

    def __init__(
        self,
        strategy_executors: dict[StrategyType, Callable],
        intent_paths: dict[str, StrategyPath] | None = None,
    ):
        """
        Initialize strategy router.

        Args:
            strategy_executors: Dict mapping StrategyType → async executor function
                Each executor should have signature: (query: str, **kwargs) -> list[RankedHit]
            intent_paths: Custom intent → path mappings (defaults to INTENT_STRATEGY_PATHS)
        """
        self.executors = strategy_executors
        self.intent_paths = intent_paths or INTENT_STRATEGY_PATHS

        # Latency tracking for adaptive routing
        self._strategy_latencies: dict[StrategyType, list[float]] = {st: [] for st in StrategyType}

    async def route(
        self,
        query: str,
        intent_prob: IntentProbability,
        confidence_threshold: float = 0.4,
        **executor_kwargs: Any,
    ) -> RoutingResult:
        """
        Route query to strategies based on intent.

        Args:
            query: Search query
            intent_prob: Intent probability distribution
            confidence_threshold: Minimum confidence to use intent-specific path
            **executor_kwargs: Additional kwargs passed to executors

        Returns:
            RoutingResult with hits from all executed strategies
        """
        start_time = time.time()

        # Determine which path to use
        dominant_intent = intent_prob.dominant_intent()
        dominant_prob = getattr(intent_prob, dominant_intent, 0.0)

        if dominant_prob >= confidence_threshold:
            path = self.intent_paths.get(dominant_intent, self.intent_paths["balanced"])
            logger.debug(f"Using {dominant_intent} path (confidence={dominant_prob:.2f})")
        else:
            path = self.intent_paths["balanced"]
            logger.debug(f"Using balanced path (low confidence: {dominant_prob:.2f})")

        # Execute strategies according to path
        all_results: list[StrategyResult] = []
        hits_by_strategy: dict[str, list[RankedHit]] = {}
        early_stopped = False

        # Phase 1: Primary strategies
        primary_results = await self._execute_strategies(
            strategies=path.primary,
            query=query,
            parallel=path.parallel_primary,
            **executor_kwargs,
        )
        all_results.extend(primary_results)

        for result in primary_results:
            if result.success:
                hits_by_strategy[result.strategy.value] = result.hits

        # Check early stop condition
        total_primary_hits = sum(len(r.hits) for r in primary_results if r.success)

        if total_primary_hits >= path.early_stop_threshold and not path.enrichment:
            early_stopped = True
            logger.debug(f"Early stopping: {total_primary_hits} hits from primary strategies")
        else:
            # Phase 2: Fallback strategies (if needed)
            if total_primary_hits < path.early_stop_threshold and path.fallback:
                fallback_results = await self._execute_strategies(
                    strategies=path.fallback,
                    query=query,
                    parallel=True,
                    **executor_kwargs,
                )
                all_results.extend(fallback_results)

                for result in fallback_results:
                    if result.success:
                        hits_by_strategy[result.strategy.value] = result.hits

            # Phase 3: Enrichment strategies (always run if defined)
            if path.enrichment:
                enrichment_results = await self._execute_strategies(
                    strategies=path.enrichment,
                    query=query,
                    parallel=True,
                    **executor_kwargs,
                )
                all_results.extend(enrichment_results)

                for result in enrichment_results:
                    if result.success:
                        hits_by_strategy[result.strategy.value] = result.hits

        total_latency = (time.time() - start_time) * 1000

        # Update latency tracking
        for result in all_results:
            self._record_latency(result.strategy, result.latency_ms)

        return RoutingResult(
            hits_by_strategy=hits_by_strategy,
            strategy_results=all_results,
            total_latency_ms=total_latency,
            strategies_executed=[r.strategy.value for r in all_results],
            early_stopped=early_stopped,
            path_used=path,
        )

    async def _execute_strategies(
        self,
        strategies: list[StrategyType],
        query: str,
        parallel: bool = True,
        **kwargs: Any,
    ) -> list[StrategyResult]:
        """Execute a list of strategies."""
        if not strategies:
            return []

        if parallel:
            # Execute all in parallel
            tasks = [self._execute_single(strategy, query, **kwargs) for strategy in strategies]
            return await asyncio.gather(*tasks)
        else:
            # Execute sequentially
            results = []
            for strategy in strategies:
                result = await self._execute_single(strategy, query, **kwargs)
                results.append(result)
            return results

    async def _execute_single(
        self,
        strategy: StrategyType,
        query: str,
        **kwargs: Any,
    ) -> StrategyResult:
        """Execute a single strategy with timing."""
        executor = self.executors.get(strategy)

        if executor is None:
            return StrategyResult(
                strategy=strategy,
                hits=[],
                latency_ms=0.0,
                success=False,
                error=f"No executor for {strategy.value}",
            )

        start = time.time()
        try:
            hits = await executor(query, **kwargs)
            latency_ms = (time.time() - start) * 1000

            return StrategyResult(
                strategy=strategy,
                hits=hits if hits else [],
                latency_ms=latency_ms,
                success=True,
            )

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start) * 1000
            logger.warning(f"Strategy {strategy.value} timed out after {latency_ms:.0f}ms")
            return StrategyResult(
                strategy=strategy,
                hits=[],
                latency_ms=latency_ms,
                success=False,
                error="Timeout",
            )

        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            logger.error(f"Strategy {strategy.value} failed: {e}")
            return StrategyResult(
                strategy=strategy,
                hits=[],
                latency_ms=latency_ms,
                success=False,
                error=str(e),
            )

    def _record_latency(self, strategy: StrategyType, latency_ms: float) -> None:
        """Record latency for adaptive routing."""
        history = self._strategy_latencies[strategy]
        history.append(latency_ms)

        # Keep last 100 measurements
        if len(history) > 100:
            history.pop(0)

    def get_average_latency(self, strategy: StrategyType) -> float:
        """Get average latency for a strategy."""
        history = self._strategy_latencies[strategy]
        if not history:
            return 0.0
        return sum(history) / len(history)

    def get_routing_stats(self) -> dict[str, Any]:
        """Get routing statistics."""
        return {
            "average_latencies": {st.value: self.get_average_latency(st) for st in StrategyType},
            "sample_counts": {st.value: len(self._strategy_latencies[st]) for st in StrategyType},
        }

    def set_custom_path(self, intent: str, path: StrategyPath) -> None:
        """Set a custom strategy path for an intent."""
        self.intent_paths[intent] = path
        logger.info(f"Custom path set for intent={intent}")


def create_default_path_for_intent(
    intent: str,
    primary_strategies: list[str],
    fallback_strategies: list[str] | None = None,
) -> StrategyPath:
    """
    Helper to create a custom strategy path.

    Args:
        intent: Intent name
        primary_strategies: List of primary strategy names
        fallback_strategies: List of fallback strategy names

    Returns:
        StrategyPath instance
    """
    primary = [StrategyType(s) for s in primary_strategies]
    fallback = [StrategyType(s) for s in (fallback_strategies or [])]

    return StrategyPath(
        primary=primary,
        fallback=fallback,
        enrichment=[],
        early_stop_threshold=20,
        parallel_primary=len(primary) > 1,
    )
