"""
Type Resolver

Resolves Python type annotations to TypeEntity.

Resolution levels:
- RAW: Just the raw string
- BUILTIN: Built-in types (int, str, list, dict, etc.)
- LOCAL: Same-file class definitions
- MODULE: Same-package imports
- PROJECT: Whole project (cross-package)
- EXTERNAL: External dependencies (stdlib, third-party)
"""

from typing import TYPE_CHECKING

from src.contexts.code_foundation.infrastructure.ir.id_strategy import generate_type_id
from src.contexts.code_foundation.infrastructure.semantic_ir.typing.models import (
    TypeEntity,
    TypeFlavor,
    TypeResolutionLevel,
)

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.external_analyzers.base import ExternalAnalyzer
    from src.contexts.code_foundation.infrastructure.ir.models import IRDocument


class TypeResolver:
    """
    Resolves Python type annotations.

    Supports:
    - RAW: raw string
    - BUILTIN: int, str, list, dict, etc.
    - LOCAL: classes defined in same file
    - MODULE: classes imported from same package
    - PROJECT: classes from other packages in project
    - EXTERNAL: stdlib and third-party types
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
        "Generator",
        "Coroutine",
        "Awaitable",
        "AsyncIterator",
        "AsyncIterable",
        "Type",
        "TypeVar",
        "Generic",
        "Protocol",
        "Final",
        "Literal",
        "ClassVar",
        "Annotated",
        # Others
        "object",
        "type",
    }

    # Standard library module types (commonly used)
    STDLIB_TYPES = {
        # pathlib
        "Path",
        "PurePath",
        "PosixPath",
        "WindowsPath",
        # datetime
        "datetime",
        "date",
        "time",
        "timedelta",
        "timezone",
        # collections
        "defaultdict",
        "OrderedDict",
        "Counter",
        "deque",
        "namedtuple",
        # abc
        "ABC",
        "ABCMeta",
        # io
        "StringIO",
        "BytesIO",
        "TextIO",
        "BinaryIO",
        # re
        "Pattern",
        "Match",
        # enum
        "Enum",
        "IntEnum",
        "StrEnum",
        "Flag",
        "IntFlag",
        # dataclasses
        "dataclass",
        # contextlib
        "contextmanager",
        "asynccontextmanager",
        # functools
        "partial",
        "wraps",
        # typing_extensions
        "Self",
        "Never",
        "Required",
        "NotRequired",
        "TypedDict",
        "ParamSpec",
        "Concatenate",
        # uuid
        "UUID",
        # decimal
        "Decimal",
        # fractions
        "Fraction",
        # logging
        "Logger",
        # asyncio
        "Task",
        "Future",
        "Event",
        "Lock",
        "Semaphore",
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
        self._module_types: dict[str, str] = {}  # type_name -> node_id (same package)
        self._project_types: dict[str, str] = {}  # fqn -> node_id (cross-package)
        self._import_aliases: dict[str, str] = {}  # alias -> original_name
        self._current_file: str | None = None
        self._current_package: str | None = None

    def set_context(self, file_path: str):
        """
        Set current file context for resolution.

        Args:
            file_path: Current file path (e.g., "src/retriever/service.py")
        """
        self._current_file = file_path
        # Extract package from file path (e.g., "src/retriever" from "src/retriever/service.py")
        if "/" in file_path:
            self._current_package = "/".join(file_path.split("/")[:-1])
        else:
            self._current_package = ""

    def register_local_class(self, class_name: str, node_id: str):
        """
        Register a local class for LOCAL resolution.

        Args:
            class_name: Class name
            node_id: Class node ID
        """
        self._local_classes[class_name] = node_id

    def register_module_type(self, type_name: str, node_id: str, source_file: str):
        """
        Register a type from the same package for MODULE resolution.

        Args:
            type_name: Type/class name
            node_id: Node ID of the type definition
            source_file: File where type is defined
        """
        self._module_types[type_name] = node_id

    def register_project_type(self, fqn: str, node_id: str):
        """
        Register a project-wide type for PROJECT resolution.

        Args:
            fqn: Fully qualified name (e.g., "src.retriever.models.SearchHit")
            node_id: Node ID of the type definition
        """
        self._project_types[fqn] = node_id
        # Also register by simple name for convenience
        simple_name = fqn.split(".")[-1] if "." in fqn else fqn
        if simple_name not in self._project_types:
            self._project_types[simple_name] = node_id

    def register_import_alias(self, alias: str, original: str):
        """
        Register an import alias.

        Args:
            alias: Alias name (e.g., "pd" for pandas)
            original: Original name (e.g., "pandas")
        """
        self._import_aliases[alias] = original

    def build_index_from_ir(self, ir_doc: "IRDocument"):
        """
        Build type resolution index from IR document.

        Extracts all classes and imports for MODULE/PROJECT resolution.

        Args:
            ir_doc: IR document with nodes and edges
        """
        from src.contexts.code_foundation.infrastructure.ir.models import EdgeKind, NodeKind

        # Index all classes by file
        classes_by_file: dict[str, list[tuple[str, str]]] = {}  # file -> [(name, node_id)]

        for node in ir_doc.nodes:
            if node.kind == NodeKind.CLASS:
                file_path = node.file_path
                if file_path not in classes_by_file:
                    classes_by_file[file_path] = []
                classes_by_file[file_path].append((node.name or "", node.id))

                # Register for project-wide resolution
                if node.fqn:
                    self.register_project_type(node.fqn, node.id)

        # Process imports to build module-level type index
        for edge in ir_doc.edges:
            if edge.kind == EdgeKind.IMPORTS:
                # edge.source_id = importer file/module
                # edge.target_id = imported symbol
                target_node = next((n for n in ir_doc.nodes if n.id == edge.target_id), None)
                if target_node and target_node.kind == NodeKind.CLASS:
                    # Get the importing file's package
                    source_node = next((n for n in ir_doc.nodes if n.id == edge.source_id), None)
                    if source_node:
                        source_package = self._get_package(source_node.file_path)
                        target_package = self._get_package(target_node.file_path)

                        # Same package = MODULE level
                        if source_package == target_package:
                            self.register_module_type(target_node.name or "", target_node.id, target_node.file_path)

                    # Check for alias in edge attrs
                    alias = edge.attrs.get("alias") if edge.attrs else None
                    if alias and target_node.name:
                        self.register_import_alias(alias, target_node.name)

    def _get_package(self, file_path: str) -> str:
        """
        Extract package path from file path.

        Args:
            file_path: File path (e.g., "src/retriever/service.py")

        Returns:
            Package path (e.g., "src/retriever")
        """
        if "/" in file_path:
            return "/".join(file_path.split("/")[:-1])
        return ""

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

        Resolution priority (highest to lowest):
        1. BUILTIN: Python built-in types
        2. LOCAL: Same-file class definitions
        3. MODULE: Same-package imports
        4. PROJECT: Cross-package project types
        5. EXTERNAL: stdlib types (known)
        6. RAW: Unresolved (unknown external)

        Args:
            type_str: Type string

        Returns:
            (flavor, resolution_level, resolved_target)
        """
        # Extract base type (before '[')
        base_type = type_str.split("[")[0].strip()

        # Resolve alias if exists
        if base_type in self._import_aliases:
            base_type = self._import_aliases[base_type]

        # 1. Check if builtin
        if base_type in self.BUILTIN_TYPES:
            return TypeFlavor.BUILTIN, TypeResolutionLevel.BUILTIN, None

        # 2. Check if local class (same file)
        if base_type in self._local_classes:
            return (
                TypeFlavor.USER,
                TypeResolutionLevel.LOCAL,
                self._local_classes[base_type],
            )

        # 3. Check if module type (same package)
        if base_type in self._module_types:
            return (
                TypeFlavor.USER,
                TypeResolutionLevel.MODULE,
                self._module_types[base_type],
            )

        # 4. Check if project type (cross-package)
        if base_type in self._project_types:
            return (
                TypeFlavor.USER,
                TypeResolutionLevel.PROJECT,
                self._project_types[base_type],
            )

        # 5. Check for qualified name in project types (e.g., "models.SearchHit")
        if "." in base_type:
            # Try to find by qualified name
            for fqn, node_id in self._project_types.items():
                if fqn.endswith(base_type) or base_type.endswith(fqn.split(".")[-1]):
                    return (
                        TypeFlavor.USER,
                        TypeResolutionLevel.PROJECT,
                        node_id,
                    )

        # 6. Check if stdlib type (known external)
        if base_type in self.STDLIB_TYPES:
            return TypeFlavor.EXTERNAL, TypeResolutionLevel.EXTERNAL, None

        # 7. Default: unresolved external
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

        # Check if closing bracket exists
        if "]" not in type_str:
            # Malformed type string, return empty
            return []

        end = type_str.rindex("]")
        params_str = type_str[start + 1 : end]

        # Split by comma, considering nested brackets
        params = self._split_params(params_str)

        # Recursively resolve each parameter
        param_ids = []
        for param in params:
            if param:
                param_entity = self.resolve_type(param)
                param_ids.append(param_entity.id)

        return param_ids

    def _split_params(self, params_str: str) -> list[str]:
        """
        Split type parameters by comma, respecting nested brackets.

        Args:
            params_str: Parameter string (e.g., "str, int" or "tuple[str, str], int")

        Returns:
            List of parameter strings
        """
        params = []
        current = []
        depth = 0

        for char in params_str:
            if char == "[":
                depth += 1
                current.append(char)
            elif char == "]":
                depth -= 1
                current.append(char)
            elif char == "," and depth == 0:
                # Top-level comma, split here
                param = "".join(current).strip()
                if param:
                    params.append(param)
                current = []
            else:
                current.append(char)

        # Add last parameter
        param = "".join(current).strip()
        if param:
            params.append(param)

        return params
