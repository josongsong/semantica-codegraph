"""
Adapters for external taint-rule-compiler integration.

Connects codegraph (Expression, IRDocument) with trcr (taint-rule-compiler).

Usage:
    from codegraph_engine.code_foundation.infrastructure.taint.adapters import (
        ExpressionEntityAdapter,
        TRCRService,
    )

    # Analyze expressions
    service = TRCRService()
    service.load_rules("python")
    matches = service.analyze_expressions(ir_doc.expressions)
"""

from .trcr_adapter import (
    ExpressionEntityAdapter,
    IRDocumentAdapter,
    TRCRAdapter,
    TRCRService,
)

__all__ = [
    "ExpressionEntityAdapter",
    "TRCRService",
    # Legacy (deprecated)
    "IRDocumentAdapter",
    "TRCRAdapter",
]
