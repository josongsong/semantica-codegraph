"""
Signature IR Builder

Builds SignatureEntity collection and SignatureIndex from Structural IR.

Strategy:
- Extract signatures already built during AST parsing
- Build index for fast lookup (function node_id → signature)
"""

from src.contexts.code_foundation.infrastructure.ir.models import IRDocument, Node, NodeKind
from src.contexts.code_foundation.infrastructure.semantic_ir.context import SignatureIndex
from src.contexts.code_foundation.infrastructure.semantic_ir.signature.models import SignatureEntity


class SignatureIrBuilder:
    """
    Builds semantic Signature IR from structural IR.

    Currently: Extracts signatures already embedded in IRDocument
    Future: Re-build signatures with enhanced analysis
    """

    def __init__(self):
        pass

    def build_full(self, ir_doc: IRDocument) -> tuple[list[SignatureEntity], SignatureIndex]:
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
        _existing_signatures: list[SignatureEntity],
        _existing_index: SignatureIndex,
    ) -> tuple[list[SignatureEntity], SignatureIndex]:
        """
        Apply incremental changes.

        Note: Since signatures are managed at IR document level and extraction
        is very fast, we simply rebuild the full signature list and index.

        Args:
            ir_doc: Updated IR document
            _existing_signatures: Existing signatures (unused - full rebuild)
            _existing_index: Existing index (unused - full rebuild)

        Returns:
            (new_signatures, new_index)
        """
        # Signature extraction is fast, so full rebuild is efficient
        # Signatures come directly from IR document, no heavy processing needed
        return self.build_full(ir_doc)

    def _build_signature_from_node(self, func_node: Node) -> SignatureEntity | None:
        """
        Build signature entity from function node.

        This is a helper method for incremental updates in other builders.
        Note: This is a simplified version - real signatures should come from IR document.

        Args:
            func_node: Function/Method node

        Returns:
            SignatureEntity or None if node has no signature
        """
        if not func_node.signature_id:
            return None

        # Build minimal signature entity
        # Real signatures should come from IR document's signatures list
        return SignatureEntity(
            id=func_node.signature_id,
            owner_node_id=func_node.id,
            name=func_node.name,
            raw=f"{func_node.name}(...)",  # Simplified signature string
            parameter_type_ids=[],  # Would need type info from IR
            return_type_id=None,  # Would need type info from IR
        )

    def _build_index(self, signatures: list[SignatureEntity]) -> SignatureIndex:
        """
        Build signature index from signature list.

        Args:
            signatures: List of signature entities

        Returns:
            Signature index
        """
        signature_index = SignatureIndex()

        for sig in signatures:
            signature_index.function_to_signature[sig.owner_node_id] = sig.id

        return signature_index
