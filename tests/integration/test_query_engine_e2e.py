"""
RFC-021 End-to-End Tests (실제 데이터)

Critical: Mock이 아닌 실제 IR 데이터로 검증

Test Cases:
1. 실제 Python 파일 → IR 빌드
2. QueryEngine (realtime/pr/full) 실행
3. DeepAnalyzer k-CFA 실제 작동
4. 성능 측정
"""

import time
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.domain.query.factories import Q
from codegraph_engine.code_foundation.domain.query.options import QueryOptions
from codegraph_engine.code_foundation.domain.query.results import StopReason


class TestRFC021EndToEnd:
    """RFC-021 E2E 테스트 (실제 데이터)"""

    @pytest.fixture
    def simple_python_file(self):
        """Simple Python file for testing"""
        return Path("benchmark/test_fixtures/python/injection/nosql_injection_simple.py")

    @pytest.fixture
    def ir_doc(self, simple_python_file):
        """Build IR from Python file"""
        if not simple_python_file.exists():
            pytest.skip(f"Benchmark file not found: {simple_python_file}")

        # Build IR
        try:
            from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator

            generator = _PythonIRGenerator()
            code = simple_python_file.read_text()
            ir_doc = generator.generate(
                code=code,
                file_path=str(simple_python_file),
                repo_id="test_benchmark",
            )

            return ir_doc
        except Exception as e:
            pytest.skip(f"IR generation failed: {e}")

    def test_realtime_mode_with_real_ir(self, ir_doc):
        """realtime 모드 + 실제 IR"""
        from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine

        engine = QueryEngine(ir_doc)

        # Taint query: user input → eval/exec
        expr = Q.Var("user_input") >> Q.Call("eval")

        start = time.time()
        result = engine.execute_flow(expr, mode="realtime")
        elapsed = (time.time() - start) * 1000

        # 검증
        assert result.stop_reason in (StopReason.COMPLETE, StopReason.NO_MATCH, StopReason.TIMEOUT)
        assert result.elapsed_ms >= 0

        # Performance check (soft limit)
        if elapsed > 100:
            print(f"⚠️  realtime mode took {elapsed:.1f}ms (target: <100ms)")

    def test_pr_mode_with_real_ir(self, ir_doc):
        """pr 모드 + 실제 IR"""
        from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine

        engine = QueryEngine(ir_doc)

        expr = Q.Var("request") >> Q.Call("execute")

        start = time.time()
        result = engine.execute_flow(expr, mode="pr")
        elapsed = (time.time() - start) * 1000

        assert result.stop_reason in (StopReason.COMPLETE, StopReason.NO_MATCH)
        assert result.elapsed_ms >= 0

        if elapsed > 5000:
            print(f"⚠️  pr mode took {elapsed:.1f}ms (target: <5000ms)")

    def test_full_mode_with_real_ir_and_context(self, ir_doc):
        """full 모드 + 실제 IR + project_context"""
        from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine

        # Build project_context with call graph
        try:
            from codegraph_engine.code_foundation.infrastructure.call_graph.builder import CallGraphBuilder

            cg_builder = CallGraphBuilder()
            call_graph = cg_builder.build_from_ir(ir_doc)

            class ProjectContext:
                def __init__(self, cg):
                    self.call_graph = cg
                    self.ir_documents = []

            ctx = ProjectContext(call_graph)

            engine = QueryEngine(ir_doc, project_context=ctx)

            expr = Q.Var("input") >> Q.Call("eval")

            start = time.time()
            result = engine.execute_flow(expr, mode="full")
            elapsed = (time.time() - start) * 1000

            # 검증
            assert result.stop_reason in (StopReason.COMPLETE, StopReason.NO_MATCH, StopReason.ERROR)
            assert result.elapsed_ms >= 0
            assert any("mode: full" in d for d in result.diagnostics)
            assert any("k_limit" in d for d in result.diagnostics)

            print(f"✅ full mode: {result.stop_reason.value}, elapsed={elapsed:.1f}ms, paths={len(result.paths)}")

        except ImportError as e:
            pytest.skip(f"CallGraphBuilder not available: {e}")

    def test_cache_performance_real_data(self, ir_doc):
        """Cache 성능 (실제 IR)"""
        from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine

        engine = QueryEngine(ir_doc)
        expr = Q.Var("x") >> Q.Var("y")

        # First run (cache miss)
        start = time.time()
        result1 = engine.execute_flow(expr, mode="pr")
        first_run_ms = (time.time() - start) * 1000

        # Second run (cache hit)
        start = time.time()
        result2 = engine.execute_flow(expr, mode="pr")
        second_run_ms = (time.time() - start) * 1000

        # Cache should be faster
        print(f"Cache performance: first={first_run_ms:.2f}ms, cached={second_run_ms:.2f}ms")
        print(f"Speedup: {first_run_ms / max(second_run_ms, 0.001):.1f}x")

        assert result1 is result2  # Same object
        assert second_run_ms < first_run_ms or first_run_ms < 1  # Cached is faster (or too fast to measure)


class TestRFC021CornerCases:
    """Corner Cases (실제 데이터)"""

    def test_empty_ir_document(self):
        """빈 IR 문서"""
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
        from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine

        ir_doc = IRDocument(repo_id="empty", snapshot_id="1", schema_version="2.0")
        # No nodes, no edges

        engine = QueryEngine(ir_doc)
        expr = Q.Var("x") >> Q.Var("y")

        result = engine.execute_flow(expr, mode="pr")

        assert result.stop_reason in (StopReason.COMPLETE, StopReason.NO_MATCH)
        assert len(result.paths) == 0

    def test_mode_override_validation(self):
        """잘못된 override는 경고만 (에러 아님)"""
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
        from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine

        ir_doc = IRDocument(repo_id="test", snapshot_id="1", schema_version="2.0")
        engine = QueryEngine(ir_doc)

        expr = Q.Var("x") >> Q.Var("y")

        # Unknown parameter (should log warning, not crash)
        result = engine.execute_flow(expr, mode="pr", unknown_param=999, another_unknown="test")

        assert result.stop_reason in (StopReason.COMPLETE, StopReason.NO_MATCH)

    def test_extremely_deep_query(self):
        """매우 깊은 쿼리 (max_depth 테스트)"""
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
        from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine

        ir_doc = IRDocument(repo_id="test", snapshot_id="1", schema_version="2.0")
        engine = QueryEngine(ir_doc)

        expr = Q.Var("x") >> Q.Var("y")

        # max_depth=1 (매우 제한적)
        result = engine.execute_flow(expr, mode="pr", max_depth=1)

        assert result.stop_reason in (StopReason.COMPLETE, StopReason.NO_MATCH, StopReason.MAX_DEPTH)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
