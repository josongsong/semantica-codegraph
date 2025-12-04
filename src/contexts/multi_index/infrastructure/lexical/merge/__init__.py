"""Base+Delta Merge Layer."""

from src.contexts.multi_index.infrastructure.lexical.merge.deduplicator import Deduplicator
from src.contexts.multi_index.infrastructure.lexical.merge.merging_index import MergingLexicalIndex

__all__ = [
    "MergingLexicalIndex",
    "Deduplicator",
]
