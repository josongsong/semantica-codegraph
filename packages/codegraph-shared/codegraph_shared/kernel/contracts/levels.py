"""
공통 레벨/등급 Enum 정의 (타입 안전성 강화)

중복 문자열 리터럴을 방지하기 위한 공통 Enum 모음.

Usage:
    from codegraph_shared.kernel.contracts.levels import RiskLevel, ComplexityLevel

    risk = RiskLevel.HIGH
    if risk == "high":  # str 비교 호환
        ...
"""

from enum import Enum


class RiskLevel(str, Enum):
    """
    위험도 레벨.

    Values:
        LOW: 낮은 위험
        MEDIUM: 중간 위험
        HIGH: 높은 위험
        CRITICAL: 치명적 위험
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplexityLevel(str, Enum):
    """
    복잡도 레벨.

    Values:
        SIMPLE: 단순
        MEDIUM: 중간
        COMPLEX: 복잡
    """

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class QualityLevel(str, Enum):
    """
    품질 레벨.

    Values:
        NONE: 품질 기준 없음
        LOW: 낮은 품질
        MEDIUM: 중간 품질
        HIGH: 높은 품질
        EXCELLENT: 우수한 품질
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXCELLENT = "excellent"


class OptimizationLevel(str, Enum):
    """
    최적화 레벨.

    Values:
        MINIMAL: 최소 최적화
        MODERATE: 중간 최적화
        FULL: 전체 최적화
    """

    MINIMAL = "minimal"
    MODERATE = "moderate"
    FULL = "full"


__all__ = [
    "RiskLevel",
    "ComplexityLevel",
    "QualityLevel",
    "OptimizationLevel",
]
