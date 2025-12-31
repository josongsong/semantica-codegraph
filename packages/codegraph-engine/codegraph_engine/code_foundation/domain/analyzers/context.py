"""
Analysis Context

RFC-024 Part 2: Framework - Type-Safe Context

Purpose:
    분석 결과를 타입 안전하게 저장/조회
    문자열 키 대신 타입 기반 (Type[T] → T)

Features:
    - 타입 안전 (Generic)
    - 증분 모드 플래그
    - SCCP baseline 보장
    - Changed functions 추적

L11 Production:
    - KeyError 대신 명확한 에러 메시지
    - SCCP baseline 필수 검증
    - Thread-safety 문서화
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.constant_propagation.models import ConstantPropagationResult

T = TypeVar("T")


class AnalysisContext:
    """
    분석 컨텍스트 (Type-Safe)

    RFC-024 핵심 설계:
        - SCCP baseline 필수 (모든 Tier 2+ 분석 전에)
        - 타입 기반 저장/조회 (문자열 키 금지!)
        - 증분 모드 지원

    Features:
        ✅ 타입 안전 (Type[T] → T)
        ✅ SCCP baseline 검증
        ✅ 증분 모드 플래그
        ✅ Changed functions 추적

    Usage:
        >>> context = AnalysisContext()
        >>> context.set(ConstantPropagationAnalyzer, result)
        >>> result = context.get(ConstantPropagationAnalyzer)  # 타입 안전!

        >>> context.require_sccp()  # SCCP 필수 검증
        >>> context.set_incremental(True)  # 증분 모드

    Thread-Safety:
        Not thread-safe (단일 스레드 전용)
        멀티스레드 시 외부 lock 필요

    Performance:
        O(1) 저장/조회 (dict 기반)
    """

    def __init__(self):
        """Initialize context"""
        # 타입 기반 저장 (Type[Analyzer] → result)
        self._results: dict[type, Any] = {}

        # 증분 모드 플래그
        self._incremental: bool = False

        # 변경된 함수 (증분 모드용)
        self._changed_functions: set[str] = set()

    def set(self, analyzer_cls: type[T], result: T) -> None:
        """
        분석 결과 저장 (타입 안전!)

        Args:
            analyzer_cls: 분석기 타입 (Type[IAnalyzer])
            result: 분석 결과

        Examples:
            >>> from src.contexts...constant_propagation import ConstantPropagationAnalyzer
            >>> context.set(ConstantPropagationAnalyzer, result)

        Thread-Safety:
            Not thread-safe
        """
        self._results[analyzer_cls] = result

    def get(self, analyzer_cls: type[T]) -> T:
        """
        분석 결과 조회 (타입 안전!)

        Args:
            analyzer_cls: 분석기 타입

        Returns:
            분석 결과 (타입: T)

        Raises:
            KeyError: 결과 없을 때 (명확한 에러 메시지)

        Examples:
            >>> result = context.get(ConstantPropagationAnalyzer)
            # result 타입: ConstantPropagationResult

        Thread-Safety:
            Read-only, 안전
        """
        if analyzer_cls not in self._results:
            raise KeyError(
                f"Analysis result not found: {analyzer_cls.__name__}. "
                f"Available: {[cls.__name__ for cls in self._results.keys()]}"
            )

        return self._results[analyzer_cls]

    def has(self, analyzer_cls: type) -> bool:
        """
        분석 결과 존재 확인

        Args:
            analyzer_cls: 분석기 타입

        Returns:
            존재하면 True

        Thread-Safety:
            안전
        """
        return analyzer_cls in self._results

    def set_incremental(self, incremental: bool) -> None:
        """
        증분 모드 설정

        Args:
            incremental: 증분 모드 여부

        Use Case:
            Pipeline.run(incremental=True)
        """
        self._incremental = incremental

    @property
    def incremental(self) -> bool:
        """증분 모드 여부"""
        return self._incremental

    def set_changed_functions(self, changed: set[str]) -> None:
        """
        변경된 함수 설정 (증분 모드용)

        Args:
            changed: 변경된 함수 ID 집합

        Use Case:
            ChangeDetector → Pipeline → 분석기
        """
        self._changed_functions = changed

    def get_changed_functions(self) -> set[str]:
        """변경된 함수 조회"""
        return self._changed_functions.copy()

    def require_sccp(self) -> ConstantPropagationResult:
        """
        SCCP baseline 필수 검증 (RFC-024 핵심!)

        Returns:
            ConstantPropagationResult

        Raises:
            RuntimeError: SCCP 실행 안 됐을 때

        Use Case:
            Tier 2+ 분석기는 반드시 호출

        Examples:
            >>> class MyAnalyzer(IAnalyzer):
            ...     def analyze(self, ir_doc, context):
            ...         sccp = context.require_sccp()  # 필수!
            ...         # SCCP 결과 활용

        RFC-024 Policy:
            "SCCP 없는 고급 분석 금지"
        """
        from codegraph_engine.code_foundation.infrastructure.dfg.constant.analyzer import ConstantPropagationAnalyzer

        if not self.has(ConstantPropagationAnalyzer):
            raise RuntimeError(
                "SCCP baseline not executed! "
                "All Tier 2+ analyzers require SCCP baseline. "
                "Pipeline must execute ConstantPropagationAnalyzer first."
            )

        return self.get(ConstantPropagationAnalyzer)

    def clear(self) -> None:
        """
        컨텍스트 초기화

        Use Case:
            테스트, 메모리 절약
        """
        self._results.clear()
        self._changed_functions.clear()
        self._incremental = False
