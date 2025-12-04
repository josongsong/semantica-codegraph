"""
Module Analyzer for Python IR

Handles file-level IR generation including FILE nodes and module FQN extraction.
"""

from src.contexts.code_foundation.infrastructure.ir.id_strategy import generate_content_hash, generate_logical_id
from src.contexts.code_foundation.infrastructure.ir.models import Node, NodeKind, Span
from src.contexts.code_foundation.infrastructure.parsing import SourceFile


class ModuleAnalyzer:
    """
    Handles file-level IR generation.

    Responsibilities:
    - Generate FILE nodes for Python source files
    - Extract module FQN from file paths
    - Detect test files

    This analyzer focuses purely on module/file-level concerns,
    delegating class/function processing to other analyzers.

    Example:
        >>> nodes = []
        >>> analyzer = ModuleAnalyzer("repo1", nodes)
        >>> source = SourceFile(file_path="src/main.py", ...)
        >>> file_node = analyzer.generate_file_node(source, "src.main")
        >>> assert file_node.kind == NodeKind.FILE
        >>> assert file_node.fqn == "src.main"
    """

    def __init__(self, repo_id: str, nodes: list[Node]):
        """
        Initialize module analyzer.

        Args:
            repo_id: Repository identifier
            nodes: Shared node collection (will be mutated)
        """
        self._repo_id = repo_id
        self._nodes = nodes

    def generate_file_node(self, source: SourceFile, module_fqn: str) -> Node:
        """
        Generate FILE node for source file.

        Args:
            source: Source file to process
            module_fqn: Module fully qualified name (e.g., "src.main")

        Returns:
            FILE node (also appended to self._nodes)

        Example:
            >>> source = SourceFile(
            ...     file_path="src/main.py",
            ...     content="def foo(): pass",
            ...     language="python",
            ...     line_count=1
            ... )
            >>> file_node = analyzer.generate_file_node(source, "src.main")
            >>> assert file_node.kind == NodeKind.FILE
            >>> assert file_node.fqn == "src.main"
            >>> assert file_node.name == "main.py"
        """
        span = Span(
            start_line=1,
            start_col=0,
            end_line=source.line_count,
            end_col=0,
        )

        node_id = generate_logical_id(
            repo_id=self._repo_id,
            kind=NodeKind.FILE,
            file_path=source.file_path,
            fqn=module_fqn,
        )

        content_hash = generate_content_hash(source.content)

        node = Node(
            id=node_id,
            kind=NodeKind.FILE,
            fqn=module_fqn,
            file_path=source.file_path,
            span=span,
            language=source.language,
            content_hash=content_hash,
            name=source.file_path.split("/")[-1],
            module_path=module_fqn,
            is_test_file=self.is_test_file(source.file_path),
        )

        self._nodes.append(node)
        return node

    def get_module_fqn(self, file_path: str) -> str:
        """
        Extract module FQN from file path.

        This method converts a file path to a Python module FQN:
        - Removes "src/" prefix if present
        - Removes ".py" extension
        - Replaces "/" with "."
        - Removes "__init__" suffix for package __init__ files

        Args:
            file_path: Relative file path (e.g., "src/main.py")

        Returns:
            Module FQN (e.g., "main")

        Examples:
            >>> analyzer.get_module_fqn("src/main.py")
            'main'
            >>> analyzer.get_module_fqn("src/foo/bar.py")
            'foo.bar'
            >>> analyzer.get_module_fqn("src/foo/__init__.py")
            'foo'
            >>> analyzer.get_module_fqn("tests/test_main.py")
            'tests.test_main'
            >>> analyzer.get_module_fqn("main.py")
            'main'
        """
        # Remove src/ prefix if present
        path = file_path
        if path.startswith("src/"):
            path = path[4:]

        # Remove .py extension
        if path.endswith(".py"):
            path = path[:-3]

        # Replace / with .
        fqn = path.replace("/", ".")

        # Remove __init__ suffix for packages
        if fqn.endswith(".__init__"):
            fqn = fqn[:-9]

        return fqn

    def is_test_file(self, file_path: str) -> bool:
        """
        Detect if file is a test file.

        A file is considered a test file if:
        - Contains "test" in the path (case-insensitive)
        - Starts with "tests/"
        - Contains "/tests/" in the path

        Args:
            file_path: File path to check

        Returns:
            True if test file, False otherwise

        Examples:
            >>> analyzer.is_test_file("test_main.py")
            True
            >>> analyzer.is_test_file("tests/test_foo.py")
            True
            >>> analyzer.is_test_file("src/tests/test_bar.py")
            True
            >>> analyzer.is_test_file("main.py")
            False
            >>> analyzer.is_test_file("src/main.py")
            False
        """
        return "test" in file_path.lower() or file_path.startswith("tests/") or "/tests/" in file_path
