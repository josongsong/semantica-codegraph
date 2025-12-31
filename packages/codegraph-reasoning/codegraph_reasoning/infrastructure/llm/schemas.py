"""
LLM Output Schemas (RFC-102)

Strict schemas for all LLM outputs to prevent parsing failures.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class LLMOutputSchema(Enum):
    """Supported LLM output schemas."""

    BOUNDARY_RANKING = "boundary_ranking"
    REFACTOR_PLAN = "refactor_plan"
    REFACTOR_PATCH = "refactor_patch"
    BREAKING_CLASSIFICATION = "breaking_classification"


@dataclass
class BoundaryRankingOutput:
    """Strict schema for boundary ranking LLM output."""

    best_match_id: str
    confidence: float  # 0.0-1.0
    top_k: list[tuple[str, float]]  # [(candidate_id, score), ...]
    rationale: str  # Single line, max 200 chars


@dataclass
class RefactorPlanOutput:
    """Strict schema for refactoring plan LLM output."""

    summary: str  # Single line, max 200 chars
    changed_files: list[str]  # Sorted alphabetically
    changed_symbols: list[str]  # Sorted alphabetically
    new_symbols: list[str]  # Sorted alphabetically (default: [])
    deleted_symbols: list[str]  # Sorted alphabetically (default: [])
    risk_flags: list[str]  # Enum: "breaking", "performance", "style", "logic"
    estimated_lines_changed: int
    estimated_complexity: str  # "simple" | "medium" | "complex"


@dataclass
class RefactorPatchOutput:
    """Strict schema for refactoring patch LLM output."""

    patch: str  # Canonicalized code
    touched_symbols: list[str]  # Sorted
    import_changes: list[str]  # Sorted


@dataclass
class BreakingClassificationOutput:
    """Strict schema for breaking change classification."""

    is_breaking: bool
    confidence: float  # 0.0-1.0
    reason: str  # One-line explanation
    severity: str  # "critical" | "high" | "medium" | "low"


class LLMOutputParseError(Exception):
    """Raised when LLM output cannot be parsed."""

    pass
