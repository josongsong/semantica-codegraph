"""
Tree-sitter Python Parser

Implements Python-specific parsing logic using Tree-sitter.
"""

from typing import List, Optional, Dict, Any, Set

import tree_sitter_python as tspython
from tree_sitter import Node

from core.core.ports.parser_port import ParsedFileInput, CodeNode
from .tree_sitter_base import TreeSitterParserBase


class TreeSitterPythonParser(TreeSitterParserBase):
    """
    Python parser using Tree-sitter.

    Extracts functions, classes, methods, and their metadata from Python code.
    """

    LANGUAGE = "python"
    TREE_SITTER_LANGUAGE = tspython.language()

    # Node types to extract
    INTERESTING_NODE_TYPES = {
        "module",
        "class_definition",
        "function_definition",
        "async_function_definition",
    }

    def _extract_nodes(
        self,
        root_node: Node,
        file_input: ParsedFileInput
    ) -> List[CodeNode]:
        """
        Extract code nodes from Python AST.

        Args:
            root_node: Tree-sitter root node
            file_input: File input

        Returns:
            List of extracted code nodes
        """
        nodes: List[CodeNode] = []

        # Create file-level node
        file_node = self._create_file_node(root_node, file_input)
        nodes.append(file_node)

        # Traverse and extract nodes
        self._traverse_and_extract(
            root_node,
            file_input,
            nodes,
            parent_id=file_node.node_id,
            current_class=None,
        )

        return nodes

    def _create_file_node(
        self,
        root_node: Node,
        file_input: ParsedFileInput
    ) -> CodeNode:
        """Create a file-level node."""
        return self._create_code_node(
            node=root_node,
            file_input=file_input,
            node_type="file",
            name=file_input.file_path.name,
            parent_id=None,
            attrs={
                "language": "python",
                "file_path": str(file_input.file_path),
            },
        )

    def _traverse_and_extract(
        self,
        node: Node,
        file_input: ParsedFileInput,
        nodes: List[CodeNode],
        parent_id: str,
        current_class: Optional[str] = None,
    ) -> None:
        """
        Traverse AST and extract interesting nodes.

        Args:
            node: Current node
            file_input: File input
            nodes: List to append extracted nodes
            parent_id: Parent node ID
            current_class: Current class name (for method context)
        """
        # Handle class definitions
        if node.type == "class_definition":
            class_node = self._extract_class(node, file_input, parent_id)
            if class_node:
                nodes.append(class_node)
                # Traverse class body
                for child in node.children:
                    self._traverse_and_extract(
                        child,
                        file_input,
                        nodes,
                        parent_id=class_node.node_id,
                        current_class=class_node.name,
                    )
                return  # Don't traverse children again

        # Handle function/method definitions
        elif node.type in ("function_definition", "async_function_definition"):
            func_node = self._extract_function(
                node,
                file_input,
                parent_id,
                is_method=(current_class is not None),
                is_async=(node.type == "async_function_definition"),
            )
            if func_node:
                nodes.append(func_node)
                # Don't traverse function body (avoid nested functions for now)
                return

        # Continue traversing
        for child in node.children:
            self._traverse_and_extract(
                child,
                file_input,
                nodes,
                parent_id,
                current_class,
            )

    def _extract_class(
        self,
        node: Node,
        file_input: ParsedFileInput,
        parent_id: str,
    ) -> Optional[CodeNode]:
        """
        Extract class definition.

        Args:
            node: Class definition node
            file_input: File input
            parent_id: Parent node ID

        Returns:
            CodeNode or None
        """
        name = self._extract_name_from_node(node, file_input.content)
        if not name:
            return None

        # Extract attributes
        attrs: Dict[str, Any] = {}

        # Decorators
        if self.config.extract_decorators:
            attrs["decorators"] = self._extract_decorators(node, file_input.content)

        # Docstring
        if self.config.extract_docstrings:
            attrs["docstring"] = self._extract_docstring(node, file_input.content)

        # Base classes
        attrs["bases"] = self._extract_base_classes(node, file_input.content)

        return self._create_code_node(
            node=node,
            file_input=file_input,
            node_type="class",
            name=name,
            parent_id=parent_id,
            attrs=attrs,
        )

    def _extract_function(
        self,
        node: Node,
        file_input: ParsedFileInput,
        parent_id: str,
        is_method: bool = False,
        is_async: bool = False,
    ) -> Optional[CodeNode]:
        """
        Extract function/method definition.

        Args:
            node: Function definition node
            file_input: File input
            parent_id: Parent node ID
            is_method: Whether this is a method
            is_async: Whether this is an async function

        Returns:
            CodeNode or None
        """
        name = self._extract_name_from_node(node, file_input.content)
        if not name:
            return None

        node_type = "method" if is_method else "function"

        # Extract attributes
        attrs: Dict[str, Any] = {
            "is_async": is_async,
            "is_method": is_method,
        }

        # Decorators
        if self.config.extract_decorators:
            attrs["decorators"] = self._extract_decorators(node, file_input.content)

        # Docstring
        if self.config.extract_docstrings:
            attrs["docstring"] = self._extract_docstring(node, file_input.content)

        # Signature
        attrs["signature"] = self._extract_signature(node, file_input.content)

        # Parameters
        attrs["parameters"] = self._extract_parameters(node, file_input.content)

        # Return type (if type hints enabled)
        if self.config.extract_type_hints:
            attrs["return_type"] = self._extract_return_type(node, file_input.content)

        # Visibility
        attrs["visibility"] = self._infer_visibility(name)

        return self._create_code_node(
            node=node,
            file_input=file_input,
            node_type=node_type,
            name=name,
            parent_id=parent_id,
            attrs=attrs,
        )

    def _extract_decorators(self, node: Node, source_code: str) -> List[str]:
        """Extract decorators from a node."""
        decorators = []
        for child in node.children:
            if child.type == "decorator":
                decorator_text = self._get_node_text(child, source_code)
                decorators.append(decorator_text)
        return decorators

    def _extract_docstring(self, node: Node, source_code: str) -> Optional[str]:
        """Extract docstring from a node."""
        # Look for expression_statement with string as first child in body
        for child in node.children:
            if child.type == "block":
                for stmt in child.children:
                    if stmt.type == "expression_statement":
                        for expr_child in stmt.children:
                            if expr_child.type == "string":
                                return self._get_node_text(expr_child, source_code).strip('"\'')
                break
        return None

    def _extract_base_classes(self, node: Node, source_code: str) -> List[str]:
        """Extract base classes from a class definition."""
        bases = []
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type in ("identifier", "attribute"):
                        bases.append(self._get_node_text(arg, source_code))
        return bases

    def _extract_signature(self, node: Node, source_code: str) -> str:
        """Extract function signature."""
        # Find parameters node
        for child in node.children:
            if child.type == "parameters":
                params_text = self._get_node_text(child, source_code)
                name = self._extract_name_from_node(node, source_code)

                # Add return type if available
                return_type = self._extract_return_type(node, source_code)
                if return_type:
                    return f"{name}{params_text} -> {return_type}"
                return f"{name}{params_text}"

        return ""

    def _extract_parameters(self, node: Node, source_code: str) -> List[Dict[str, Any]]:
        """Extract function parameters."""
        params = []
        for child in node.children:
            if child.type == "parameters":
                for param_node in child.children:
                    if param_node.type in ("identifier", "typed_parameter", "default_parameter"):
                        param_info = self._parse_parameter(param_node, source_code)
                        if param_info:
                            params.append(param_info)
        return params

    def _parse_parameter(self, param_node: Node, source_code: str) -> Optional[Dict[str, Any]]:
        """Parse a single parameter node."""
        param_text = self._get_node_text(param_node, source_code)

        param_info: Dict[str, Any] = {
            "name": "",
            "type": None,
            "default": None,
        }

        # Simple identifier
        if param_node.type == "identifier":
            param_info["name"] = param_text
            return param_info

        # Extract name and type
        for child in param_node.children:
            if child.type == "identifier":
                param_info["name"] = self._get_node_text(child, source_code)
            elif child.type == "type":
                param_info["type"] = self._get_node_text(child, source_code)

        return param_info if param_info["name"] else None

    def _extract_return_type(self, node: Node, source_code: str) -> Optional[str]:
        """Extract return type annotation."""
        for child in node.children:
            if child.type == "type":
                return self._get_node_text(child, source_code)
        return None

    def _infer_visibility(self, name: str) -> str:
        """Infer visibility from name."""
        if name.startswith("__") and not name.endswith("__"):
            return "private"
        elif name.startswith("_"):
            return "protected"
        else:
            return "public"