"""
IR Models - Core structural IR models

Contains Node, Edge, Span, and IRDocument definitions.

NOTE (RFC-031): NodeKind/EdgeKind are now defined in kinds.py as the
canonical source of truth. They are re-exported here for compatibility.
"""

from codegraph_engine.code_foundation.infrastructure.ir.models.core import (
    ControlFlowSummary,
    Edge,
    Node,
    Span,
)
from codegraph_engine.code_foundation.infrastructure.ir.models.diagnostic import (
    Diagnostic,
    DiagnosticIndex,
    DiagnosticSeverity,
)
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

# RFC-031: Import canonical kinds from unified module
from codegraph_engine.code_foundation.infrastructure.ir.models.kinds import (
    EDGE_KIND_META,
    NODE_KIND_META,
    EdgeKind,
    EdgeKindMeta,
    KindMeta,
    NodeKind,
    get_edge_meta,
    get_node_meta,
    is_graph_kind,
    is_ir_kind,
    to_graph_node_kind,
)
from codegraph_engine.code_foundation.infrastructure.ir.models.occurrence import Occurrence, OccurrenceIndex, SymbolRole
from codegraph_engine.code_foundation.infrastructure.ir.models.package import PackageIndex, PackageMetadata

__all__ = [
    # Structural IR
    "Node",
    "NodeKind",
    "Edge",
    "EdgeKind",
    "Span",
    "ControlFlowSummary",
    "IRDocument",
    # RFC-031: Kind metadata
    "KindMeta",
    "EdgeKindMeta",
    "NODE_KIND_META",
    "EDGE_KIND_META",
    "get_node_meta",
    "get_edge_meta",
    "to_graph_node_kind",
    "is_ir_kind",
    "is_graph_kind",
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
