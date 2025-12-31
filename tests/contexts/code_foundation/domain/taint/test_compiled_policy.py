"""
CompiledPolicy Unit Tests

SOTA L11급:
- Base case: 기본 생성 및 속성
- Edge case: 빈 값, None 처리
- Corner case: 큰 constraints, 특수 문자
- Error case: 타입 검증
"""

import pytest


class TestCompiledPolicy:
    """CompiledPolicy Value Object 테스트"""

    # ========================================================================
    # Base Cases
    # ========================================================================

    def test_base_case_creation(self):
        """기본 생성"""
        from codegraph_engine.code_foundation.domain.taint.compiled_policy import CompiledPolicy

        # Given: 기본 파라미터
        flow_query = object()  # Mock FlowExpr
        constraints = {"max_depth": 10}

        # When: 생성
        policy = CompiledPolicy(
            flow_query=flow_query,
            constraints=constraints,
        )

        # Then: 속성 확인
        assert policy.flow_query is flow_query
        assert policy.constraints == {"max_depth": 10}
        assert policy.metadata == {}

    def test_base_case_with_metadata(self):
        """메타데이터 포함 생성"""
        from codegraph_engine.code_foundation.domain.taint.compiled_policy import CompiledPolicy

        metadata = {"policy_id": "sql-injection", "version": "1.0"}
        policy = CompiledPolicy(
            flow_query=object(),
            constraints={},
            metadata=metadata,
        )

        assert policy.metadata == metadata

    def test_base_case_repr(self):
        """__repr__ 확인"""
        from codegraph_engine.code_foundation.domain.taint.compiled_policy import CompiledPolicy

        policy = CompiledPolicy(
            flow_query=object(),
            constraints={"a": 1, "b": 2},
        )

        repr_str = repr(policy)
        assert "CompiledPolicy" in repr_str
        assert "a" in repr_str or "b" in repr_str

    # ========================================================================
    # Edge Cases
    # ========================================================================

    def test_edge_case_empty_constraints(self):
        """빈 constraints"""
        from codegraph_engine.code_foundation.domain.taint.compiled_policy import CompiledPolicy

        policy = CompiledPolicy(
            flow_query=object(),
            constraints={},
        )

        assert policy.constraints == {}

    def test_edge_case_none_metadata(self):
        """None 메타데이터 → 빈 dict"""
        from codegraph_engine.code_foundation.domain.taint.compiled_policy import CompiledPolicy

        policy = CompiledPolicy(
            flow_query=object(),
            constraints={},
            metadata=None,
        )

        assert policy.metadata == {}

    def test_edge_case_none_flow_query(self):
        """None flow_query (허용)"""
        from codegraph_engine.code_foundation.domain.taint.compiled_policy import CompiledPolicy

        policy = CompiledPolicy(
            flow_query=None,
            constraints={},
        )

        assert policy.flow_query is None

    # ========================================================================
    # Corner Cases
    # ========================================================================

    def test_corner_case_large_constraints(self):
        """많은 constraints"""
        from codegraph_engine.code_foundation.domain.taint.compiled_policy import CompiledPolicy

        constraints = {f"key_{i}": i for i in range(1000)}
        policy = CompiledPolicy(
            flow_query=object(),
            constraints=constraints,
        )

        assert len(policy.constraints) == 1000

    def test_corner_case_nested_constraints(self):
        """중첩된 constraints"""
        from codegraph_engine.code_foundation.domain.taint.compiled_policy import CompiledPolicy

        constraints = {"level1": {"level2": {"level3": {"value": 42}}}}
        policy = CompiledPolicy(
            flow_query=object(),
            constraints=constraints,
        )

        assert policy.constraints["level1"]["level2"]["level3"]["value"] == 42

    def test_corner_case_special_chars_in_keys(self):
        """특수 문자 키"""
        from codegraph_engine.code_foundation.domain.taint.compiled_policy import CompiledPolicy

        constraints = {
            "key-with-dash": 1,
            "key.with.dot": 2,
            "key:with:colon": 3,
            "한글키": 4,
        }
        policy = CompiledPolicy(
            flow_query=object(),
            constraints=constraints,
        )

        assert policy.constraints["한글키"] == 4

    # ========================================================================
    # Integration: Domain Import
    # ========================================================================

    def test_import_from_domain_package(self):
        """domain.taint 패키지에서 import 가능"""
        from codegraph_engine.code_foundation.domain.taint import CompiledPolicy

        policy = CompiledPolicy(
            flow_query=object(),
            constraints={"test": True},
        )

        assert policy is not None

    def test_import_from_infrastructure_reexport(self):
        """infrastructure에서 re-export된 CompiledPolicy와 동일"""
        from codegraph_engine.code_foundation.domain.taint.compiled_policy import (
            CompiledPolicy as DomainCP,
        )
        from codegraph_engine.code_foundation.infrastructure.taint.query_adapter import (
            CompiledPolicy as InfraCP,
        )

        assert DomainCP is InfraCP, "Domain과 Infrastructure의 CompiledPolicy가 동일해야 함"

    # ========================================================================
    # Hexagonal Architecture Compliance
    # ========================================================================

    def test_hexagonal_no_infrastructure_import(self):
        """compiled_policy.py가 infrastructure를 import하지 않음"""
        from pathlib import Path

        file_path = Path("src/contexts/code_foundation/domain/taint/compiled_policy.py")
        content = file_path.read_text()

        assert "from codegraph_engine.code_foundation.infrastructure" not in content
        assert "import codegraph_engine.code_foundation.infrastructure" not in content
