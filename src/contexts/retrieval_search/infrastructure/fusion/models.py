"""Common models for fusion strategies."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SearchStrategy(str, Enum):
    """Search strategy types."""

    VECTOR = "vector"
    LEXICAL = "lexical"
    SYMBOL = "symbol"
    GRAPH = "graph"


@dataclass
class StrategyResult:
    """Results from a single search strategy."""

    strategy: SearchStrategy
    chunks: list[dict[str, Any]]
    confidence: float  # Overall confidence for this strategy (0-1)
    metadata: dict[str, Any]
