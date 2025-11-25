"""
Pyright External Analyzer Adapter

Adapter that wraps PyrightSemanticDaemon to implement the ExternalAnalyzer protocol.

This allows seamless integration with SemanticIrBuilder without modifying
the existing PyrightSemanticDaemon API.
"""

from pathlib import Path

from .base import Location, TypeInfo
from .pyright_daemon import PyrightSemanticDaemon
from .pyright_lsp import PyrightLSPClient


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

    def analyze_file_locations(
        self, file_path: Path, locations: list[tuple[int, int]]
    ) -> list[TypeInfo]:
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

    def analyze_symbol(self, file_path: Path, line: int, column: int) -> TypeInfo | None:
        """
        Analyze a specific symbol at a location.

        Args:
            file_path: Path to source file
            line: Line number (1-indexed)
            column: Column number (0-indexed)

        Returns:
            Type information or None if not found

        Example:
            type_info = analyzer.analyze_symbol(Path("main.py"), 10, 5)
            if type_info:
                print(f"Type: {type_info.inferred_type}")
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

        # Create TypeInfo
        return TypeInfo(
            symbol_name=symbol_name,
            file_path=str(file_path),
            line=line,
            column=column,
            inferred_type=type_str,
            declared_type=type_str,  # Pyright doesn't distinguish inferred vs declared
            is_builtin=False,  # TODO: Detect builtins
        )

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
        definition = self._lsp_client.goto_definition(file_path, line, column)

        if not definition:
            return None

        # Extract location from definition result
        # LSP definition returns: {file_path, line, column, end_line, end_column}
        return Location(
            file_path=definition.get("file_path", str(file_path)),
            line=definition.get("line", line),
            column=definition.get("column", column),
            end_line=definition.get("end_line"),
            end_column=definition.get("end_column"),
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
        references = self._lsp_client.find_references(file_path, line, column)

        if not references:
            return []

        # Convert to Location objects
        locations = []
        for ref in references:
            location = Location(
                file_path=ref.get("file_path", str(file_path)),
                line=ref.get("line", 0),
                column=ref.get("column", 0),
                end_line=ref.get("end_line"),
                end_column=ref.get("end_column"),
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

    def export_semantic_for_locations(
        self, file_path: Path, locations: list[tuple[int, int]]
    ):
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

    async def export_semantic_for_locations_async(
        self, file_path: Path, locations: list[tuple[int, int]]
    ):
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
        return await self._daemon.export_semantic_for_locations_async(
            file_path, locations
        )

    def export_semantic_for_files(
        self, file_locations: dict[Path, list[tuple[int, int]]]
    ):
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
