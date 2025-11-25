"""
Index Layer Common Components

Shared schemas and utilities for all index types.
"""

from .documents import IndexDocument, SearchHit
from .transformer import IndexDocumentTransformer

__all__ = [
    "IndexDocument",
    "SearchHit",
    "IndexDocumentTransformer",
]
