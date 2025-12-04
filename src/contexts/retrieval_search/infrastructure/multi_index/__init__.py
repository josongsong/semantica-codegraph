"""Multi-index retrieval orchestrator."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.contexts.retrieval_search.infrastructure.multi_index.lexical_client import LexicalIndexClient
    from src.contexts.retrieval_search.infrastructure.multi_index.orchestrator import (
        MultiIndexOrchestrator,
        MultiIndexResult,
    )
    from src.contexts.retrieval_search.infrastructure.multi_index.symbol_client import SymbolIndexClient
    from src.contexts.retrieval_search.infrastructure.multi_index.vector_client import VectorIndexClient


def __getattr__(name: str):
    """Lazy import for heavy client classes."""
    if name == "LexicalIndexClient":
        from src.contexts.retrieval_search.infrastructure.multi_index.lexical_client import LexicalIndexClient

        return LexicalIndexClient
    if name == "MultiIndexOrchestrator":
        from src.contexts.retrieval_search.infrastructure.multi_index.orchestrator import MultiIndexOrchestrator

        return MultiIndexOrchestrator
    if name == "MultiIndexResult":
        from src.contexts.retrieval_search.infrastructure.multi_index.orchestrator import MultiIndexResult

        return MultiIndexResult
    if name == "SymbolIndexClient":
        from src.contexts.retrieval_search.infrastructure.multi_index.symbol_client import SymbolIndexClient

        return SymbolIndexClient
    if name == "VectorIndexClient":
        from src.contexts.retrieval_search.infrastructure.multi_index.vector_client import VectorIndexClient

        return VectorIndexClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "LexicalIndexClient",
    "MultiIndexOrchestrator",
    "MultiIndexResult",
    "SymbolIndexClient",
    "VectorIndexClient",
]
