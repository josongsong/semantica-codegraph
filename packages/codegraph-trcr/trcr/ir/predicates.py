"""PredicateIR - RFC-033 Section 6.

6종 Predicate:
- TypeMatchPredicateIR: Type matching
- CallMatchPredicateIR: Call matching
- ReadPropertyPredicateIR: Property read matching
- ArgConstraintPredicateIR: Argument constraints
- KwargConstraintPredicateIR: Keyword argument constraints
- GuardPredicateIR: Guard-aware confidence (RFC-038)
"""

from dataclasses import dataclass
from typing import Literal

# ============================================================================
# Value Constraints
# ============================================================================


@dataclass(frozen=True)
class IsConstIR:
    """Check if argument is constant."""

    kind: Literal["is_const"] = "is_const"


@dataclass(frozen=True)
class IsNotConstIR:
    """Check if argument is NOT constant.

    Critical for SQL injection: we care about dynamic values.
    """

    kind: Literal["is_not_const"] = "is_not_const"


@dataclass(frozen=True)
class IsStringLikeIR:
    """Check if argument is string-like (str, bytes, etc.)."""

    kind: Literal["is_string_like"] = "is_string_like"


@dataclass(frozen=True)
class IsIntLikeIR:
    """Check if argument is int-like."""

    kind: Literal["is_int_like"] = "is_int_like"


@dataclass(frozen=True)
class MatchesRegexIR:
    """Check if argument value matches regex.

    Example: Check if SQL query starts with SELECT.
    """

    pattern: str
    regex_id: str  # Compiled regex reference (for caching)
    kind: Literal["matches_regex"] = "matches_regex"


@dataclass(frozen=True)
class LengthBoundIR:
    """Check if argument length is within bounds."""

    kind: Literal["length_bound"] = "length_bound"
    min_length: int | None = None
    max_length: int | None = None


# Union type for value constraints
ValueConstraintIR = IsConstIR | IsNotConstIR | IsStringLikeIR | IsIntLikeIR | MatchesRegexIR | LengthBoundIR


# ============================================================================
# Predicates
# ============================================================================


@dataclass(frozen=True)
class TypeMatchPredicateIR:
    """Type matching predicate.

    RFC-033 Section 6.

    Checks if entity's base_type matches the pattern.

    Cost:
        - exact: 2 (string comparison)
        - wildcard: 3 (regex match)
    """

    mode: Literal["exact", "wildcard"]
    pattern: str  # "sqlite3.Cursor" or "*.Cursor"
    matcher_id: str  # Reference to compiled matcher (regex or exact)
    kind: Literal["type_match"] = "type_match"
    negate: bool = False
    cost_hint: int = 2  # or 3 for wildcard

    def __post_init__(self) -> None:
        """Validate and set cost hint."""
        if self.mode == "wildcard":
            # Wildcard mode is more expensive
            object.__setattr__(self, "cost_hint", 3)


@dataclass(frozen=True)
class CallMatchPredicateIR:
    """Call matching predicate.

    Checks if entity's call name matches the pattern.

    Cost: 2 (exact) or 3 (wildcard)
    """

    mode: Literal["exact", "wildcard"]
    pattern: str  # "execute" or "execute*"
    matcher_id: str
    kind: Literal["call_match"] = "call_match"
    negate: bool = False
    cost_hint: int = 2

    def __post_init__(self) -> None:
        """Validate and set cost hint."""
        if self.mode == "wildcard":
            object.__setattr__(self, "cost_hint", 3)


@dataclass(frozen=True)
class ReadPropertyPredicateIR:
    """Property read matching predicate.

    For HTTP sources: request.GET, request.POST, etc.

    Cost: 2
    """

    property_name: str  # "GET", "POST", "args"
    kind: Literal["read_property"] = "read_property"
    negate: bool = False
    cost_hint: int = 2


@dataclass(frozen=True)
class ArgConstraintPredicateIR:
    """Argument constraint predicate.

    RFC-033 Section 6.

    Checks semantic constraints on positional arguments.

    Example:
        args[0] must be not_const (for SQL injection)
        args[1] must match regex pattern

    Cost: 4 (more expensive due to constraint checking)
    """

    arg_index: int
    constraints: list[ValueConstraintIR]
    kind: Literal["arg_constraint"] = "arg_constraint"
    cost_hint: int = 4

    def __post_init__(self) -> None:
        """Validate constraints."""
        if not self.constraints:
            raise ValueError("At least one constraint required")

        if self.arg_index < 0:
            raise ValueError(f"Invalid arg_index: {self.arg_index}")


@dataclass(frozen=True)
class KwargConstraintPredicateIR:
    """Keyword argument constraint predicate.

    RFC-033 Section 6.

    Checks constraints on keyword arguments.

    Example:
        shell=True (dangerous!)
        check_hostname=False (security risk!)

    Cost: 4
    """

    kwarg_name: str  # "shell", "check_hostname"
    constraints: list[ValueConstraintIR]
    kind: Literal["kwarg_constraint"] = "kwarg_constraint"
    cost_hint: int = 4

    def __post_init__(self) -> None:
        """Validate constraints."""
        if not self.constraints:
            raise ValueError("At least one constraint required")


@dataclass(frozen=True)
class GuardPredicateIR:
    """Guard-aware predicate.

    RFC-038: Guard-aware Execution.

    Checks if a sanitizer/guard is present in the dataflow.
    If guard is present, confidence is reduced.

    Example:
        If SQL query is parameterized → confidence *= 0.3
        If input is validated → confidence *= 0.5

    Cost: 5 (requires dataflow analysis)
    """

    guard_type: Literal["sanitizer", "validator", "encoder"]
    guard_pattern: str  # Pattern to match guard
    effect: Literal["block", "reduce_confidence"]  # What happens if guard found
    kind: Literal["guard"] = "guard"
    confidence_multiplier: float = 0.3  # If reduce_confidence
    cost_hint: int = 5

    def __post_init__(self) -> None:
        """Validate guard predicate."""
        if self.effect == "reduce_confidence" and not (0.0 <= self.confidence_multiplier <= 1.0):
            raise ValueError(f"Invalid confidence_multiplier: {self.confidence_multiplier}")


# Union type for all predicates
PredicateIR = (
    TypeMatchPredicateIR
    | CallMatchPredicateIR
    | ReadPropertyPredicateIR
    | ArgConstraintPredicateIR
    | KwargConstraintPredicateIR
    | GuardPredicateIR
)


# ============================================================================
# Predicate Execution Plan
# ============================================================================


@dataclass
class PredicateExecPlan:
    """Optimized predicate execution plan.

    RFC-033 Section 12.

    Predicates are reordered by cost for early exit.
    Short-circuit evaluation on first failure.
    """

    predicates: list[PredicateIR]  # Sorted by cost_hint (cheap first)
    short_circuit: bool = True  # Stop on first failure

    def __post_init__(self) -> None:
        """Sort predicates by cost for optimal execution."""
        # Sort by cost_hint (ascending)
        self.predicates.sort(key=lambda p: p.cost_hint)

    @property
    def total_cost_estimate(self) -> int:
        """Estimate total cost (assuming all pass)."""
        return sum(p.cost_hint for p in self.predicates)

    @property
    def best_case_cost(self) -> int:
        """Best case cost (first predicate fails)."""
        return self.predicates[0].cost_hint if self.predicates else 0

    @property
    def worst_case_cost(self) -> int:
        """Worst case cost (all predicates pass)."""
        return self.total_cost_estimate
