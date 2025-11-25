"""
AST Tree wrapper for Tree-sitter
"""


try:
    from tree_sitter import Node as TSNode
    from tree_sitter import Tree as TSTree
except ImportError as e:
    raise ImportError("tree-sitter is required. Install with: pip install tree-sitter") from e

from ..ir.models import Span
from .parser_registry import get_registry
from .source_file import SourceFile


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

    def walk(self, node: TSNode | None = None) -> list[TSNode]:
        """
        Walk AST in depth-first order.

        Args:
            node: Starting node (defaults to root)

        Returns:
            List of nodes in DFS order
        """
        if node is None:
            node = self._root

        nodes = [node]
        for child in node.children:
            nodes.extend(self.walk(child))
        return nodes

    def find_by_type(self, node_type: str, node: TSNode | None = None) -> list[TSNode]:
        """
        Find all nodes of specific type.

        Args:
            node_type: Node type to find (e.g., "function_definition", "class_definition")
            node: Starting node (defaults to root)

        Returns:
            List of matching nodes
        """
        if node is None:
            node = self._root

        matches = []
        if node.type == node_type:
            matches.append(node)

        for child in node.children:
            matches.extend(self.find_by_type(node_type, child))

        return matches

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

        Args:
            node: Tree-sitter node

        Returns:
            IR Span (1-indexed lines, 0-indexed columns)
        """
        # Tree-sitter uses 0-indexed lines, IR uses 1-indexed
        return Span(
            start_line=node.start_point[0] + 1,
            start_col=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_col=node.end_point[1],
        )

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
