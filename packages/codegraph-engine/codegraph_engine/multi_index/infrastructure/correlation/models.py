"""
Correlation Index Models

Defines data structures for symbol correlation tracking.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CorrelationType(str, Enum):
    """Type of correlation between symbols/files."""

    CO_CHANGE = "co_change"  # Changed together in git commits
    CO_OCCURRENCE = "co_occurrence"  # Used together in same context
    CO_SEARCH = "co_search"  # Searched together by users (future)


@dataclass
class CorrelationEntry:
    """
    A correlation relationship between two entities (files or symbols).

    Attributes:
        source_id: First entity (file path or symbol FQN)
        target_id: Second entity (file path or symbol FQN)
        correlation_type: Type of correlation
        strength: Correlation strength (0.0 - 1.0)
        count: Number of observations
        metadata: Additional context
    """

    source_id: str
    target_id: str
    correlation_type: CorrelationType
    strength: float = 0.0
    count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Normalize ordering for consistent storage
        if self.source_id > self.target_id:
            self.source_id, self.target_id = self.target_id, self.source_id


@dataclass
class CorrelationSearchResult:
    """Result from correlation search."""

    entity_id: str
    correlation_type: CorrelationType
    strength: float
    count: int
    metadata: dict[str, Any] = field(default_factory=dict)
