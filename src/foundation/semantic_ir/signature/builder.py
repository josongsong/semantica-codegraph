"""
Signature IR Builder

Builds SignatureEntity collection and SignatureIndex from Structural IR.

Strategy:
- Extract signatures already built during AST parsing
- Build index for fast lookup (function node_id → signature)
"""

from ...ir.models import IRDocument, NodeKind
from ..context import SignatureIndex
from .models import SignatureEntity


class SignatureIrBuilder:
    """
    Builds semantic Signature IR from structural IR.

    Currently: Extracts signatures already embedded in IRDocument
    Future: Re-build signatures with enhanced analysis
    """

    def __init__(self):
        pass

    def build_full(
        self, ir_doc: IRDocument
    ) -> tuple[list[SignatureEntity], SignatureIndex]:
        """
        Build complete signature IR from structural IR document.

        Args:
            ir_doc: Structural IR document (with signatures already built)

        Returns:
            (signatures, signature_index)
        """
        # Collect all SignatureEntity from IRDocument
        signatures = ir_doc.signatures.copy()

        # Build index: function node_id → signature_id
        signature_index = SignatureIndex()

        for node in ir_doc.nodes:
            if node.kind in (NodeKind.FUNCTION, NodeKind.METHOD, NodeKind.LAMBDA):
                if node.signature_id:
                    signature_index.function_to_signature[node.id] = node.signature_id

        return signatures, signature_index

    def apply_delta(
        self,
        ir_doc: IRDocument,
        existing_signatures: list[SignatureEntity],
        existing_index: SignatureIndex,
    ) -> tuple[list[SignatureEntity], SignatureIndex]:
        """
        Apply incremental changes (simplified - full rebuild for now).

        Args:
            ir_doc: Updated IR document
            existing_signatures: Existing signatures
            existing_index: Existing index

        Returns:
            (new_signatures, new_index)
        """
        # For now, just rebuild
        # TODO: Implement proper delta logic
        # - Check signature_hash to detect changes
        # - Reuse unchanged signatures
        return self.build_full(ir_doc)
