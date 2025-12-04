"""
Integration Tests for Query Decomposition & Multi-hop Retrieval (Phase 3.1)
"""

import pytest

from src.retriever.query.decomposer import QueryDecomposer
from src.retriever.query.models import DecomposedQuery, QueryType


class MockLLMClient:
    """Mock LLM client for testing."""

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate mock response."""
        # Return a mock JSON response for decomposition
        return """
        {
            "query_type": "multi_hop",
            "steps": [
                {
                    "step_number": 1,
                    "query": "Find authentication function definition",
                    "dependencies": [],
                    "expected_type": "definition"
                },
                {
                    "step_number": 2,
                    "query": "Find all usages of the authentication function",
                    "dependencies": [1],
                    "expected_type": "usage"
                }
            ],
            "reasoning": "This is a multi-hop query requiring definition then usage search"
        }
        """


@pytest.mark.asyncio
async def test_query_decomposer_basic():
    """Test basic query decomposition."""
    llm_client = MockLLMClient()
    decomposer = QueryDecomposer(llm_client)

    query = "Find the authentication function and show where it's called"
    decomposed = await decomposer.decompose(query)

    assert isinstance(decomposed, DecomposedQuery)
    assert decomposed.original_query == query
    assert decomposed.query_type == QueryType.MULTI_HOP
    assert len(decomposed.steps) == 2
    assert decomposed.steps[0].step_number == 1
    assert decomposed.steps[1].step_number == 2
    assert 1 in decomposed.steps[1].dependencies


@pytest.mark.asyncio
async def test_query_decomposer_single_hop():
    """Test single-hop query decomposition."""

    class SingleHopMockLLM:
        async def generate(self, prompt: str, **kwargs) -> str:
            return """
            {
                "query_type": "single_hop",
                "steps": [
                    {
                        "step_number": 1,
                        "query": "Find authentication function",
                        "dependencies": [],
                        "expected_type": "definition"
                    }
                ],
                "reasoning": "Simple single-step query"
            }
            """

    llm_client = SingleHopMockLLM()
    decomposer = QueryDecomposer(llm_client)

    query = "Find authentication function"
    decomposed = await decomposer.decompose(query)

    assert decomposed.query_type == QueryType.SINGLE_HOP
    assert len(decomposed.steps) == 1


@pytest.mark.asyncio
async def test_decomposed_query_execution_order():
    """Test topological sorting for execution order."""
    llm_client = MockLLMClient()
    decomposer = QueryDecomposer(llm_client)

    query = "Find X and Y, then compare them"
    decomposed = await decomposer.decompose(query)

    # Get execution order
    execution_order = decomposed.get_execution_order()

    # Verify order respects dependencies
    assert len(execution_order) == len(decomposed.steps)
    for step in execution_order:
        # All dependencies must have been executed before this step
        for dep_step_num in step.dependencies:
            dep_step = next(s for s in decomposed.steps if s.step_number == dep_step_num)
            assert execution_order.index(dep_step) < execution_order.index(step)


@pytest.mark.asyncio
async def test_multi_hop_retriever_integration():
    """Test MultiHopRetriever with mock retriever service."""
    from src.retriever.query.multi_hop import MultiHopRetriever

    class MockRetrieverService:
        """Mock retriever for testing."""

        async def retrieve(self, repo_id, snapshot_id, query, **kwargs):
            """Mock retrieve returns results based on query."""
            return {
                "results": [{"chunk_id": f"chunk_{query[:10]}", "score": 0.9, "content": query}],
                "count": 1,
            }

    llm_client = MockLLMClient()
    decomposer = QueryDecomposer(llm_client)
    mock_retriever = MockRetrieverService()
    multi_hop = MultiHopRetriever(mock_retriever, decomposer)

    query = "Find authentication function and its usages"
    decomposed = await decomposer.decompose(query)

    result = await multi_hop.retrieve_multi_hop(repo_id="test-repo", snapshot_id="main", decomposed=decomposed)

    # Verify multi-hop result structure
    assert result.original_query == query
    assert result.query_type == QueryType.MULTI_HOP
    assert len(result.step_results) == 2  # Two steps from mock
    assert len(result.all_results) > 0  # Combined results


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
