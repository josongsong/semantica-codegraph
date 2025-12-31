"""
Type IR Builder

Builds TypeEntity collection and TypeIndex from Structural IR.

Strategy:
- Phase 1: Extract types already resolved during AST parsing
- Phase 2: Re-resolve types using TypeResolver for MODULE/PROJECT/EXTERNAL resolution
- Phase 3: Cross-module type resolution with import tracking
"""

from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument, Node, NodeKind
from codegraph_engine.code_foundation.infrastructure.semantic_ir.context import TypeIndex
from codegraph_engine.code_foundation.infrastructure.semantic_ir.typing.models import TypeEntity
from codegraph_engine.code_foundation.infrastructure.semantic_ir.typing.resolver import TypeResolver


class TypeIrBuilder:
    """
    Builds semantic Type IR from structural IR.

    Enhanced with:
    - TypeResolver for MODULE/PROJECT/EXTERNAL resolution
    - Automatic index building from IR document
    - Cross-file type linking via import tracking
    """

    def __init__(self):
        self._type_cache: dict[str, TypeEntity] = {}
        self._resolver: TypeResolver | None = None

    def build_full(self, ir_doc: IRDocument) -> tuple[list[TypeEntity], TypeIndex]:
        """
        Build complete type IR from structural IR document.

        Enhanced with TypeResolver for MODULE/PROJECT/EXTERNAL resolution.

        Args:
            ir_doc: Structural IR document (with types already resolved)

        Returns:
            (types, type_index)
        """
        # Reset cache
        self._type_cache = {}

        # Initialize TypeResolver with repo_id
        self._resolver = TypeResolver(repo_id=ir_doc.repo_id)
        self._resolver.build_index_from_ir(ir_doc)

        # Collect all TypeEntity from IRDocument
        types = ir_doc.types.copy()
        for t in types:
            self._type_cache[t.id] = t

        # Enhance types with resolver (upgrade RAW → MODULE/PROJECT/EXTERNAL)
        self._enhance_types_with_resolver(types, ir_doc)

        # Link generic_param_ids to actual TypeEntity IDs
        self._link_generic_params(types)

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

    def _enhance_types_with_resolver(self, types: list[TypeEntity], ir_doc: IRDocument):
        """
        Enhance existing types with TypeResolver for better resolution.

        Upgrades RAW types to MODULE/PROJECT/EXTERNAL when possible.

        Args:
            types: List of type entities to enhance
            ir_doc: IR document for context
        """
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.typing.models import TypeResolutionLevel

        if not self._resolver:
            return

        for type_entity in types:
            # Only enhance types that are currently RAW (unresolved)
            if type_entity.resolution_level == TypeResolutionLevel.RAW:
                # Try to resolve using TypeResolver
                if type_entity.raw:
                    resolved = self._resolver.resolve_type(type_entity.raw)

                    # Update if we got a better resolution
                    if resolved.resolution_level != TypeResolutionLevel.RAW:
                        type_entity.resolution_level = resolved.resolution_level
                        type_entity.flavor = resolved.flavor
                        type_entity.resolved_target = resolved.resolved_target

                        # Update generic params if extracted
                        if resolved.generic_param_ids and not type_entity.generic_param_ids:
                            type_entity.generic_param_ids = resolved.generic_param_ids

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
        _existing_types: list[TypeEntity],
        _existing_index: TypeIndex,
    ) -> tuple[list[TypeEntity], TypeIndex]:
        """
        Apply incremental changes.

        Note: Since types are managed at IR document level, we simply
        rebuild the full type list and index. This is efficient because
        type extraction is fast (no heavy computation).

        Args:
            ir_doc: Updated IR document
            _existing_types: Existing types (unused - full rebuild)
            _existing_index: Existing index (unused - full rebuild)

        Returns:
            (new_types, new_index)
        """
        # Type extraction is fast, so full rebuild is efficient
        # Types come directly from IR document, no heavy processing needed
        return self.build_full(ir_doc)

    def _link_generic_params(self, types: list[TypeEntity]):
        """
        Link generic_param_ids to actual TypeEntity IDs in the cache.

        When TypeResolver generates generic param IDs, they may be synthetic.
        This method resolves them to actual TypeEntity IDs if available.

        Args:
            types: List of type entities
        """
        # Build raw string → type_id mapping for lookup
        raw_to_id: dict[str, str] = {}
        for t in types:
            if t.raw:
                raw_to_id[t.raw] = t.id
                # Also index normalized form
                normalized = t.raw.strip().replace(" ", "")
                if normalized not in raw_to_id:
                    raw_to_id[normalized] = t.id

        # Resolve generic param IDs
        for type_entity in types:
            if type_entity.generic_param_ids:
                resolved_ids = []
                for param_id in type_entity.generic_param_ids:
                    # If param_id is already a valid type ID, keep it
                    if param_id in self._type_cache:
                        resolved_ids.append(param_id)
                    else:
                        # Try to resolve by raw string
                        # Extract the type name from the ID (format: type:{repo}:{raw})
                        parts = param_id.split(":")
                        if len(parts) >= 3:
                            raw_type = ":".join(parts[2:])
                            if raw_type in raw_to_id:
                                resolved_ids.append(raw_to_id[raw_type])
                            else:
                                # Keep original if can't resolve
                                resolved_ids.append(param_id)
                        else:
                            resolved_ids.append(param_id)

                type_entity.generic_param_ids = resolved_ids

    def _build_index(self, types: list[TypeEntity]) -> TypeIndex:
        """
        Build type index from type list.

        Args:
            types: List of type entities

        Returns:
            Type index
        """
        type_index = TypeIndex()

        # Build basic type cache
        for t in types:
            self._type_cache[t.id] = t

        return type_index
