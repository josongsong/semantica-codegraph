"""
Python Signature Builder - FIXED VERSION

Ensures TSNode is not confused with IR Node
"""

from src.contexts.code_foundation.infrastructure.ir.id_strategy import generate_signature_id
from src.contexts.code_foundation.infrastructure.semantic_ir.signature.models import SignatureEntity
from src.contexts.code_foundation.infrastructure.semantic_ir.typing.resolver import TypeResolver


class PythonSignatureBuilder:
    """
    Builds function/method signatures from Python AST.

    Works with tree-sitter AST nodes (not IR nodes).
    """

    def __init__(self, type_resolver: TypeResolver, types: dict):
        """
        Initialize signature builder.

        Args:
            type_resolver: Type resolver instance
            types: Shared types dictionary
        """
        self._type_resolver = type_resolver
        self._types = types

    def build_signature(
        self,
        func_ast_node,  # tree-sitter AST node
        node_id: str,
        func_name: str,
        param_type_ids: list[str],
        get_node_text_fn,
        source_bytes: bytes,
    ):
        """
        Build signature from function AST node.

        Args:
            func_ast_node: tree-sitter AST node (not IR node!)
            node_id: Function node ID
            func_name: Function name
            param_type_ids: List of parameter type IDs
            get_node_text_fn: Function to extract text
            source_bytes: Source bytes

        Returns:
            SignatureEntity or None
        """
        # Extract return type - look for "-> Type" pattern
        return_type_id = None

        # tree-sitter node has .children attribute
        if hasattr(func_ast_node, "children"):
            for child in func_ast_node.children:
                # Look for type annotation after ->
                if child.type in ["type", "type_annotation"]:
                    raw_return_type = get_node_text_fn(child, source_bytes)
                    if raw_return_type:
                        return_type_entity = self._type_resolver.resolve_type(raw_return_type)
                        if return_type_entity and self._types is not None:
                            self._types[return_type_entity.id] = return_type_entity
                            return_type_id = return_type_entity.id
                        break

        # Build signature string
        param_type_strs = []
        for type_id in param_type_ids:
            type_entity = self._types.get(type_id)
            if type_entity:
                param_type_strs.append(type_entity.raw)

        return_type_str = ""
        if return_type_id:
            ret_type_entity = self._types.get(return_type_id)
            if ret_type_entity:
                return_type_str = f" -> {ret_type_entity.raw}"

        raw_signature = f"({', '.join(param_type_strs)}){return_type_str}"

        # Generate signature ID
        return_type_raw = None
        if return_type_id:
            ret_type_ent = self._types.get(return_type_id)
            if ret_type_ent:
                return_type_raw = ret_type_ent.raw

        sig_id = generate_signature_id(
            owner_node_id=node_id,
            name=func_name,
            param_types=param_type_strs,
            return_type=return_type_raw,
        )

        # Generate hash
        import hashlib

        sig_hash = hashlib.sha256(raw_signature.encode()).hexdigest()[:16]

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

    def process_parameters(
        self,
        func_ast_node,  # tree-sitter AST node
        function_id: str,
        get_node_text_fn,
        source_bytes: bytes,
    ) -> list[str]:
        """
        Process parameters and return type IDs.

        Args:
            func_ast_node: tree-sitter AST node (not IR node!)
            function_id: Function node ID
            get_node_text_fn: Text extraction function
            source_bytes: Source bytes

        Returns:
            List of parameter type IDs
        """
        param_type_ids = []

        # Find parameters node
        params_node = None
        if hasattr(func_ast_node, "children"):
            for child in func_ast_node.children:
                if child.type == "parameters":
                    params_node = child
                    break

        if not params_node:
            return param_type_ids

        # Process each parameter
        for param in params_node.children:
            if param.type not in ["identifier", "typed_parameter", "default_parameter"]:
                continue

            # Get type annotation if present
            type_annotation = None
            for child in param.children if hasattr(param, "children") else []:
                if child.type == "type":
                    type_annotation = child
                    break

            if type_annotation:
                raw_type = get_node_text_fn(type_annotation, source_bytes)
                if raw_type:
                    type_entity = self._type_resolver.resolve_type(raw_type)
                    if type_entity and self._types is not None:
                        self._types[type_entity.id] = type_entity
                        param_type_ids.append(type_entity.id)

        return param_type_ids
