"""Guard Types - RFC-038 Guard-aware Execution.

Guards are validation/sanitization patterns detected during dataflow analysis.
These are PROVIDED BY codegraph (not detected by trcr).

Guard Detection Flow:
    1. codegraph performs CFG analysis
    2. codegraph detects guards (allowlist, regex validation, etc.)
    3. codegraph populates Entity.guards field
    4. trcr uses guards for confidence adjustment

Guard Types:
    - AllowlistGuard: Value checked against whitelist
    - RegexGuard: Value validated by regex pattern
    - LengthGuard: Value length constrained
    - TypeGuard: Value type checked
    - EscapeGuard: Value escaped/encoded
    - SanitizerGuard: Value passed through sanitizer

Usage:
    # codegraph creates entity with guards
    entity = Entity(
        id="call_123",
        guards=[
            AllowlistGuard(confidence_multiplier=0.3),
            RegexGuard(pattern="^[a-zA-Z]+$", confidence_multiplier=0.5),
        ]
    )

    # trcr adjusts confidence based on guards
    for guard in entity.guards:
        confidence *= guard.confidence_multiplier
"""

from dataclasses import dataclass
from typing import Literal, Protocol


class Guard(Protocol):
    """Guard protocol - represents a detected guard/validation.

    RFC-038: Guard-aware Execution.

    Guards are detected by CFG analysis (codegraph's responsibility).
    trcr uses guards to adjust match confidence.

    Attributes:
        kind: Guard type identifier
        confidence_multiplier: Factor to multiply confidence by (0.0-1.0)
        is_fail_fast: Whether guard aborts on failure (stronger guarantee)
    """

    @property
    def kind(self) -> str:
        """Guard type identifier."""
        ...

    @property
    def confidence_multiplier(self) -> float:
        """Confidence multiplier when guard is present (0.0-1.0).

        Lower value = stronger guard = more confidence reduction.
        Examples:
            - 0.3 = strong guard (70% confidence reduction)
            - 0.5 = medium guard (50% confidence reduction)
            - 0.8 = weak guard (20% confidence reduction)
        """
        ...

    @property
    def is_fail_fast(self) -> bool:
        """Whether guard aborts execution on failure.

        If True, reaching the sink means the guard passed.
        This provides stronger security guarantee.
        """
        ...


@dataclass(frozen=True)
class AllowlistGuard:
    """Value checked against a whitelist.

    Example: table name validated against allowed tables.

    Strong guard (0.3 multiplier) when fail-fast.
    """

    kind: Literal["allowlist"] = "allowlist"
    confidence_multiplier: float = 0.3
    is_fail_fast: bool = True

    # Optional: actual allowlist values (for analysis)
    values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate guard parameters."""
        if not 0.0 <= self.confidence_multiplier <= 1.0:
            raise ValueError(f"confidence_multiplier must be in [0, 1]: {self.confidence_multiplier}")


@dataclass(frozen=True)
class RegexGuard:
    """Value validated by regex pattern.

    Example: Input validated to contain only alphanumeric chars.

    Medium guard (0.5 multiplier) - regex can be bypassed.
    """

    kind: Literal["regex"] = "regex"
    confidence_multiplier: float = 0.5
    is_fail_fast: bool = True

    # The regex pattern (for analysis)
    pattern: str = ""

    def __post_init__(self) -> None:
        """Validate guard parameters."""
        if not 0.0 <= self.confidence_multiplier <= 1.0:
            raise ValueError(f"confidence_multiplier must be in [0, 1]: {self.confidence_multiplier}")


@dataclass(frozen=True)
class LengthGuard:
    """Value length constrained.

    Example: Input length limited to 100 characters.

    Weak guard (0.8 multiplier) - length alone doesn't prevent injection.
    """

    kind: Literal["length"] = "length"
    confidence_multiplier: float = 0.8
    is_fail_fast: bool = True

    # Length constraints
    min_length: int | None = None
    max_length: int | None = None

    def __post_init__(self) -> None:
        """Validate guard parameters."""
        if not 0.0 <= self.confidence_multiplier <= 1.0:
            raise ValueError(f"confidence_multiplier must be in [0, 1]: {self.confidence_multiplier}")

        if self.min_length is not None and self.min_length < 0:
            raise ValueError(f"min_length must be >= 0: {self.min_length}")

        if self.max_length is not None and self.max_length < 0:
            raise ValueError(f"max_length must be >= 0: {self.max_length}")


@dataclass(frozen=True)
class TypeGuard:
    """Value type checked.

    Example: Input verified to be integer (not string).

    Medium guard (0.6 multiplier) - type confusion still possible.
    """

    kind: Literal["type"] = "type"
    confidence_multiplier: float = 0.6
    is_fail_fast: bool = True

    # Expected type
    expected_type: str = ""

    def __post_init__(self) -> None:
        """Validate guard parameters."""
        if not 0.0 <= self.confidence_multiplier <= 1.0:
            raise ValueError(f"confidence_multiplier must be in [0, 1]: {self.confidence_multiplier}")


@dataclass(frozen=True)
class EscapeGuard:
    """Value escaped or encoded.

    Example: Input HTML-escaped or SQL-escaped.

    Strong guard (0.2 multiplier) - proper escaping is effective.
    """

    kind: Literal["escape"] = "escape"
    confidence_multiplier: float = 0.2
    is_fail_fast: bool = False  # Escaping doesn't abort

    # Escape method
    escape_method: str = ""  # "html", "sql", "shell", "url"

    def __post_init__(self) -> None:
        """Validate guard parameters."""
        if not 0.0 <= self.confidence_multiplier <= 1.0:
            raise ValueError(f"confidence_multiplier must be in [0, 1]: {self.confidence_multiplier}")


@dataclass(frozen=True)
class SanitizerGuard:
    """Value passed through a sanitizer function.

    Example: bleach.clean(), html.escape(), etc.

    Strong guard (0.2 multiplier) - trusted sanitizer.
    """

    kind: Literal["sanitizer"] = "sanitizer"
    confidence_multiplier: float = 0.2
    is_fail_fast: bool = False  # Sanitization transforms, doesn't abort

    # Sanitizer function
    sanitizer_name: str = ""  # "bleach.clean", "markupsafe.escape"

    def __post_init__(self) -> None:
        """Validate guard parameters."""
        if not 0.0 <= self.confidence_multiplier <= 1.0:
            raise ValueError(f"confidence_multiplier must be in [0, 1]: {self.confidence_multiplier}")


# Union type for all guards
GuardType = AllowlistGuard | RegexGuard | LengthGuard | TypeGuard | EscapeGuard | SanitizerGuard


def calculate_combined_multiplier(guards: list[GuardType]) -> float:
    """Calculate combined confidence multiplier from multiple guards.

    Multipliers are combined multiplicatively.
    More guards = lower final confidence.

    Args:
        guards: List of guards

    Returns:
        Combined multiplier (0.0-1.0)

    Example:
        >>> guards = [AllowlistGuard(), RegexGuard()]
        >>> calculate_combined_multiplier(guards)
        0.15  # 0.3 * 0.5 = 0.15
    """
    if not guards:
        return 1.0

    result = 1.0
    for guard in guards:
        result *= guard.confidence_multiplier

    return result


def has_strong_guard(guards: list[GuardType]) -> bool:
    """Check if any guard is considered strong.

    Strong guards have multiplier <= 0.3.

    Args:
        guards: List of guards

    Returns:
        True if any strong guard present
    """
    return any(g.confidence_multiplier <= 0.3 for g in guards)


def has_fail_fast_guard(guards: list[GuardType]) -> bool:
    """Check if any guard is fail-fast.

    Fail-fast guards provide stronger security guarantees.

    Args:
        guards: List of guards

    Returns:
        True if any fail-fast guard present
    """
    return any(g.is_fail_fast for g in guards)
