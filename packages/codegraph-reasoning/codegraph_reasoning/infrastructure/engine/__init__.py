"""
High-performance graph engines for reasoning.

RFC-007: Rust-based engines for 10-50x speedup (SOTA)

Components:
- MemgraphVFGExtractor: Extract VFG from Memgraph
- RustTaintEngine: Fast taint analysis (rustworkx, LRU cache)
- ValueFlowGraphSaver: Save VFG to Memgraph (batch UNWIND)

Performance:
- Cold: 1-10ms (20x faster than Memgraph Cypher)
- Cache: 0.01ms (1000x faster, true LRU)
- Load: 10ms per 1k nodes
"""

from .memgraph_extractor import MemgraphVFGExtractor
from .vfg_saver import ValueFlowGraphSaver

try:
    from .rust_taint_engine import RustTaintEngine
except ImportError:
    RustTaintEngine = None  # type: ignore

__all__ = [
    "MemgraphVFGExtractor",
    "RustTaintEngine",
    "ValueFlowGraphSaver",
]
