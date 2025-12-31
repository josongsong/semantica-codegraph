"""Tier Inference - RFC-033.

Automatically infer tier from match clause patterns.

Tier classification:
    - tier1: Exact matches (base_type + call, no wildcards)
    - tier2: Wildcard matches (*.Cursor, subprocess.*)
    - tier3: Fallback (broad patterns, contains wildcards)

Algorithm:
    1. Check for wildcards in patterns
    2. Count specificity (exact fields vs wildcards)
    3. Assign tier based on specificity score
"""

import logging
from typing import Literal

from trcr.ir.spec import MatchClauseSpec

logger = logging.getLogger(__name__)


def infer_tier(clause: MatchClauseSpec) -> Literal["tier1", "tier2", "tier3"]:
    """Infer tier from match clause.

    RFC-033: Tier classification based on pattern specificity.

    Rules:
        - tier1: Exact type + exact call (no wildcards)
        - tier2: One wildcard (*.Cursor or subprocess.*)
        - tier3: Multiple wildcards or very broad patterns

    Args:
        clause: Match clause to classify

    Returns:
        Tier: "tier1", "tier2", or "tier3"

    Examples:
        >>> clause = MatchClauseSpec(base_type="sqlite3.Cursor", call="execute")
        >>> infer_tier(clause)
        'tier1'

        >>> clause = MatchClauseSpec(base_type_pattern="*.Cursor", call="execute")
        >>> infer_tier(clause)
        'tier2'

        >>> clause = MatchClauseSpec(base_type_pattern="*mongo*")
        >>> infer_tier(clause)
        'tier3'
    """
    # Count wildcards
    wildcard_count = 0
    exact_count = 0

    # Type matching
    if clause.base_type:
        exact_count += 1
    elif clause.base_type_pattern:
        wildcard_count += _count_wildcards(clause.base_type_pattern)

    # Call matching
    if clause.call:
        exact_count += 1
    elif clause.call_pattern:
        wildcard_count += _count_wildcards(clause.call_pattern)

    # Property read (exact)
    if clause.read:
        exact_count += 1

    # Tier classification
    if wildcard_count == 0 and exact_count >= 2:
        # tier1: Exact type + exact call (or similar)
        return "tier1"

    elif wildcard_count == 0 and exact_count == 1:
        # tier2: Single exact field (call-only or type-only)
        # Not as precise as tier1, but still good
        return "tier2"

    elif wildcard_count == 1 and exact_count >= 1:
        # tier2: One wildcard + one exact
        return "tier2"

    elif wildcard_count == 1 and exact_count == 0:
        # tier2: Single wildcard pattern (e.g., *.Cursor)
        # Check if it's a simple suffix/prefix pattern
        if clause.base_type_pattern and _is_simple_pattern(clause.base_type_pattern):
            return "tier2"
        if clause.call_pattern and _is_simple_pattern(clause.call_pattern):
            return "tier2"

    # tier3: Multiple wildcards or complex patterns
    return "tier3"


def _count_wildcards(pattern: str) -> int:
    """Count wildcards in pattern.

    Args:
        pattern: Pattern string

    Returns:
        Number of wildcard segments

    Examples:
        >>> _count_wildcards("*.Cursor")
        1
        >>> _count_wildcards("*mongo*")
        2
        >>> _count_wildcards("subprocess.*")
        1
    """
    # Count * characters
    return pattern.count("*")


def _is_simple_pattern(pattern: str) -> bool:
    """Check if pattern is simple (prefix or suffix).

    Simple patterns:
        - *.Cursor (suffix)
        - subprocess.* (prefix)

    Complex patterns:
        - *mongo* (contains)
        - *sql*db* (multiple wildcards)

    Args:
        pattern: Pattern string

    Returns:
        True if simple pattern

    Examples:
        >>> _is_simple_pattern("*.Cursor")
        True
        >>> _is_simple_pattern("subprocess.*")
        True
        >>> _is_simple_pattern("*mongo*")
        False
    """
    # Simple: starts with * or ends with * (but not both)
    starts_with_wildcard = pattern.startswith("*")
    ends_with_wildcard = pattern.endswith("*")

    # Count wildcards
    wildcard_count = pattern.count("*")

    # Simple if:
    # - Single wildcard at start or end
    # - Not both
    if wildcard_count == 1:
        return starts_with_wildcard or ends_with_wildcard

    return False


def calculate_specificity_score(clause: MatchClauseSpec) -> float:
    """Calculate specificity score for clause.

    Used for tie-breaking when multiple rules match.

    Score calculation:
        - Exact field: +10
        - Wildcard field: +5
        - Literal characters: +0.1 per char

    Args:
        clause: Match clause

    Returns:
        Specificity score (higher = more specific)

    Examples:
        >>> clause = MatchClauseSpec(base_type="sqlite3.Cursor", call="execute")
        >>> calculate_specificity_score(clause)
        22.3  # 10 + 10 + 2.3 (23 chars)
    """
    score = 0.0

    # Type matching
    if clause.base_type:
        score += 10.0
        score += len(clause.base_type) * 0.1
    elif clause.base_type_pattern:
        score += 5.0
        # Count non-wildcard characters
        literal_chars = clause.base_type_pattern.replace("*", "")
        score += len(literal_chars) * 0.1

    # Call matching
    if clause.call:
        score += 10.0
        score += len(clause.call) * 0.1
    elif clause.call_pattern:
        score += 5.0
        literal_chars = clause.call_pattern.replace("*", "")
        score += len(literal_chars) * 0.1

    # Property read
    if clause.read:
        score += 10.0
        score += len(clause.read) * 0.1

    # Constraints add specificity
    if clause.constraints:
        score += 5.0

    return score


def infer_tier_batch(
    clauses: list[MatchClauseSpec],
) -> dict[int, Literal["tier1", "tier2", "tier3"]]:
    """Infer tiers for multiple clauses.

    Args:
        clauses: List of match clauses

    Returns:
        Dict mapping clause index to tier

    Example:
        >>> clauses = [
        ...     MatchClauseSpec(base_type="sqlite3.Cursor", call="execute"),
        ...     MatchClauseSpec(base_type_pattern="*.Cursor"),
        ... ]
        >>> infer_tier_batch(clauses)
        {0: 'tier1', 1: 'tier2'}
    """
    return {i: infer_tier(clause) for i, clause in enumerate(clauses)}
