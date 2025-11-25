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

from .builder import BfgBuilder
from .models import BasicFlowBlock, BasicFlowGraph, BFGBlockKind

__all__ = [
    "BfgBuilder",
    "BFGBlockKind",
    "BasicFlowBlock",
    "BasicFlowGraph",
]
