"""
Python Signature Builder

Responsible for building function/method signatures from Python AST.
"""

try:
    from tree_sitter import Node as TSNode
except ImportError:
    TSNode = None

from ...ir.id_strategy import generate_signature_id
from ...semantic_ir.signature.models import SignatureEntity
from ...semantic_ir.typing.models import TypeEntity
from ...semantic_ir.typing.resolver import TypeResolver


class PythonSignatureBuilder:
    """
    Builds function/method signatures from Python AST.

    Responsibilities:
    - Parameter extraction with type annotations
    - Return type extraction
    - Signature entity creation with hash
    """

    def __init__(self, type_resolver: TypeResolver, types: dict[str, TypeEntity]):
        """
        Initialize signature builder.

        Args:
            type_resolver: Type resolver for annotation processing
            types: Shared types dictionary (type_id -> TypeEntity)
        """
        self._type_resolver = type_resolver
        self._types = types

    def build_signature(
        self,
        func_node: TSNode,
        node_id: str,
        func_name: str,
        param_type_ids: list[str],
        get_node_text_fn,
        source_bytes: bytes,
    ) -> SignatureEntity | None:
        """
        Build signature entity for function/method.

        Args:
            func_node: function_definition AST node
            node_id: Function node ID
            func_name: Function name
            param_type_ids: List of parameter type IDs (from process_parameters)
            get_node_text_fn: Function to extract text from AST node
            source_bytes: Source file bytes for text extraction

        Returns:
            SignatureEntity or None
        """
        # Extract return type annotation
        return_type_id = None
        return_type_node = func_node.child_by_field_name("return_type")
        if return_type_node:
            raw_return_type = get_node_text_fn(return_type_node, source_bytes)
            return_type_entity = self._type_resolver.resolve_type(raw_return_type)
            self._types[return_type_entity.id] = return_type_entity
            return_type_id = return_type_entity.id

        # Build signature string
        param_type_strs = []
        for type_id in param_type_ids:
            type_entity: TypeEntity | None = self._types.get(type_id)
            if type_entity:
                param_type_strs.append(type_entity.raw)

        return_type_str = ""
        if return_type_id:
            ret_type_entity: TypeEntity | None = self._types.get(return_type_id)
            if ret_type_entity:
                return_type_str = f" -> {ret_type_entity.raw}"

        params_str = ", ".join(param_type_strs) if param_type_strs else ""
        raw_signature = f"{func_name}({params_str}){return_type_str}"

        # Generate signature ID
        return_type_raw = None
        if return_type_id:
            ret_type_ent: TypeEntity | None = self._types.get(return_type_id)
            if ret_type_ent:
                return_type_raw = ret_type_ent.raw

        sig_id = generate_signature_id(
            owner_node_id=node_id,
            name=func_name,
            param_types=param_type_strs,
            return_type=return_type_raw,
        )

        # Calculate signature hash for change detection
        import hashlib

        sig_hash = hashlib.sha256(raw_signature.encode()).hexdigest()

        # Create signature entity
        signature = SignatureEntity(
            id=sig_id,
            owner_node_id=node_id,
            name=func_name,
            raw=raw_signature,
            parameter_type_ids=param_type_ids,
            return_type_id=return_type_id,
            signature_hash=f"sha256:{sig_hash}",
        )

        return signature
