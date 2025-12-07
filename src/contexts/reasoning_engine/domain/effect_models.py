"""
Effect System Domain Models

코드 변화의 동작 의미(behavioral semantics) 표현
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class EffectType(str, Enum):
    """
    Effect 분류

    함수/메서드가 가지는 side-effect 종류
    """

    # Pure
    PURE = "pure"

    # State Effects
    READ_STATE = "read_state"  # 글로벌/멤버 상태 읽기
    WRITE_STATE = "write_state"  # 글로벌/멤버 상태 쓰기
    GLOBAL_MUTATION = "global_mutation"  # 글로벌 객체 변형

    # I/O Effects
    IO = "io"  # 파일/콘솔 입출력
    LOG = "log"  # 로깅

    # External Effects
    DB_READ = "db_read"  # Database 읽기
    DB_WRITE = "db_write"  # Database 쓰기
    NETWORK = "network"  # 네트워크 요청

    # Unknown
    UNKNOWN_EFFECT = "unknown_effect"  # 정적 분석 불가


# Effect Hierarchy (상속 관계)
EFFECT_HIERARCHY: dict[EffectType, EffectType] = {
    EffectType.IO: EffectType.WRITE_STATE,
    EffectType.LOG: EffectType.WRITE_STATE,
    EffectType.DB_WRITE: EffectType.WRITE_STATE,
    EffectType.DB_READ: EffectType.READ_STATE,
    EffectType.NETWORK: EffectType.WRITE_STATE,
}


@dataclass
class EffectSet:
    """
    함수의 effect 집합

    Example:
        pure_func = EffectSet("func1", {EffectType.PURE}, idempotent=True)
        io_func = EffectSet("func2", {EffectType.IO}, idempotent=False)
    """

    symbol_id: str
    effects: set[EffectType] = field(default_factory=set)
    idempotent: bool = True
    confidence: float = 1.0  # 0.0 ~ 1.0
    source: Literal["static", "inferred", "allowlist", "annotation", "unknown"] = "static"
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_pure(self) -> bool:
        """Pure function인지 (side-effect 없음)"""
        return self.effects == {EffectType.PURE} or len(self.effects) == 0

    def has_side_effect(self) -> bool:
        """Side-effect 있는지"""
        return not self.is_pure()

    def includes(self, effect: EffectType) -> bool:
        """
        Effect 포함 여부 (Hierarchy 고려)

        Args:
            effect: 확인할 effect

        Returns:
            포함 여부
        """
        if effect in self.effects:
            return True

        # Check hierarchy
        for e in self.effects:
            if EFFECT_HIERARCHY.get(e) == effect:
                return True

        return False

    def is_compatible_with(self, other: "EffectSet") -> bool:
        """
        다른 EffectSet과 호환 가능한지

        호환: 같거나 더 약한 effect
        """
        # Pure는 모든 것과 호환
        if self.is_pure():
            return True

        # Other가 pure면 비호환 (side-effect 추가)
        if other.is_pure():
            return False

        # 모든 effect가 포함되어야 함
        return self.effects.issubset(other.effects)

    def __repr__(self) -> str:
        if self.is_pure():
            return f"EffectSet({self.symbol_id}, PURE)"
        return f"EffectSet({self.symbol_id}, {{{', '.join(e.value for e in self.effects)}}})"


@dataclass
class EffectDiff:
    """
    변경 전후 Effect 차이

    Example:
        diff = EffectDiff(
            symbol_id="func1",
            before={EffectType.PURE},
            after={EffectType.GLOBAL_MUTATION},
            is_breaking=True
        )
    """

    symbol_id: str
    before: set[EffectType]
    after: set[EffectType]
    added: set[EffectType] = field(default_factory=set)
    removed: set[EffectType] = field(default_factory=set)
    is_breaking: bool = False
    severity: Literal["none", "low", "medium", "high", "critical"] = "none"

    def __post_init__(self):
        """자동 계산"""
        # PURE는 제외하고 계산
        before_effects = self.before - {EffectType.PURE}
        after_effects = self.after - {EffectType.PURE}

        self.added = after_effects - before_effects
        self.removed = before_effects - after_effects

        self._calculate_severity()

    def _calculate_severity(self):
        """심각도 계산"""
        # Global mutation 추가 = critical
        if EffectType.GLOBAL_MUTATION in self.added:
            self.is_breaking = True
            self.severity = "critical"
            return

        # Pure → Side-effect = high, breaking
        if EffectType.PURE in self.before and self.after != {EffectType.PURE}:
            self.is_breaking = True
            self.severity = "high"
            return

        # DB/Network 추가 = high, breaking
        if any(e in self.added for e in [EffectType.DB_WRITE, EffectType.NETWORK]):
            self.is_breaking = True
            self.severity = "high"
            return

        # IO/Log 추가 = medium (non-breaking if not from pure)
        if any(e in self.added for e in [EffectType.IO, EffectType.LOG]):
            self.severity = "medium"
            return

        # Effect 제거 (일반적으로 safe)
        if self.removed and not self.added:
            self.severity = "low"
            return

        # 변화 없음
        if not self.added and not self.removed:
            self.severity = "none"

    def has_changes(self) -> bool:
        """변화가 있는지"""
        return len(self.added) > 0 or len(self.removed) > 0

    def is_safe(self) -> bool:
        """안전한 변경인지"""
        return not self.is_breaking and self.severity in ["none", "low"]

    def summary(self) -> str:
        """요약 메시지"""
        if not self.has_changes():
            return "No effect changes"

        parts = []

        if self.added:
            parts.append(f"Added: {', '.join(e.value for e in self.added)}")

        if self.removed:
            parts.append(f"Removed: {', '.join(e.value for e in self.removed)}")

        if self.is_breaking:
            parts.append("⚠️  BREAKING")

        return " | ".join(parts)

    def __repr__(self) -> str:
        return f"EffectDiff({self.symbol_id}, {self.severity}, {self.summary()})"


class EffectSeverity(str, Enum):
    """Effect change 심각도"""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
