"""
Integration Tests for Observability & Explainability (Phase 3.3)
"""

import pytest

from src.retriever.observability.explainer import RetrievalExplainer
from src.retriever.observability.models import Explanation, RetrievalTrace
from src.retriever.observability.tracing import RetrievalTracer, TraceCollector


def test_retrieval_explainer_basic():
    """Test basic explanation generation."""
    explainer = RetrievalExplainer()

    explanation = explainer.explain_result(
        chunk_id="chunk_123",
        final_score=0.85,
        source_scores={
            "lexical": 0.9,
            "vector": 0.8,
            "symbol": 0.7,
        },
        matched_terms=["authenticate", "login", "user"],
    )

    assert isinstance(explanation, Explanation)
    assert explanation.chunk_id == "chunk_123"
    assert explanation.final_score == 0.85
    assert len(explanation.breakdown) == 3
    assert explanation.reasoning != ""

    # Verify breakdown is sorted by contribution
    contributions = [b.contribution for b in explanation.breakdown]
    assert contributions == sorted(contributions, reverse=True)


def test_explanation_with_source_details():
    """Test explanation with detailed source information."""
    explainer = RetrievalExplainer()

    explanation = explainer.explain_result(
        chunk_id="chunk_456",
        final_score=0.92,
        source_scores={
            "lexical": 0.95,
            "symbol": 0.90,
        },
        source_details={
            "lexical": {"matched_keywords": ["auth", "login"]},
            "symbol": {"matched_symbols": ["authenticate", "login_user"]},
        },
    )

    assert len(explanation.breakdown) == 2
    assert explanation.breakdown[0].details.get("matched_keywords") is not None


def test_explain_ranking():
    """Test ranking explanation for multiple results."""
    explainer = RetrievalExplainer()

    results = [
        {
            "chunk_id": "chunk_1",
            "score": 0.95,
            "source_scores": {"lexical": 0.9, "vector": 0.85},
        },
        {
            "chunk_id": "chunk_2",
            "score": 0.85,
            "source_scores": {"lexical": 0.8, "vector": 0.8},
        },
        {
            "chunk_id": "chunk_3",
            "score": 0.75,
            "source_scores": {"lexical": 0.7, "vector": 0.7},
        },
    ]

    explanations = explainer.explain_ranking(results, top_k=3)

    assert len(explanations) == 3
    assert all(isinstance(exp, Explanation) for exp in explanations)
    # Verify explanations include rank metadata
    assert explanations[0].metadata.get("rank") == 1
    assert explanations[2].metadata.get("rank") == 3


def test_compare_results():
    """Test result comparison."""
    explainer = RetrievalExplainer()

    exp_a = explainer.explain_result(
        chunk_id="chunk_a",
        final_score=0.9,
        source_scores={"lexical": 0.95, "vector": 0.7},
    )

    exp_b = explainer.explain_result(
        chunk_id="chunk_b",
        final_score=0.8,
        source_scores={"lexical": 0.7, "vector": 0.85},
    )

    comparison = explainer.compare_results(exp_a, exp_b)

    assert comparison["score_difference"] == 0.1
    assert "source_differences" in comparison
    assert "primary_reasons" in comparison
    assert len(comparison["primary_reasons"]) > 0


def test_retrieval_tracer_basic():
    """Test basic retrieval tracing."""
    tracer = RetrievalTracer()

    # Start trace
    trace = tracer.start_trace(
        query="find authentication",
        intent="find_definition",
        scope_type="repo",
    )

    assert isinstance(trace, RetrievalTrace)
    assert trace.query == "find authentication"
    assert trace.intent == "find_definition"

    # Record source queries
    tracer.record_source_query("lexical", num_results=50)
    tracer.record_source_query("vector", num_results=30)

    assert trace.num_sources_queried == 2
    assert trace.source_results["lexical"] == 50

    # Finalize
    final_trace = tracer.finalize_trace()
    assert final_trace.total_latency_ms > 0


def test_stage_timing():
    """Test stage latency tracking."""
    import time

    tracer = RetrievalTracer()
    tracer.start_trace("test query", "test_intent")

    # Simulate stages
    with tracer.stage("lexical_search"):
        time.sleep(0.01)  # 10ms

    with tracer.stage("vector_search"):
        time.sleep(0.02)  # 20ms

    trace = tracer.finalize_trace()

    assert "lexical_search" in trace.stage_latencies
    assert "vector_search" in trace.stage_latencies
    assert trace.stage_latencies["lexical_search"] >= 10.0
    assert trace.stage_latencies["vector_search"] >= 20.0


def test_trace_summary():
    """Test trace summary generation."""
    tracer = RetrievalTracer()
    trace = tracer.start_trace("test", "test")

    with tracer.stage("stage1"):
        pass
    with tracer.stage("stage2"):
        pass

    tracer.record_source_query("lexical", 50)
    tracer.finalize_trace()

    summary = tracer.get_trace_summary(trace)

    assert "query" in summary
    assert "sources_queried" in summary
    assert "stage_breakdown" in summary
    assert "total_latency_ms" in summary


def test_trace_collector():
    """Test trace collection and statistics."""
    collector = TraceCollector(max_traces=10)

    # Add traces
    for i in range(5):
        trace = RetrievalTrace(
            query=f"query_{i}",
            intent="find_definition",
            scope_type="repo",
            num_sources_queried=3,
            total_latency_ms=100.0 + i * 10,
        )
        collector.add_trace(trace)

    stats = collector.get_statistics()

    assert stats["total_traces"] == 5
    assert "avg_latency_ms" in stats
    assert "intent_distribution" in stats
    assert stats["intent_distribution"]["find_definition"] == 5


def test_slow_query_detection():
    """Test slow query detection."""
    collector = TraceCollector()

    # Add normal and slow traces
    for i in range(3):
        trace = RetrievalTrace(
            query=f"normal_query_{i}",
            intent="test",
            scope_type="repo",
            total_latency_ms=500.0,
        )
        collector.add_trace(trace)

    for i in range(2):
        trace = RetrievalTrace(
            query=f"slow_query_{i}",
            intent="test",
            scope_type="repo",
            total_latency_ms=1500.0,
        )
        collector.add_trace(trace)

    slow_queries = collector.get_slow_queries(threshold_ms=1000.0)

    assert len(slow_queries) == 2
    assert all(t.total_latency_ms > 1000.0 for t in slow_queries)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
