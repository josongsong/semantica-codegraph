"""Match Result - Domain Layer.

Match represents a successful rule match against an entity.
"""

from dataclasses import dataclass, field

from trcr.types.entity import Entity


@dataclass
class TraceInfo:
    """Trace information for match explainability.

    RFC-033 Section 10: TracePolicyIR.

    Explains why this match occurred.
    """

    rule_id: str
    atom_id: str
    tier: str

    # Generator info
    generator_kind: str
    index_used: str
    candidates_generated: int

    # Predicate info
    predicates_evaluated: int
    predicates_passed: int
    predicate_results: list[tuple[str, bool, float]]  # (kind, passed, confidence_adj)

    # Confidence breakdown
    base_confidence: float
    confidence_adjustments: list[tuple[str, float]]  # (reason, adjustment)
    final_confidence: float

    # Specificity
    specificity_score: float


@dataclass
class Match:
    """Match result from rule execution.

    RFC-033: Represents a successful rule match.

    Contains:
        - Which rule matched
        - Which entity matched
        - Confidence score
        - Optional trace (for debugging)
    """

    # Identity
    rule_id: str
    atom_id: str

    # Matched entity
    entity: Entity

    # Match quality
    confidence: float  # [0.0, 1.0]
    specificity: float

    # Effect (what happens)
    effect_kind: str  # "source", "sink", "sanitizer", etc.
    taint_positions: list[int]  # Which args are tainted

    # Optional metadata
    tier: str  # "tier1", "tier2", "tier3"
    severity: str | None = None  # For sinks
    tags: list[str] = field(default_factory=lambda: [])

    # Trace (optional, for debugging)
    trace: TraceInfo | None = None

    def __post_init__(self) -> None:
        """Validate match."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0, 1]: {self.confidence}")

    def should_report(self, threshold: float = 0.7) -> bool:
        """Check if match should be reported.

        Args:
            threshold: Confidence threshold

        Returns:
            True if confidence >= threshold
        """
        return self.confidence >= threshold

    def __lt__(self, other: "Match") -> bool:
        """Sort by specificity (higher first), then confidence."""
        if self.specificity != other.specificity:
            return self.specificity > other.specificity

        if self.confidence != other.confidence:
            return self.confidence > other.confidence

        return self.rule_id < other.rule_id


@dataclass
class MatchContext:
    """Context for rule matching.

    Provides indices and utility functions for rule execution.
    """

    # Indices (populated by IndexBuilder)
    exact_type_call_index: dict[tuple[str, str], list[Entity]] = field(default_factory=lambda: {})
    exact_call_index: dict[str, list[Entity]] = field(default_factory=lambda: {})

    # Statistics (for optimization)
    total_entities: int = 0
    index_hit_count: dict[str, int] = field(default_factory=lambda: {})

    def record_hit(self, index_name: str) -> None:
        """Record index hit for statistics.

        Args:
            index_name: Name of index that was hit
        """
        self.index_hit_count[index_name] = self.index_hit_count.get(index_name, 0) + 1
