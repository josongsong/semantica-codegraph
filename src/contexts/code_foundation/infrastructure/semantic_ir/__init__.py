"""
Semantic IR

Semantic analysis layer on top of Structural IR.

Phases:
- Phase 1: Type System + Signatures 
- Phase 2: CFG (Control Flow Graph)
- Phase 3: DFG (Data Flow Graph)
"""

from typing import TYPE_CHECKING

# Models (lightweight)
from src.contexts.code_foundation.infrastructure.semantic_ir.bfg.models import (
    BasicFlowBlock,
    BasicFlowGraph,
    BFGBlockKind,
)
from src.contexts.code_foundation.infrastructure.semantic_ir.cfg.models import (
    CFGBlockKind,
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
    ControlFlowGraph,
)
from src.contexts.code_foundation.infrastructure.semantic_ir.context import (
    SemanticIndex,
    SemanticIrDelta,
    SemanticIrSnapshot,
    SignatureIndex,
    TypeIndex,
)
from src.contexts.code_foundation.infrastructure.semantic_ir.signature.models import SignatureEntity, Visibility
from src.contexts.code_foundation.infrastructure.semantic_ir.typing.models import (
    TypeEntity,
    TypeFlavor,
    TypeResolutionLevel,
)

if TYPE_CHECKING:
    # Builders (heavy - lazy import via TYPE_CHECKING)
    from src.contexts.code_foundation.infrastructure.semantic_ir.bfg.builder import BfgBuilder
    from src.contexts.code_foundation.infrastructure.semantic_ir.builder import (
        DefaultSemanticIrBuilder,
        SemanticIrBuilder,
    )
    from src.contexts.code_foundation.infrastructure.semantic_ir.cfg.builder import CfgBuilder
    from src.contexts.code_foundation.infrastructure.semantic_ir.signature.builder import SignatureIrBuilder
    from src.contexts.code_foundation.infrastructure.semantic_ir.typing.builder import TypeIrBuilder


def __getattr__(name: str):
    """Lazy import for heavy builder classes."""
    if name in ("SemanticIrBuilder", "DefaultSemanticIrBuilder"):
        from src.contexts.code_foundation.infrastructure.semantic_ir.builder import (
            DefaultSemanticIrBuilder,
            SemanticIrBuilder,
        )

        return {"SemanticIrBuilder": SemanticIrBuilder, "DefaultSemanticIrBuilder": DefaultSemanticIrBuilder}[name]
    if name == "TypeIrBuilder":
        from src.contexts.code_foundation.infrastructure.semantic_ir.typing.builder import TypeIrBuilder

        return TypeIrBuilder
    if name == "SignatureIrBuilder":
        from src.contexts.code_foundation.infrastructure.semantic_ir.signature.builder import SignatureIrBuilder

        return SignatureIrBuilder
    if name == "BfgBuilder":
        from src.contexts.code_foundation.infrastructure.semantic_ir.bfg.builder import BfgBuilder

        return BfgBuilder
    if name == "CfgBuilder":
        from src.contexts.code_foundation.infrastructure.semantic_ir.cfg.builder import CfgBuilder

        return CfgBuilder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Builder (heavy - lazy import via TYPE_CHECKING)
    "SemanticIrBuilder",
    "DefaultSemanticIrBuilder",
    "TypeIrBuilder",
    "SignatureIrBuilder",
    "BfgBuilder",
    "CfgBuilder",
    # Context (lightweight)
    "SemanticIrSnapshot",
    "SemanticIrDelta",
    "SemanticIndex",
    "TypeIndex",
    "SignatureIndex",
    # Models (lightweight)
    "TypeEntity",
    "TypeFlavor",
    "TypeResolutionLevel",
    "SignatureEntity",
    "Visibility",
    "BFGBlockKind",
    "BasicFlowBlock",
    "BasicFlowGraph",
    "CFGBlockKind",
    "CFGEdgeKind",
    "ControlFlowBlock",
    "ControlFlowEdge",
    "ControlFlowGraph",
]
