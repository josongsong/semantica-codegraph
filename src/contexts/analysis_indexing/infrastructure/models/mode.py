"""인덱싱 모드 및 레이어 정의."""

from enum import Enum


class Layer(str, Enum):
    """인덱싱 레이어 정의 (L0~L4)."""

    L0 = "l0"  # 변경 감지 (git diff, mtime, hash)
    L1 = "l1"  # 파싱 (AST, 심볼 추출)
    L2 = "l2"  # 기본 IR + 청크 생성
    L3 = "l3"  # Semantic IR (요약 CFG/DFG Tier1)
    L3_SUMMARY = "l3_summary"  # L3 제한 버전 (Bootstrap용)
    L4 = "l4"  # 고급 분석 (Full DFG, Git History, Cross-function)


class IndexingMode(str, Enum):
    """인덱싱 실행 모드."""

    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"
    BOOTSTRAP = "bootstrap"
    REPAIR = "repair"


# 모드별 활성 레이어 매핑
MODE_LAYER_CONFIG: dict[IndexingMode, list[Layer]] = {
    IndexingMode.FAST: [Layer.L1, Layer.L2],
    IndexingMode.BALANCED: [Layer.L1, Layer.L2, Layer.L3],
    IndexingMode.DEEP: [Layer.L1, Layer.L2, Layer.L3, Layer.L4],
    IndexingMode.BOOTSTRAP: [Layer.L1, Layer.L2, Layer.L3_SUMMARY],
    IndexingMode.REPAIR: [],  # 동적 결정
}


# L3/L4 경계 설정
class LayerThreshold:
    """레이어 경계 임계값."""

    # L3: 요약 CFG/DFG
    L3_CFG_MAX_NODES = 100
    L3_DFG_SCOPE = "single_function"
    L3_GIT_HISTORY_COMMITS = 10

    # L4: Full 분석
    L4_CFG_UNLIMITED = True
    L4_DFG_SCOPE = "cross_function"
    L4_GIT_HISTORY_ALL = True


# 모드별 범위 제한
class ModeScopeLimit:
    """모드별 처리 범위 제한."""

    # Balanced: 인접 모듈 최대 개수
    BALANCED_MAX_NEIGHBORS = 100

    # Deep subset: on-demand
    DEEP_SUBSET_MAX_FILES = 500
    DEEP_SUBSET_MAX_PERCENT = 0.1  # 전체의 10%

    # 확장 깊이
    BALANCED_NEIGHBOR_DEPTH = 1  # 1-hop
    DEEP_NEIGHBOR_DEPTH = 2  # 2-hop


# 모드 전환 조건
class ModeTransitionConfig:
    """모드 자동 전환 조건."""

    # Fast → Balanced 트리거
    FAST_TO_BALANCED_MIN_CHANGED_FILES = 10
    FAST_TO_BALANCED_HOURS_SINCE_LAST = 24
    FAST_TO_BALANCED_IDLE_MINUTES = 5

    # Balanced 중단 조건
    BALANCED_CHECKPOINT_INTERVAL_MINUTES = 5


__all__ = [
    "Layer",
    "IndexingMode",
    "MODE_LAYER_CONFIG",
    "LayerThreshold",
    "ModeScopeLimit",
    "ModeTransitionConfig",
]
