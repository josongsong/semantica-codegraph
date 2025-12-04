"""Graph runtime expansion for flow tracing."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.contexts.retrieval_search.infrastructure.graph_runtime_expansion.flow_expander import GraphExpansionClient


def __getattr__(name: str):
    """Lazy import for heavy client class."""
    if name == "GraphExpansionClient":
        from src.contexts.retrieval_search.infrastructure.graph_runtime_expansion.flow_expander import (
            GraphExpansionClient,
        )

        return GraphExpansionClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["GraphExpansionClient"]
