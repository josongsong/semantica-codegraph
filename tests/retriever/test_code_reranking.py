"""
Integration Tests for Code-Specific Reranking (Phase 3.4)
"""

import pytest

from src.retriever.code_reranking.callgraph_reranker import (
    CallGraphReranker,
    MockCallGraphAdapter,
)
from src.retriever.code_reranking.models import CodeRerankedChunk
from src.retriever.code_reranking.structural_reranker import StructuralReranker


def test_structural_reranker_basic():
    """Test basic structural reranking."""
    reranker = StructuralReranker(boost_factor=0.15)

    candidates = [
        {
            "chunk_id": "chunk_1",
            "score": 0.7,
            "content": """
def authenticate(username, password):
    if validate_user(username, password):
        return create_session()
    return None
            """,
        },
        {
            "chunk_id": "chunk_2",
            "score": 0.75,
            "content": """
def login(user):
    session = create_session(user)
    return session
            """,
        },
    ]

    reference_code = """
def authenticate(user, pwd):
    return validate_credentials(user, pwd)
    """

    results = reranker.rerank(
        candidates=candidates,
        reference_code=reference_code,
    )

    assert len(results) == 2
    assert all(isinstance(r, CodeRerankedChunk) for r in results)
    # Verify structural scores are computed
    assert all(r.structural_score >= 0.0 for r in results)
    # Verify boost is applied
    assert all(r.final_score >= r.original_score for r in results)


def test_structural_similarity_function_signatures():
    """Test structural similarity based on function signatures."""
    reranker = StructuralReranker()

    candidates = [
        {
            "chunk_id": "similar_signature",
            "score": 0.6,
            "content": """
def authenticate(username, password):
    pass
            """,
        },
        {
            "chunk_id": "different_signature",
            "score": 0.65,
            "content": """
def process_data(data):
    pass
            """,
        },
    ]

    reference = """
def authenticate(user, pwd):
    pass
    """

    results = reranker.rerank(candidates, reference_code=reference)

    # Chunk with similar function signature should rank higher
    similar_chunk = next(r for r in results if r.chunk_id == "similar_signature")
    different_chunk = next(r for r in results if r.chunk_id == "different_signature")

    assert similar_chunk.structural_score > different_chunk.structural_score


def test_pattern_matching_on_query():
    """Test pattern matching when no reference code is provided."""
    reranker = StructuralReranker()

    candidates = [
        {
            "chunk_id": "has_function",
            "score": 0.7,
            "content": "def process(): pass",
        },
        {
            "chunk_id": "has_class",
            "score": 0.7,
            "content": "class User: pass",
        },
    ]

    # Query asking for function
    results_func = reranker.rerank(
        candidates,
        query_context="find function that processes data",
    )

    func_chunk = next(r for r in results_func if r.chunk_id == "has_function")
    assert func_chunk.ast_similarity is not None

    # Query asking for class
    results_class = reranker.rerank(
        candidates,
        query_context="find class definition",
    )

    class_chunk = next(r for r in results_class if r.chunk_id == "has_class")
    assert class_chunk.ast_similarity is not None


def test_callgraph_reranker_basic():
    """Test basic call graph reranking."""
    adapter = MockCallGraphAdapter()
    reranker = CallGraphReranker(boost_factor=0.20)

    candidates = [
        {
            "chunk_id": "func_b",
            "score": 0.7,
            "functions": ["func_b"],
        },
        {
            "chunk_id": "func_e",
            "score": 0.75,
            "functions": ["func_e"],
        },
    ]

    # Mock graph: func_a -> func_b -> func_c, func_d -> func_e
    # Reference func_a
    results = reranker.rerank(
        candidates,
        reference_functions=["func_a"],
        call_graph_adapter=adapter,
    )

    assert len(results) == 2
    assert all(isinstance(r, CodeRerankedChunk) for r in results)

    # func_b should have higher proximity (direct callee of func_a)
    func_b_result = next(r for r in results if r.chunk_id == "func_b")
    assert func_b_result.cg_proximity is not None
    assert func_b_result.cg_proximity.distance > 0


def test_callgraph_direct_relationship():
    """Test direct caller/callee relationships."""
    adapter = MockCallGraphAdapter()
    reranker = CallGraphReranker()

    candidates = [
        {
            "chunk_id": "direct_callee",
            "score": 0.6,
            "functions": ["func_b"],  # func_a calls func_b
        },
        {
            "chunk_id": "indirect",
            "score": 0.65,
            "functions": ["func_c"],  # func_a -> func_b -> func_c
        },
    ]

    results = reranker.rerank(
        candidates,
        reference_functions=["func_a"],
        call_graph_adapter=adapter,
    )

    direct = next(r for r in results if r.chunk_id == "direct_callee")
    indirect = next(r for r in results if r.chunk_id == "indirect")

    # Direct relationship should have distance 1, score 1.0
    assert direct.cg_proximity.distance == 1
    assert direct.cg_proximity.score == 1.0
    assert direct.cg_proximity.relationship == "callee"

    # Indirect should have distance 2, lower score
    if indirect.cg_proximity:
        assert indirect.cg_proximity.distance == 2
        assert indirect.cg_proximity.score < 1.0


def test_callgraph_path_finding():
    """Test shortest path finding in call graph."""
    adapter = MockCallGraphAdapter()
    reranker = CallGraphReranker(max_distance=3)

    candidates = [
        {
            "chunk_id": "connected",
            "score": 0.7,
            "functions": ["func_c"],
        }
    ]

    results = reranker.rerank(
        candidates,
        reference_functions=["func_a"],
        call_graph_adapter=adapter,
    )

    connected = results[0]
    assert connected.cg_proximity is not None
    assert len(connected.cg_proximity.path) > 1
    assert connected.cg_proximity.path[0] == "func_a"
    assert connected.cg_proximity.path[-1] == "func_c"


def test_production_kuzu_adapter_integration():
    """Test KuzuCallGraphAdapter with mock Kuzu store."""
    from src.retriever.code_reranking.kuzu_callgraph_adapter import (
        KuzuCallGraphAdapter,
    )

    class MockKuzuStore:
        """Mock Kuzu store for testing."""

        def __init__(self):
            self._conn = None

        def query_called_by(self, func_id):
            """Mock implementation."""
            if func_id == "target_func":
                return ["caller_func1", "caller_func2"]
            return []

    mock_store = MockKuzuStore()
    adapter = KuzuCallGraphAdapter(mock_store)

    # Test get_callers
    callers = adapter.get_callers("target_func")
    assert len(callers) == 2
    assert "caller_func1" in callers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
