"""
Query Decomposer

LLM-based query decomposition for multi-hop retrieval.
"""

import json
import logging
from typing import TYPE_CHECKING

from .models import DecomposedQuery, QueryStep, QueryType

if TYPE_CHECKING:
    from src.ports import LLMPort

logger = logging.getLogger(__name__)


DECOMPOSITION_PROMPT = """Break down this code search query into sequential sub-tasks for retrieval.

**Query:** "{query}"

Analyze the query and determine:
1. Query type: single_hop (simple), multi_hop (sequential steps), comparative, or causal
2. If multi-hop: break into sequential steps with dependencies
3. For each step: clear description, search query, expected output type

**Output format (JSON only):**
```json
{{
  "query_type": "single_hop" | "multi_hop" | "comparative" | "causal",
  "reasoning": "Brief explanation of decomposition strategy",
  "steps": [
    {{
      "step_id": "step1",
      "description": "What to find in this step",
      "query": "Actual search query",
      "dependencies": [],
      "expected_output": "function" | "file" | "class" | "flow"
    }},
    {{
      "step_id": "step2",
      "description": "What to find using step1 results",
      "query": "Search query building on step1",
      "dependencies": ["step1"],
      "expected_output": "function"
    }}
  ]
}}
```

**Examples:**

Query: "Find the authenticate function"
→ Type: single_hop (simple symbol lookup)
```json
{{
  "query_type": "single_hop",
  "reasoning": "Simple symbol navigation - single function lookup",
  "steps": [
    {{
      "step_id": "step1",
      "description": "Find authenticate function definition",
      "query": "authenticate function",
      "dependencies": [],
      "expected_output": "function"
    }}
  ]
}}
```

Query: "Find where user authentication calls the database and how errors are handled"
→ Type: multi_hop (sequential flow tracing)
```json
{{
  "query_type": "multi_hop",
  "reasoning": "Multi-step: 1) find auth functions, 2) trace DB calls, 3) find error handling",
  "steps": [
    {{
      "step_id": "step1",
      "description": "Find user authentication functions",
      "query": "user authentication function",
      "dependencies": [],
      "expected_output": "function"
    }},
    {{
      "step_id": "step2",
      "description": "Trace database calls from authentication",
      "query": "database call from authentication",
      "dependencies": ["step1"],
      "expected_output": "function"
    }},
    {{
      "step_id": "step3",
      "description": "Find error handling in call chain",
      "query": "error handling try except catch",
      "dependencies": ["step2"],
      "expected_output": "flow"
    }}
  ]
}}
```

Query: "Compare authentication implementation between REST API and GraphQL"
→ Type: comparative
```json
{{
  "query_type": "comparative",
  "reasoning": "Compare two different implementations",
  "steps": [
    {{
      "step_id": "step1",
      "description": "Find REST API authentication",
      "query": "REST API authentication",
      "dependencies": [],
      "expected_output": "function"
    }},
    {{
      "step_id": "step2",
      "description": "Find GraphQL authentication",
      "query": "GraphQL authentication",
      "dependencies": [],
      "expected_output": "function"
    }}
  ]
}}
```

Now decompose the query. Respond with JSON only, no additional text.
"""


class QueryDecomposer:
    """
    Decomposes complex queries into sequential sub-queries.

    Uses LLM to analyze query complexity and break it down into
    executable steps with dependencies.
    """

    def __init__(self, llm_client: "LLMPort"):
        """
        Initialize query decomposer.

        Args:
            llm_client: LLM client for decomposition
        """
        self.llm_client = llm_client

    async def decompose(self, query: str) -> DecomposedQuery:
        """
        Decompose query into steps.

        Args:
            query: User query

        Returns:
            DecomposedQuery with steps and dependencies

        Raises:
            ValueError: If decomposition fails
        """
        logger.info(f"Decomposing query: '{query}'")

        # Build prompt
        prompt = DECOMPOSITION_PROMPT.format(query=query)

        try:
            # Call LLM
            response_text = await self.llm_client.generate(
                prompt, max_tokens=800, temperature=0.3
            )

            # Parse JSON
            response_json = self._extract_json(response_text)

            # Convert to DecomposedQuery
            decomposed = self._parse_response(response_json, query)

            logger.info(
                f"Decomposed into {len(decomposed.steps)} steps "
                f"(type={decomposed.query_type.value})"
            )

            return decomposed

        except Exception as e:
            logger.error(f"Query decomposition failed: {e}")
            # Fallback: treat as single-hop
            return self._create_single_hop_fallback(query)

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response."""
        import re

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try markdown code block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))

        # Try first {...} block
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            return json.loads(brace_match.group(0))

        raise ValueError("No valid JSON found in response")

    def _parse_response(self, response: dict, original_query: str) -> DecomposedQuery:
        """Parse LLM response into DecomposedQuery."""
        query_type_str = response.get("query_type", "single_hop")
        try:
            query_type = QueryType(query_type_str)
        except ValueError:
            logger.warning(f"Unknown query type '{query_type_str}', defaulting to single_hop")
            query_type = QueryType.SINGLE_HOP

        steps = []
        for step_data in response.get("steps", []):
            step = QueryStep(
                step_id=step_data.get("step_id", f"step{len(steps) + 1}"),
                description=step_data.get("description", ""),
                query=step_data.get("query", original_query),
                dependencies=step_data.get("dependencies", []),
                expected_output=step_data.get("expected_output", "code"),
            )
            steps.append(step)

        return DecomposedQuery(
            original_query=original_query,
            query_type=query_type,
            steps=steps,
            reasoning=response.get("reasoning", ""),
        )

    def _create_single_hop_fallback(self, query: str) -> DecomposedQuery:
        """Create single-hop fallback when decomposition fails."""
        return DecomposedQuery(
            original_query=query,
            query_type=QueryType.SINGLE_HOP,
            steps=[
                QueryStep(
                    step_id="step1",
                    description="Search for relevant code",
                    query=query,
                    dependencies=[],
                    expected_output="code",
                )
            ],
            reasoning="Fallback: treated as single-hop query",
        )
