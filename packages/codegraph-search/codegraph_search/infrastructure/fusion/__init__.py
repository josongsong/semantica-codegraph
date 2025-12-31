"""Fusion strategies for multi-index retrieval."""

from typing import TYPE_CHECKING

from codegraph_search.infrastructure.fusion.models import SearchStrategy, StrategyResult

if TYPE_CHECKING:
    from codegraph_search.infrastructure.fusion.engine import FusionEngine


def __getattr__(name: str):
    """Lazy import for heavy engine class."""
    if name == "FusionEngine":
        from codegraph_search.infrastructure.fusion.engine import FusionEngine

        return FusionEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["FusionEngine", "SearchStrategy", "StrategyResult"]
