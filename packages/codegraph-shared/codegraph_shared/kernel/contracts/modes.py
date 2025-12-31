"""
공통 분석 모드 정의 (RFC-021)

ENUM 중복 방지를 위한 단일 정의.

사용처:
- analysis_indexing: IndexingMode (alias)
- code_foundation: PyrightMode (alias), BuildConfig.pyright_mode

str, Enum 패턴:
- JSON 직렬화 자동 지원 (FastAPI, Pydantic)
- 타입 안전성 보장 (IDE, mypy)
- 문자열 비교 호환 ("fast" == AnalysisMode.FAST)
"""

from enum import Enum


class AnalysisMode(str, Enum):
    """
    분석 깊이 모드.

    모든 bounded context에서 공통으로 사용.

    Values:
        FAST: 최소 분석 - 속도 우선 (에디터, 자동완성)
        BALANCED: 균형 모드 - 기본 분석 (PR 리뷰)
        DEEP: 전체 분석 - 정확도 우선 (CI, 보안 감사)
        BOOTSTRAP: 초기 인덱싱 - 빠른 시작
        REPAIR: 복구 모드 - 특정 파일만

    Usage:
        from codegraph_shared.kernel.contracts.modes import AnalysisMode

        mode = AnalysisMode.FAST
        if mode == "fast":  # str 비교 호환
            ...
    """

    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"
    BOOTSTRAP = "bootstrap"
    REPAIR = "repair"

    @classmethod
    def from_string(cls, value: str) -> "AnalysisMode":
        """
        Case-insensitive conversion from string.

        Args:
            value: Mode string (e.g., "FAST", "fast", "Fast")

        Returns:
            AnalysisMode enum

        Raises:
            ValueError: If invalid mode
        """
        normalized = value.lower().strip()
        for member in cls:
            if member.value == normalized:
                return member
        valid = [m.value for m in cls]
        raise ValueError(f"Invalid AnalysisMode: '{value}'. Valid: {valid}")


def to_semantic_mode(mode: AnalysisMode) -> str:
    """
    AnalysisMode → SemanticIrBuildMode 문자열 변환.

    SemanticIrBuildMode는 code_foundation 내부 ENUM이므로
    순환 import를 피하기 위해 문자열로 반환.

    Mapping:
        FAST, BALANCED → "quick" or "pr" (context dependent)
        DEEP, BOOTSTRAP → "full"
        REPAIR → "pr"

    Args:
        mode: AnalysisMode enum

    Returns:
        SemanticIrBuildMode 호환 문자열 ("quick", "pr", "full")
    """
    if mode in (AnalysisMode.FAST,):
        return "quick"
    elif mode in (AnalysisMode.BALANCED, AnalysisMode.REPAIR):
        return "pr"
    else:  # DEEP, BOOTSTRAP
        return "full"


__all__ = ["AnalysisMode", "to_semantic_mode"]
