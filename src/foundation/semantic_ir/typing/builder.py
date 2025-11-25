"""
Type IR Builder

Builds TypeEntity collection and TypeIndex from Structural IR.

Strategy:
- Phase 1: Extract types already resolved during AST parsing
- Phase 2: Re-resolve types using language-specific resolvers (Pyright, TS server)
- Phase 3: Cross-module type resolution
"""


from ...ir.models import IRDocument, Node, NodeKind
from ..context import TypeIndex
from .models import TypeEntity


class TypeIrBuilder:
    """
    Builds semantic Type IR from structural IR.

    Currently: Extracts types already embedded in IRDocument
    Future: Re-resolve types using external type checkers
    """

    def __init__(self):
        self._type_cache: dict[str, TypeEntity] = {}

    def build_full(self, ir_doc: IRDocument) -> tuple[list[TypeEntity], TypeIndex]:
        """
        Build complete type IR from structural IR document.

        Args:
            ir_doc: Structural IR document (with types already resolved)

        Returns:
            (types, type_index)
        """
        # Reset cache
        self._type_cache = {}

        # Collect all TypeEntity from IRDocument
        types = ir_doc.types.copy()
        for t in types:
            self._type_cache[t.id] = t

        # Build index
        type_index = TypeIndex()

        # Index functions → parameter types + return type
        for node in ir_doc.nodes:
            if node.kind in (NodeKind.FUNCTION, NodeKind.METHOD):
                self._index_function(node, ir_doc, type_index)

        # Index variables → declared type
        for node in ir_doc.nodes:
            if node.kind == NodeKind.VARIABLE:
                if node.declared_type_id:
                    type_index.variable_to_type_id[node.id] = node.declared_type_id

        return types, type_index

    def _index_function(self, func_node: Node, ir_doc: IRDocument, type_index: TypeIndex):
        """
        Index function's parameter types and return type.

        Args:
            func_node: Function or Method node
            ir_doc: IR document
            type_index: Type index to populate
        """
        # Find signature
        if not func_node.signature_id:
            return

        signature = next(
            (s for s in ir_doc.signatures if s.id == func_node.signature_id),
            None,
        )
        if not signature:
            return

        # Index parameter types
        if signature.parameter_type_ids:
            type_index.function_to_param_type_ids[func_node.id] = signature.parameter_type_ids

        # Index return type
        if signature.return_type_id:
            type_index.function_to_return_type_id[func_node.id] = signature.return_type_id

    def apply_delta(
        self,
        ir_doc: IRDocument,
        existing_types: list[TypeEntity],
        existing_index: TypeIndex,
    ) -> tuple[list[TypeEntity], TypeIndex]:
        """
        Apply incremental changes (simplified - full rebuild for now).

        Args:
            ir_doc: Updated IR document
            existing_types: Existing types (for GC later)
            existing_index: Existing index

        Returns:
            (new_types, new_index)
        """
        # For now, just rebuild
        # TODO: Implement proper delta logic
        return self.build_full(ir_doc)
