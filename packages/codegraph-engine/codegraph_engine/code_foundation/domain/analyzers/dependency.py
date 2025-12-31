"""
Analyzer Dependency Specification

RFC-024 Part 2: Framework - Dependency Abstraction

Purpose:
    분석기마다 다른 의존성 형태를 추상화
    - Constructor 주입 (InterproceduralTaint)
    - Optional enrichment (PointsTo)
    - IRDocument 필드 (dfg_snapshot)

Patterns:
    - RequiredDependency: 필수 (없으면 에러)
    - OptionalDependency: 선택적 (없으면 lazy 생성)
    - IRFieldDependency: IRDocument 필드 (없으면 빌드)

L11 Production:
    - 타입 안전 (Generic)
    - Lazy evaluation
    - 순환 의존성 탐지 가능
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.analyzers.context import AnalysisContext
    from codegraph_engine.code_foundation.domain.analyzers.ports import IAnalyzer
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument


class DependencySpec(ABC):
    """
    의존성 명세 추상 클래스

    Purpose:
        분석기 의존성의 다양한 형태를 통일된 인터페이스로

    Implementations:
        - RequiredDependency: 필수 의존성
        - OptionalDependency: 선택적 (Lazy)
        - IRFieldDependency: IRDocument 필드

    SOLID:
        - Open/Closed: 새 의존성 타입 추가 가능
        - Liskov: 모든 구현체 치환 가능

    Thread-Safety:
        resolve()는 일반적으로 not thread-safe (context 수정)
    """

    @abstractmethod
    def resolve(
        self,
        ir_doc: "IRDocument",
        context: "AnalysisContext",
    ) -> Any:
        """
        의존성 해결

        Args:
            ir_doc: IR Document
            context: 분석 컨텍스트

        Returns:
            해결된 의존성 값

        Raises:
            RuntimeError: 의존성 해결 실패

        Side Effects:
            context 업데이트 가능 (OptionalDependency)
        """
        ...

    @property
    @abstractmethod
    def analyzer_type(self) -> type["IAnalyzer"] | None:
        """
        의존하는 분석기 타입 (DAG 구축용)

        Returns:
            분석기 타입 or None (IRFieldDependency는 None)

        Use Case:
            Pipeline이 의존성 그래프 구축 시 사용
        """
        ...


class RequiredDependency(DependencySpec):
    """
    필수 의존성

    Behavior:
        - context에 없으면 RuntimeError
        - 반드시 선행 분석기가 실행되어야 함

    Use Case:
        DeepSecurityAnalyzer → InterproceduralTaint (필수!)

    Examples:
        >>> dep = RequiredDependency(InterproceduralTaintAnalyzer)
        >>> result = dep.resolve(ir_doc, context)
        # context에 없으면 RuntimeError!
    """

    def __init__(
        self,
        analyzer_cls: type["IAnalyzer"],
        extractor: Callable[["AnalysisContext"], Any] | None = None,
    ):
        """
        Args:
            analyzer_cls: 의존 분석기 타입
            extractor: context에서 값 추출 함수 (기본: context.get())
        """
        self._analyzer_cls = analyzer_cls
        self._extractor = extractor or (lambda ctx: ctx.get(analyzer_cls))

    @property
    def analyzer_type(self) -> type["IAnalyzer"]:
        return self._analyzer_cls

    def resolve(
        self,
        ir_doc: "IRDocument",
        context: "AnalysisContext",
    ) -> Any:
        """
        필수 의존성 해결

        Raises:
            RuntimeError: context에 없을 때
        """
        if not context.has(self._analyzer_cls):
            raise RuntimeError(
                f"Missing required dependency: {self._analyzer_cls.__name__}. "
                f"Pipeline must execute {self._analyzer_cls.__name__} before this analyzer."
            )

        return self._extractor(context)


class OptionalDependency(DependencySpec):
    """
    선택적 의존성 (Lazy Initialization)

    Behavior:
        - context에 있으면 재사용
        - 없으면 factory로 생성 → context 저장

    Use Case:
        InterproceduralTaint → PointsTo (있으면 사용, 없으면 생성)

    Performance:
        Lazy evaluation (필요할 때만)

    Examples:
        >>> def create_points_to(ir_doc, ctx):
        ...     return PointsToAnalysis().analyze(ir_doc)
        >>> dep = OptionalDependency(PointsToAnalysis, create_points_to)
        >>> result = dep.resolve(ir_doc, context)
        # 첫 호출: factory 실행 → context 저장
        # 두 번째: context에서 재사용
    """

    def __init__(
        self,
        analyzer_cls: type["IAnalyzer"],
        factory: Callable[["IRDocument", "AnalysisContext"], Any],
    ):
        """
        Args:
            analyzer_cls: 의존 분석기 타입
            factory: (ir_doc, context) → instance 생성 함수
        """
        self._analyzer_cls = analyzer_cls
        self._factory = factory

    @property
    def analyzer_type(self) -> type["IAnalyzer"]:
        return self._analyzer_cls

    def resolve(
        self,
        ir_doc: "IRDocument",
        context: "AnalysisContext",
    ) -> Any:
        """
        선택적 의존성 해결 (Lazy)

        Side Effects:
            factory 실행 시 context 업데이트
        """
        # 캐시 확인
        if context.has(self._analyzer_cls):
            return context.get(self._analyzer_cls)

        # Lazy creation
        instance = self._factory(ir_doc, context)

        # Context 저장
        context.set(self._analyzer_cls, instance)

        return instance


class IRFieldDependency(DependencySpec):
    """
    IRDocument 필드 의존성

    Behavior:
        - IRDocument 필드 조회
        - 없으면 builder로 생성 (optional)

    Use Case:
        SCCP → dfg_snapshot (IRDocument 필드)

    Examples:
        >>> dep = IRFieldDependency("dfg_snapshot", dfg_builder)
        >>> dfg = dep.resolve(ir_doc, context)
        # ir_doc.dfg_snapshot 있으면 반환
        # 없으면 dfg_builder(ir_doc, context) 실행
    """

    def __init__(
        self,
        field_name: str,
        builder: Callable[["IRDocument", "AnalysisContext"], Any] | None = None,
    ):
        """
        Args:
            field_name: IRDocument 필드명 (예: "dfg_snapshot")
            builder: 필드 없을 때 생성 함수 (optional)
        """
        self._field_name = field_name
        self._builder = builder

    @property
    def analyzer_type(self) -> None:
        """IRDocument 필드는 분석기 타입 없음 (DAG 영향 없음)"""
        return None

    def resolve(
        self,
        ir_doc: "IRDocument",
        context: "AnalysisContext",
    ) -> Any:
        """
        IRDocument 필드 해결

        Returns:
            필드 값 or None

        Side Effects:
            builder 실행 시 IRDocument 수정 (setattr)
        """
        value = getattr(ir_doc, self._field_name, None)

        if value is None and self._builder:
            # 필드 없으면 빌드
            value = self._builder(ir_doc, context)
            setattr(ir_doc, self._field_name, value)

        return value
