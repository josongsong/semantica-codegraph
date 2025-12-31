"""
Domain Models - Reasoning Engine (Legacy Compatibility Layer)

WARNING: 이 파일은 레거시 호환성을 위해 유지됩니다.
새 코드에서는 다음 모듈을 직접 import하세요:
- domain.impact_models: ImpactLevel, ImpactNode, ImpactPath, ImpactReport, PropagationType
- domain.effect_models: EffectType, EffectSet, EffectDiff
- domain.speculative_models: RiskLevel, RiskReport, SpeculativePatch

이 파일의 모델들은 impact_propagator, impact_classifier, effect_system에서만 사용됩니다.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.models import (
        GraphDocument,
        GraphEdge,
        GraphNode,
    )


# =============================================================================
# Hash-based Impact Analysis Models (for incremental rebuild)
# =============================================================================


@dataclass(frozen=True)
class SymbolHash:
    """
    Salsa-style symbol-level hash.

    Used by: impact_classifier, symbol_hasher
    """

    symbol_id: str
    signature_hash: str
    body_hash: str
    impact_hash: str


class HashBasedImpactLevel(str, Enum):
    """
    Hash 기반 Impact 수준 (Salsa-style incremental rebuild용)

    Note: impact_models.ImpactLevel과는 다른 용도
    - 이 enum: Hash 비교 기반 (signature/body 변경 분류)
    - impact_models.ImpactLevel: 영향 강도 (NONE/LOW/MEDIUM/HIGH/CRITICAL)
    """

    NO_IMPACT = "no_impact"
    IR_LOCAL = "ir_local"
    SIGNATURE_CHANGE = "signature_change"
    STRUCTURAL_CHANGE = "structural_change"


# REMOVED: Legacy alias "ImpactLevel = HashBasedImpactLevel"
# This alias caused confusion with impact_models.ImpactLevel (NONE/LOW/MEDIUM/HIGH/CRITICAL)
# Use HashBasedImpactLevel explicitly for hash-based impact analysis


@dataclass
class ImpactType:
    """Hash 기반 변경 영향도 분류"""

    level: HashBasedImpactLevel
    affected_symbols: list[str]
    reason: str
    confidence: float = 1.0


# =============================================================================
# Effect System Models (for effect_system.py)
# =============================================================================


class EffectType(str, Enum):
    """Effect 분류"""

    PURE = "pure"
    READ_STATE = "read_state"
    WRITE_STATE = "write_state"
    GLOBAL_MUTATION = "global_mutation"
    IO = "io"
    LOG = "log"
    DB_READ = "db_read"
    DB_WRITE = "db_write"
    NETWORK = "network"
    UNKNOWN_EFFECT = "unknown_effect"


EFFECT_HIERARCHY: dict[EffectType, EffectType] = {
    EffectType.IO: EffectType.WRITE_STATE,
    EffectType.LOG: EffectType.WRITE_STATE,
    EffectType.DB_WRITE: EffectType.WRITE_STATE,
    EffectType.DB_READ: EffectType.READ_STATE,
    EffectType.NETWORK: EffectType.WRITE_STATE,
}


@dataclass
class EffectSet:
    """함수의 effect 집합 (effect_system용)"""

    symbol_id: str
    effects: set[EffectType] = field(default_factory=set)
    idempotent: bool = True
    confidence: float = 1.0
    source: Literal["static", "inferred", "allowlist", "annotation", "unknown"] = "static"

    def is_pure(self) -> bool:
        return self.effects == {EffectType.PURE} or len(self.effects) == 0

    def has_side_effect(self) -> bool:
        return not self.is_pure()

    def includes(self, effect: EffectType) -> bool:
        if effect in self.effects:
            return True
        for e in self.effects:
            if EFFECT_HIERARCHY.get(e) == effect:
                return True
        return False


# =============================================================================
# Semantic Diff Models
# =============================================================================


class ChangeType(str, Enum):
    """변경 타입"""

    SIGNATURE_CHANGE = "signature_change"
    CALL_GRAPH_CHANGE = "call_graph_change"
    EFFECT_CHANGE = "effect_change"
    CONTROL_FLOW_CHANGE = "control_flow_change"
    REACHABLE_SET_CHANGE = "reachable_set_change"


@dataclass
class SemanticDiff:
    """의미적 변화 감지 결과"""

    signature_changes: list[str] = field(default_factory=list)
    call_graph_changes: dict[str, list[str]] = field(default_factory=dict)
    effect_changes: dict[str, tuple[EffectSet, EffectSet]] = field(default_factory=dict)
    reachable_set_changes: dict[str, set[str]] = field(default_factory=dict)
    is_pure_refactoring: bool = True
    confidence: float = 1.0
    reason: str = ""

    def get_breaking_changes(self) -> list[str]:
        breaking = []
        if self.signature_changes:
            breaking.extend(self.signature_changes)
        for symbol_id, (old_eff, new_eff) in self.effect_changes.items():
            if new_eff.has_side_effect() and old_eff.is_pure():
                breaking.append(f"{symbol_id}: Added side effect")
        return breaking


# =============================================================================
# Speculative Execution Models (Legacy - use speculative_models.py instead)
# =============================================================================


@dataclass
class DeltaLayer:
    """Overlay delta layer (Legacy)"""

    patch_id: str
    added_nodes: dict[str, "GraphNode"] = field(default_factory=dict)
    removed_node_ids: set[str] = field(default_factory=set)
    added_edges: list["GraphEdge"] = field(default_factory=list)
    removed_edge_ids: set[str] = field(default_factory=set)


@dataclass
class PatchMetadata:
    """패치 메타데이터"""

    patch_id: str
    description: str
    timestamp: float
    files_changed: list[str]
    symbols_changed: list[str]
    author: str | None = None


@dataclass
class ErrorSnapshot:
    """Speculative 실패 시 에러 스냅샷"""

    patch_id: str
    error_type: str
    error_message: str
    partial_graph: Optional["GraphDocument"] = None

    def to_llm_feedback(self) -> str:
        return f"패치 적용 실패 ({self.patch_id}): {self.error_type} - {self.error_message}"


# =============================================================================
# Program Slice Models (Legacy - infrastructure/slicer uses its own SliceResult)
# =============================================================================


@dataclass
class SliceNode:
    """Slice에 포함된 노드"""

    node_id: str
    node_type: Literal["block", "variable", "expression"]
    file_path: str
    start_line: int
    end_line: int
    relevance_score: float


@dataclass
class RelevanceScore:
    """노드 중요도"""

    node_id: str
    score: float
    reason: Literal["distance", "effect", "recentness", "hotspot"]


# SliceResult moved to shared_kernel (RFC-021 Phase 0)
# Use: from codegraph_shared.kernel.slice.models import SliceResult
