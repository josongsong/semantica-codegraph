"""
Symbol Index (Memgraph-based)

Provides graph-based symbol search:
- Go-to-definition
- Find references
- Call graph queries (callers/callees)
"""

from codegraph_engine.multi_index.infrastructure.symbol.adapter_memgraph import MemgraphSymbolIndex

__all__ = ["MemgraphSymbolIndex"]
