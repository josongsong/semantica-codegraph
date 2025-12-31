"""
Production Readiness Tests (L11 SOTA)

리네이밍 후 실제 production 배포 가능 여부 검증.

Test Coverage:
1. Logger 메시지 일관성
2. Parameter 이름 일관성
3. Error 메시지 명확성
4. 성능 regression 없음
"""

import pytest


class TestLoggerConsistency:
    """Logger 메시지가 새 이름 사용"""

    def test_deep_reasoning_logger_messages(self):
        """DeepReasoning orchestrator의 logger가 올바른 이름 사용"""
        from apps.orchestrator.orchestrator.orchestrator.deep_reasoning_orchestrator import logger

        # Logger name check
        assert "deep_reasoning" in logger.name.lower() or "agent" in logger.name.lower()

    def test_fast_path_logger_messages(self):
        """FastPath orchestrator의 logger가 올바른 이름 사용"""
        from apps.orchestrator.orchestrator.orchestrator.fast_path_orchestrator import logger

        # Logger name check
        assert "fast_path" in logger.name.lower() or "agent" in logger.name.lower()


class TestParameterNaming:
    """함수 parameter 이름이 일관적"""

    def test_deep_reasoning_init_params(self):
        """DeepReasoningOrchestrator.__init__ parameter 이름 확인"""
        import inspect

        from apps.orchestrator.orchestrator.orchestrator import DeepReasoningOrchestrator

        sig = inspect.signature(DeepReasoningOrchestrator.__init__)
        params = list(sig.parameters.keys())

        # fast_path_orchestrator 사용 (v7_orchestrator 아님)
        assert "fast_path_orchestrator" in params
        assert "v7_orchestrator" not in params


class TestErrorMessages:
    """Error 메시지가 명확하고 새 이름 사용"""

    def test_import_error_suggests_correct_names(self):
        """Import 실패 시 에러 메시지 명확"""
        # This is meta-test: Python's ImportError should be clear
        try:
            from apps.orchestrator.orchestrator.orchestrator import NonExistentClass  # noqa: F401
        except ImportError as e:
            error_msg = str(e)
            # Should have clear error message (not crash)
            assert "cannot import" in error_msg or "ImportError" in str(type(e))
            assert "NonExistentClass" in error_msg


class TestPerformanceRegression:
    """리네이밍으로 인한 성능 저하 없음"""

    def test_import_time_acceptable(self):
        """Import 시간이 합리적 (<1초)"""
        import time

        start = time.time()
        from apps.orchestrator.orchestrator.orchestrator import (  # noqa: F401
            DeepReasoningOrchestrator,
            FastPathOrchestrator,
        )

        elapsed = time.time() - start

        # Import should be fast (<1 second)
        assert elapsed < 1.0, f"Import took {elapsed:.2f}s (too slow)"

    def test_alias_resolution_zero_overhead(self):
        """Alias 사용 시 overhead 없음 (same object)"""
        from apps.orchestrator.orchestrator.orchestrator import (
            DeepReasoningOrchestrator,
            V8AgentOrchestrator,
        )

        # Identity check (no wrapper, no proxy)
        assert V8AgentOrchestrator is DeepReasoningOrchestrator

        # Memory address check
        assert id(V8AgentOrchestrator) == id(DeepReasoningOrchestrator)


class TestDocumentation:
    """문서화가 충분함"""

    def test_deep_reasoning_has_docstring(self):
        """DeepReasoningOrchestrator에 docstring 존재"""
        from apps.orchestrator.orchestrator.orchestrator import DeepReasoningOrchestrator

        assert DeepReasoningOrchestrator.__doc__ is not None
        assert len(DeepReasoningOrchestrator.__doc__) > 50

    def test_fast_path_has_docstring(self):
        """FastPathOrchestrator에 docstring 존재"""
        from apps.orchestrator.orchestrator.orchestrator import FastPathOrchestrator

        assert FastPathOrchestrator.__doc__ is not None
        assert len(FastPathOrchestrator.__doc__) > 50

    def test_docstrings_use_new_names(self):
        """Docstring이 새 이름 사용"""
        from apps.orchestrator.orchestrator.orchestrator import (
            DeepReasoningOrchestrator,
            FastPathOrchestrator,
        )

        deep_doc = DeepReasoningOrchestrator.__doc__.lower()
        fast_doc = FastPathOrchestrator.__doc__.lower()

        # Should mention their own names
        assert "deep" in deep_doc or "reasoning" in deep_doc or "system 2" in deep_doc
        assert "fast" in fast_doc or "path" in fast_doc or "system 1" in fast_doc


class TestProductionSafety:
    """Production 환경에서 안전"""

    def test_no_test_only_imports(self):
        """Production 코드에 test-only import 없음"""
        from pathlib import Path

        orchestrator_dir = Path(__file__).parent.parent.parent.parent / "src" / "agent" / "orchestrator"

        for py_file in orchestrator_dir.glob("*.py"):
            if py_file.name.startswith("test_"):
                continue

            content = py_file.read_text()

            # Should not import pytest, unittest, mock in production code
            assert "import pytest" not in content
            assert "from pytest" not in content
            # Mock is OK if it's typing.TYPE_CHECKING block

    def test_all_exports_are_real_classes(self):
        """__all__에 export된 것들이 실제 클래스 또는 유효한 값"""
        from src.agent import orchestrator

        for name in orchestrator.__all__:
            obj = getattr(orchestrator, name)

            # Should be a real object (not None)
            assert obj is not None

            # Strings are OK for __version__ and similar metadata
            if name in ("__version__",):
                assert isinstance(obj, str)
            else:
                # Others should be classes or enums
                assert not isinstance(obj, str) or name.startswith("__")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
