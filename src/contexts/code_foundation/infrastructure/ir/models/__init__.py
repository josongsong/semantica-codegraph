"""
IR Models - Core structural IR models

Contains Node, Edge, Span, and IRDocument definitions.
"""

from src.contexts.code_foundation.infrastructure.ir.models.core import (
    ControlFlowSummary,
    Edge,
    EdgeKind,
    Node,
    NodeKind,
    Span,
)
from src.contexts.code_foundation.infrastructure.ir.models.diagnostic import (
    Diagnostic,
    DiagnosticIndex,
    DiagnosticSeverity,
)
from src.contexts.code_foundation.infrastructure.ir.models.document import IRDocument
from src.contexts.code_foundation.infrastructure.ir.models.occurrence import Occurrence, OccurrenceIndex, SymbolRole
from src.contexts.code_foundation.infrastructure.ir.models.package import PackageIndex, PackageMetadata

__all__ = [
    # Structural IR
    "Node",
    "NodeKind",
    "Edge",
    "EdgeKind",
    "Span",
    "ControlFlowSummary",
    "IRDocument",
    # Occurrence IR
    "Occurrence",
    "OccurrenceIndex",
    "SymbolRole",
    # Diagnostics
    "Diagnostic",
    "DiagnosticIndex",
    "DiagnosticSeverity",
    # Packages
    "PackageMetadata",
    "PackageIndex",
]
