"""
Analyzer Builder

RFC-024 Part 2: Framework - Declarative Dependency Builder

Purpose:
    선언적으로 분석기 의존성 명세
    Fluent API로 체이닝 가능

Features:
    - Fluent API (.require(), .optional(), .ir_field())
    - 의존성 선언적 명세
    - 생성 로직 커스터마이징

L11 Production:
    - 타입 안전
    - 명확한 에러 메시지
    - 순환 의존성 탐지 가능
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from codegraph_engine.code_foundation.domain.analyzers.dependency import (
    DependencySpec,
    IRFieldDependency,
    OptionalDependency,
    RequiredDependency,
)

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.analyzers.context import AnalysisContext
    from codegraph_engine.code_foundation.domain.analyzers.ports import IAnalyzer
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument


class AnalyzerBuilder:
    """
    분석기 빌더 (Fluent API)

    Purpose:
        분석기 의존성을 선언적으로 명세

    Features:
        - Fluent Interface (체이닝)
        - 의존성 타입 (Required/Optional/IRField)
        - 커스텀 생성자

    SOLID:
        - Builder Pattern
        - Open/Closed (확장 가능)

    Usage:
        >>> builder = (
        ...     AnalyzerBuilder(InterproceduralTaintAnalyzer)
        ...     .require("sccp", ConstantPropagationAnalyzer)
        ...     .optional("points_to", PointsToAnalysis, factory)
        ...     .constructor(lambda ir_doc, deps, ctx: InterproceduralTaintAnalyzer(
        ...         call_graph=deps["call_graph"],
        ...         ir_provider=ir_doc,
        ...         incremental_mode=ctx.incremental,
        ...     ))
        ... )
        >>> analyzer = builder.build(ir_doc, context)

    Thread-Safety:
        Not thread-safe (빌드 시)
    """

    def __init__(self, analyzer_cls: type["IAnalyzer"]):
        """
        Initialize builder

        Args:
            analyzer_cls: 분석기 타입
        """
        self._analyzer_cls = analyzer_cls
        self._dependencies: dict[str, DependencySpec] = {}
        self._constructor: Callable[[IRDocument, dict, AnalysisContext], Any] | None = None

    def require(
        self,
        name: str,
        analyzer_cls: type["IAnalyzer"],
        extractor: Callable | None = None,
    ) -> "AnalyzerBuilder":
        """
        필수 의존성 추가 (Fluent API)

        Args:
            name: 의존성 이름 (예: "sccp", "points_to")
            analyzer_cls: 의존 분석기 타입
            extractor: context 추출 함수 (optional)

        Returns:
            self (체이닝)

        Examples:
            >>> builder.require("sccp", ConstantPropagationAnalyzer)
        """
        self._dependencies[name] = RequiredDependency(analyzer_cls, extractor)
        return self

    def optional(
        self,
        name: str,
        analyzer_cls: type["IAnalyzer"],
        factory: Callable[["IRDocument", "AnalysisContext"], Any],
    ) -> "AnalyzerBuilder":
        """
        선택적 의존성 추가 (Lazy, Fluent API)

        Args:
            name: 의존성 이름
            analyzer_cls: 의존 분석기 타입
            factory: (ir_doc, context) → instance 생성 함수

        Returns:
            self (체이닝)

        Examples:
            >>> def create_points_to(ir_doc, ctx):
            ...     return PointsToAnalysis().analyze(ir_doc)
            >>> builder.optional("points_to", PointsToAnalysis, create_points_to)
        """
        self._dependencies[name] = OptionalDependency(analyzer_cls, factory)
        return self

    def ir_field(
        self,
        name: str,
        field: str,
        builder: Callable | None = None,
    ) -> "AnalyzerBuilder":
        """
        IRDocument 필드 의존성 (Fluent API)

        Args:
            name: 의존성 이름
            field: IRDocument 필드명 (예: "dfg_snapshot")
            builder: 필드 없을 때 생성 함수 (optional)

        Returns:
            self (체이닝)

        Examples:
            >>> builder.ir_field("dfg", "dfg_snapshot", dfg_builder)
        """
        self._dependencies[name] = IRFieldDependency(field, builder)
        return self

    def constructor(
        self,
        factory: Callable[["IRDocument", dict, "AnalysisContext"], Any],
    ) -> "AnalyzerBuilder":
        """
        커스텀 생성자 설정

        Args:
            factory: (ir_doc, resolved_deps, context) → analyzer

        Returns:
            self (체이닝)

        Use Case:
            복잡한 생성 로직 (여러 인자, 증분 모드 등)

        Examples:
            >>> builder.constructor(lambda ir_doc, deps, ctx:
            ...     InterproceduralTaintAnalyzer(
            ...         call_graph=deps["call_graph"],
            ...         incremental_mode=ctx.incremental,
            ...     )
            ... )
        """
        self._constructor = factory
        return self

    def build(
        self,
        ir_doc: "IRDocument",
        context: "AnalysisContext",
    ) -> Any:
        """
        분석기 생성 (의존성 자동 해결!)

        Args:
            ir_doc: IR Document
            context: 분석 컨텍스트

        Returns:
            분석기 인스턴스

        Raises:
            RuntimeError: 의존성 해결 실패

        Algorithm:
            1. 모든 DependencySpec.resolve() 호출
            2. 의존성 dict 생성
            3. 생성자 호출 (커스텀 or 기본)

        Performance:
            O(Dependencies) - 일반적으로 < 10개
        """
        # 1. 의존성 해결
        resolved = {}
        for name, spec in self._dependencies.items():
            try:
                resolved[name] = spec.resolve(ir_doc, context)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to resolve dependency '{name}' for {self._analyzer_cls.__name__}: {e}"
                ) from e

        # 2. 생성
        if self._constructor:
            # 커스텀 생성자
            return self._constructor(ir_doc, resolved, context)
        else:
            # 기본 생성자 (IRDocument만)
            try:
                return self._analyzer_cls(ir_doc)
            except TypeError:
                # 의존성 없는 경우
                try:
                    return self._analyzer_cls()
                except Exception as e:
                    raise RuntimeError(
                        f"Failed to create {self._analyzer_cls.__name__}: {e}. "
                        f"Consider providing .constructor() for complex initialization."
                    ) from e

    def get_dependencies(self) -> list[type["IAnalyzer"]]:
        """
        의존성 타입 리스트 (DAG 구축용)

        Returns:
            분석기 타입 리스트

        Use Case:
            Pipeline._build_dependency_graph()
        """
        deps = []
        for spec in self._dependencies.values():
            if spec.analyzer_type:
                deps.append(spec.analyzer_type)
        return deps
