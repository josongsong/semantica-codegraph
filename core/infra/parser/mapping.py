"""
AST Node Type Mapping

Maps language-specific AST node types to unified node types and attributes.
"""

from enum import Enum
from typing import Any


class UnifiedNodeType(str, Enum):
    """Unified node types across all languages."""

    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    INTERFACE = "interface"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    ENUM = "enum"
    TYPE_ALIAS = "type_alias"
    IMPORT = "import"


class ASTNodeMapper:
    """
    Maps language-specific AST node types to unified types.

    Provides extensible mapping tables for different languages.
    """

    # Python AST → Unified mapping
    PYTHON_NODE_MAP: dict[str, str] = {
        "module": UnifiedNodeType.FILE,
        "class_definition": UnifiedNodeType.CLASS,
        "function_definition": UnifiedNodeType.FUNCTION,
        "async_function_definition": UnifiedNodeType.FUNCTION,
        "import_statement": UnifiedNodeType.IMPORT,
        "import_from_statement": UnifiedNodeType.IMPORT,
    }

    # TypeScript AST → Unified mapping
    TYPESCRIPT_NODE_MAP: dict[str, str] = {
        "program": UnifiedNodeType.FILE,
        "class_declaration": UnifiedNodeType.CLASS,
        "interface_declaration": UnifiedNodeType.INTERFACE,
        "function_declaration": UnifiedNodeType.FUNCTION,
        "method_definition": UnifiedNodeType.METHOD,
        "method_signature": UnifiedNodeType.METHOD,
        "variable_declaration": UnifiedNodeType.VARIABLE,
        "lexical_declaration": UnifiedNodeType.VARIABLE,
        "enum_declaration": UnifiedNodeType.ENUM,
        "type_alias_declaration": UnifiedNodeType.TYPE_ALIAS,
        "import_statement": UnifiedNodeType.IMPORT,
    }

    # JavaScript AST → Unified mapping
    JAVASCRIPT_NODE_MAP: dict[str, str] = {
        "program": UnifiedNodeType.FILE,
        "class_declaration": UnifiedNodeType.CLASS,
        "function_declaration": UnifiedNodeType.FUNCTION,
        "method_definition": UnifiedNodeType.METHOD,
        "variable_declaration": UnifiedNodeType.VARIABLE,
        "lexical_declaration": UnifiedNodeType.VARIABLE,
        "import_statement": UnifiedNodeType.IMPORT,
    }

    @classmethod
    def get_unified_type(cls, language: str, ast_node_type: str) -> str:
        """
        Get unified node type for a language-specific AST node type.

        Args:
            language: Programming language
            ast_node_type: AST node type from tree-sitter

        Returns:
            Unified node type
        """
        language = language.lower()

        if language == "python":
            return cls.PYTHON_NODE_MAP.get(ast_node_type, ast_node_type)
        elif language in ("typescript", "tsx"):
            return cls.TYPESCRIPT_NODE_MAP.get(ast_node_type, ast_node_type)
        elif language in ("javascript", "jsx"):
            return cls.JAVASCRIPT_NODE_MAP.get(ast_node_type, ast_node_type)
        else:
            return ast_node_type

    @classmethod
    def get_default_attrs(cls, language: str, unified_type: str) -> dict[str, Any]:
        """
        Get default attributes for a unified node type.

        Args:
            language: Programming language
            unified_type: Unified node type

        Returns:
            Default attributes dict
        """
        base_attrs: dict[str, Any] = {
            "language": language,
        }

        if unified_type == UnifiedNodeType.FUNCTION:
            base_attrs.update(
                {
                    "is_async": False,
                    "is_generator": False,
                    "visibility": "public",
                }
            )
        elif unified_type == UnifiedNodeType.METHOD:
            base_attrs.update(
                {
                    "is_async": False,
                    "is_static": False,
                    "is_abstract": False,
                    "visibility": "public",
                }
            )
        elif unified_type == UnifiedNodeType.CLASS:
            base_attrs.update(
                {
                    "is_abstract": False,
                    "visibility": "public",
                }
            )

        return base_attrs


# Language-specific attribute extractors
class PythonAttrExtractor:
    """Extract Python-specific attributes."""

    @staticmethod
    def extract_function_attrs(node_info: dict[str, Any]) -> dict[str, Any]:
        """Extract function-specific attributes."""
        return {
            "is_async": node_info.get("is_async", False),
            "decorators": node_info.get("decorators", []),
            "has_self": "self" in node_info.get("parameters", []),
        }


class TypeScriptAttrExtractor:
    """Extract TypeScript-specific attributes."""

    @staticmethod
    def extract_function_attrs(node_info: dict[str, Any]) -> dict[str, Any]:
        """Extract function-specific attributes."""
        return {
            "is_async": node_info.get("is_async", False),
            "is_generator": node_info.get("is_generator", False),
            "access_modifier": node_info.get("access_modifier", "public"),
        }
