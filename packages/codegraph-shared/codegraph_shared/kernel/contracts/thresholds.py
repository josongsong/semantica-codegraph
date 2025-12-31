"""
공통 임계값 상수 정의 (Magic Number 제거)

하드코딩된 숫자를 Named Constants로 관리.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ComplexityThresholds:
    """
    복잡도 판단 임계값.

    Usage:
        if specificity > ComplexityThresholds.HIGH_SPECIFICITY:
            ...
    """

    # Query complexity
    HIGH_SPECIFICITY: float = 0.7  # 높은 특이도
    LOW_SPECIFICITY: float = 0.4  # 낮은 특이도
    SIMPLE_TOKEN_COUNT: int = 3  # 단순 쿼리 토큰 수
    COMPLEX_TOKEN_COUNT: int = 8  # 복잡 쿼리 토큰 수


@dataclass(frozen=True)
class RiskThresholds:
    """
    위험도 판단 임계값.

    Usage:
        if score >= RiskThresholds.CRITICAL:
            ...
    """

    CRITICAL: float = 0.80  # 치명적 위험
    HIGH: float = 0.60  # 높은 위험
    MEDIUM: float = 0.40  # 중간 위험
    # LOW는 0.40 미만


@dataclass(frozen=True)
class ReasoningThresholds:
    """
    추론 전략 선택 임계값.

    Usage:
        if complexity > ReasoningThresholds.VERY_HIGH_COMPLEXITY:
            use_alphacode()
    """

    VERY_HIGH_COMPLEXITY: float = 0.8  # 매우 높은 복잡도
    HIGH_COMPLEXITY: float = 0.7  # 높은 복잡도
    HIGH_RISK: float = 0.7  # 높은 위험도
    HIGH_DEPENDENCY_COUNT: int = 10  # 높은 의존성 개수


@dataclass(frozen=True)
class ScaleLimits:
    """
    확장성 제한 상수.

    Usage:
        if file_count > ScaleLimits.MAX_FILES_FOR_GRAPH:
            skip_graph_analysis()
    """

    MAX_FILES_FOR_GRAPH: int = 10000  # 그래프 분석 최대 파일 수
    MAX_TEST_ENTRIES: int = 20  # 최대 테스트 진입점 수
    MAX_LINE_CHANGE_PERCENT: float = 0.20  # 함수 변경 감지 임계값 (20%)


@dataclass(frozen=True)
class PerformanceThresholds:
    """
    성능 관련 임계값.

    Usage:
        if cpu_usage > PerformanceThresholds.HIGH_CPU:
            throttle()
    """

    HIGH_CPU: float = 90.0  # 높은 CPU 사용률 (%)
    HIGH_MEMORY: float = 80.0  # 높은 메모리 사용률 (%)


# Singleton instances (immutable)
COMPLEXITY = ComplexityThresholds()
RISK = RiskThresholds()
REASONING = ReasoningThresholds()
SCALE = ScaleLimits()
PERFORMANCE = PerformanceThresholds()


__all__ = [
    "ComplexityThresholds",
    "RiskThresholds",
    "ReasoningThresholds",
    "ScaleLimits",
    "PerformanceThresholds",
    "COMPLEXITY",
    "RISK",
    "REASONING",
    "SCALE",
    "PERFORMANCE",
]
