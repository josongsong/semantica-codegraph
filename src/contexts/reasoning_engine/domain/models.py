"""
Domain Models - Reasoning Engine

v6 추론 엔진의 핵심 도메인 모델들.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional

# =============================================================================
# Impact Analysis Models
# =============================================================================


@dataclass(frozen=True)
class SymbolHash:
    """
    Salsa-style symbol-level hash.

    Attributes:
        symbol_id: Symbol의 고유 ID (IRNode.id)
        signature_hash: 시그니처 해시 (이름, 파라미터, 반환 타입)
        body_hash: Body 해시 (함수 내부 AST)
        impact_hash: 영향도 해시 (Signature + callees' signatures)
    """

    symbol_id: str
    signature_hash: str
    body_hash: str
    impact_hash: str


class ImpactLevel(str, Enum):
    """Impact 수준"""

    NO_IMPACT = "no_impact"  # 주석, 포맷팅만 변경
    IR_LOCAL = "ir_local"  # Body 변경, signature 불변
    SIGNATURE_CHANGE = "signature_change"  # Signature 변경 (callers 영향)
    STRUCTURAL_CHANGE = "structural_change"  # Import/Export 구조 변경


@dataclass
class ImpactType:
    """변경 영향도 분류"""

    level: ImpactLevel
    affected_symbols: list[str]
    reason: str
    confidence: float = 1.0  # 0.0 ~ 1.0


# =============================================================================
# Effect System Models
# =============================================================================


class EffectType(str, Enum):
    """Effect 분류"""

    PURE = "pure"

    # State Effects
    READ_STATE = "read_state"
    WRITE_STATE = "write_state"
    GLOBAL_MUTATION = "global_mutation"

    # I/O Effects
    IO = "io"
    LOG = "log"

    # External Effects
    DB_READ = "db_read"
    DB_WRITE = "db_write"
    NETWORK = "network"

    # Unknown
    UNKNOWN_EFFECT = "unknown_effect"


# Effect Hierarchy (parent relationship)
EFFECT_HIERARCHY = {
    EffectType.IO: EffectType.WRITE_STATE,
    EffectType.LOG: EffectType.WRITE_STATE,
    EffectType.DB_WRITE: EffectType.WRITE_STATE,
    EffectType.DB_READ: EffectType.READ_STATE,
    EffectType.NETWORK: EffectType.WRITE_STATE,
}


@dataclass
class EffectSet:
    """
    함수의 effect 집합.

    Attributes:
        symbol_id: 함수/메서드의 ID
        effects: Effect 집합
        idempotent: 멱등성 (같은 입력 → 같은 결과)
        confidence: 추론 신뢰도 (0.0 ~ 1.0)
        source: 추론 방식
    """

    symbol_id: str
    effects: set[EffectType]
    idempotent: bool
    confidence: float  # 0.0 ~ 1.0
    source: Literal["static", "inferred", "allowlist", "annotation", "unknown"]

    def is_pure(self) -> bool:
        """순수 함수 여부"""
        return self.effects == {EffectType.PURE}

    def has_side_effect(self) -> bool:
        """Side effect 존재 여부"""
        return not self.is_pure()

    def includes(self, effect: EffectType) -> bool:
        """특정 effect 포함 여부 (hierarchy 고려)"""
        if effect in self.effects:
            return True

        # Check hierarchy
        for e in self.effects:
            if EFFECT_HIERARCHY.get(e) == effect:
                return True

        return False


@dataclass
class EffectDiff:
    """Effect 변화"""

    symbol_id: str
    old_effect: EffectSet
    new_effect: EffectSet

    added_effects: set[EffectType]
    removed_effects: set[EffectType]

    idempotency_changed: bool
    risk_level: Literal["low", "medium", "high"]

    def is_behavioral_change(self) -> bool:
        """동작 변화 여부"""
        return len(self.added_effects) > 0 or len(self.removed_effects) > 0


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
    """
    의미적 변화 감지 결과.

    동작 변화 vs 순수 리팩토링 구분.
    """

    signature_changes: list[str]
    call_graph_changes: dict[str, list[str]]  # added/removed calls
    effect_changes: dict[str, tuple[EffectSet, EffectSet]]  # old → new
    reachable_set_changes: dict[str, set[str]]

    is_pure_refactoring: bool
    confidence: float
    reason: str

    def get_breaking_changes(self) -> list[str]:
        """Breaking change 목록"""
        breaking = []

        if self.signature_changes:
            breaking.extend(self.signature_changes)

        for symbol_id, (old_eff, new_eff) in self.effect_changes.items():
            if new_eff.has_side_effect() and old_eff.is_pure():
                breaking.append(f"{symbol_id}: Added side effect")

        return breaking


# =============================================================================
# Speculative Execution Models
# =============================================================================


@dataclass
class DeltaLayer:
    """
    Overlay delta layer.

    Base graph는 immutable하게 유지하고,
    변경 사항만 delta로 관리.
    """

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
    """
    Speculative 실패 시 에러 스냅샷.

    LLM에게 피드백으로 전달.
    """

    patch_id: str
    error_type: str  # "SyntaxError" | "TypeError" | "IRGenerationError"
    error_message: str
    partial_graph: Optional["GraphDocument"] = None

    def to_llm_feedback(self) -> str:
        """LLM-friendly 피드백 메시지"""
        return f"""
패치 적용 실패 (patch_id: {self.patch_id})

에러 타입: {self.error_type}
에러 메시지: {self.error_message}

제안:
1. Syntax 에러인 경우 → 패치 재작성 필요
2. Type 에러인 경우 → 타입 어노테이션 확인
3. IR 생성 실패 → 파일 구조 확인
"""


# =============================================================================
# Program Slice Models
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


@dataclass
class SliceResult:
    """
    Program slice 결과.

    LLM에게 전달할 최소한의 컨텍스트.
    """

    target_variable: str
    slice_nodes: list[SliceNode]
    code_fragments: list[tuple[str, int, int]]  # (file, start_line, end_line)
    control_context: list[str]
    total_tokens: int

    def to_llm_context(self) -> str:
        """LLM-friendly 컨텍스트 생성"""
        # TODO: Implement in infrastructure layer
        pass

    def is_within_budget(self, budget: int) -> bool:
        """토큰 예산 초과 여부"""
        return self.total_tokens <= budget
