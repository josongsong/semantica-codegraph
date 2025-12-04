"""
Pyright External Analyzer Adapter

Adapter that wraps PyrightSemanticDaemon to implement the ExternalAnalyzer protocol.

This allows seamless integration with SemanticIrBuilder without modifying
the existing PyrightSemanticDaemon API.

Features:
- Symbol type analysis
- Union type decomposition
- Type narrowing detection (isinstance, TypeGuard)
- Definition/Reference resolution
"""

import re
from pathlib import Path

from src.contexts.code_foundation.infrastructure.ir.external_analyzers.base import (
    Location,
    NarrowingContext,
    NarrowingKind,
    TypeInfo,
)
from src.contexts.code_foundation.infrastructure.ir.external_analyzers.pyright_daemon import PyrightSemanticDaemon
from src.contexts.code_foundation.infrastructure.ir.external_analyzers.pyright_lsp import PyrightLSPClient

# Patterns for Union type parsing
UNION_PATTERN = re.compile(r"^(.+?)\s*\|\s*(.+)$")  # A | B
UNION_BRACKET_PATTERN = re.compile(r"^Union\[(.+)\]$")  # Union[A, B, C]
OPTIONAL_PATTERN = re.compile(r"^Optional\[(.+)\]$")  # Optional[A] = A | None
TYPE_GUARD_PATTERN = re.compile(r"TypeGuard\[(.+)\]")  # TypeGuard[T]


def parse_union_type(type_str: str) -> tuple[bool, list[str]]:
    """
    Parse a type string and extract Union variants.

    Args:
        type_str: Type string (e.g., "int | str | None", "Union[int, str]", "Optional[str]")

    Returns:
        Tuple of (is_union, variants list)

    Examples:
        "int | str" -> (True, ["int", "str"])
        "Optional[str]" -> (True, ["str", "None"])
        "Union[int, str, None]" -> (True, ["int", "str", "None"])
        "int" -> (False, [])
    """
    if not type_str:
        return False, []

    type_str = type_str.strip()

    # Check for Optional[T] -> T | None
    optional_match = OPTIONAL_PATTERN.match(type_str)
    if optional_match:
        inner_type = optional_match.group(1).strip()
        # Recursively parse inner type in case it's also a Union
        is_inner_union, inner_variants = parse_union_type(inner_type)
        if is_inner_union:
            return True, inner_variants + ["None"]
        return True, [inner_type, "None"]

    # Check for Union[A, B, C]
    union_bracket_match = UNION_BRACKET_PATTERN.match(type_str)
    if union_bracket_match:
        inner = union_bracket_match.group(1)
        # Split by comma, but handle nested brackets
        variants = _split_union_args(inner)
        return True, [v.strip() for v in variants]

    # Check for A | B | C (PEP 604 style)
    if " | " in type_str:
        # Split by |, handling nested types
        variants = _split_pipe_union(type_str)
        if len(variants) > 1:
            return True, variants

    return False, []


def _split_union_args(args_str: str) -> list[str]:
    """Split Union arguments, respecting nested brackets."""
    result = []
    current = []
    depth = 0

    for char in args_str:
        if char == "[":
            depth += 1
            current.append(char)
        elif char == "]":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            result.append("".join(current).strip())
            current = []
        else:
            current.append(char)

    if current:
        result.append("".join(current).strip())

    return result


def _split_pipe_union(type_str: str) -> list[str]:
    """Split pipe-style union (A | B | C), respecting nested brackets."""
    result = []
    current = []
    depth = 0
    i = 0

    while i < len(type_str):
        char = type_str[i]

        if char == "[":
            depth += 1
            current.append(char)
        elif char == "]":
            depth -= 1
            current.append(char)
        elif char == "|" and depth == 0:
            # Check if it's " | " (with spaces)
            if i > 0 and i < len(type_str) - 1:
                result.append("".join(current).strip())
                current = []
                # Skip the space after |
                if i + 1 < len(type_str) and type_str[i + 1] == " ":
                    i += 1
            else:
                current.append(char)
        else:
            current.append(char)
        i += 1

    if current:
        result.append("".join(current).strip())

    return result


def detect_narrowing_kind(type_str: str, hover_text: str | None = None) -> NarrowingKind | None:
    """
    Detect the kind of type narrowing from context.

    Args:
        type_str: The narrowed type string
        hover_text: Full hover text from LSP (may contain narrowing hints)

    Returns:
        NarrowingKind if narrowing detected, None otherwise
    """
    if not hover_text:
        return None

    hover_lower = hover_text.lower()

    # TypeGuard detection
    if "typeguard" in hover_lower:
        return NarrowingKind.TYPE_GUARD

    # isinstance narrowing is often indicated in hover
    if "isinstance" in hover_lower or "(narrowed)" in hover_lower:
        return NarrowingKind.ISINSTANCE

    # None check
    if "is none" in hover_lower or "is not none" in hover_lower:
        return NarrowingKind.IDENTITY

    # Truthiness check
    if "truthy" in hover_lower or "falsy" in hover_lower:
        return NarrowingKind.TRUTHINESS

    return None


class PyrightExternalAnalyzer:
    """
    Adapter: PyrightSemanticDaemon → ExternalAnalyzer protocol.

    Wraps PyrightSemanticDaemon to provide the ExternalAnalyzer interface
    required by SemanticIrBuilder.

    Design:
        - Uses PyrightLSPClient for symbol-level queries
        - Uses PyrightSemanticDaemon for snapshot-based analysis
        - Implements ExternalAnalyzer protocol methods

    Usage:
        # Initialize
        analyzer = PyrightExternalAnalyzer(project_root)

        # Open file
        analyzer.open_file(Path("main.py"), code)

        # Analyze symbol
        type_info = analyzer.analyze_symbol(Path("main.py"), 10, 5)

        # Analyze entire file (with IR-provided locations)
        locations = [(10, 5), (15, 0), (20, 4)]
        type_infos = analyzer.analyze_file_locations(
            Path("main.py"), locations
        )

        # Clean up
        analyzer.shutdown()
    """

    def __init__(self, project_root: Path):
        """
        Initialize Pyright adapter.

        Args:
            project_root: Root directory of the project

        Raises:
            RuntimeError: If pyright-langserver not found
        """
        # Initialize daemon (for snapshot-based analysis)
        self._daemon = PyrightSemanticDaemon(project_root)

        # Direct access to LSP client (for single queries)
        self._lsp_client: PyrightLSPClient = self._daemon._lsp_client

        self.project_root = project_root

    # ============================================================
    # File Management
    # ============================================================

    def open_file(self, file_path: Path, content: str) -> None:
        """
        Open a file in Pyright LSP.

        Args:
            file_path: Path to file
            content: File content

        Note:
            This is required before calling analyze_file() or analyze_symbol().
        """
        self._daemon.open_file(file_path, content)

    def open_files(self, files: list[tuple[Path, str]]) -> None:
        """
        Open multiple files in Pyright LSP.

        Args:
            files: List of (file_path, content) tuples
        """
        self._daemon.open_files(files)

    # ============================================================
    # ExternalAnalyzer Protocol Implementation
    # ============================================================

    def analyze_file(self, file_path: Path) -> list[TypeInfo]:
        """
        Analyze a single file and extract type information.

        ⚠️ IMPORTANT: This method requires IR-provided locations.
        Use analyze_file_locations() instead for better performance.

        Args:
            file_path: Path to source file

        Returns:
            List of type information for symbols in the file

        Note:
            Without IR locations, this would be O(N^2) blind scan.
            Prefer analyze_file_locations() with IR-extracted locations.
        """
        # This is a placeholder - callers should use analyze_file_locations()
        # with IR-provided locations to avoid N^2 blind scanning
        return []

    def analyze_file_locations(self, file_path: Path, locations: list[tuple[int, int]]) -> list[TypeInfo]:
        """
        Analyze specific locations in a file (IR-provided).

        This is the recommended method - uses IR locations to avoid O(N^2).

        Args:
            file_path: Path to source file
            locations: List of (line, col) tuples from IR
                      line: 1-indexed, col: 0-indexed

        Returns:
            List of type information for queried locations

        Performance:
            O(N) where N = len(locations), NOT O(file_size)
        """
        type_infos = []

        for line, col in locations:
            type_info = self.analyze_symbol(file_path, line, col)
            if type_info:
                type_infos.append(type_info)

        return type_infos

    def analyze_symbol(
        self,
        file_path: Path,
        line: int,
        column: int,
        declared_type: str | None = None,
    ) -> TypeInfo | None:
        """
        Analyze a specific symbol at a location.

        Args:
            file_path: Path to source file
            line: Line number (1-indexed)
            column: Column number (0-indexed)
            declared_type: Optional declared type for narrowing detection

        Returns:
            Type information with Union decomposition and narrowing context

        Example:
            type_info = analyzer.analyze_symbol(Path("main.py"), 10, 5)
            if type_info:
                print(f"Type: {type_info.inferred_type}")
                if type_info.is_union:
                    print(f"Union variants: {type_info.union_variants}")
                if type_info.is_narrowed():
                    print(f"Narrowed from: {type_info.narrowing_context.original_type}")
        """
        # Normalize path
        if not file_path.is_absolute():
            file_path = self.project_root / file_path

        # Query LSP hover
        hover_result = self._lsp_client.hover(file_path, line, column)

        if not hover_result or not hover_result.get("type"):
            return None

        # Extract symbol name from hover result
        symbol_name = hover_result.get("symbol_name", "unknown")
        type_str = hover_result["type"]
        hover_text = hover_result.get("contents", "")

        # Parse Union type
        is_union, union_variants = parse_union_type(type_str)

        # Detect narrowing (if declared type differs from inferred)
        narrowing_context = None
        type_guard_func = None

        if declared_type and declared_type != type_str:
            # Check if this is a narrowing situation
            is_declared_union, declared_variants = parse_union_type(declared_type)

            if is_declared_union:
                # The declared type is a Union, but inferred is narrower
                narrowing_kind = detect_narrowing_kind(type_str, hover_text)

                if narrowing_kind:
                    narrowing_context = NarrowingContext(
                        original_type=declared_type,
                        narrowed_type=type_str,
                        narrowing_kind=narrowing_kind,
                        guard_types=[type_str] if not is_union else union_variants,
                    )

        # Check for TypeGuard in return type
        type_guard_match = TYPE_GUARD_PATTERN.search(type_str)
        if type_guard_match:
            # Store function name with guarded type info
            guarded_type = type_guard_match.group(1)
            type_guard_func = f"{symbol_name}[{guarded_type}]"
            # TypeGuard functions don't produce union variants
            if not is_union:
                is_union, union_variants = False, []

        # Detect builtin types
        is_builtin = self._is_builtin_type(type_str)

        # Create TypeInfo with Union and narrowing support
        return TypeInfo(
            symbol_name=symbol_name,
            file_path=str(file_path),
            line=line,
            column=column,
            inferred_type=type_str,
            declared_type=declared_type or type_str,
            is_builtin=is_builtin,
            is_union=is_union,
            union_variants=union_variants,
            narrowing_context=narrowing_context,
            type_guard_function=type_guard_func,
        )

    def _is_builtin_type(self, type_str: str) -> bool:
        """Check if type is a Python builtin."""
        builtins = {
            "int",
            "str",
            "float",
            "bool",
            "bytes",
            "bytearray",
            "list",
            "dict",
            "set",
            "frozenset",
            "tuple",
            "None",
            "NoneType",
            "type",
            "object",
            "complex",
            "range",
            "slice",
            "memoryview",
        }

        # Check base type (before [])
        base_type = type_str.split("[")[0].strip()
        return base_type in builtins

    def get_definition(self, file_path: Path, line: int, column: int) -> Location | None:
        """
        Get definition location for a symbol (LSP: textDocument/definition).

        Args:
            file_path: Path to source file
            line: Line number (1-indexed)
            column: Column number (0-indexed)

        Returns:
            Definition location or None if not found

        Example:
            location = analyzer.get_definition(Path("main.py"), 15, 5)
            if location:
                print(f"Defined at {location.file_path}:{location.line}")
        """
        # Normalize path
        if not file_path.is_absolute():
            file_path = self.project_root / file_path

        # Query LSP definition
        definition = self._lsp_client.definition(file_path, line, column)

        if not definition:
            return None

        # Convert BaseLocation to Location
        # definition is already a BaseLocation (Location) object
        return Location(
            file_path=str(definition.file_path),
            line=definition.line,
            column=definition.column,
            end_line=definition.end_line,
            end_column=definition.end_column,
        )

    def get_references(self, file_path: Path, line: int, column: int) -> list[Location]:
        """
        Get all reference locations for a symbol (LSP: textDocument/references).

        Args:
            file_path: Path to source file where symbol is defined
            line: Line number (1-indexed)
            column: Column number (0-indexed)

        Returns:
            List of reference locations (may be empty)

        Example:
            refs = analyzer.get_references(Path("main.py"), 10, 5)
            print(f"Found {len(refs)} references")
        """
        # Normalize path
        if not file_path.is_absolute():
            file_path = self.project_root / file_path

        # Query LSP references
        references = self._lsp_client.references(file_path, line, column)

        if not references:
            return []

        # Convert BaseLocation objects to Location objects
        # references is already a list of BaseLocation (Location) objects
        locations = []
        for ref in references:
            location = Location(
                file_path=str(ref.file_path),
                line=ref.line,
                column=ref.column,
                end_line=ref.end_line if hasattr(ref, "end_line") else None,
                end_column=ref.end_column if hasattr(ref, "end_column") else None,
            )
            locations.append(location)

        return locations

    def shutdown(self):
        """
        Clean up resources (stop LSP server).

        Always call this when done to properly terminate pyright-langserver.
        """
        self._daemon.shutdown()

    # ============================================================
    # Additional Methods (Non-Protocol)
    # ============================================================

    def export_semantic_for_locations(self, file_path: Path, locations: list[tuple[int, int]]):
        """
        Export semantic snapshot for specific locations.

        This is a direct passthrough to PyrightSemanticDaemon for
        snapshot-based workflows.

        Args:
            file_path: Path to file
            locations: List of (line, col) tuples

        Returns:
            PyrightSemanticSnapshot

        Note:
            For integration with SemanticIrBuilder, use analyze_symbol()
            or analyze_file_locations() instead.
        """
        return self._daemon.export_semantic_for_locations(file_path, locations)

    async def export_semantic_for_locations_async(self, file_path: Path, locations: list[tuple[int, int]]):
        """
        Export semantic snapshot for specific locations (async/parallel).

        Args:
            file_path: Path to file
            locations: List of (line, col) tuples

        Returns:
            PyrightSemanticSnapshot

        Performance:
            5-10x faster than sync version (M2.3 parallel hover)
        """
        return await self._daemon.export_semantic_for_locations_async(file_path, locations)

    def export_semantic_for_files(self, file_locations: dict[Path, list[tuple[int, int]]]):
        """
        Export semantic snapshot for multiple files.

        RFC-023 M0: Batch export for all files in a project.

        Args:
            file_locations: Dict mapping file paths to list of (line, col) tuples

        Returns:
            PyrightSemanticSnapshot with type information for all files

        Note:
            For orchestrator integration (full project analysis).
        """
        return self._daemon.export_semantic_for_files(file_locations)

    def export_semantic_incremental(
        self,
        changed_files: dict[Path, list[tuple[int, int]]],
        previous_snapshot,
        deleted_files: list[Path] | None = None,
    ):
        """
        Export semantic snapshot incrementally (only changed files).

        RFC-023 M2: Incremental update for changed files.

        Args:
            changed_files: Dict mapping changed file paths to locations
            previous_snapshot: Previous PyrightSemanticSnapshot
            deleted_files: List of deleted file paths (optional)

        Returns:
            New PyrightSemanticSnapshot with merged changes

        Performance:
            200x faster for small changes (100 files → 1 file: 100s → 500ms)

        Note:
            For orchestrator integration (incremental indexing).
        """
        return self._daemon.export_semantic_incremental(
            changed_files=changed_files,
            previous_snapshot=previous_snapshot,
            deleted_files=deleted_files,
        )

    def health_check(self) -> dict:
        """
        Get health status of Pyright LSP server.

        Returns:
            Dictionary with status information
        """
        return self._daemon.health_check()
