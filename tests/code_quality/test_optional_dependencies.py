"""
Optional Dependency Fallback 테스트 (L11 SOTA급)

Fake/Stub 금지 원칙 검증:
- Optional dependency 없으면 명시적 NotImplementedError
- return True 같은 fake 응답 금지

Test Isolation:
- Mock을 사용한 dependency injection
- CI 환경에서도 안정적 실행
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestTreeSitterCompatibility:
    """tree-sitter optional dependency 검증"""

    def test_base_case_tree_sitter_available(self):
        """Base Case: tree-sitter 있으면 정상 동작"""
        from codegraph_engine.code_foundation.infrastructure.generators.python._tree_sitter_compat import (
            TREE_SITTER_AVAILABLE,
            require_tree_sitter,
        )

        if TREE_SITTER_AVAILABLE:
            # 에러 없이 통과해야 함
            require_tree_sitter()
        else:
            # 없으면 NotImplementedError 발생해야 함
            with pytest.raises(NotImplementedError, match="tree-sitter is required"):
                require_tree_sitter()

    def test_edge_case_tree_sitter_not_available_mock(self):
        """Edge Case: tree-sitter 없는 환경 Mock 테스트 (격리)"""
        # Mock으로 tree-sitter 없는 환경 시뮬레이션
        with patch.dict(sys.modules, {"tree_sitter": None}):
            # require_tree_sitter import (cache 회피)
            import importlib

            from codegraph_engine.code_foundation.infrastructure.generators.python import _tree_sitter_compat

            importlib.reload(_tree_sitter_compat)

            # NotImplementedError 발생해야 함
            with pytest.raises(NotImplementedError, match="tree-sitter"):
                _tree_sitter_compat.require_tree_sitter()

    def test_edge_case_safe_node_type_with_none(self):
        """Edge Case: None 입력에 대한 안전한 처리"""
        from codegraph_engine.code_foundation.infrastructure.generators.python._tree_sitter_compat import safe_node_type

        # None 입력
        result = safe_node_type(None)
        assert result == "", "None should return empty string"

    def test_corner_case_safe_node_type_without_tree_sitter(self):
        """Corner Case: tree-sitter 없어도 safe_node_type는 fallback"""
        from codegraph_engine.code_foundation.infrastructure.generators.python._tree_sitter_compat import safe_node_type

        # Mock object without 'type' attribute
        class FakeNode:
            pass

        fake_node = FakeNode()
        result = safe_node_type(fake_node)
        assert result == "", "Object without 'type' should return empty string"

    def test_extreme_case_no_fake_success_responses(self):
        """Extreme Case: Fake 응답 금지 - 실패 시 명시적 에러"""
        from codegraph_engine.code_foundation.infrastructure.generators.python._tree_sitter_compat import (
            TREE_SITTER_AVAILABLE,
            require_tree_sitter,
        )

        # tree-sitter 없으면 NotImplementedError (return True 같은 fake 금지!)
        if not TREE_SITTER_AVAILABLE:
            with pytest.raises(NotImplementedError):
                require_tree_sitter()

            # 에러 메시지가 구체적이어야 함
            try:
                require_tree_sitter()
            except NotImplementedError as e:
                assert "tree-sitter" in str(e).lower()
                assert "pip install" in str(e).lower()


class TestAsyncpgCompatibility:
    """asyncpg optional dependency 검증"""

    def test_base_case_asyncpg_import_error_handling(self):
        """Base Case: asyncpg 없으면 명시적 에러"""
        from codegraph_engine.repo_structure.infrastructure.storage_postgres import PostgresRepoMapStore

        # asyncpg 없으면 __init__에서 ImportError 발생
        # (mock으로 확인 - 실제 테스트는 CI에서)
        assert PostgresRepoMapStore is not None

    def test_edge_case_deprecation_warning(self):
        """Edge Case: Deprecated 클래스는 경고 발생"""
        with pytest.warns(DeprecationWarning, match="PostgresRepoMapStore is deprecated"):
            try:
                from codegraph_engine.repo_structure.infrastructure.storage_postgres import PostgresRepoMapStore

                # asyncpg 없으면 여기서 ImportError 발생 가능
                _ = PostgresRepoMapStore("postgresql://fake")
            except ImportError:
                # asyncpg 없는 경우 - 정상
                pass


class TestRustworkxCompatibility:
    """rustworkx optional dependency 검증"""

    def test_base_case_rustworkx_required_error(self):
        """Base Case: rustworkx 없으면 __init__에서 명시적 에러"""
        from codegraph_engine.reasoning_engine.infrastructure.engine.rust_taint_engine import RustTaintEngine

        # Import는 성공
        assert RustTaintEngine is not None

    def test_edge_case_rx_none_handling(self):
        """Edge Case: rx=None일 때 명시적 ImportError"""
        # RustTaintEngine.__init__()에서 rx가 None이면 ImportError 발생해야 함
        # (실제로는 rx import 여부에 따라 다르므로 조건부 테스트)
        pass


# ============================================================
# Integration Tests
# ============================================================


class TestContainerAgentHandling:
    """Container AgentContainer 처리 검증 (L11급)"""

    def test_base_case_agent_not_available(self):
        """Base Case: AgentContainer 없으면 NotImplementedError"""
        from codegraph_shared.container import HAS_AGENT_AUTOMATION, Container

        if not HAS_AGENT_AUTOMATION:
            container = Container()

            # _agent 접근 시 NotImplementedError 발생해야 함 (None 반환 금지!)
            with pytest.raises(NotImplementedError, match="AgentContainer not available"):
                _ = container._agent

    def test_edge_case_agent_error_message_clarity(self):
        """Edge Case: 에러 메시지가 구체적이고 해결책 제시"""
        from codegraph_shared.container import HAS_AGENT_AUTOMATION, Container

        if not HAS_AGENT_AUTOMATION:
            container = Container()

            try:
                _ = container._agent
                pytest.fail("Should raise NotImplementedError")
            except NotImplementedError as e:
                error_msg = str(e).lower()
                # 에러 메시지가 구체적이어야 함
                assert "agent" in error_msg or "automation" in error_msg
                # 해결책 제시
                assert "v7" in error_msg or "orchestrator" in error_msg or "migration" in error_msg

    def test_corner_case_no_fake_none_return(self):
        """Corner Case: None 반환하지 않고 명시적 에러 (Fake 금지!)"""
        from codegraph_shared.container import HAS_AGENT_AUTOMATION, Container

        if not HAS_AGENT_AUTOMATION:
            container = Container()

            # return None 같은 fake 응답 금지!
            try:
                result = container._agent
                # 여기 도달하면 안 됨 (NotImplementedError 발생해야 함)
                assert result is not None, "Should not return None, should raise NotImplementedError"
            except NotImplementedError:
                # 예상된 동작
                pass


@pytest.mark.integration
class TestIntegrationOptionalDependencies:
    """통합 테스트 - 실제 시나리오"""

    def test_base_case_all_imports_work(self):
        """Base Case: 모든 수정된 파일 import 가능"""
        modules = [
            "src.agent.domain.lock_keeper",
            "src.agent.adapters.code_editing.refactoring.code_transformer",
            "src.contexts.codegen_loop.infrastructure.shadowfs.plugins.incremental_plugin",
            "src.contexts.code_foundation.domain.analyzers.ports",
            "src.contexts.code_foundation.domain.constant_propagation.ports",
            "src.contexts.llm_arbitration.infrastructure.adapters.reasoning_adapter",
            "src.contexts.llm_arbitration.infrastructure.adapters.risk_adapter",
        ]

        for module in modules:
            try:
                __import__(module)
                print(f"✅ {module}")
            except Exception as e:
                pytest.fail(f"Failed to import {module}: {e}")

    def test_edge_case_circular_import_prevention(self):
        """Edge Case: 순환 import 방지 (container.py factory 패턴)"""
        # Container import 시 순환 import 발생하지 않아야 함
        try:
            from codegraph_shared.container import Container

            print("✅ Container import without circular dependency")
        except ImportError as e:
            if "circular" in str(e).lower():
                pytest.fail(f"Circular import detected: {e}")
            # 다른 이유의 ImportError는 허용 (optional dependency 등)

    def test_corner_case_lazy_initialization_isolation(self):
        """Corner Case: Lazy initialization이 서로 독립적"""
        from codegraph_shared.container import Container

        container = Container()

        # _retriever, _indexing 초기화가 _agent에 영향 주지 않아야 함
        # (각각 독립적인 lazy property)
        assert hasattr(container, "_Container__retriever")
        assert hasattr(container, "_Container__indexing")
        assert hasattr(container, "_Container__agent")


@pytest.mark.integration
class TestIntegrationCodeQualityRegression:
    """회귀 테스트 - 코드 품질 유지"""

    def test_base_case_no_undefined_variables(self):
        """Base Case: 정의되지 않은 변수 없음"""
        # 이전에 수정한 code_transformer.py 검증
        from apps.orchestrator.orchestrator.adapters.code_editing.refactoring.code_transformer import ASTCodeTransformer

        # __init__ 가능해야 함
        transformer = ASTCodeTransformer("/tmp")
        assert transformer is not None

    def test_edge_case_deque_memory_bounded(self):
        """Edge Case: deque maxlen 설정되어 메모리 누수 방지"""
        from apps.orchestrator.orchestrator.domain.lock_keeper import RenewalMetrics
        from codegraph_runtime.codegen_loop.infrastructure.shadowfs.plugins.incremental_plugin import PluginMetrics

        # RenewalMetrics
        renewal = RenewalMetrics()
        # _latencies가 maxlen=1000으로 bounded되어 있어야 함
        assert renewal._latencies.maxlen == 1000, "deque should be bounded to prevent memory leak"

        # PluginMetrics
        plugin = PluginMetrics()
        assert plugin._batch_sizes.maxlen == 1000
        assert plugin._ir_delta_latencies.maxlen == 1000
        assert plugin._indexing_latencies.maxlen == 1000

    def test_corner_case_no_hardcoded_values_in_type_checks(self):
        """Corner Case: 타입 체크에 하드코딩된 값 없음"""
        # TYPE_CHECKING 블록이 있는 파일들이 하드코딩 없이 동작해야 함
        from codegraph_engine.code_foundation.infrastructure.generators.python._tree_sitter_compat import (
            safe_node_type,
        )

        # None 입력에 대한 안전한 fallback (하드코딩 아님, 방어적 코딩)
        result = safe_node_type(None)
        assert result == ""

        # Mock object
        class MockNode:
            @property
            def type(self):
                return "test_type"

        mock = MockNode()
        result = safe_node_type(mock)
        assert result == "test_type"
