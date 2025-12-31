"""
FileSystemCodeTraceAdapter - L11급 SOTA

Real implementation of CodeTraceProvider Port.

Responsibilities:
- Read actual source files
- Extract code snippets with context
- Format traces for human readability
- Handle edge cases (missing files, invalid line numbers, etc.)

SOLID:
- S: Code trace generation만 담당
- O: Extensible for new formatting styles
- L: Implements CodeTraceProvider protocol
- I: Focused interface
- D: Depends on Port abstraction
"""

from pathlib import Path
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.query.results import PathResult, UnifiedNode

logger = get_logger(__name__)


class FileSystemCodeTraceAdapter:
    """
    FileSystem-based implementation of CodeTraceProvider

    Reads actual source files from disk and generates code traces.

    Features:
    - Context lines (before/after)
    - Line number highlighting
    - Error handling (missing files, invalid lines)
    - Multiple file support

    Thread Safety:
        File reads are stateless and thread-safe.

    Example:
        adapter = FileSystemCodeTraceAdapter(project_root="/path/to/project")
        trace = adapter.get_trace(path_result, context_lines=2)
    """

    def __init__(self, project_root: str | Path):
        """
        Initialize adapter

        Args:
            project_root: Project root directory (absolute path)

        Raises:
            ValueError: If project_root doesn't exist
        """
        self.project_root = Path(project_root)

        if not self.project_root.exists():
            raise ValueError(f"Project root does not exist: {project_root}")

        if not self.project_root.is_dir():
            raise ValueError(f"Project root is not a directory: {project_root}")

        logger.debug("code_trace_adapter_initialized", project_root=str(self.project_root))

    def get_trace(self, path: "PathResult", context_lines: int = 2) -> str:
        """
        Get code trace for a path result

        Args:
            path: PathResult from query execution
            context_lines: Number of context lines before/after (default: 2)

        Returns:
            Formatted code trace as string

        Format:
            File: path/to/file.py
            ----
              10 | context line before
              11 | context line before
            > 12 | highlighted line (node location)
              13 | context line after
              14 | context line after
            ----
            File: path/to/other.py
            ...

        Edge Cases:
            - File not found: Returns error message
            - Invalid line number: Returns warning
            - Empty file: Returns "(empty file)"
            - Binary file: Returns "(binary file)"
        """
        if not path or not path.nodes:
            return "(no path to trace)"

        lines = []
        lines.append("=" * 60)
        lines.append(f"PATH TRACE ({len(path.nodes)} nodes)")
        lines.append("=" * 60)

        # Group nodes by file for better readability
        current_file = None

        for i, node in enumerate(path.nodes):
            # Check if node has location info
            if not node.file_path or node.line_number is None:
                lines.append(f"\nNode {i + 1}: {node.kind} '{node.name}' (no location info)")
                continue

            # New file - print header
            if node.file_path != current_file:
                current_file = node.file_path
                lines.append(f"\n{'─' * 60}")
                lines.append(f"File: {node.file_path}")
                lines.append(f"{'─' * 60}")

            # Read file and extract snippet
            try:
                snippet = self._read_snippet(node.file_path, node.line_number, context_lines)
                lines.append(f"\nNode {i + 1}: {node.kind} '{node.name}' (line {node.line_number})")
                lines.append(snippet)
            except FileNotFoundError:
                lines.append(f"\nNode {i + 1}: {node.kind} '{node.name}' (line {node.line_number})")
                lines.append(f"  ERROR: File not found: {node.file_path}")
            except Exception as e:
                lines.append(f"\nNode {i + 1}: {node.kind} '{node.name}' (line {node.line_number})")
                lines.append(f"  ERROR: {type(e).__name__}: {e}")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)

    def _read_snippet(self, file_path: str, line_number: int, context_lines: int) -> str:
        """
        Read code snippet from file

        Args:
            file_path: Relative file path from project root
            line_number: Target line number (1-based)
            context_lines: Number of context lines

        Returns:
            Formatted snippet

        Raises:
            FileNotFoundError: If file doesn't exist
            UnicodeDecodeError: If file is binary
        """
        # Resolve absolute path
        abs_path = self.project_root / file_path

        if not abs_path.exists():
            raise FileNotFoundError(f"File not found: {abs_path}")

        # Read file
        try:
            with open(abs_path, encoding="utf-8") as f:
                file_lines = f.readlines()
        except UnicodeDecodeError:
            return "  (binary file - cannot display)"

        if not file_lines:
            return "  (empty file)"

        # Validate line number
        if line_number < 1 or line_number > len(file_lines):
            return f"  (invalid line number: {line_number}, file has {len(file_lines)} lines)"

        # Calculate range
        start = max(0, line_number - context_lines - 1)
        end = min(len(file_lines), line_number + context_lines)

        # Format snippet
        snippet_lines = []
        max_line_num_width = len(str(end))

        for i in range(start, end):
            line_num = i + 1
            line_content = file_lines[i].rstrip()

            # Highlight target line
            if line_num == line_number:
                marker = ">"
            else:
                marker = " "

            # Format: "> 123 | line content"
            formatted = f"{marker} {line_num:>{max_line_num_width}} | {line_content}"
            snippet_lines.append(formatted)

        return "\n".join(snippet_lines)

    def get_trace_for_node(self, node: "UnifiedNode", context_lines: int = 2) -> str:
        """
        Get code trace for a single node

        Args:
            node: UnifiedNode
            context_lines: Context lines

        Returns:
            Formatted code trace
        """

        if not node.file_path or node.line_number is None:
            return f"{node.kind} '{node.name}' (no location info)"

        try:
            snippet = self._read_snippet(node.file_path, node.line_number, context_lines)
            return f"{node.kind} '{node.name}' at {node.file_path}:{node.line_number}\n{snippet}"
        except FileNotFoundError:
            return f"{node.kind} '{node.name}' at {node.file_path}:{node.line_number}\nERROR: File not found"
        except Exception as e:
            return f"{node.kind} '{node.name}' at {node.file_path}:{node.line_number}\nERROR: {e}"


class InMemoryCodeTraceAdapter:
    """
    In-memory implementation of CodeTraceProvider

    For testing without filesystem access.

    Usage:
        adapter = InMemoryCodeTraceAdapter()
        adapter.add_file("test.py", "def foo():\\n    return 42")
        trace = adapter.get_trace(path_result)
    """

    def __init__(self):
        """Initialize with empty file cache"""
        self._files: dict[str, list[str]] = {}
        logger.debug("in_memory_code_trace_adapter_initialized")

    def add_file(self, file_path: str, content: str) -> None:
        """
        Add file content to cache

        Args:
            file_path: File path (relative)
            content: File content (string)
        """
        self._files[file_path] = content.splitlines(keepends=True)

    def get_trace(self, path: "PathResult", context_lines: int = 2) -> str:
        """Get trace from cached files"""
        if not path or not path.nodes:
            return "(no path to trace)"

        lines = []
        lines.append("=" * 60)
        lines.append(f"PATH TRACE ({len(path.nodes)} nodes)")
        lines.append("=" * 60)

        current_file = None

        for i, node in enumerate(path.nodes):
            if not node.file_path or node.line_number is None:
                lines.append(f"\nNode {i + 1}: {node.kind} '{node.name}' (no location info)")
                continue

            if node.file_path != current_file:
                current_file = node.file_path
                lines.append(f"\n{'─' * 60}")
                lines.append(f"File: {node.file_path}")
                lines.append(f"{'─' * 60}")

            try:
                snippet = self._read_snippet(node.file_path, node.line_number, context_lines)
                lines.append(f"\nNode {i + 1}: {node.kind} '{node.name}' (line {node.line_number})")
                lines.append(snippet)
            except KeyError:
                lines.append(f"\nNode {i + 1}: {node.kind} '{node.name}' (line {node.line_number})")
                lines.append(f"  ERROR: File not in cache: {node.file_path}")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)

    def _read_snippet(self, file_path: str, line_number: int, context_lines: int) -> str:
        """Read snippet from cached file"""
        if file_path not in self._files:
            raise KeyError(f"File not in cache: {file_path}")

        file_lines = self._files[file_path]

        if not file_lines:
            return "  (empty file)"

        if line_number < 1 or line_number > len(file_lines):
            return f"  (invalid line number: {line_number}, file has {len(file_lines)} lines)"

        start = max(0, line_number - context_lines - 1)
        end = min(len(file_lines), line_number + context_lines)

        snippet_lines = []
        max_line_num_width = len(str(end))

        for i in range(start, end):
            line_num = i + 1
            line_content = file_lines[i].rstrip()

            marker = ">" if line_num == line_number else " "
            formatted = f"{marker} {line_num:>{max_line_num_width}} | {line_content}"
            snippet_lines.append(formatted)

        return "\n".join(snippet_lines)
