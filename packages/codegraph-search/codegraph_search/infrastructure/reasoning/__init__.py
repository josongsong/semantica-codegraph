"""
Test-Time Reasoning Module (Phase 3 SOTA)

o1-style reasoning for adaptive search strategies.
"""

from typing import TYPE_CHECKING

from codegraph_search.infrastructure.reasoning.models import (
    ReasonedResult,
    ReasoningStep,
    SearchStrategy,
    SearchTool,
)

if TYPE_CHECKING:
    from codegraph_search.infrastructure.reasoning.test_time_compute import ReasoningRetriever


def __getattr__(name: str):
    """Lazy import for heavy retriever class."""
    if name == "ReasoningRetriever":
        from codegraph_search.infrastructure.reasoning.test_time_compute import ReasoningRetriever

        return ReasoningRetriever
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Models (lightweight)
    "SearchTool",
    "ReasoningStep",
    "SearchStrategy",
    "ReasonedResult",
    # Retriever (heavy - lazy import via TYPE_CHECKING)
    "ReasoningRetriever",
]
