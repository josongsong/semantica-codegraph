"""
LLM Reranker v2

Uses LLM to provide additional scoring for top candidates.
Implements Phase 3 Action 16-1 from the retrieval execution plan.

Strategy:
- Apply only to top-N candidates (e.g., top 20) to manage cost
- LLM scores based on: Match Quality, Semantic Relevance, Structural Fit
- Combine LLM score with existing scores
"""

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.api.shared.ports import LLMPort
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class LLMScore:
    """LLM reranking score breakdown."""

    match_quality: float  # 0-1: How well chunk matches query literally
    semantic_relevance: float  # 0-1: Semantic/conceptual relevance
    structural_fit: float  # 0-1: Code structure appropriateness
    overall: float  # Combined score
    reasoning: str  # LLM's explanation


@dataclass
class LLMRerankedChunk:
    """Chunk with LLM reranking score."""

    chunk_id: str
    original_score: float
    llm_score: LLMScore
    final_score: float
    content: str
    metadata: dict[str, Any]


class LLMReranker:
    """
    LLM-based reranker for final precision boost.

    Applies LLM reasoning only to top candidates to balance cost and quality.
    """

    def __init__(
        self,
        llm_client: "LLMPort",
        top_k: int = 20,
        llm_weight: float = 0.3,
        timeout_seconds: float = 5.0,
    ):
        """
        Initialize LLM reranker.

        Args:
            llm_client: LLM client for scoring
            top_k: Number of top candidates to rerank with LLM
            llm_weight: Weight for LLM score in final score (0-1)
            timeout_seconds: Timeout for LLM scoring
        """
        self.llm_client = llm_client
        self.top_k = top_k
        self.llm_weight = llm_weight
        self.original_weight = 1.0 - llm_weight
        self.timeout = timeout_seconds

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        batch_size: int = 5,
    ) -> list[LLMRerankedChunk]:
        """
        Rerank top candidates using LLM.

        Args:
            query: User query
            candidates: Candidate chunks with scores
            batch_size: Batch size for LLM calls

        Returns:
            Reranked chunks with LLM scores
        """
        # Sort by original score and take top-k
        sorted_candidates = sorted(candidates, key=lambda c: c.get("score", 0.0), reverse=True)
        top_candidates = sorted_candidates[: self.top_k]

        logger.info(f"LLM reranking top {len(top_candidates)} candidates (batch_size={batch_size})")

        # Score candidates in batches
        reranked = []
        for i in range(0, len(top_candidates), batch_size):
            batch = top_candidates[i : i + batch_size]
            batch_results = await self._score_batch(query, batch)
            reranked.extend(batch_results)

        # Re-sort by final score
        reranked.sort(key=lambda c: c.final_score, reverse=True)

        logger.info(
            f"LLM reranking complete: scored {len(reranked)} chunks, "
            f"avg LLM score={sum(c.llm_score.overall for c in reranked) / len(reranked):.3f}"
        )

        return reranked

    async def _score_batch(self, query: str, batch: list[dict[str, Any]]) -> list[LLMRerankedChunk]:
        """
        Score a batch of candidates with LLM.

        Args:
            query: User query
            batch: Batch of candidates

        Returns:
            Scored chunks
        """
        tasks = [self._score_candidate(query, candidate) for candidate in batch]

        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=self.timeout)
        except asyncio.TimeoutError:
            logger.warning(f"LLM reranking batch timeout after {self.timeout}s")
            # Fallback: use original scores only
            results = [None] * len(batch)

        reranked = []
        for candidate, result in zip(batch, results, strict=False):
            if isinstance(result, Exception) or result is None:
                # Fallback: neutral LLM score
                llm_score = LLMScore(
                    match_quality=0.5,
                    semantic_relevance=0.5,
                    structural_fit=0.5,
                    overall=0.5,
                    reasoning="LLM scoring failed or timed out",
                )
            else:
                llm_score = result

            original_score = candidate.get("score", 0.0)
            final_score = self._combine_scores(original_score, llm_score.overall)

            reranked.append(
                LLMRerankedChunk(
                    chunk_id=candidate["chunk_id"],
                    original_score=original_score,
                    llm_score=llm_score,
                    final_score=final_score,
                    content=candidate.get("content", ""),
                    metadata=candidate.get("metadata", {}),
                )
            )

        return reranked

    async def _score_candidate(self, query: str, candidate: dict[str, Any]) -> LLMScore:
        """
        Score a single candidate with LLM.

        Args:
            query: User query
            candidate: Candidate chunk

        Returns:
            LLM score
        """
        prompt = self._build_scoring_prompt(query, candidate)

        try:
            response = await self.llm_client.generate(prompt, max_tokens=300)
            llm_score = self._parse_llm_response(response)
        except Exception as e:
            logger.warning(f"LLM scoring failed: {e}")
            llm_score = LLMScore(
                match_quality=0.5,
                semantic_relevance=0.5,
                structural_fit=0.5,
                overall=0.5,
                reasoning=f"Scoring error: {str(e)}",
            )

        return llm_score

    def _build_scoring_prompt(self, query: str, candidate: dict[str, Any]) -> str:
        """
        Build LLM scoring prompt.

        Args:
            query: User query
            candidate: Candidate chunk

        Returns:
            LLM prompt
        """
        content = candidate.get("content", "")
        file_path = candidate.get("file_path", "unknown")
        chunk_type = candidate.get("chunk_type", "unknown")

        # Truncate content if too long
        max_content_len = 1000
        if len(content) > max_content_len:
            content = content[:max_content_len] + "\n... (truncated)"

        prompt = f"""You are a code search relevance scorer. Rate how well this code chunk matches the user's query.

Query: "{query}"

Code Chunk:
File: {file_path}
Type: {chunk_type}
```
{content}
```

Score the chunk on three dimensions (0.0-1.0):

1. Match Quality: How well does the chunk literally match the query terms?
   - 1.0: Perfect match of query terms
   - 0.5: Partial match
   - 0.0: No match

2. Semantic Relevance: How relevant is the chunk's purpose/functionality to the query intent?
   - 1.0: Directly answers the query
   - 0.5: Related but not direct
   - 0.0: Unrelated

3. Structural Fit: Is this the right type of code element for the query?
   - 1.0: Exactly the right structure (e.g., query asks for function, chunk is function definition)
   - 0.5: Acceptable structure
   - 0.0: Wrong structure

Respond in JSON format only:
{{
  "match_quality": <score>,
  "semantic_relevance": <score>,
  "structural_fit": <score>,
  "reasoning": "<brief explanation>"
}}"""

        return prompt

    def _parse_llm_response(self, response: str) -> LLMScore:
        """
        Parse LLM response into LLMScore.

        Args:
            response: LLM response string

        Returns:
            Parsed LLM score
        """
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_str = response.strip()
            if json_str.startswith("```"):
                # Remove markdown code block
                lines = json_str.split("\n")
                json_str = "\n".join(lines[1:-1]) if len(lines) > 2 else json_str

            data = json.loads(json_str)

            match_quality = float(data.get("match_quality", 0.5))
            semantic_relevance = float(data.get("semantic_relevance", 0.5))
            structural_fit = float(data.get("structural_fit", 0.5))
            reasoning = data.get("reasoning", "")

            # Clamp to 0-1
            match_quality = max(0.0, min(1.0, match_quality))
            semantic_relevance = max(0.0, min(1.0, semantic_relevance))
            structural_fit = max(0.0, min(1.0, structural_fit))

            # Overall score: weighted average
            overall = 0.4 * match_quality + 0.4 * semantic_relevance + 0.2 * structural_fit

            return LLMScore(
                match_quality=match_quality,
                semantic_relevance=semantic_relevance,
                structural_fit=structural_fit,
                overall=overall,
                reasoning=reasoning,
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse LLM response: {e}\nResponse: {response}")
            return LLMScore(
                match_quality=0.5,
                semantic_relevance=0.5,
                structural_fit=0.5,
                overall=0.5,
                reasoning="Failed to parse LLM response",
            )

    def _combine_scores(self, original: float, llm: float) -> float:
        """
        Combine original score with LLM score.

        Args:
            original: Original retrieval score
            llm: LLM reranking score

        Returns:
            Combined final score
        """
        return self.original_weight * original + self.llm_weight * llm

    def explain(self, reranked: LLMRerankedChunk) -> str:
        """
        Generate explanation for reranked chunk.

        Args:
            reranked: Reranked chunk

        Returns:
            Human-readable explanation
        """
        return f"""Chunk: {reranked.chunk_id}
Original Score: {reranked.original_score:.3f}
LLM Score: {reranked.llm_score.overall:.3f}
  - Match Quality: {reranked.llm_score.match_quality:.3f}
  - Semantic Relevance: {reranked.llm_score.semantic_relevance:.3f}
  - Structural Fit: {reranked.llm_score.structural_fit:.3f}
Final Score: {reranked.final_score:.3f}
Reasoning: {reranked.llm_score.reasoning}
"""
