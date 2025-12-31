"""Container Fallback Logic Tests

V8 실패 시 V7으로 fallback하는 로직을 검증합니다.
"""

from unittest.mock import PropertyMock, patch

import pytest

from apps.orchestrator.orchestrator.orchestrator import DeepReasoningOrchestrator, FastPathOrchestrator
from codegraph_shared.container import Container


class TestContainerFallback:
    """Container의 fallback 로직 테스트"""

    def test_v8_success_returns_v8(self):
        """V8이 정상 동작하면 V8 반환"""
        container = Container()
        orchestrator = container.agent_orchestrator

        # V8 반환 확인
        assert isinstance(orchestrator, DeepReasoningOrchestrator)
        assert orchestrator.__class__.__name__ == "DeepReasoningOrchestrator"

    def test_v8_failure_falls_back_to_v7(self):
        """V8 초기화 실패 시 V7으로 fallback"""

        with patch.object(Container, "v8_agent_orchestrator", new_callable=PropertyMock) as mock_v8:
            # V8 초기화 실패 시뮬레이션
            mock_v8.side_effect = RuntimeError("V8 initialization failed")

            container = Container()

            # V7으로 fallback되어야 함
            orchestrator = container.agent_orchestrator
            assert isinstance(orchestrator, FastPathOrchestrator)
            assert orchestrator.__class__.__name__ == "FastPathOrchestrator"

    def test_both_fail_raises_runtime_error(self):
        """V8, V7 모두 실패 시 RuntimeError 발생"""

        with (
            patch.object(Container, "v8_agent_orchestrator", new_callable=PropertyMock) as mock_v8,
            patch.object(Container, "v7_agent_orchestrator", new_callable=PropertyMock) as mock_v7,
        ):
            # 둘 다 실패
            mock_v8.side_effect = RuntimeError("V8 failed")
            mock_v7.side_effect = RuntimeError("V7 failed")

            container = Container()

            # RuntimeError 발생
            with pytest.raises(RuntimeError, match="Agent orchestrator initialization failed"):
                _ = container.agent_orchestrator

    def test_fallback_preserves_functionality(self):
        """Fallback 후에도 기본 기능 동작"""

        with patch.object(Container, "v8_agent_orchestrator", new_callable=PropertyMock) as mock_v8:
            mock_v8.side_effect = RuntimeError("V8 failed")

            container = Container()
            orchestrator = container.agent_orchestrator

            # V7이지만 기본 속성 접근 가능
            assert hasattr(orchestrator, "execute")
            assert callable(orchestrator.execute)

    def test_multiple_calls_consistent(self):
        """여러 번 호출해도 일관된 결과"""

        with patch.object(Container, "v8_agent_orchestrator", new_callable=PropertyMock) as mock_v8:
            mock_v8.side_effect = RuntimeError("V8 failed")

            container = Container()

            # 여러 번 호출
            orch1 = container.agent_orchestrator
            orch2 = container.agent_orchestrator

            # 같은 인스턴스 (cached_property)
            assert orch1 is orch2
            assert isinstance(orch1, FastPathOrchestrator)


class TestContainerV7DirectAccess:
    """Container의 v7_agent_orchestrator 직접 접근 테스트"""

    def test_v7_direct_access_always_works(self):
        """v7_agent_orchestrator는 직접 접근 가능"""
        container = Container()
        v7 = container.v7_agent_orchestrator

        assert isinstance(v7, FastPathOrchestrator)
        assert v7.__class__.__name__ == "FastPathOrchestrator"


class TestContainerV8DirectAccess:
    """Container의 v8_agent_orchestrator 직접 접근 테스트"""

    def test_v8_direct_access_returns_v8(self):
        """v8_agent_orchestrator는 V8 반환"""
        container = Container()
        v8 = container.v8_agent_orchestrator

        assert isinstance(v8, DeepReasoningOrchestrator)
        assert v8.__class__.__name__ == "DeepReasoningOrchestrator"
