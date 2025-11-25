"""
Type Resolver

Resolves Python type annotations to TypeEntity.

Resolution levels:
- RAW: Just the raw string
- BUILTIN: Built-in types (int, str, list, dict, etc.)
- LOCAL: Same-file class definitions
- MODULE: Same-package imports (future)
- PROJECT: Whole project (future)
- EXTERNAL: External dependencies (future)
"""

from typing import TYPE_CHECKING

from ...ir.id_strategy import generate_type_id
from .models import TypeEntity, TypeFlavor, TypeResolutionLevel

if TYPE_CHECKING:
    from ...ir.external_analyzers.base import ExternalAnalyzer


class TypeResolver:
    """
    Resolves Python type annotations.

    Currently supports:
    - RAW: raw string
    - BUILTIN: int, str, list, dict, etc.
    - LOCAL: classes defined in same file
    """

    # Built-in types
    BUILTIN_TYPES = {
        # Python primitives
        "int",
        "str",
        "float",
        "bool",
        "bytes",
        "None",
        # Collections
        "list",
        "List",
        "dict",
        "Dict",
        "set",
        "Set",
        "tuple",
        "Tuple",
        "frozenset",
        # Typing module
        "Any",
        "Optional",
        "Union",
        "Callable",
        "Iterable",
        "Iterator",
        "Sequence",
        # Others
        "object",
        "type",
    }

    def __init__(self, repo_id: str, external_analyzer: "ExternalAnalyzer | None" = None):
        """
        Initialize type resolver.

        Args:
            repo_id: Repository identifier
            external_analyzer: Optional external type checker (Pyright/Mypy)
        """
        self.repo_id = repo_id
        self.external_analyzer = external_analyzer
        self._local_classes: dict[str, str] = {}  # class_name -> node_id

    def register_local_class(self, class_name: str, node_id: str):
        """
        Register a local class for LOCAL resolution.

        Args:
            class_name: Class name
            node_id: Class node ID
        """
        self._local_classes[class_name] = node_id

    def resolve_type(self, raw_type: str) -> TypeEntity:
        """
        Resolve type annotation to TypeEntity.

        Args:
            raw_type: Raw type string (e.g., "List[str]", "int", "MyClass")

        Returns:
            TypeEntity
        """
        # Normalize
        normalized = raw_type.strip()

        # Generate type ID
        type_id = generate_type_id(normalized, self.repo_id)

        # Determine flavor and resolution level
        flavor, resolution_level, resolved_target = self._classify_type(normalized)

        # Parse generic parameters
        generic_param_ids = self._extract_generic_params(normalized)

        return TypeEntity(
            id=type_id,
            raw=normalized,
            flavor=flavor,
            is_nullable=self._is_nullable(normalized),
            resolution_level=resolution_level,
            resolved_target=resolved_target,
            generic_param_ids=generic_param_ids,
        )

    def _classify_type(self, type_str: str) -> tuple[TypeFlavor, TypeResolutionLevel, str | None]:
        """
        Classify type into flavor and resolution level.

        Args:
            type_str: Type string

        Returns:
            (flavor, resolution_level, resolved_target)
        """
        # Extract base type (before '[')
        base_type = type_str.split("[")[0].strip()

        # Check if builtin
        if base_type in self.BUILTIN_TYPES:
            return TypeFlavor.BUILTIN, TypeResolutionLevel.BUILTIN, None

        # Check if local class
        if base_type in self._local_classes:
            return (
                TypeFlavor.USER,
                TypeResolutionLevel.LOCAL,
                self._local_classes[base_type],
            )

        # Default: external (unresolved)
        return TypeFlavor.EXTERNAL, TypeResolutionLevel.RAW, None

    def _is_nullable(self, type_str: str) -> bool:
        """
        Check if type is nullable (Optional or Union with None).

        Args:
            type_str: Type string

        Returns:
            True if nullable
        """
        return "Optional[" in type_str or "| None" in type_str or "None |" in type_str

    def _extract_generic_params(self, type_str: str) -> list[str]:
        """
        Extract generic type parameters.

        Args:
            type_str: Type string (e.g., "List[str]", "Dict[str, int]")

        Returns:
            List of TypeEntity IDs for generic parameters
        """
        # Simple extraction (doesn't handle nested generics perfectly)
        if "[" not in type_str:
            return []

        # Extract content between first '[' and last ']'
        start = type_str.index("[")
        end = type_str.rindex("]")
        params_str = type_str[start + 1 : end]

        # Split by comma (simple approach)
        params = [p.strip() for p in params_str.split(",")]

        # Recursively resolve each parameter
        param_ids = []
        for param in params:
            if param:
                param_entity = self.resolve_type(param)
                param_ids.append(param_entity.id)

        return param_ids
