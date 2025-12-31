"""
Query Index Components

Separated indexes following Single Responsibility Principle.

Architecture:
    UnifiedGraphIndex (Facade)
        ├─ NodeIndex (Node storage & lookup)
        ├─ EdgeIndex (Edge storage & lookup)
        ├─ SemanticIndex (Name-based search)
        ├─ BloomFilter (O(1) existence pre-check)  # SOTA
        └─ ReachabilityIndex (Transitive Closure)  # SOTA
"""

from .bloom_filter import BloomFilter, EdgeBloomFilter, ReachabilityBloomFilter
from .edge_index import EdgeIndex
from .node_index import NodeIndex
from .reachability_index import BidirectionalReachabilityIndex, ReachabilityIndex
from .semantic_index import SemanticIndex

__all__ = [
    "NodeIndex",
    "EdgeIndex",
    "SemanticIndex",
    # SOTA Indexes
    "BloomFilter",
    "EdgeBloomFilter",
    "ReachabilityBloomFilter",
    "ReachabilityIndex",
    "BidirectionalReachabilityIndex",
]
