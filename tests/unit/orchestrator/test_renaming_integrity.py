"""
Renaming Integrity Tests (L11 SOTA)

v7/v8 → FastPath/DeepReasoning 리네이밍 검증.

Test Coverage:
1. Import integrity (새 이름 + backward compatibility)
2. Class existence & type correctness
3. Alias mapping correctness
4. No orphaned references
"""

import pytest


class TestRenamingIntegrity:
    """리네이밍 완전성 검증 (SOTA)"""

    def test_new_names_importable(self):
        """새 이름으로 import 가능"""
        from apps.orchestrator.orchestrator.orchestrator import (
            DeepReasoningOrchestrator,
            DeepReasoningRequest,
            DeepReasoningResponse,
            FastPathOrchestrator,
            FastPathRequest,
            FastPathResponse,
        )

        assert DeepReasoningOrchestrator is not None
        assert DeepReasoningRequest is not None
        assert DeepReasoningResponse is not None
        assert FastPathOrchestrator is not None
        assert FastPathRequest is not None
        assert FastPathResponse is not None

    def test_backward_compatibility_v8(self):
        """V8 이름으로 여전히 import 가능 (backward compatibility)"""
        from apps.orchestrator.orchestrator.orchestrator import (
            V8AgentOrchestrator,
            V8AgentRequest,
            V8AgentResponse,
        )

        assert V8AgentOrchestrator is not None
        assert V8AgentRequest is not None
        assert V8AgentResponse is not None

    def test_backward_compatibility_v7(self):
        """V7 이름으로 여전히 import 가능 (backward compatibility)"""
        from apps.orchestrator.orchestrator.orchestrator import (
            V7AgentOrchestrator,
            V7AgentRequest,
            V7AgentResponse,
        )

        assert V7AgentOrchestrator is not None
        assert V7AgentRequest is not None
        assert V7AgentResponse is not None

    def test_backward_compatibility_generic(self):
        """Generic 이름으로 여전히 import 가능 (backward compatibility)"""
        from apps.orchestrator.orchestrator.orchestrator import (
            AgentOrchestrator,
            AgentRequest,
            AgentResponse,
        )

        assert AgentOrchestrator is not None
        assert AgentRequest is not None
        assert AgentResponse is not None

    def test_alias_mapping_correctness_v8(self):
        """V8 alias가 DeepReasoning으로 올바르게 매핑됨"""
        from apps.orchestrator.orchestrator.orchestrator import (
            DeepReasoningOrchestrator,
            DeepReasoningRequest,
            DeepReasoningResponse,
            V8AgentOrchestrator,
            V8AgentRequest,
            V8AgentResponse,
        )

        # Identity check (same class object)
        assert V8AgentOrchestrator is DeepReasoningOrchestrator
        assert V8AgentRequest is DeepReasoningRequest
        assert V8AgentResponse is DeepReasoningResponse

    def test_alias_mapping_correctness_v7(self):
        """V7 alias가 FastPath로 올바르게 매핑됨"""
        from apps.orchestrator.orchestrator.orchestrator import (
            FastPathOrchestrator,
            FastPathRequest,
            FastPathResponse,
            V7AgentOrchestrator,
            V7AgentRequest,
            V7AgentResponse,
        )

        # Identity check (same class object)
        assert V7AgentOrchestrator is FastPathOrchestrator
        assert V7AgentRequest is FastPathRequest
        assert V7AgentResponse is FastPathResponse

    def test_alias_mapping_correctness_generic(self):
        """Generic alias가 FastPath로 올바르게 매핑됨"""
        from apps.orchestrator.orchestrator.orchestrator import (
            AgentOrchestrator,
            AgentRequest,
            AgentResponse,
            FastPathOrchestrator,
            FastPathRequest,
            FastPathResponse,
        )

        # Identity check (same class object)
        assert AgentOrchestrator is FastPathOrchestrator
        assert AgentRequest is FastPathRequest
        assert AgentResponse is FastPathResponse

    def test_class_names_correct(self):
        """클래스 __name__ 속성이 올바름"""
        from apps.orchestrator.orchestrator.orchestrator import (
            DeepReasoningOrchestrator,
            FastPathOrchestrator,
        )

        assert DeepReasoningOrchestrator.__name__ == "DeepReasoningOrchestrator"
        assert FastPathOrchestrator.__name__ == "FastPathOrchestrator"

    def test_no_old_file_references(self):
        """v7_orchestrator.py, v8_orchestrator.py 파일이 존재하지 않음"""
        import os
        from pathlib import Path

        orchestrator_dir = Path(__file__).parent.parent.parent.parent / "src" / "agent" / "orchestrator"

        old_files = [
            "v7_orchestrator.py",
            "v8_orchestrator.py",
        ]

        for old_file in old_files:
            file_path = orchestrator_dir / old_file
            assert not file_path.exists(), f"Old file still exists: {file_path}"

    def test_new_files_exist(self):
        """새 파일들이 존재함"""
        from pathlib import Path

        orchestrator_dir = Path(__file__).parent.parent.parent.parent / "src" / "agent" / "orchestrator"

        new_files = [
            "fast_path_orchestrator.py",
            "deep_reasoning_orchestrator.py",
        ]

        for new_file in new_files:
            file_path = orchestrator_dir / new_file
            assert file_path.exists(), f"New file missing: {file_path}"

    def test_container_integration(self):
        """Container가 새 이름으로 작동함"""
        # Note: Container 초기화는 환경 설정 필요하므로 import만 검증
        from codegraph_shared.container import Container

        # Container 클래스 존재 확인
        assert Container is not None

        # Container가 agent_orchestrator 메서드를 가지고 있는지 확인
        assert hasattr(Container, "agent_orchestrator")

    def test_top_level_exports(self):
        """src.agent 최상위에서도 import 가능"""
        from src.agent import (
            DeepReasoningOrchestrator,
            DeepReasoningRequest,
            DeepReasoningResponse,
            FastPathOrchestrator,
            FastPathRequest,
            FastPathResponse,
        )

        assert DeepReasoningOrchestrator is not None
        assert FastPathOrchestrator is not None

    def test_dataclass_integrity(self):
        """Request/Response가 dataclass로 올바르게 정의됨"""
        from dataclasses import is_dataclass

        from apps.orchestrator.orchestrator.orchestrator import (
            DeepReasoningRequest,
            DeepReasoningResponse,
            FastPathRequest,
            FastPathResponse,
        )

        assert is_dataclass(DeepReasoningRequest)
        assert is_dataclass(DeepReasoningResponse)
        assert is_dataclass(FastPathRequest)
        assert is_dataclass(FastPathResponse)


class TestEdgeCases:
    """엣지 케이스 검증"""

    def test_multiple_import_styles(self):
        """다양한 import 스타일 모두 작동"""
        # Style 1: Direct import
        # Style 3: Top-level import
        from src.agent import DeepReasoningOrchestrator as DRO2

        # Style 2: Package import
        from apps.orchestrator.orchestrator.orchestrator import DeepReasoningOrchestrator as DRO
        from apps.orchestrator.orchestrator.orchestrator.deep_reasoning_orchestrator import (
            DeepReasoningOrchestrator,
        )

        # All should be same class
        assert DeepReasoningOrchestrator is DRO is DRO2

    def test_circular_import_prevention(self):
        """순환 import가 없음"""
        # 이 테스트가 통과하면 순환 import 없음
        from apps.orchestrator.orchestrator.orchestrator import (
            DeepReasoningOrchestrator,
            FastPathOrchestrator,
        )

        assert DeepReasoningOrchestrator is not None
        assert FastPathOrchestrator is not None

    def test_no_name_collision(self):
        """이름 충돌이 없음"""
        from apps.orchestrator.orchestrator.orchestrator import (
            DeepReasoningOrchestrator,
            DeepReasoningRequest,
            FastPathOrchestrator,
            FastPathRequest,
        )

        # 모두 다른 클래스여야 함
        assert DeepReasoningOrchestrator is not FastPathOrchestrator
        assert DeepReasoningRequest is not FastPathRequest


class TestBackwardCompatibilityExtreme:
    """극한 Backward Compatibility 테스트"""

    def test_legacy_code_pattern_1(self):
        """레거시 패턴 1: V8AgentOrchestrator 직접 사용"""
        from apps.orchestrator.orchestrator.orchestrator import V8AgentOrchestrator

        # 인스턴스 생성은 안 하지만 클래스는 존재해야 함
        assert V8AgentOrchestrator is not None
        assert hasattr(V8AgentOrchestrator, "execute")

    def test_legacy_code_pattern_2(self):
        """레거시 패턴 2: V7AgentOrchestrator 직접 사용"""
        from apps.orchestrator.orchestrator.orchestrator import V7AgentOrchestrator

        assert V7AgentOrchestrator is not None
        assert hasattr(V7AgentOrchestrator, "execute")

    def test_legacy_code_pattern_3(self):
        """레거시 패턴 3: Generic AgentOrchestrator"""
        from apps.orchestrator.orchestrator.orchestrator import AgentOrchestrator

        assert AgentOrchestrator is not None
        assert hasattr(AgentOrchestrator, "execute")

    def test_mixed_old_new_imports(self):
        """구 이름과 신 이름 혼용 가능"""
        from apps.orchestrator.orchestrator.orchestrator import (
            DeepReasoningOrchestrator,
            FastPathOrchestrator,
            V7AgentOrchestrator,
            V8AgentOrchestrator,
        )

        # Alias 관계 검증
        assert V8AgentOrchestrator is DeepReasoningOrchestrator
        assert V7AgentOrchestrator is FastPathOrchestrator


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
