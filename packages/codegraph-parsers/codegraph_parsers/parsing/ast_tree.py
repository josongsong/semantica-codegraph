"""
AST Tree wrapper for Tree-sitter
"""

try:
    from tree_sitter import Node as TSNode
    from tree_sitter import Tree as TSTree
except ImportError as e:
    raise ImportError("tree-sitter is required. Install with: pip install tree-sitter") from e

from functools import lru_cache

from codegraph_parsers.models import Span
from codegraph_parsers.parsing.ast_index import AstIndex
from codegraph_parsers.parsing.parser_registry import get_registry
from codegraph_parsers.parsing.source_file import SourceFile


class AstTree:
    """
    Wrapper for Tree-sitter AST.

    Provides convenient methods for traversing and analyzing the AST.
    """

    def __init__(self, source: SourceFile, tree: TSTree):
        """
        Initialize AST tree.

        Args:
            source: Source file
            tree: Tree-sitter tree
        """
        self.source = source
        self.tree = tree
        self._root = tree.root_node
        self._index: AstIndex | None = None  # Lazy initialization
        self._span_cache: dict[int, Span] = {}  # Per-instance span cache (node id → Span)

    @classmethod
    def parse(cls, source: SourceFile) -> "AstTree":
        """
        Parse source file into AST.

        Args:
            source: Source file to parse

        Returns:
            AstTree instance

        Raises:
            ValueError: If language not supported or parsing fails
        """
        registry = get_registry()
        parser = registry.get_parser(source.language)

        if parser is None:
            raise ValueError(f"Language not supported: {source.language}")

        # Parse source code
        tree = parser.parse(source.content.encode(source.encoding))

        if tree is None:
            raise ValueError(f"Failed to parse file: {source.file_path}")

        return cls(source, tree)

    @property
    def root(self) -> TSNode:
        """Get root node"""
        return self._root

    def walk(self, node: TSNode | None = None, _depth: int = 0) -> list[TSNode]:
        """
        Walk AST in depth-first order with stack overflow protection.

        Args:
            node: Starting node (defaults to root)
            _depth: Internal recursion depth counter (do not set manually)

        Returns:
            List of nodes in DFS order

        Raises:
            RecursionError: If nesting depth exceeds safety limit (10000 levels)
        """
        # Safety check: Prevent stack overflow on pathologically nested code
        MAX_DEPTH = 10000
        if _depth > MAX_DEPTH:
            raise RecursionError(
                f"AST walk() exceeded maximum depth of {MAX_DEPTH}. "
                f"This usually indicates extremely deeply nested code (e.g., {MAX_DEPTH}+ nested blocks). "
                "Consider refactoring the input code or using iterative traversal."
            )

        if node is None:
            node = self._root

        nodes = [node]
        for child in node.children:
            nodes.extend(self.walk(child, _depth + 1))
        return nodes

    def build_index(self) -> AstIndex:
        """
        Build multi-level index for O(1) lookups.

        SOTA Optimization: Replaces O(n) find_by_type with O(1) index lookup.

        Build time: O(n) where n = total nodes
        Memory: ~200 bytes per node

        Returns:
            AstIndex with type, line, and position indexes
        """
        if self._index is not None:
            return self._index

        self._index = AstIndex()
        self._build_index_recursive(self._root)

        return self._index

    def _build_index_recursive(self, node: TSNode) -> None:
        """Recursively build index for all nodes."""
        # Get span for line/position indexing
        span = self.get_span(node)

        # Add to index
        self._index.add_node(node, span)

        # Recurse to children
        for child in node.children:
            self._build_index_recursive(child)

    def get_index(self) -> AstIndex:
        """
        Get or build AST index (lazy initialization).

        Returns:
            AstIndex instance
        """
        if self._index is None:
            self.build_index()
        return self._index

    def find_by_type(self, node_type: str, node: TSNode | None = None) -> list[TSNode]:
        """
        Find all nodes of specific type.

        OPTIMIZED: Uses index if available (O(1) vs O(n) recursive search).
        Falls back to recursive search if starting from non-root node.

        Args:
            node_type: Node type to find (e.g., "function_definition", "class_definition")
            node: Starting node (defaults to root)

        Returns:
            List of matching nodes
        """
        # Fast path: Use index for root-level queries
        if node is None or node == self._root:
            if self._index is not None:
                return self._index.get_by_type(node_type)

        # Slow path: Recursive search for subtree queries
        if node is None:
            node = self._root

        matches = []
        if node.type == node_type:
            matches.append(node)

        for child in node.children:
            matches.extend(self.find_by_type(node_type, child))

        return matches

    def find_function_at_line(self, line: int) -> TSNode | None:
        """
        Find function at line (O(1) index, O(k) filter where k = nodes at line).

        L11 Trade-off: Direct TSNode for true O(1).
        Safety contract: Caller must not use TSNode after tree invalidation.

        Args:
            line: Line number (1-based)

        Returns:
            TSNode or None
        """
        if self._index is None:
            self.build_index()

        return self._index.find_function_at_line(line, self.source.language)

    def invalidate_index(self) -> None:
        """
        Invalidate cached index (call after tree modification).

        Required for:
        - File content changes
        - Tree regeneration
        - Incremental builds
        """
        self._index = None
        self._span_cache.clear()

    def get_text(self, node: TSNode) -> str:
        """
        Get text content of a node.

        Args:
            node: Tree-sitter node

        Returns:
            Node text
        """
        return self.source.content[node.start_byte : node.end_byte]

    def get_span(self, node: TSNode) -> Span:
        """
        Convert Tree-sitter node to IR Span.

        SOTA: Instance-level caching (per-file optimization).
        Using node.id as cache key since TSNode is not hashable for lru_cache.

        Args:
            node: Tree-sitter node

        Returns:
            IR Span (1-indexed lines, 0-indexed columns)
        """
        # Check cache (using node.id as key)
        node_id = id(node)
        if node_id in self._span_cache:
            return self._span_cache[node_id]

        # Tree-sitter uses 0-indexed lines, IR uses 1-indexed
        span = Span(
            start_line=node.start_point[0] + 1,
            start_col=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_col=node.end_point[1],
        )

        # Cache for reuse
        self._span_cache[node_id] = span
        return span

    def find_node_at_line(self, line: int, node: TSNode | None = None) -> TSNode | None:
        """
        Find deepest node containing the given line.

        Args:
            line: Line number (1-indexed)
            node: Starting node (defaults to root)

        Returns:
            Deepest node containing the line, or None
        """
        if node is None:
            node = self._root

        # Convert to 0-indexed for Tree-sitter
        line_0 = line - 1

        # Check if line is within node
        if not (node.start_point[0] <= line_0 <= node.end_point[0]):
            return None

        # Try to find deeper match in children
        for child in node.children:
            deeper = self.find_node_at_line(line, child)
            if deeper is not None:
                return deeper

        # This node is the deepest match
        return node

    def get_parent(self, node: TSNode) -> TSNode | None:
        """Get parent node"""
        return node.parent

    def get_children(self, node: TSNode) -> list[TSNode]:
        """Get child nodes"""
        return list(node.children)

    def get_named_children(self, node: TSNode) -> list[TSNode]:
        """Get named child nodes (excluding anonymous nodes)"""
        return [child for child in node.children if child.is_named]

    def has_error(self, node: TSNode | None = None) -> bool:
        """
        Check if AST has any error nodes.

        Args:
            node: Starting node (defaults to root)

        Returns:
            True if errors found
        """
        if node is None:
            node = self._root

        if node.type == "ERROR" or node.is_missing:
            return True

        return any(self.has_error(child) for child in node.children)

    def get_errors(self, node: TSNode | None = None) -> list[TSNode]:
        """
        Get all error nodes.

        Args:
            node: Starting node (defaults to root)

        Returns:
            List of error nodes
        """
        if node is None:
            node = self._root

        errors = []
        if node.type == "ERROR" or node.is_missing:
            errors.append(node)

        for child in node.children:
            errors.extend(self.get_errors(child))

        return errors

    def __repr__(self) -> str:
        return f"AstTree(file={self.source.file_path}, language={self.source.language})"
