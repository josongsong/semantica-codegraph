"""
Analyzer Framework Ports

RFC-024 Part 2: Framework - IAnalyzer Port

Hexagonal Architecture:
- Port: 모든 분석기의 공통 인터페이스
- Adapter: 53개 기존 분석기 래핑

SOLID:
- Single Responsibility: 분석만
- Open/Closed: 새 분석기 추가 가능
- Liskov: 모든 분석기 치환 가능
- Interface Segregation: 최소 인터페이스
- Dependency Inversion: 추상에 의존
"""

from enum import Enum
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.constant_propagation.analysis_context import AnalysisContext
    from codegraph_engine.code_foundation.domain.ir_document import IRDocument

T = TypeVar("T")


class AnalyzerCategory(Enum):
    """
    분석기 카테고리

    RFC-024: SCCP를 baseline으로, 다른 분석기는 optional

    Categories:
        - BASELINE: 모든 분석 전에 실행 (SCCP!)
        - TAINT: Taint 분석
        - HEAP: Heap/Memory 분석
        - TYPE: 타입 분석
        - SECURITY: 통합 보안 분석
    """

    BASELINE = "baseline"  # SCCP (필수!)
    TAINT = "taint"
    HEAP = "heap"
    TYPE = "type"
    SECURITY = "security"


class AnalyzerTier(Enum):
    """
    분석기 계층 (실행 순서 힌트)

    Tier:
        1: Baseline (SCCP) - 항상 먼저
        2: Core (Taint, Null) - SCCP 이후
        3: Integration (DeepSecurity) - 모든 것 이후
    """

    TIER_1 = 1  # Baseline (SCCP)
    TIER_2 = 2  # Core
    TIER_3 = 3  # Integration


@runtime_checkable
class IAnalyzer(Protocol, Generic[T]):
    """
    분석기 공통 인터페이스 (Hexagonal Port)

    책임:
        IRDocument 분석 → 분석 결과

    Hexagonal:
        Domain (Port) ← Infrastructure (Adapter)

    Usage:
        >>> analyzer: IAnalyzer = ConstantPropagationAnalyzer()
        >>> result = analyzer.analyze(ir_doc, context)

    Thread-Safety:
        구현체에 따라 다름 (일반적으로 not thread-safe)
    """

    @property
    def name(self) -> str:
        """
        분석기 이름

        Returns:
            고유 이름 (예: "sccp_baseline", "interprocedural_taint")
        """
        ...

    @property
    def category(self) -> AnalyzerCategory:
        """
        분석기 카테고리

        Returns:
            AnalyzerCategory
        """
        ...

    @property
    def tier(self) -> AnalyzerTier:
        """
        분석기 계층 (실행 순서 힌트)

        Returns:
            AnalyzerTier (1: Baseline, 2: Core, 3: Integration)
        """
        ...

    @property
    def dependencies(self) -> list[type["IAnalyzer"]]:
        """
        의존하는 분석기 타입 리스트

        Returns:
            분석기 타입 리스트 (예: [ConstantPropagationAnalyzer])

        Use Case:
            Pipeline이 Topological Sort로 순서 결정

        Examples:
            >>> class InterproceduralTaint(IAnalyzer):
            ...     @property
            ...     def dependencies(self):
            ...         return [ConstantPropagationAnalyzer, PointsToAnalysis]
        """
        ...

    def analyze(self, ir_doc: "IRDocument", context: "AnalysisContext") -> T:
        """
        분석 실행

        Args:
            ir_doc: IR Document
            context: 분석 컨텍스트 (이전 분석 결과 포함)

        Returns:
            분석 결과 (타입은 구현체마다 다름)

        Raises:
            ValueError: 입력 검증 실패
            RuntimeError: 분석 실패

        Pre-condition:
            - context에 dependencies 충족
            - SCCP baseline 실행됨 (Tier 2 이상)

        Post-condition:
            - 결과는 context에 저장됨

        Performance:
            구현체마다 다름
        """
        ...
