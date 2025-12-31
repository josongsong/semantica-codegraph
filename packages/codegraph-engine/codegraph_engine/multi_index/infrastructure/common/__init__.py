"""
Index Layer Common Components

Shared schemas and utilities for all index types.

Note: transformer is lazy loaded to avoid pulling in heavy dependencies
(repomap -> foundation -> etc.) when only schemas are needed.
"""

from codegraph_engine.multi_index.infrastructure.common.documents import IndexDocument, SearchHit


def __getattr__(name: str):
    """Lazy import for heavy components."""
    if name == "IndexDocumentTransformer":
        from codegraph_engine.multi_index.infrastructure.common.transformer import IndexDocumentTransformer

        return IndexDocumentTransformer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "IndexDocument",
    "SearchHit",
    "IndexDocumentTransformer",
]
