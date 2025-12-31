"""
Speculative Execution Domain Models

Phase 2 교훈: Type hints 100%, docstring 완벽
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DeltaOperation(Enum):
    """Delta 연산 타입"""

    ADD_NODE = "add_node"
    UPDATE_NODE = "update_node"
    DELETE_NODE = "delete_node"
    ADD_EDGE = "add_edge"
    UPDATE_EDGE = "update_edge"
    DELETE_EDGE = "delete_edge"


class PatchType(Enum):
    """LLM 패치 타입"""

    RENAME_SYMBOL = "rename_symbol"
    ADD_PARAMETER = "add_parameter"
    REMOVE_PARAMETER = "remove_parameter"
    CHANGE_RETURN_TYPE = "change_return_type"
    ADD_FUNCTION = "add_function"
    DELETE_FUNCTION = "delete_function"
    MODIFY_BODY = "modify_body"
    REFACTOR = "refactor"


class RiskLevel(Enum):
    """위험도 레벨"""

    SAFE = "safe"  # < 5 symbols affected
    LOW = "low"  # 5-20 symbols
    MEDIUM = "medium"  # 20-50 symbols
    HIGH = "high"  # 50+ symbols
    BREAKING = "breaking"  # Breaking change detected


@dataclass(frozen=True)
class Delta:
    """
    단일 변경사항

    Immutable for safety (Copy-on-Write)
    """

    operation: DeltaOperation
    node_id: str | None = None
    edge_id: str | None = None
    new_data: dict[str, Any] | None = None
    old_data: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    def __repr__(self) -> str:
        target = self.node_id or self.edge_id or "unknown"
        return f"Delta({self.operation.value}, {target})"


@dataclass
class SpeculativePatch:
    """
    LLM이 제안한 코드 패치

    Example:
        patch = SpeculativePatch(
            patch_id="p1",
            patch_type=PatchType.RENAME_SYMBOL,
            target_symbol="old_func",
            new_name="new_func"
        )
    """

    patch_id: str
    patch_type: PatchType
    target_symbol: str  # Function/class/variable name

    # Patch content
    before_code: str | None = None
    after_code: str | None = None

    # Type-specific data
    new_name: str | None = None  # For RENAME
    parameters: list[dict] | None = None  # For ADD/REMOVE_PARAMETER
    return_type: str | None = None  # For CHANGE_RETURN_TYPE

    # Metadata
    confidence: float = 1.0  # LLM confidence score
    reason: str = ""  # Why this patch?
    source: str = "llm"  # llm | user | tool

    def __repr__(self) -> str:
        return f"SpeculativePatch({self.patch_id}, {self.patch_type.value}, {self.target_symbol})"


@dataclass
class RiskReport:
    """
    패치 위험도 분석 결과

    Example:
        if risk_report.is_safe():
            apply_patch()
        else:
            log_warning(risk_report.recommendation)
    """

    patch_id: str
    risk_level: RiskLevel
    risk_score: float  # 0.0 (safe) - 1.0 (very risky)

    # Impact analysis
    affected_symbols: set[str] = field(default_factory=set)
    affected_files: set[str] = field(default_factory=set)

    # Breaking changes
    breaking_changes: list[str] = field(default_factory=list)

    # Recommendations
    recommendation: str = ""
    safe_to_apply: bool = True

    # Metadata
    analysis_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_safe(self) -> bool:
        """안전한가? (SAFE or LOW)"""
        return self.risk_level in [RiskLevel.SAFE, RiskLevel.LOW]

    def is_breaking(self) -> bool:
        """Breaking change인가?"""
        return self.risk_level == RiskLevel.BREAKING or len(self.breaking_changes) > 0

    def __repr__(self) -> str:
        return f"RiskReport({self.patch_id}, {self.risk_level.value}, score={self.risk_score:.2f})"
