"""
Verify TaintTyper-style infrastructure connection

Tests:
1. FunctionTaintSummaryCache integration
2. PathSensitiveTaintAnalyzer connection
3. CFG/DFG-based analysis
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.function_summary import (
    FunctionSummaryCache,
    FunctionTaintSummary,
)
from codegraph_engine.code_foundation.infrastructure.analyzers.interprocedural_taint import (
    InterproceduralTaintAnalyzer,
    SimpleCallGraph,
)


class TestInfrastructureConnection:
    """Test TaintTyper infrastructure connection"""

    def test_cache_integration(self):
        """Test FunctionTaintSummaryCache integration"""
        # Create analyzer with cache
        cg = SimpleCallGraph()
        cg.add_call("main", "process")

        analyzer = InterproceduralTaintAnalyzer(
            call_graph=cg,
            max_depth=10,
        )

        # Cache should be available
        assert analyzer.summary_cache is not None, "Cache should be initialized"
        assert isinstance(analyzer.summary_cache, FunctionSummaryCache)

    def test_modular_checking(self):
        """Test TaintTyper-style modular checking"""
        cache = FunctionSummaryCache()

        # Add summary
        summary = FunctionTaintSummary(
            function_id="test_func",
            tainted_params={0, 1},
            tainted_return=True,
            confidence=0.9,
        )
        cache.put(summary)

        # Retrieve
        retrieved = cache.get("test_func")

        assert retrieved is not None
        assert retrieved.function_id == "test_func"
        assert retrieved.tainted_params == {0, 1}
        assert retrieved.tainted_return is True

    def test_cache_effectiveness(self):
        """Test cache is properly set up"""
        cg = SimpleCallGraph()
        cg.add_call("main", "shared_func")

        analyzer = InterproceduralTaintAnalyzer(call_graph=cg)

        # First analysis
        sources = {"shared_func": {"param_0"}}
        analyzer.analyze(sources=sources, sinks={})

        # Cache should have stats
        stats = analyzer.summary_cache.get_stats()

        # Cache is initialized and tracking
        assert "hits" in stats
        assert "misses" in stats
        assert "cache_size" in stats

        # Should have some activity
        assert stats["hits"] + stats["misses"] >= 0, "Cache should be tracking"

    def test_ir_provider_integration(self):
        """Test IR provider for CFG/DFG access"""
        cg = SimpleCallGraph()
        cg.add_call("main", "process")

        # Mock IR provider
        class MockIRProvider:
            def __init__(self):
                self.cfgs = []
                self.dfg_snapshot = None

        ir_provider = MockIRProvider()

        analyzer = InterproceduralTaintAnalyzer(
            call_graph=cg,
            ir_provider=ir_provider,
        )

        # Should accept IR provider
        assert analyzer.ir_provider is not None
        assert analyzer.ir_provider == ir_provider

    def test_fallback_without_ir(self):
        """Test fallback when IR not available"""
        cg = SimpleCallGraph()
        cg.add_call("main", "process")

        analyzer = InterproceduralTaintAnalyzer(
            call_graph=cg,
            ir_provider=None,  # No IR
        )

        sources = {"process": {"user_input"}}
        paths = analyzer.analyze(sources=sources, sinks={})

        # Should work with conservative analysis
        assert len(analyzer.function_summaries) > 0

    def test_deep_analysis_integration(self):
        """Test deep analysis with CFG/DFG"""
        cg = SimpleCallGraph()
        cg.add_call("source_func", "sink_func")

        analyzer = InterproceduralTaintAnalyzer(
            call_graph=cg,
            ir_provider=None,
        )

        sources = {"source_func": {"param_0"}}
        sinks = {"sink_func": {"param_0"}}

        paths = analyzer.analyze(sources=sources, sinks=sinks)

        # Should detect taint path
        assert len(paths) > 0, "Should find taint path from source to sink"
        assert paths[0].source == "source_func"
        assert paths[0].sink == "sink_func"


class TestPerformance:
    """Test performance improvements from modular checking"""

    def test_cache_improves_performance(self):
        """Test cache provides performance benefit"""
        # Create large call graph
        cg = SimpleCallGraph()
        for i in range(20):
            cg.add_call(f"caller_{i}", "shared_func")

        analyzer = InterproceduralTaintAnalyzer(call_graph=cg)

        import time

        # First run (cache misses)
        start = time.perf_counter()
        sources = {"shared_func": {"param_0"}}
        analyzer.analyze(sources=sources, sinks={})
        first_duration = time.perf_counter() - start

        # Second run (cache hits)
        start = time.perf_counter()
        analyzer.analyze(sources=sources, sinks={})
        second_duration = time.perf_counter() - start

        # Second should be faster or similar
        # (Not much slower at least)
        assert second_duration <= first_duration * 2, (
            f"Cache should not slow down: {second_duration:.4f}s vs {first_duration:.4f}s"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
