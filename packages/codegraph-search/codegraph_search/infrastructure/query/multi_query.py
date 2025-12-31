"""
RAG-Fusion: Multi-Query Generation

Generates multiple query perspectives for comprehensive retrieval.

References:
- RAG-Fusion: https://github.com/Raudaschl/RAG-Fusion
- Query Rewriting for Retrieval-Augmented Generation (Ma et al., 2023)

Key Insight:
A single query may miss relevant documents. Generate multiple
rephrased queries and fuse results for better coverage.
"""

from typing import Any, Protocol

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class LLMPort(Protocol):
    """LLM interface for query generation."""

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from prompt."""
        ...


MULTI_QUERY_PROMPT = """You are an expert at understanding code search queries and generating alternative perspectives.

Original query: "{query}"

Generate 2-3 alternative ways to search for this information in a codebase. Each alternative should:
- Focus on a different aspect or perspective
- Use different terminology or phrasing
- Maintain the original intent

Format each alternative query on a new line, numbered:
1. [first alternative]
2. [second alternative]
3. [third alternative]

Alternative queries:"""


class MultiQueryGenerator:
    """
    RAG-Fusion style multi-query generator.

    Generates multiple query variations for comprehensive retrieval.

    Features:
    - LLM-based query generation
    - Perspective diversity (syntax vs semantics vs use-case)
    - Configurable number of variations
    - Fallback to original query
    """

    def __init__(
        self,
        llm: LLMPort,
        num_queries: int = 3,
        temperature: float = 0.7,
        max_tokens: int = 200,
    ):
        """
        Initialize multi-query generator.

        Args:
            llm: LLM for query generation
            num_queries: Number of query variations (2-5 recommended)
            temperature: Generation temperature (0.7 for diversity)
            max_tokens: Max tokens for generated queries
        """
        self.llm = llm
        self.num_queries = num_queries
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def generate_queries(self, query: str) -> list[str]:
        """
        Generate multiple query variations.

        Args:
            query: Original query

        Returns:
            List of query variations (including original)
        """
        try:
            # Generate alternative queries using LLM
            prompt = MULTI_QUERY_PROMPT.format(query=query)

            response = await self.llm.generate(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            # Parse numbered responses
            variations = self._parse_numbered_queries(response)

            # Always include original query first
            all_queries = [query] + variations

            # Deduplicate while preserving order
            seen = set()
            unique_queries = []
            for q in all_queries:
                q_normalized = q.lower().strip()
                if q_normalized and q_normalized not in seen:
                    seen.add(q_normalized)
                    unique_queries.append(q.strip())

            # Limit to num_queries
            final_queries = unique_queries[: self.num_queries]

            logger.info(
                "multi_query_generation_success",
                original_query=query[:50],
                num_generated=len(final_queries),
                variations=final_queries,
            )

            return final_queries

        except Exception as e:
            logger.warning(
                "multi_query_generation_failed",
                error=str(e),
                query=query[:100],
            )
            # Fallback: return only original query
            return [query]

    def _parse_numbered_queries(self, response: str) -> list[str]:
        """
        Parse numbered query variations from LLM response.

        Expected format:
        1. First query
        2. Second query
        3. Third query

        Args:
            response: LLM response text

        Returns:
            List of parsed queries
        """
        queries = []

        for line in response.strip().split("\n"):
            line = line.strip()

            # Match numbered format: "1. query" or "1) query"
            if line and (line[0].isdigit() or line.startswith("-")):
                # Remove number prefix
                query = line.lstrip("0123456789.-) ").strip()
                if query:
                    queries.append(query)

        return queries


class MultiQueryRetriever:
    """
    Retriever using RAG-Fusion multi-query approach.

    Retrieves with multiple query variations and fuses results.
    """

    def __init__(
        self,
        query_generator: MultiQueryGenerator,
        fusion_method: str = "rrf",  # reciprocal rank fusion
        rrf_k: int = 60,
    ):
        """
        Initialize multi-query retriever.

        Args:
            query_generator: Multi-query generator
            fusion_method: Result fusion method (rrf/linear/max)
            rrf_k: RRF constant (60 is standard)
        """
        self.generator = query_generator
        self.fusion_method = fusion_method
        self.rrf_k = rrf_k

    async def expand_query(self, query: str) -> dict[str, Any]:
        """
        Expand query into multiple variations.

        Args:
            query: Original query

        Returns:
            Dict with:
                - queries: list[str] - All query variations
                - num_queries: int - Number of variations
        """
        queries = await self.generator.generate_queries(query)

        return {
            "queries": queries,
            "num_queries": len(queries),
            "original_query": query,
        }

    def fuse_results(
        self,
        results_per_query: list[list[tuple[str, float]]],
    ) -> list[tuple[str, float]]:
        """
        Fuse results from multiple queries using RRF.

        Args:
            results_per_query: List of result lists, each containing (doc_id, score) tuples

        Returns:
            Fused and ranked results as list of (doc_id, fused_score)
        """
        if self.fusion_method == "rrf":
            return self._reciprocal_rank_fusion(results_per_query)
        elif self.fusion_method == "linear":
            return self._linear_fusion(results_per_query)
        elif self.fusion_method == "max":
            return self._max_fusion(results_per_query)
        else:
            logger.warning(f"Unknown fusion method: {self.fusion_method}, using RRF")
            return self._reciprocal_rank_fusion(results_per_query)

    def _reciprocal_rank_fusion(
        self,
        results_per_query: list[list[tuple[str, float]]],
    ) -> list[tuple[str, float]]:
        """
        Reciprocal Rank Fusion (RRF).

        RRF formula: score(d) = sum over queries of 1/(k + rank(d))
        where k is a constant (typically 60).

        Args:
            results_per_query: Results from each query

        Returns:
            Fused results sorted by RRF score
        """
        doc_scores: dict[str, float] = {}

        for results in results_per_query:
            for rank, (doc_id, _score) in enumerate(results, start=1):
                rrf_score = 1.0 / (self.rrf_k + rank)
                doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + rrf_score

        # Sort by fused score
        fused = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)

        logger.debug(
            "rrf_fusion_complete",
            num_docs=len(fused),
            top_score=fused[0][1] if fused else 0,
        )

        return fused

    def _linear_fusion(
        self,
        results_per_query: list[list[tuple[str, float]]],
    ) -> list[tuple[str, float]]:
        """
        Linear score fusion (simple average).

        Args:
            results_per_query: Results from each query

        Returns:
            Fused results sorted by average score
        """
        doc_scores: dict[str, list[float]] = {}

        for results in results_per_query:
            for doc_id, score in results:
                if doc_id not in doc_scores:
                    doc_scores[doc_id] = []
                doc_scores[doc_id].append(score)

        # Average scores
        doc_avg = {doc_id: sum(scores) / len(scores) for doc_id, scores in doc_scores.items()}

        fused = sorted(doc_avg.items(), key=lambda x: x[1], reverse=True)

        return fused

    def _max_fusion(
        self,
        results_per_query: list[list[tuple[str, float]]],
    ) -> list[tuple[str, float]]:
        """
        Max score fusion (take best score per document).

        Args:
            results_per_query: Results from each query

        Returns:
            Fused results sorted by max score
        """
        doc_scores: dict[str, float] = {}

        for results in results_per_query:
            for doc_id, score in results:
                doc_scores[doc_id] = max(doc_scores.get(doc_id, 0.0), score)

        fused = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)

        return fused
