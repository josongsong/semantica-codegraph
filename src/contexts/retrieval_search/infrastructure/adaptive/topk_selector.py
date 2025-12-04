"""
Query-adaptive Top-K Selection

Dynamically adjusts the number of candidates retrieved based on:
1. Query complexity and specificity
2. Result quality (score distribution)
3. Query intent
4. Available compute budget

Problem:
- Fixed top-k is suboptimal:
  - Simple queries: top-5 may be enough
  - Complex queries: may need top-100
  - Over-retrieval wastes latency and compute
  - Under-retrieval misses relevant results

Solution:
- Analyze query to estimate required k
- Monitor result score distribution
- Adaptive cutoff based on score gaps
- Intent-specific defaults

Expected improvement: Latency -30%, Coverage maintained

Examples:
- "find User class" → k=10 (specific, likely few results)
- "authentication logic" → k=50 (broad, many possible locations)
- "how does auth work" → k=30 (conceptual, moderate scope)
"""

import re
from dataclasses import dataclass
from typing import Any

import numpy as np

from src.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class TopKConfig:
    """Configuration for top-k selection."""

    # Base limits
    min_k: int = 5
    max_k: int = 100
    default_k: int = 50

    # Query complexity adjustments
    simple_query_k: int = 10
    medium_query_k: int = 30
    complex_query_k: int = 80

    # Intent-specific defaults
    symbol_nav_k: int = 15
    code_search_k: int = 50
    flow_trace_k: int = 60
    concept_search_k: int = 40

    # Score distribution thresholds
    min_score_threshold: float = 0.3
    score_gap_threshold: float = 0.1
    quality_score_threshold: float = 0.7


@dataclass
class QueryComplexity:
    """Query complexity analysis."""

    token_count: int
    has_code_identifiers: bool
    has_file_path: bool
    has_natural_language: bool
    has_boolean_operators: bool
    specificity_score: float  # 0-1, higher = more specific

    @property
    def complexity_level(self) -> str:
        """Get complexity level: simple, medium, or complex."""
        if self.specificity_score > 0.7 and self.token_count <= 3:
            return "simple"
        elif self.specificity_score < 0.4 or self.token_count > 8:
            return "complex"
        else:
            return "medium"


class QueryAnalyzer:
    """Analyze query characteristics for adaptive top-k."""

    def __init__(self):
        """Initialize query analyzer."""
        self.code_pattern = re.compile(r"[A-Z][a-z]+(?:[A-Z][a-z]+)*|[a-z_][a-z0-9_]*")
        self.path_pattern = re.compile(r"[\w/]+\.(?:py|ts|js|tsx|jsx|java|go)")
        self.boolean_pattern = re.compile(r"\b(AND|OR|NOT|and|or|not)\b")

    def analyze(self, query: str) -> QueryComplexity:
        """
        Analyze query complexity.

        Args:
            query: User query

        Returns:
            Query complexity analysis
        """
        tokens = query.split()
        token_count = len(tokens)

        # Detect code identifiers
        code_matches = self.code_pattern.findall(query)
        has_code_identifiers = len(code_matches) > 0

        # Detect file paths
        has_file_path = bool(self.path_pattern.search(query))

        # Detect natural language (words longer than 4 chars)
        has_natural_language = any(len(token) > 4 and token.isalpha() for token in tokens)

        # Detect boolean operators
        has_boolean_operators = bool(self.boolean_pattern.search(query))

        # Compute specificity score (0-1, higher = more specific)
        specificity_factors = []

        # Code identifiers increase specificity
        if has_code_identifiers:
            # CamelCase suggests class/function names (high specificity)
            camel_case_count = sum(1 for m in code_matches if m[0].isupper() and len(m) > 1)
            specificity_factors.append(0.8 if camel_case_count > 0 else 0.5)

        # File paths are very specific
        if has_file_path:
            specificity_factors.append(0.9)

        # Short queries are often more specific
        if token_count <= 2:
            specificity_factors.append(0.7)
        elif token_count > 6:
            specificity_factors.append(0.3)

        # Pure natural language is less specific
        if has_natural_language and not has_code_identifiers:
            specificity_factors.append(0.3)

        # Boolean operators suggest complex query (less specific per clause)
        if has_boolean_operators:
            specificity_factors.append(0.2)

        # Average specificity
        specificity_score = np.mean(specificity_factors) if specificity_factors else 0.5

        return QueryComplexity(
            token_count=token_count,
            has_code_identifiers=has_code_identifiers,
            has_file_path=has_file_path,
            has_natural_language=has_natural_language,
            has_boolean_operators=has_boolean_operators,
            specificity_score=float(specificity_score),
        )


class AdaptiveTopKSelector:
    """
    Adaptive top-k selector for retrieval.

    Dynamically adjusts k based on:
    1. Query complexity
    2. Result score distribution
    3. Query intent
    4. Compute budget
    """

    def __init__(self, config: TopKConfig | None = None):
        """
        Initialize adaptive top-k selector.

        Args:
            config: Configuration (optional)
        """
        self.config = config or TopKConfig()
        self.query_analyzer = QueryAnalyzer()

    def select_initial_k(self, query: str, intent: str | None = None) -> int:
        """
        Select initial k before retrieval.

        Args:
            query: User query
            intent: Query intent (optional)

        Returns:
            Recommended initial k
        """
        # Analyze query
        complexity = self.query_analyzer.analyze(query)

        # Base k from complexity
        if complexity.complexity_level == "simple":
            base_k = self.config.simple_query_k
        elif complexity.complexity_level == "complex":
            base_k = self.config.complex_query_k
        else:
            base_k = self.config.medium_query_k

        # Adjust by intent
        if intent:
            intent_lower = intent.lower()
            if "symbol" in intent_lower or "definition" in intent_lower:
                base_k = min(base_k, self.config.symbol_nav_k)
            elif "flow" in intent_lower or "trace" in intent_lower:
                base_k = max(base_k, self.config.flow_trace_k)
            elif "concept" in intent_lower or "explain" in intent_lower:
                base_k = self.config.concept_search_k

        # Clamp to limits
        k = max(self.config.min_k, min(base_k, self.config.max_k))

        logger.info(
            f"Adaptive top-k: query complexity={complexity.complexity_level}, "
            f"specificity={complexity.specificity_score:.2f}, "
            f"initial_k={k}"
        )

        return k

    def refine_k_from_scores(self, scores: list[float], initial_k: int) -> int:
        """
        Refine k based on score distribution.

        Args:
            scores: Retrieved chunk scores (sorted descending)
            initial_k: Initial k value

        Returns:
            Refined k (may be smaller if quality drops off)
        """
        if not scores or len(scores) < self.config.min_k:
            return initial_k

        # Convert to numpy for analysis
        scores_arr = np.array(scores)

        # Find cutoff point based on score gaps
        cutoff_k = initial_k

        for i in range(self.config.min_k, min(len(scores), initial_k)):
            # Check score gap
            if i > 0:
                gap = scores_arr[i - 1] - scores_arr[i]

                # Large gap suggests quality drop-off
                if gap > self.config.score_gap_threshold:
                    cutoff_k = i
                    logger.info(
                        f"Score gap detected at position {i}: "
                        f"{scores_arr[i - 1]:.3f} → {scores_arr[i]:.3f} (gap={gap:.3f})"
                    )
                    break

            # Check absolute score threshold
            if scores_arr[i] < self.config.min_score_threshold:
                cutoff_k = max(i, self.config.min_k)
                logger.info(
                    f"Score threshold reached at position {i}: "
                    f"score={scores_arr[i]:.3f} < {self.config.min_score_threshold}"
                )
                break

        # If we have many high-quality results, might want to expand
        high_quality_count = np.sum(scores_arr >= self.config.quality_score_threshold)
        if high_quality_count > initial_k * 0.8:
            # Most results are high quality, consider expanding
            cutoff_k = min(int(initial_k * 1.5), self.config.max_k, len(scores))
            logger.info(f"High quality results ({high_quality_count}), expanding k to {cutoff_k}")

        logger.info(f"Refined k: {initial_k} → {cutoff_k}")

        return cutoff_k

    def select_adaptive_k(
        self,
        query: str,
        intent: str | None = None,
        available_scores: list[float] | None = None,
    ) -> int:
        """
        Select adaptive k (combines initial selection and refinement).

        Args:
            query: User query
            intent: Query intent (optional)
            available_scores: Scores from preliminary retrieval (optional)

        Returns:
            Adaptive k value
        """
        # Initial k from query analysis
        initial_k = self.select_initial_k(query, intent)

        # Refine if we have score distribution
        if available_scores:
            final_k = self.refine_k_from_scores(available_scores, initial_k)
        else:
            final_k = initial_k

        return final_k


class TwoStageRetrieval:
    """
    Two-stage retrieval with adaptive top-k.

    Stage 1: Fast retrieval with large k (e.g., k=200)
    Stage 2: Analyze scores, select adaptive k, return top-k

    Benefit: Avoid missing results while controlling downstream compute.
    """

    def __init__(
        self,
        selector: AdaptiveTopKSelector | None = None,
        stage1_k: int = 200,
    ):
        """
        Initialize two-stage retrieval.

        Args:
            selector: Adaptive top-k selector
            stage1_k: K for stage 1 (large, for coverage)
        """
        self.selector = selector or AdaptiveTopKSelector()
        self.stage1_k = stage1_k

    async def retrieve(
        self,
        query: str,
        intent: str | None,
        retrieval_func: Any,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Two-stage retrieval with adaptive k.

        Args:
            query: User query
            intent: Query intent
            retrieval_func: Retrieval function (async callable)

        Returns:
            Tuple of (results, adaptive_k)
        """
        # Stage 1: Retrieve large k
        logger.info(f"Stage 1: Retrieving top-{self.stage1_k} candidates")
        stage1_results = await retrieval_func(query, k=self.stage1_k)

        # Extract scores
        scores = [c.get("score", 0.0) for c in stage1_results]

        # Stage 2: Select adaptive k
        adaptive_k = self.selector.select_adaptive_k(query, intent, available_scores=scores)

        logger.info(f"Stage 2: Selected adaptive k={adaptive_k} from {len(stage1_results)} candidates")

        # Return top adaptive_k
        return stage1_results[:adaptive_k], adaptive_k


class BudgetAwareSelector:
    """
    Budget-aware top-k selector.

    Considers compute budget (time, cost) when selecting k.
    Useful for production systems with latency/cost constraints.
    """

    def __init__(
        self,
        base_selector: AdaptiveTopKSelector,
        max_latency_ms: float = 1000.0,
        max_cost_per_query: float = 0.01,
    ):
        """
        Initialize budget-aware selector.

        Args:
            base_selector: Base adaptive selector
            max_latency_ms: Max latency budget (ms)
            max_cost_per_query: Max cost budget ($)
        """
        self.base_selector = base_selector
        self.max_latency_ms = max_latency_ms
        self.max_cost_per_query = max_cost_per_query

        # Estimate cost/latency per candidate (will be calibrated)
        self.latency_per_candidate_ms = 1.0  # 1ms per candidate
        self.cost_per_candidate = 0.0001  # $0.0001 per candidate

    def select_with_budget(
        self,
        query: str,
        intent: str | None = None,
    ) -> int:
        """
        Select k within budget constraints.

        Args:
            query: User query
            intent: Query intent

        Returns:
            Budget-constrained k
        """
        # Get base adaptive k
        base_k = self.base_selector.select_initial_k(query, intent)

        # Compute budget limits
        latency_limit_k = int(self.max_latency_ms / self.latency_per_candidate_ms)
        cost_limit_k = int(self.max_cost_per_query / self.cost_per_candidate)

        # Take minimum
        budget_k = min(base_k, latency_limit_k, cost_limit_k)

        # Clamp to config limits
        budget_k = max(
            self.base_selector.config.min_k,
            min(budget_k, self.base_selector.config.max_k),
        )

        if budget_k < base_k:
            logger.warning(
                f"Budget constraint: reduced k from {base_k} to {budget_k} "
                f"(latency_limit={latency_limit_k}, cost_limit={cost_limit_k})"
            )

        return budget_k


# Example usage
def example_usage():
    """Example usage of adaptive top-k selection."""
    selector = AdaptiveTopKSelector()

    # Example 1: Simple specific query
    query1 = "User class"
    k1 = selector.select_initial_k(query1, intent="symbol_navigation")
    print(f"Query: '{query1}' → k={k1}")

    # Example 2: Complex broad query
    query2 = "how does the authentication and authorization system work"
    k2 = selector.select_initial_k(query2, intent="concept_search")
    print(f"Query: '{query2}' → k={k2}")

    # Example 3: Code search query
    query3 = "find functions that process user input"
    k3 = selector.select_initial_k(query3, intent="code_search")
    print(f"Query: '{query3}' → k={k3}")

    # Example 4: Refine from scores
    scores = [0.9, 0.85, 0.8, 0.75, 0.7, 0.4, 0.35, 0.3, 0.25]
    refined_k = selector.refine_k_from_scores(scores, initial_k=50)
    print(f"Refined k from scores: initial=50 → refined={refined_k}")
