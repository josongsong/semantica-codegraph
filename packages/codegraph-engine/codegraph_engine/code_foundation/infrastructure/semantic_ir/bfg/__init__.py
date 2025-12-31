"""
BFG (Basic Flow Graph) Layer

Extracts Basic Blocks from functions.
Basic Blocks are maximal sequences of statements with:
- Single entry point (first statement)
- Single exit point (last statement)
- No internal branches

This layer is separate from CFG to enable:
- Cleaner architecture (separation of concerns)
- Better testing and debugging
- Reusability for SSA, reaching definitions, etc.
- Incremental updates (can cache BFG when only edges change)
"""

from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.builder import BfgBuilder
from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import (
    BasicFlowBlock,
    BasicFlowGraph,
    BFGBlockKind,
)

__all__ = [
    "BfgBuilder",
    "BFGBlockKind",
    "BasicFlowBlock",
    "BasicFlowGraph",
]
