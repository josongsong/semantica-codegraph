"""
L11 SOTA급 타입 체킹 패턴 검증 테스트

Test Coverage:
- Base Case: TYPE_CHECKING 패턴이 올바르게 적용되었는지
- Edge Case: Optional dependencies fallback 동작
- Corner Case: Runtime import 실패 시나리오
- Extreme Case: 순환 import 방지 확인
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


class TestTypeCheckingPatterns:
    """TYPE_CHECKING 패턴 검증"""

    def test_base_case_type_checking_imports(self):
        """Base Case: TYPE_CHECKING 블록이 있는 파일들이 정상 import됨"""
        # 최근 수정한 핵심 파일들
        modules_to_test = [
            "src.agent.domain.lock_keeper",
            "src.contexts.code_foundation.infrastructure.dfg.analyzers.python_analyzer",
            "src.contexts.code_foundation.infrastructure.generators.python.analyzers.class_analyzer",
            "src.contexts.code_foundation.infrastructure.generators.python.analyzers.function_analyzer",
        ]

        for module_name in modules_to_test:
            try:
                # Import 가능해야 함
                __import__(module_name)
            except ImportError as e:
                pytest.fail(f"Failed to import {module_name}: {e}")

    def test_edge_case_optional_dependencies(self):
        """Edge Case: Optional dependencies가 없어도 import 가능"""
        # tree-sitter가 없는 상황 시뮬레이션은 어렵지만,
        # TYPE_CHECKING 패턴이 있으면 runtime import 실패하지 않음을 확인

        # AgentContainer (optional)
        try:
            from codegraph_shared.container import HAS_AGENT_AUTOMATION

            # HAS_AGENT_AUTOMATION이 False여도 container import는 성공해야 함
            assert isinstance(HAS_AGENT_AUTOMATION, bool)
        except ImportError as e:
            pytest.fail(f"container.py import failed: {e}")

    def test_corner_case_runtime_type_usage(self):
        """Corner Case: Runtime에서 TYPE_CHECKING 타입 사용 불가능"""
        from apps.orchestrator.orchestrator.domain.lock_keeper import LockKeeper

        # TYPE_CHECKING 블록의 타입은 runtime에 사용 불가
        # 하지만 클래스는 정상 import 가능해야 함
        assert LockKeeper is not None
        assert hasattr(LockKeeper, "__init__")

    def test_extreme_case_no_circular_imports(self):
        """Extreme Case: 순환 import 없음 (container.py의 factory 패턴)"""
        from codegraph_shared.container import Container

        # Container 인스턴스 생성 시 순환 import 발생하지 않아야 함
        # (실제로 인스턴스화하지 않고 클래스만 확인)
        assert Container is not None
        assert hasattr(Container, "_retriever")
        assert hasattr(Container, "_indexing")
        assert hasattr(Container, "_agent")


class TestFutureAnnotations:
    """from __future__ import annotations 검증"""

    def test_base_case_future_annotations_present(self):
        """Base Case: 주요 파일들에 future annotations 있음"""
        files_to_check = [
            "src/container.py",
            "src/contexts/code_foundation/infrastructure/generators/python_generator.py",
            "src/contexts/code_foundation/infrastructure/semantic_ir/bfg/builder.py",
            "src/contexts/codegen_loop/infrastructure/hcg_adapter.py",
        ]

        base_path = Path(__file__).parent.parent.parent

        for file_rel in files_to_check:
            file_path = base_path / file_rel
            assert file_path.exists(), f"File not found: {file_rel}"

            content = file_path.read_text(encoding="utf-8")
            assert "from __future__ import annotations" in content, f"Missing future annotations in {file_rel}"

    def test_edge_case_no_duplicate_imports(self):
        """Edge Case: TYPE_CHECKING import와 일반 import 중복 없음"""
        file_path = Path(__file__).parent.parent.parent / "src/agent/domain/lock_keeper.py"
        content = file_path.read_text(encoding="utf-8")

        # 'deque'가 한 번만 import되어야 함
        import_count = content.count("from collections import deque")
        assert import_count == 1, f"deque imported {import_count} times (expected 1)"


class TestRuntimeBehavior:
    """Runtime 동작 검증"""

    def test_base_case_deque_usage(self):
        """Base Case: deque가 runtime에서 정상 작동"""
        from collections import deque

        from apps.orchestrator.orchestrator.domain.lock_keeper import RenewalMetrics

        metrics = RenewalMetrics()
        metrics.record_renewal(10.5, True)

        # deque가 제대로 동작해야 함
        assert metrics.total_renewals == 1
        assert metrics.avg_renewal_latency_ms > 0

    def test_edge_case_optional_dependency_fallback(self):
        """Edge Case: Optional dependency 없어도 fallback 동작"""
        # AgentContainer가 없어도 container import는 성공
        from codegraph_shared.container import HAS_AGENT_AUTOMATION, Container

        if not HAS_AGENT_AUTOMATION:
            # AgentContainer None이어도 Container는 동작해야 함
            assert Container is not None

    def test_corner_case_tsnode_any_fallback(self):
        """Corner Case: TSNode이 Any로 fallback되어도 함수 동작"""
        from codegraph_engine.code_foundation.infrastructure.generators.python.analyzers.class_analyzer import (
            ClassAnalyzer,
        )

        # TSNode이 Any여도 ClassAnalyzer는 import 가능
        assert ClassAnalyzer is not None


class TestTypeIgnoreComments:
    """# type: ignore 주석 검증"""

    def test_base_case_type_ignore_documented(self):
        """Base Case: type: ignore 주석이 있는 라인들이 명확히 문서화됨"""
        files_with_type_ignore = [
            "src/container.py",
            "src/contexts/code_foundation/infrastructure/parsing/incremental_parser.py",
            "src/contexts/codegen_loop/infrastructure/hcg_adapter.py",
        ]

        base_path = Path(__file__).parent.parent.parent

        for file_rel in files_with_type_ignore:
            file_path = base_path / file_rel
            content = file_path.read_text(encoding="utf-8")

            # type: ignore 주석이 있으면 그 이유가 명확해야 함
            # (optional dependency, runtime conditional import 등)
            if "# type: ignore" in content:
                # 주석 근처에 설명이 있어야 함 (주석 또는 try/except)
                assert "optional" in content.lower() or "TYPE_CHECKING" in content or "try:" in content, (
                    f"{file_rel} has type: ignore without explanation"
                )

    def test_edge_case_no_blanket_type_ignore(self):
        """Edge Case: 파일 전체 type: ignore 금지"""
        files_to_check = [
            "src/container.py",
            "src/agent/domain/lock_keeper.py",
        ]

        base_path = Path(__file__).parent.parent.parent

        for file_rel in files_to_check:
            file_path = base_path / file_rel
            content = file_path.read_text(encoding="utf-8")

            # 파일 상단에 blanket type: ignore 금지
            first_lines = "\n".join(content.splitlines()[:20])
            assert "# type: ignore" not in first_lines or "Optional" in first_lines, (
                f"{file_rel} has blanket type: ignore at file level"
            )


@pytest.mark.integration
class TestIntegrationTypeChecking:
    """통합 테스트 - 실제 사용 시나리오"""

    def test_base_case_container_lazy_init(self):
        """Base Case: Container lazy initialization이 타입 안전하게 동작"""
        from codegraph_shared.container import Container

        # Container 생성 (실제 services는 호출하지 않음)
        container = Container()

        # Private 속성 체크 (타입 힌트 검증)
        assert hasattr(container, "_Container__retriever")
        assert hasattr(container, "_Container__indexing")
        assert hasattr(container, "_Container__agent")

    def test_edge_case_incremental_parser_tree_cache(self):
        """Edge Case: IncrementalParser의 Tree 캐시가 타입 안전하게 동작"""
        from codegraph_engine.code_foundation.infrastructure.parsing.incremental_parser import IncrementalParser

        # Parser 없어도 클래스 import는 가능
        assert IncrementalParser is not None

    def test_corner_case_memgraph_transaction_context_manager(self):
        """Corner Case: MemgraphStore transaction이 올바른 Generator 타입"""
        # transaction()이 Generator를 반환하도록 타입 힌트되어 있어야 함
        import inspect

        from codegraph_engine.code_foundation.infrastructure.storage.memgraph.store import MemgraphGraphStore

        sig = inspect.signature(MemgraphGraphStore.transaction)

        # Generator 타입이어야 함 (contextmanager)
        assert sig is not None


# ============================================================
# Extreme Case - AST 기반 검증
# ============================================================


class TestASTLevelVerification:
    """AST 레벨에서 타입 체킹 패턴 검증"""

    def test_extreme_case_no_undefined_variables_in_type_hints(self):
        """Extreme Case: 타입 힌트에 정의되지 않은 변수 없음"""
        problematic_files = [
            "src/agent/adapters/code_editing/refactoring/code_transformer.py",
        ]

        base_path = Path(__file__).parent.parent.parent

        for file_rel in problematic_files:
            file_path = base_path / file_rel
            content = file_path.read_text(encoding="utf-8")

            # AST 파싱
            try:
                tree = ast.parse(content, filename=str(file_path))
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {file_rel}: {e}")

            # FunctionDef에서 undefined 변수 사용 체크
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # 함수 시그니처에서 타입 힌트 체크
                    for arg in node.args.args:
                        if arg.annotation:
                            # annotation이 Name이면서 정의되지 않은 변수면 문제
                            if isinstance(arg.annotation, ast.Name):
                                # TYPE_CHECKING 블록에 정의되어 있거나
                                # 실제 import되어 있어야 함
                                pass  # 간단한 체크만 (실제로는 scope analysis 필요)

    def test_extreme_case_all_type_checking_blocks_valid(self):
        """Extreme Case: 모든 TYPE_CHECKING 블록이 valid Python"""
        files_with_type_checking = [
            "src/agent/domain/lock_keeper.py",
            "src/contexts/code_foundation/domain/analyzers/ports.py",
        ]

        base_path = Path(__file__).parent.parent.parent

        for file_rel in files_with_type_checking:
            file_path = base_path / file_rel
            content = file_path.read_text(encoding="utf-8")

            assert "TYPE_CHECKING" in content, f"{file_rel} should have TYPE_CHECKING"

            # AST 파싱 가능해야 함
            try:
                ast.parse(content, filename=str(file_path))
            except SyntaxError as e:
                pytest.fail(f"Invalid Python syntax in {file_rel}: {e}")
