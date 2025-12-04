"""Context Builder Module.

Provides components for building context from retrieved chunks.
"""

from typing import TYPE_CHECKING

from src.contexts.retrieval_search.infrastructure.context_builder.models import ContextChunk, ContextResult

if TYPE_CHECKING:
    from src.contexts.retrieval_search.infrastructure.context_builder.builder import ContextBuilder


def __getattr__(name: str):
    """Lazy import for heavy builder class."""
    if name == "ContextBuilder":
        from src.contexts.retrieval_search.infrastructure.context_builder.builder import ContextBuilder

        return ContextBuilder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ContextBuilder", "ContextChunk", "ContextResult"]
