"""
Error DTO with Recovery Hints

RFC-052: MCP Service Layer Architecture
Errors are not just failures - they are guidance for agent self-correction.

Design Principles:
- Every error has actionable recovery hints
- Hints guide agent to modify QueryPlan
- Structured (not free-text)

Error Types:
- BUDGET_EXCEEDED: Query too expensive
- SNAPSHOT_MISMATCH: Evidence from different snapshot
- INVALID_QUERYPLAN: Plan validation failed
- TIMEOUT: Execution timeout
- NOT_FOUND: Resource not found
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Structured error codes"""

    # Budget/Resource
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    TIMEOUT = "TIMEOUT"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"

    # Snapshot/Version
    SNAPSHOT_MISMATCH = "SNAPSHOT_MISMATCH"
    SNAPSHOT_NOT_FOUND = "SNAPSHOT_NOT_FOUND"

    # QueryPlan
    INVALID_QUERYPLAN = "INVALID_QUERYPLAN"
    PLAN_TOO_BROAD = "PLAN_TOO_BROAD"
    PLAN_AMBIGUOUS = "PLAN_AMBIGUOUS"

    # Not Found
    SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"

    # Internal
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class RecoveryHint:
    """
    Actionable recovery hint for agent.

    Structured guidance (not free-text).
    """

    action: str  # e.g., "reduce_depth", "add_file_scope", "use_lighter_budget"
    parameters: dict[str, Any] = field(default_factory=dict)
    reason: str = ""  # Human-readable reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "parameters": self.parameters,
            "reason": self.reason,
        }


@dataclass
class AnalysisError:
    """
    Error with recovery hints.

    Enables agent self-correction loop.
    """

    error_code: ErrorCode
    message: str
    recovery_hints: list[RecoveryHint] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code.value,
            "message": self.message,
            "recovery_hints": [h.to_dict() for h in self.recovery_hints],
            "context": self.context,
        }

    @classmethod
    def budget_exceeded(
        cls,
        max_nodes: int,
        max_depth: int,
        current_scope: str | None = None,
    ) -> AnalysisError:
        """
        Budget exceeded error with recovery hints.

        Hints guide agent to:
        - Reduce depth
        - Add file/function scope
        - Use lighter budget profile
        """
        hints = [
            RecoveryHint(
                action="reduce_depth",
                parameters={"suggested_depth": max(1, max_depth // 2)},
                reason=f"Current depth {max_depth} exceeded node limit {max_nodes}",
            ),
        ]

        if not current_scope:
            hints.append(
                RecoveryHint(
                    action="add_file_scope",
                    parameters={"scope_type": "file or function"},
                    reason="Query is too broad - restrict to specific file/function",
                )
            )

        hints.append(
            RecoveryHint(
                action="use_lighter_budget",
                parameters={"budget_profile": "light"},
                reason="Use Budget.light() for quick queries",
            )
        )

        return cls(
            error_code=ErrorCode.BUDGET_EXCEEDED,
            message=f"Query exceeded budget: {max_nodes} nodes",
            recovery_hints=hints,
            context={"max_nodes": max_nodes, "max_depth": max_depth},
        )

    @classmethod
    def snapshot_mismatch(
        cls,
        expected_snapshot: str,
        actual_snapshot: str,
        evidence_id: str,
    ) -> AnalysisError:
        """
        Snapshot mismatch error.

        Evidence was generated from a different snapshot.
        """
        hints = [
            RecoveryHint(
                action="use_same_snapshot",
                parameters={"snapshot_id": expected_snapshot},
                reason="Reuse the same snapshot for consistency",
            ),
            RecoveryHint(
                action="recalculate_with_current_snapshot",
                parameters={"snapshot_id": actual_snapshot},
                reason="Recalculate with the latest snapshot",
            ),
        ]

        return cls(
            error_code=ErrorCode.SNAPSHOT_MISMATCH,
            message=f"Evidence {evidence_id} from snapshot {expected_snapshot}, but current is {actual_snapshot}",
            recovery_hints=hints,
            context={
                "expected_snapshot": expected_snapshot,
                "actual_snapshot": actual_snapshot,
                "evidence_id": evidence_id,
            },
        )

    @classmethod
    def invalid_queryplan(
        cls,
        reason: str,
        patterns: list[str] | None = None,
    ) -> AnalysisError:
        """
        Invalid QueryPlan error.

        Plan is malformed or too risky.
        """
        hints = []

        if "ambiguous" in reason.lower():
            hints.append(
                RecoveryHint(
                    action="add_constraints",
                    parameters={"constraint_types": ["file_scope", "function_scope"]},
                    reason="Pattern is ambiguous - add file or function scope",
                )
            )

        if "too broad" in reason.lower():
            hints.append(
                RecoveryHint(
                    action="specify_entry_point",
                    parameters={"entry_types": ["main function", "API endpoint"]},
                    reason="Query is too broad - specify entry point",
                )
            )

        return cls(
            error_code=ErrorCode.INVALID_QUERYPLAN,
            message=f"Invalid QueryPlan: {reason}",
            recovery_hints=hints,
            context={"patterns": patterns or []},
        )

    @classmethod
    def symbol_not_found(cls, symbol: str, suggestion: str | None = None) -> AnalysisError:
        """Symbol not found error"""
        hints = []
        if suggestion:
            hints.append(
                RecoveryHint(
                    action="use_suggested_symbol",
                    parameters={"suggested_symbol": suggestion},
                    reason=f"Did you mean '{suggestion}'?",
                )
            )
        else:
            hints.append(
                RecoveryHint(
                    action="search_similar_symbols",
                    parameters={"pattern": symbol},
                    reason="Try fuzzy search to find similar symbols",
                )
            )

        return cls(
            error_code=ErrorCode.SYMBOL_NOT_FOUND,
            message=f"Symbol '{symbol}' not found",
            recovery_hints=hints,
            context={"symbol": symbol},
        )
