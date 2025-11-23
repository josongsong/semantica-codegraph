"""
Foundation: Intermediate Representation (IR) v4.1

This module provides the core data models and utilities for the IR layer.

Key components:
- models: Core IR entities (Node, Edge, Type, Signature, CFG, IRDocument)
- id_strategy: ID generation strategies (logical_id, stable_id, content_hash)
"""

from .id_strategy import (
    generate_cfg_block_id,
    generate_cfg_id,
    generate_content_hash,
    generate_edge_id,
    generate_logical_id,
    generate_signature_hash,
    generate_signature_id,
    generate_stable_id,
    generate_type_id,
)
from .models import (
    CFGBlockKind,
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
    ControlFlowGraph,
    ControlFlowSummary,
    Edge,
    EdgeKind,
    IRDocument,
    Node,
    NodeKind,
    SignatureEntity,
    Span,
    TypeEntity,
    TypeFlavor,
    TypeResolutionLevel,
    Visibility,
)

__all__ = [
    # Models
    "Node",
    "Edge",
    "TypeEntity",
    "SignatureEntity",
    "ControlFlowBlock",
    "ControlFlowEdge",
    "ControlFlowGraph",
    "ControlFlowSummary",
    "Span",
    "IRDocument",
    # Enums
    "NodeKind",
    "EdgeKind",
    "TypeFlavor",
    "TypeResolutionLevel",
    "Visibility",
    "CFGBlockKind",
    "CFGEdgeKind",
    # ID Strategy
    "generate_logical_id",
    "generate_stable_id",
    "generate_content_hash",
    "generate_edge_id",
    "generate_type_id",
    "generate_signature_id",
    "generate_signature_hash",
    "generate_cfg_id",
    "generate_cfg_block_id",
]
