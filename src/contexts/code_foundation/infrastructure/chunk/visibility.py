"""
Symbol Visibility Extractor

Determines symbol visibility (public/internal/private) based on:
- Language-specific naming conventions
- IR node attributes
- Source code annotations

Supports:
- Python: _private, __dunder
- TypeScript/JavaScript: private, protected, public
- Go: Uppercase = public, lowercase = private
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.models import Node


class VisibilityExtractor:
    """
    Extracts symbol visibility from IR nodes.

    Visibility levels:
    - public: Exported, external API
    - internal: Package/module-internal
    - private: Class/file-private
    """

    @staticmethod
    def extract(node: "Node", language: str | None = None) -> str:
        """
        Extract visibility from node.

        Args:
            node: IR node
            language: Programming language (optional, auto-detect from node)

        Returns:
            Visibility: "public" | "internal" | "private"
        """
        # Use node's language if not specified
        if language is None:
            language = getattr(node, "language", "python")

        # 1. Check explicit attrs (if available from IR)
        if hasattr(node, "attrs") and node.attrs:
            if "visibility" in node.attrs:
                return node.attrs["visibility"]

            # Check for modifiers (TypeScript/Java)
            if "modifiers" in node.attrs:
                modifiers = node.attrs["modifiers"]
                if "private" in modifiers:
                    return "private"
                if "protected" in modifiers:
                    return "internal"
                if "public" in modifiers:
                    return "public"

        # 2. Language-specific inference from name
        name = node.name
        if not name:
            return "public"  # Default

        if language == "python":
            return VisibilityExtractor._extract_python(name)
        elif language in ("typescript", "javascript"):
            return VisibilityExtractor._extract_typescript(name)
        elif language == "go":
            return VisibilityExtractor._extract_go(name)
        else:
            return "public"  # Default for unknown languages

    @staticmethod
    def _extract_python(name: str) -> str:
        """
        Python naming conventions:
        - __name__: Dunder methods (public)
        - __name: Name mangling (private)
        - _name: Internal convention (internal)
        - name: Public
        """
        if name.startswith("__") and name.endswith("__"):
            # Dunder methods are public (__init__, __str__, etc.)
            return "public"
        elif name.startswith("__"):
            # Name mangling: __private_var
            return "private"
        elif name.startswith("_"):
            # Single underscore: _internal
            return "internal"
        else:
            # Public
            return "public"

    @staticmethod
    def _extract_typescript(name: str) -> str:
        """
        TypeScript/JavaScript conventions:
        - #private: Private fields (ES2022)
        - _internal: Convention (internal)
        - name: Public

        Note: Actual private/protected keywords should be in modifiers (checked above)
        """
        if name.startswith("#"):
            # ES2022 private fields
            return "private"
        elif name.startswith("_"):
            # Internal convention
            return "internal"
        else:
            return "public"

    @staticmethod
    def _extract_go(name: str) -> str:
        """
        Go visibility rules:
        - Uppercase first letter: Exported (public)
        - Lowercase first letter: Package-private (internal)
        """
        if not name:
            return "public"

        first_char = name[0]
        if first_char.isupper():
            return "public"
        else:
            return "internal"

    @staticmethod
    def is_public(visibility: str) -> bool:
        """Check if visibility is public"""
        return visibility == "public"

    @staticmethod
    def is_private(visibility: str) -> bool:
        """Check if visibility is private"""
        return visibility == "private"

    @staticmethod
    def is_internal(visibility: str) -> bool:
        """Check if visibility is internal"""
        return visibility == "internal"
