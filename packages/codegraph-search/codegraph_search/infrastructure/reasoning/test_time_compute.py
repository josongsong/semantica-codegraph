"""
Test-Time Reasoning (o1-style)

LLM-driven search strategy with reasoning at retrieval time.
"""

import json
from typing import TYPE_CHECKING

from codegraph_search.infrastructure.reasoning.models import (
    ReasonedResult,
    ReasoningStep,
    SearchStrategy,
    SearchTool,
)

if TYPE_CHECKING:
    from codegraph_search.infrastructure.multi_index import MultiIndexOrchestrator
    from apps.api.shared.ports import LLMPort
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)
STRATEGY_PLANNING_PROMPT = """You are an expert code search assistant. Analyze this query and plan a search strategy.

**Query:** "{query}"

**Available search tools:**
1. **lexical**: Fast text/regex search (best for exact terms, keywords)
2. **vector**: Semantic search (best for concepts, natural language)
3. **symbol**: Symbol navigation (best for functions, classes, go-to-definition)
4. **graph**: Call graph traversal (best for tracing execution flow)

**Your task:**
1. Analyze the query complexity and intent
2. Plan a multi-step search strategy using available tools
3. For each step: explain reasoning, choose tool, write query
4. Estimate when you have sufficient results

**Output format (JSON):**
```json
{{
  "analysis": "Analysis of query intent and complexity",
  "estimated_difficulty": 1-5,
  "steps": [
    {{
      "step_num": 1,
      "thought": "What I'm trying to find and why",
      "tool": "lexical|vector|symbol|graph",
      "query": "Specific search query for this tool",
      "expected_outcome": "What I expect to find"
    }}
  ]
}}
```

**Example:**

Query: "How does user authentication flow to database?"

```json
{{
  "analysis": "Multi-step flow tracing: need to find auth entry point, then trace to DB",
  "estimated_difficulty": 4,
  "steps": [
    {{
      "step_num": 1,
      "thought": "First find authentication entry points (likely route handlers or middleware)",
      "tool": "symbol",
      "query": "authenticate login auth",
      "expected_outcome": "Authentication functions or handlers"
    }},
    {{
      "step_num": 2,
      "thought": "From auth functions, need to trace database interactions",
      "tool": "lexical",
      "query": "database db query select insert",
      "expected_outcome": "Database call sites within auth flow"
    }},
    {{
      "step_num": 3,
      "thought": "Use call graph to verify flow from auth to DB",
      "tool": "graph",
      "query": "call chain from authentication to database",
      "expected_outcome": "Complete call chain showing flow"
    }}
  ]
}}
```

Plan the search strategy. Respond with JSON only.
"""

RESULT_EVALUATION_PROMPT = """Evaluate if these search results sufficiently answer the query.

**Original query:** "{query}"

**Results so far:** {num_results} chunks found

**Top result snippets:**
{result_snippets}

**Question:** Do these results adequately answer the query?

Respond with JSON:
```json
{{
  "sufficient": true|false,
  "confidence": 0.0-1.0,
  "reasoning": "Why results are sufficient or what's missing",
  "next_action": "stop" | "continue" | "refine"
}}
```
"""


class ReasoningRetriever:
    """
    Reasoning-based retriever using test-time compute.

    Allows LLM to reason about search strategy and adapt based on results,
    similar to OpenAI's o1 reasoning approach.
    """

    def __init__(
        self,
        llm_client: "LLMPort",
        orchestrator: "MultiIndexOrchestrator",
        max_reasoning_steps: int = 5,
        reasoning_budget_tokens: int = 2000,
    ):
        """
        Initialize reasoning retriever.

        Args:
            llm_client: LLM for reasoning
            orchestrator: Multi-index orchestrator for actual searches
            max_reasoning_steps: Maximum reasoning steps
            reasoning_budget_tokens: Token budget for reasoning (separate from results)
        """
        self.llm_client = llm_client
        self.orchestrator = orchestrator
        self.max_reasoning_steps = max_reasoning_steps
        self.reasoning_budget_tokens = reasoning_budget_tokens

    async def retrieve_with_reasoning(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
    ) -> ReasonedResult:
        """
        Retrieve using LLM reasoning.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: User query

        Returns:
            ReasonedResult with reasoning trace
        """
        logger.info(f"Starting reasoning retrieval: '{query}'")

        # Step 1: LLM plans search strategy
        strategy = await self._plan_search(query)

        logger.info(f"Strategy planned: {len(strategy.steps)} steps (difficulty={strategy.estimated_difficulty})")

        # Step 2: Execute strategy steps
        step_results = []

        for step in strategy.steps[: self.max_reasoning_steps]:
            logger.info(f"Step {step.step_num}: {step.thought}")

            # Execute search for this step
            result = await self._execute_search_step(repo_id, snapshot_id, step)

            step_results.append(result)

            # Step 3: Evaluate if sufficient
            is_sufficient = await self._evaluate_sufficiency(query, step_results)

            if is_sufficient:
                logger.info(f"Results sufficient after step {step.step_num}, stopping early")
                break

        # Step 4: Refine results
        all_results = self._consolidate_results(step_results)
        refined_results = await self._refine_results(query, all_results)

        # Build final result
        reasoning_trace = self._build_trace(strategy, step_results)

        return ReasonedResult(
            strategy=strategy,
            step_results=step_results,
            raw_results=all_results,
            refined_results=refined_results,
            reasoning_trace=reasoning_trace,
            metadata={
                "num_steps_executed": len(step_results),
                "num_steps_planned": len(strategy.steps),
                "early_stop": len(step_results) < len(strategy.steps),
            },
        )

    async def _plan_search(self, query: str) -> SearchStrategy:
        """Plan search strategy using LLM."""
        prompt = STRATEGY_PLANNING_PROMPT.format(query=query)

        try:
            response_text = await self.llm_client.generate(prompt, max_tokens=600, temperature=0.3)

            response_json = self._extract_json(response_text)

            # Parse strategy
            steps = []
            for step_data in response_json.get("steps", []):
                tool_str = step_data.get("tool", "lexical")
                try:
                    tool = SearchTool(tool_str)
                except ValueError:
                    tool = SearchTool.LEXICAL

                step = ReasoningStep(
                    step_num=step_data.get("step_num", len(steps) + 1),
                    thought=step_data.get("thought", ""),
                    action=f"{tool.value}: {step_data.get('query', '')}",
                    tool=tool,
                    query=step_data.get("query", query),
                    expected_outcome=step_data.get("expected_outcome", ""),
                )
                steps.append(step)

            return SearchStrategy(
                query=query,
                analysis=response_json.get("analysis", ""),
                steps=steps,
                estimated_difficulty=int(response_json.get("estimated_difficulty", 3)),
                trace=response_text,
            )

        except Exception as e:
            logger.error(f"Strategy planning failed: {e}")
            # Fallback: single lexical search
            return SearchStrategy(
                query=query,
                analysis="Fallback strategy",
                steps=[
                    ReasoningStep(
                        step_num=1,
                        thought="Fallback to lexical search",
                        action=f"lexical: {query}",
                        tool=SearchTool.LEXICAL,
                        query=query,
                    )
                ],
            )

    async def _execute_search_step(self, repo_id: str, snapshot_id: str, step: ReasoningStep) -> dict:
        """Execute a single search step."""
        # Map tool to index

        # Execute search (simplified - would use full orchestrator)
        # For now, return mock result
        return {
            "step_num": step.step_num,
            "tool": step.tool.value,
            "query": step.query,
            "chunks": [],  # Would contain actual results
            "num_results": 0,
        }

    async def _evaluate_sufficiency(self, query: str, step_results: list[dict]) -> bool:
        """Evaluate if results are sufficient."""
        if not step_results:
            return False

        # Simplified: check if we have results
        total_results = sum(r.get("num_results", 0) for r in step_results)

        if total_results == 0:
            return False

        if total_results >= 10:  # Threshold
            return True

        # Could call LLM for evaluation (uses reasoning budget)
        return False

    async def _refine_results(self, query: str, results: list[dict]) -> list[dict]:
        """Refine results using LLM."""
        # Simplified: just return top results
        return results[:20]

    def _consolidate_results(self, step_results: list[dict]) -> list[dict]:
        """Consolidate results from all steps."""
        all_chunks = []
        seen_ids = set()

        for step_result in step_results:
            for chunk in step_result.get("chunks", []):
                chunk_id = chunk.get("chunk_id")
                if chunk_id and chunk_id not in seen_ids:
                    seen_ids.add(chunk_id)
                    all_chunks.append(chunk)

        return all_chunks

    def _build_trace(self, strategy: SearchStrategy, step_results: list[dict]) -> str:
        """Build reasoning trace."""
        lines = [
            "=== Reasoning Trace ===",
            f"Query: {strategy.query}",
            f"Analysis: {strategy.analysis}",
            f"Difficulty: {strategy.estimated_difficulty}/5",
            "",
        ]

        for step, result in zip(strategy.steps, step_results, strict=False):
            lines.append(f"Step {step.step_num}:")
            lines.append(f"  Thought: {step.thought}")
            lines.append(f"  Action: {step.action}")
            lines.append(f"  Result: {result.get('num_results', 0)} chunks found")
            lines.append("")

        return "\n".join(lines)

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from text."""
        import re

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))

        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            return json.loads(brace_match.group(0))

        return {}
