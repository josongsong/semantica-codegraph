"""Base+Delta Merge Layer."""

from codegraph_engine.multi_index.infrastructure.lexical.merge.deduplicator import Deduplicator
from codegraph_engine.multi_index.infrastructure.lexical.merge.merging_index import MergingLexicalIndex

__all__ = [
    "MergingLexicalIndex",
    "Deduplicator",
]
