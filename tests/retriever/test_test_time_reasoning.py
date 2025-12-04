"""
Integration Tests for Test-Time Reasoning (Phase 3.2)
"""

import pytest

from src.retriever.reasoning.models import SearchTool
from src.retriever.reasoning.test_time_compute import ReasoningRetriever


class MockLLMClient:
    """Mock LLM client for reasoning."""

    def __init__(self):
        self.call_count = 0

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate mock response."""
        self.call_count += 1

        # First call: planning
        if self.call_count == 1:
            return """
            {
                "reasoning": "Start with symbol search to find definitions",
                "steps": [
                    {
                        "step_number": 1,
                        "tool": "symbol",
                        "query": "authentication functions",
                        "reasoning": "Symbol search is best for finding definitions"
                    },
                    {
                        "step_number": 2,
                        "tool": "lexical",
                        "query": "auth login",
                        "reasoning": "Lexical search for usage patterns"
                    }
                ]
            }
            """

        # Second call: sufficiency evaluation
        return """
        {
            "is_sufficient": true,
            "reasoning": "Found enough results",
            "confidence": 0.9
        }
        """


class MockRetrieverService:
    """Mock retriever service."""

    async def retrieve(self, repo_id, snapshot_id, query, scope=None, **kwargs):
        """Mock retrieve."""
        return {
            "results": [{"chunk_id": f"chunk_{query[:5]}", "score": 0.85, "content": query}],
            "count": 1,
        }


@pytest.mark.asyncio
async def test_reasoning_retriever_basic():
    """Test basic reasoning retrieval."""
    llm_client = MockLLMClient()
    retriever_service = MockRetrieverService()

    reasoner = ReasoningRetriever(retriever_service, llm_client)

    result = await reasoner.retrieve_with_reasoning(
        repo_id="test-repo",
        snapshot_id="main",
        query="How does authentication work?",
    )

    # Verify result structure
    assert result.original_query == "How does authentication work?"
    assert result.strategy is not None
    assert len(result.strategy.steps) > 0
    assert len(result.steps) > 0
    assert result.final_results is not None


@pytest.mark.asyncio
async def test_reasoning_step_execution():
    """Test individual reasoning step execution."""
    llm_client = MockLLMClient()
    retriever_service = MockRetrieverService()

    reasoner = ReasoningRetriever(retriever_service, llm_client)

    # Plan strategy
    strategy = await reasoner._plan_search("Find error handling")

    assert strategy is not None
    assert len(strategy.steps) > 0
    assert strategy.steps[0].tool in SearchTool


@pytest.mark.asyncio
async def test_sufficiency_evaluation():
    """Test result sufficiency evaluation."""
    llm_client = MockLLMClient()
    retriever_service = MockRetrieverService()

    reasoner = ReasoningRetriever(retriever_service, llm_client)

    # Create mock step results
    step_results = [
        {
            "step_number": 1,
            "tool": SearchTool.SYMBOL,
            "results": [{"chunk_id": "chunk_1", "score": 0.9}],
        }
    ]

    is_sufficient = await reasoner._evaluate_sufficiency("Find auth", step_results)

    assert isinstance(is_sufficient, bool)


@pytest.mark.asyncio
async def test_adaptive_strategy_selection():
    """Test that strategy adapts to query type."""

    class AdaptiveMockLLM:
        async def generate(self, prompt: str, **kwargs) -> str:
            if "definition" in prompt.lower():
                # For definition queries, prefer symbol search
                return """
                {
                    "reasoning": "Definition query needs symbol search",
                    "steps": [
                        {
                            "step_number": 1,
                            "tool": "symbol",
                            "query": "function definition",
                            "reasoning": "Symbol search for definitions"
                        }
                    ]
                }
                """
            else:
                # For other queries, start with vector search
                return """
                {
                    "reasoning": "Semantic search needed",
                    "steps": [
                        {
                            "step_number": 1,
                            "tool": "vector",
                            "query": "semantic meaning",
                            "reasoning": "Vector search for semantic similarity"
                        }
                    ]
                }
                """

    llm_client = AdaptiveMockLLM()
    retriever_service = MockRetrieverService()
    reasoner = ReasoningRetriever(retriever_service, llm_client)

    # Test definition query
    strategy_def = await reasoner._plan_search("Find definition of authenticate")
    assert strategy_def.steps[0].tool == SearchTool.SYMBOL

    # Test semantic query
    strategy_sem = await reasoner._plan_search("What does this code do?")
    assert strategy_sem.steps[0].tool == SearchTool.VECTOR


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
