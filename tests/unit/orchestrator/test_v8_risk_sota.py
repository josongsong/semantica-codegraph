"""
V8 Risk Calculation SOTA Improvements Tests

Tests for:
- Caching performance
- Error handling
- Validation
"""

from unittest.mock import Mock

import pytest

from apps.orchestrator.orchestrator.domain.code_context import (
    ASTAnalyzer,
    CodeContext,
    DependencyGraphBuilder,
    LanguageSupport,
)
from apps.orchestrator.orchestrator.domain.models import AgentTask
from apps.orchestrator.orchestrator.orchestrator.deep_reasoning_orchestrator import DeepReasoningOrchestrator


class TestRiskCalculationCaching:
    """Risk calculation caching tests (P1-1: Performance)"""

    @pytest.fixture
    def v8(self):
        return DeepReasoningOrchestrator(
            decide_reasoning_path=Mock(),
            execute_tot=Mock(),
            reflection_judge=Mock(),
            fast_path_orchestrator=Mock(),
            ast_analyzer=ASTAnalyzer(),
            graph_builder=DependencyGraphBuilder(),
            embedding_service=Mock(),
        )

    def test_cache_hit_same_file_same_imports(self, v8):
        """
        CRITICAL: Same file + same imports → cache hit

        Performance optimization
        """
        context = CodeContext(
            file_path="test.py",
            language=LanguageSupport.PYTHON,
            ast_depth=5,
            complexity_score=0.3,
            loc=50,
            imports=["os", "sys"],
        )

        task = AgentTask(task_id="1", description="test", repo_id="r1", snapshot_id="s1", metadata={})

        # First call
        risk1 = v8._calculate_risk_score(context, task)

        # Second call (should hit cache)
        risk2 = v8._calculate_risk_score(context, task)

        # Should be identical (cached)
        assert risk1 == risk2

        # Check cache size
        assert len(v8._risk_cache) == 1

    def test_cache_miss_different_imports(self, v8):
        """
        Different imports → cache miss
        """
        context1 = CodeContext(
            file_path="test.py",
            language=LanguageSupport.PYTHON,
            ast_depth=5,
            complexity_score=0.3,
            loc=50,
            imports=["os", "sys"],  # 2 imports
        )

        context2 = CodeContext(
            file_path="test.py",  # Same file
            language=LanguageSupport.PYTHON,
            ast_depth=5,
            complexity_score=0.3,
            loc=50,
            imports=["numpy", "pandas", "scipy", "matplotlib", "seaborn"],  # 5 imports (different count)
        )

        task = AgentTask(task_id="1", description="test", repo_id="r1", snapshot_id="s1", metadata={})

        risk1 = v8._calculate_risk_score(context1, task)
        risk2 = v8._calculate_risk_score(context2, task)

        # Different cache entries (different import hash)
        assert len(v8._risk_cache) == 2

        # Risks might be same if dependency_count is same
        # (dependency_count is from depends_on + depended_by, not imports)
        # Just verify both are valid
        assert 0.0 <= risk1 <= 1.0
        assert 0.0 <= risk2 <= 1.0

    def test_cache_performance_benefit(self, v8):
        """
        Cache provides performance benefit

        Measure: Multiple calls should be faster
        """
        import time

        context = CodeContext(
            file_path="perf.py",
            language=LanguageSupport.PYTHON,
            ast_depth=10,
            complexity_score=0.5,
            loc=200,
            imports=[f"module_{i}" for i in range(10)],
        )

        task = AgentTask(task_id="1", description="test", repo_id="r1", snapshot_id="s1", metadata={})

        # First call (no cache)
        start = time.perf_counter()
        v8._calculate_risk_score(context, task)
        first_time = time.perf_counter() - start

        # Second call (cached)
        start = time.perf_counter()
        v8._calculate_risk_score(context, task)
        cached_time = time.perf_counter() - start

        # Cached should be faster (or at least not slower)
        assert cached_time <= first_time * 1.1  # Allow 10% margin


class TestRiskCalculationErrorHandling:
    """Enhanced error handling tests (P1-2)"""

    @pytest.fixture
    def v8(self):
        return DeepReasoningOrchestrator(
            decide_reasoning_path=Mock(),
            execute_tot=Mock(),
            reflection_judge=Mock(),
            fast_path_orchestrator=Mock(),
            ast_analyzer=ASTAnalyzer(),
            graph_builder=DependencyGraphBuilder(),
            embedding_service=Mock(),
        )

    def test_invalid_all_project_files_type(self, v8):
        """
        CRITICAL: all_project_files가 list가 아닐 때

        Type validation
        """
        context = CodeContext(
            file_path="test.py",
            language=LanguageSupport.PYTHON,
            ast_depth=5,
            complexity_score=0.3,
            loc=50,
            imports=["os"],
        )

        task = AgentTask(
            task_id="1",
            description="test",
            repo_id="r1",
            snapshot_id="s1",
            metadata={"all_project_files": "not a list"},  # ❌ Wrong type
        )

        # Should not crash, should fallback to heuristic
        risk = v8._calculate_risk_score(context, task)

        # Should return valid risk (heuristic only)
        assert 0.0 <= risk <= 1.0

    def test_too_many_files_limit(self, v8):
        """
        CRITICAL: 너무 많은 파일 (> 10K) → skip graph analysis

        DoS protection
        """
        context = CodeContext(
            file_path="test.py",
            language=LanguageSupport.PYTHON,
            ast_depth=5,
            complexity_score=0.3,
            loc=50,
            imports=["os"],
        )

        # 15K files (too many)
        huge_file_list = [f"file_{i}.py" for i in range(15000)]

        task = AgentTask(
            task_id="1",
            description="test",
            repo_id="r1",
            snapshot_id="s1",
            metadata={"all_project_files": huge_file_list},
        )

        # Should not crash or hang
        risk = v8._calculate_risk_score(context, task)

        # Should return heuristic-only risk
        assert 0.0 <= risk <= 1.0

    def test_graph_builder_exception_handling(self, v8):
        """
        Graph builder에서 예외 발생 → graceful fallback
        """
        # Mock graph builder to raise exception
        v8.graph_builder = Mock()
        v8.graph_builder.build_from_contexts.side_effect = ValueError("Invalid graph")

        context = CodeContext(
            file_path="test.py",
            language=LanguageSupport.PYTHON,
            ast_depth=5,
            complexity_score=0.3,
            loc=50,
            imports=["os"],
        )

        task = AgentTask(
            task_id="1", description="test", repo_id="r1", snapshot_id="s1", metadata={"all_project_files": ["test.py"]}
        )

        # Should not crash
        risk = v8._calculate_risk_score(context, task)

        # Should return heuristic-only risk
        assert 0.0 <= risk <= 1.0


class TestRiskCalculationEdgeCases:
    """Edge cases for SOTA risk calculation"""

    @pytest.fixture
    def v8(self):
        return DeepReasoningOrchestrator(
            decide_reasoning_path=Mock(),
            execute_tot=Mock(),
            reflection_judge=Mock(),
            fast_path_orchestrator=Mock(),
            ast_analyzer=ASTAnalyzer(),
            graph_builder=DependencyGraphBuilder(),
            embedding_service=Mock(),
        )

    def test_empty_imports_list(self, v8):
        """
        No imports → minimum dependency risk
        """
        context = CodeContext(
            file_path="isolated.py",
            language=LanguageSupport.PYTHON,
            ast_depth=2,
            complexity_score=0.05,
            loc=10,
            imports=[],  # Empty
        )

        task = AgentTask(task_id="1", description="test", repo_id="r1", snapshot_id="s1", metadata={})

        risk = v8._calculate_risk_score(context, task)

        # Very low risk
        assert risk < 0.1

    def test_cache_key_stability(self, v8):
        """
        Same imports in different order → same cache key
        """
        context1 = CodeContext(
            file_path="test.py",
            language=LanguageSupport.PYTHON,
            ast_depth=5,
            complexity_score=0.3,
            loc=50,
            imports=["os", "sys", "json"],
        )

        context2 = CodeContext(
            file_path="test.py",
            language=LanguageSupport.PYTHON,
            ast_depth=5,
            complexity_score=0.3,
            loc=50,
            imports=["json", "os", "sys"],  # Different order
        )

        task = AgentTask(task_id="1", description="test", repo_id="r1", snapshot_id="s1", metadata={})

        risk1 = v8._calculate_risk_score(context1, task)
        risk2 = v8._calculate_risk_score(context2, task)

        # Should be same (imports sorted before hashing)
        assert risk1 == risk2

        # Should hit cache (only 1 entry)
        assert len(v8._risk_cache) == 1
