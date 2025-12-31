"""Scoring IR - Specificity and Confidence.

RFC-033 Sections 7-8.
"""

from dataclasses import dataclass, field
from typing import Literal

# ============================================================================
# Specificity (Rule Prioritization)
# ============================================================================


@dataclass
class SpecificityIR:
    """Rule specificity for deterministic ordering.

    RFC-033 Section 7.

    Used in tie-breaking when multiple rules match.
    Higher specificity = higher priority.

    Calculation:
        final_score = base_score - wildcard_count * 10 + literal_length * 0.5

    Tie-breaking order:
        1. final_score (higher better)
        2. wildcard_count (lower better)
        3. literal_length (higher better)
        4. rule_id (lexicographic)
    """

    base_score: int  # 100=tier1, 80=tier2, 50=tier3, 10=fallback
    wildcard_count: int  # Penalty for wildcards
    literal_length: int  # Bonus for literal characters
    final_score: float  # Computed score

    @classmethod
    def from_tier(
        cls,
        tier: Literal["tier1", "tier2", "tier3"],
        wildcard_count: int = 0,
        literal_length: int = 0,
    ) -> "SpecificityIR":
        """Calculate specificity from tier and pattern info."""
        from trcr.config import DEFAULT_TIER_CONFIG

        # Base score by tier
        base = DEFAULT_TIER_CONFIG.get_specificity_base(tier)

        # Final score calculation
        final = (
            base
            - wildcard_count * DEFAULT_TIER_CONFIG.WILDCARD_PENALTY
            + literal_length * DEFAULT_TIER_CONFIG.LITERAL_BONUS
        )

        return cls(
            base_score=base,
            wildcard_count=wildcard_count,
            literal_length=literal_length,
            final_score=final,
        )

    def __lt__(self, other: "SpecificityIR") -> bool:
        """Compare specificity for sorting.

        Higher specificity comes FIRST (reverse order).
        """
        # 1. Compare final_score (higher better)
        if self.final_score != other.final_score:
            return self.final_score > other.final_score

        # 2. Compare wildcard_count (lower better)
        if self.wildcard_count != other.wildcard_count:
            return self.wildcard_count < other.wildcard_count

        # 3. Compare literal_length (higher better)
        return self.literal_length > other.literal_length


# ============================================================================
# Confidence (Match Quality)
# ============================================================================


@dataclass(frozen=True)
class GuardAdjustmentIR:
    """Confidence adjustment from guard.

    RFC-038: Guard-aware Execution.

    If guard/sanitizer detected, reduce confidence.
    """

    op: Literal["add", "mul", "set"]
    value: float
    kind: Literal["guard_adjust"] = "guard_adjust"
    reason: str = "guard_detected"

    def __post_init__(self) -> None:
        """Validate adjustment."""
        if self.op == "mul" and not (0.0 <= self.value <= 1.0):
            raise ValueError(f"Multiplier must be in [0, 1]: {self.value}")

        if self.op == "set" and not (0.0 <= self.value <= 1.0):
            raise ValueError(f"Set value must be in [0, 1]: {self.value}")


@dataclass(frozen=True)
class ConstraintAdjustmentIR:
    """Confidence adjustment from constraint satisfaction.

    Example:
        - arg is not_const → +0.1 (more confident)
        - kwarg shell=True → +0.2 (very dangerous)
    """

    op: Literal["add", "mul"]
    value: float
    reason: str  # "not_const", "kwarg_shell", etc.
    kind: Literal["constraint_adjust"] = "constraint_adjust"

    def __post_init__(self) -> None:
        """Validate adjustment."""
        if self.op == "mul" and not (0.0 <= self.value <= 2.0):
            raise ValueError(f"Multiplier must be in [0, 2]: {self.value}")


@dataclass(frozen=True)
class TierAdjustmentIR:
    """Confidence adjustment from tier.

    Lower tier = lower base confidence.
    """

    tier: Literal["tier1", "tier2", "tier3"]
    value: float  # Base confidence: tier1=1.0, tier2=0.9, tier3=0.6
    kind: Literal["tier_adjust"] = "tier_adjust"

    @classmethod
    def from_tier(cls, tier: Literal["tier1", "tier2", "tier3"]) -> "TierAdjustmentIR":
        """Create tier adjustment."""
        from trcr.config import DEFAULT_TIER_CONFIG

        value = DEFAULT_TIER_CONFIG.get_confidence(tier)
        return cls(tier=tier, value=value)


# Union type for confidence adjustments
ConfidenceAdjustmentIR = GuardAdjustmentIR | ConstraintAdjustmentIR | TierAdjustmentIR


@dataclass
class ConfidenceIR:
    """Confidence calculation spec.

    RFC-033 Section 8.

    Confidence = base + adjustments

    Base confidence:
        - tier1: 1.0 (exact match)
        - tier2: 0.9 (wildcard match)
        - tier3: 0.6 (fallback)
        - tier3 + fallback: 0.4

    Adjustments:
        - Guard detected: *= 0.3 (RFC-038)
        - Constraint satisfied: +0.1
        - Shell kwarg: +0.2

    Final confidence must be in [0.0, 1.0].
    Reporting threshold: >= 0.7 (default).
    """

    base_confidence: float  # 1.0/0.9/0.6/0.4
    adjustments: list[ConfidenceAdjustmentIR] = field(default_factory=list)
    min_report_threshold: float = field(default_factory=lambda: 0.7)  # Configurable

    def __post_init__(self) -> None:
        """Validate confidence."""
        if not (0.0 <= self.base_confidence <= 1.0):
            raise ValueError(f"base_confidence must be in [0, 1]: {self.base_confidence}")

        if not (0.0 <= self.min_report_threshold <= 1.0):
            raise ValueError(f"min_report_threshold must be in [0, 1]: {self.min_report_threshold}")

    def calculate_final(self) -> float:
        """Calculate final confidence after all adjustments.

        Returns:
            Final confidence in [0.0, 1.0]
        """
        confidence = self.base_confidence

        for adj in self.adjustments:
            if isinstance(adj, GuardAdjustmentIR | ConstraintAdjustmentIR):
                if adj.op == "add":
                    confidence += adj.value
                elif adj.op == "mul":
                    confidence *= adj.value
                elif adj.op == "set":
                    confidence = adj.value
            elif isinstance(adj, TierAdjustmentIR):
                # Tier adjustment is already applied to base_confidence
                pass

        # Clamp to [0, 1]
        return max(0.0, min(1.0, confidence))

    def should_report(self) -> bool:
        """Check if confidence meets reporting threshold."""
        return self.calculate_final() >= self.min_report_threshold


# ============================================================================
# Effect (Taint Analysis Impact)
# ============================================================================


@dataclass
class VulnerabilityIR:
    """Vulnerability metadata.

    For sink rules: what vulnerability does this represent?
    """

    cwe: str | None = None  # "CWE-89"
    category: str = "unknown"  # "sql_injection", "xss", "path_traversal"
    severity: Literal["low", "medium", "high", "critical"] = "medium"


@dataclass
class EffectIR:
    """How this rule affects taint analysis.

    RFC-033 Section 9.

    Defines what happens when rule matches:
        - source: Introduces taint (return value or property read)
        - sink: Consumes taint (argument positions)
        - sanitizer: Removes taint
        - passthrough: Propagates taint
    """

    kind: Literal["source", "sink", "sanitizer", "propagator", "passthrough"]

    # Taint positions
    arg_positions: list[int] = field(default_factory=list)  # Which args are tainted
    read_property: str | None = None  # For sources: request.GET
    write_target: Literal["return", "arg", "field"] | None = None

    # Vulnerability info (for sinks)
    vulnerability: VulnerabilityIR | None = None

    def __post_init__(self) -> None:
        """Validate effect."""
        if self.kind == "sink" and not self.arg_positions:
            # Default to arg 0 for sinks
            object.__setattr__(self, "arg_positions", [0])

        if self.kind == "source" and not (self.read_property or self.write_target):
            # Source must specify how taint is introduced
            object.__setattr__(self, "write_target", "return")  # Default: return value

        if self.kind == "sink" and not self.vulnerability:
            # Default vulnerability for sink
            object.__setattr__(self, "vulnerability", VulnerabilityIR(category="unknown"))


# ============================================================================
# Trace (Explainability)
# ============================================================================

TraceField = Literal[
    "rule_id",
    "atom_id",
    "candidate_generators",
    "index_path",
    "predicate_results",
    "confidence_breakdown",
    "specificity_breakdown",
]


@dataclass
class TracePolicyIR:
    """Trace emission policy.

    RFC-033 Section 10.

    Controls what debug info is collected for explainability.
    """

    enabled: bool = True
    emit_on: Literal["match", "mismatch", "both"] = "match"
    fields: list[TraceField] = field(default_factory=list)

    @classmethod
    def disabled(cls) -> "TracePolicyIR":
        """No tracing."""
        return cls(enabled=False, emit_on="match", fields=[])

    @classmethod
    def debug_all(cls) -> "TracePolicyIR":
        """Full debug trace."""
        return cls(
            enabled=True,
            emit_on="both",
            fields=[
                "rule_id",
                "atom_id",
                "candidate_generators",
                "index_path",
                "predicate_results",
                "confidence_breakdown",
                "specificity_breakdown",
            ],
        )

    @classmethod
    def production(cls) -> "TracePolicyIR":
        """Production trace (match only, minimal fields)."""
        return cls(
            enabled=True,
            emit_on="match",
            fields=["rule_id", "atom_id", "confidence_breakdown"],
        )
