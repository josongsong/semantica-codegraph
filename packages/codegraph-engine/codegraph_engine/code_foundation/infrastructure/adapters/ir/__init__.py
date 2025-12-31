"""
IR Port Adapters

Production-grade implementations for ir_port.py.

Exports:
- IRNodePort → IRNodeAdapter
- IRDocumentPort → IRDocumentAdapter
"""

from .document_adapter import IRDocumentAdapter, create_ir_document_adapter
from .node_adapter import IRNodeAdapter, create_ir_node_adapter

__all__ = [
    # Adapters
    "IRNodeAdapter",
    "IRDocumentAdapter",
    # Factory functions
    "create_ir_node_adapter",
    "create_ir_document_adapter",
]
