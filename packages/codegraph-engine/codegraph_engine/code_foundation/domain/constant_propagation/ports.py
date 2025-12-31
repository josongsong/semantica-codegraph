"""
Constant Propagation Ports

RFC-024 Part 1: SCCP Baseline - Hexagonal Port

Hexagonal Architecture:
- Port: 인터페이스 정의 (Domain Layer)
- Adapter: 구현 (Infrastructure Layer)
- Dependency Inversion: Infrastructure → Domain (의존성 역전)
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .models import ConstantPropagationResult

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.ir_document import IRDocument


@runtime_checkable
class IConstantPropagator(Protocol):
    """
    상수 전파 분석 Port (Hexagonal)

    책임:
        IRDocument 분석 → 변수별 상수 값 추론

    구현:
        Infrastructure Layer에서 ConstantPropagationAnalyzer가 구현

    Hexagonal 패턴:
        Domain (Port) ← Infrastructure (Adapter)

        ┌─────────────────────┐
        │   Domain            │
        │  IConstantPropagator│ ← Port (interface)
        └─────────────────────┘
                  ↑ implements
        ┌─────────────────────┐
        │  Infrastructure     │
        │  ConstantPropagation│ ← Adapter (concrete)
        │  Analyzer           │
        └─────────────────────┘

    SOLID:
        - Single Responsibility: 상수 전파만
        - Open/Closed: 확장 가능 (여러 구현체)
        - Liskov: 구현체 치환 가능
        - Interface Segregation: 작은 인터페이스
        - Dependency Inversion: 추상에 의존
    """

    def analyze(self, ir_doc: "IRDocument") -> ConstantPropagationResult:
        """
        전체 IR 문서 분석

        Args:
            ir_doc: IR Document (dfg_snapshot, cfg_blocks, expressions 포함)

        Returns:
            ConstantPropagationResult

        Raises:
            ValueError: DFG 또는 CFG 없을 때
            RuntimeError: 분석 실패 시

        Post-condition:
            - result.var_values는 비어있지 않음
            - result.reachable_blocks는 최소 1개 (entry)
            - result.constants_found >= 0

        Performance:
            O(SSA Edges) - Sparse 알고리즘
            1000 LOC < 100ms 목표

        Thread-Safety:
            읽기 전용, 안전
        """
        ...

    def analyze_function(
        self,
        func_id: str,
        ir_doc: "IRDocument",
    ) -> ConstantPropagationResult:
        """
        단일 함수 분석

        Args:
            func_id: 함수 Node ID
            ir_doc: IR Document

        Returns:
            해당 함수의 ConstantPropagationResult (필터링됨)

        Use Case:
            특정 함수만 분석 (증분 모드)
        """
        ...
