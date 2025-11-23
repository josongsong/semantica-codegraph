"""
Base IR Generator

Abstract base class for language-specific IR generators.
"""

import hashlib
from abc import ABC, abstractmethod
from typing import Optional

try:
    from tree_sitter import Node as TSNode
except ImportError:
    TSNode = None

from ..models import IRDocument
from ...parsing import SourceFile


class IRGenerator(ABC):
    """
    Abstract base class for IR generators.

    Each language (Python, TypeScript, etc.) implements this interface.
    """

    def __init__(self, repo_id: str):
        """
        Initialize generator.

        Args:
            repo_id: Repository identifier
        """
        self.repo_id = repo_id

    @abstractmethod
    def generate(self, source: SourceFile, snapshot_id: str) -> IRDocument:
        """
        Generate IR document from source file.

        Args:
            source: Source file to parse
            snapshot_id: Snapshot identifier

        Returns:
            Complete IR document for this file
        """
        pass

    # ============================================================
    # Utility Methods
    # ============================================================

    def generate_content_hash(self, text: str) -> str:
        """
        Generate SHA256 hash of code text.

        Args:
            text: Source code text

        Returns:
            Hash in format "sha256:{hex}"
        """
        normalized = text.strip()
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        return f"sha256:{digest}"

    def calculate_cyclomatic_complexity(
        self, node: Optional[TSNode], node_type_branches: set[str]
    ) -> int:
        """
        Calculate cyclomatic complexity using AST.

        McCabe's formula: M = E - N + 2P
        Simplified: M = number of decision points + 1

        Decision points:
        - if, elif
        - while, for
        - and, or (boolean operators)
        - try/except handlers
        - case (match statement)

        Args:
            node: Tree-sitter AST node
            node_type_branches: Set of node types that count as branches

        Returns:
            Cyclomatic complexity
        """
        if node is None:
            return 1

        complexity = 1  # Base complexity

        # Count decision points recursively
        def count_branches(n: TSNode) -> int:
            count = 0

            if n.type in node_type_branches:
                count += 1

            for child in n.children:
                count += count_branches(child)

            return count

        complexity += count_branches(node)
        return complexity

    def has_loop(self, node: Optional[TSNode], loop_types: set[str]) -> bool:
        """
        Check if node contains any loop.

        Args:
            node: Tree-sitter AST node
            loop_types: Set of node types that are loops

        Returns:
            True if loop found
        """
        if node is None:
            return False

        if node.type in loop_types:
            return True

        return any(self.has_loop(child, loop_types) for child in node.children)

    def has_try(self, node: Optional[TSNode], try_types: set[str]) -> bool:
        """
        Check if node contains try/except.

        Args:
            node: Tree-sitter AST node
            try_types: Set of node types that are try statements

        Returns:
            True if try found
        """
        if node is None:
            return False

        if node.type in try_types:
            return True

        return any(self.has_try(child, try_types) for child in node.children)

    def count_branches(self, node: Optional[TSNode], branch_types: set[str]) -> int:
        """
        Count number of branches (if/elif/case).

        Args:
            node: Tree-sitter AST node
            branch_types: Set of node types that are branches

        Returns:
            Number of branches
        """
        if node is None:
            return 0

        count = 1 if node.type in branch_types else 0

        for child in node.children:
            count += self.count_branches(child, branch_types)

        return count

    def get_node_text(self, node: TSNode, source_bytes: bytes) -> str:
        """
        Get text content of AST node.

        Args:
            node: Tree-sitter node
            source_bytes: Source code as bytes

        Returns:
            Node text
        """
        return source_bytes[node.start_byte : node.end_byte].decode("utf-8")

    def find_child_by_type(self, node: TSNode, child_type: str) -> Optional[TSNode]:
        """
        Find first child node of specific type.

        Args:
            node: Parent node
            child_type: Type to find

        Returns:
            First matching child or None
        """
        for child in node.children:
            if child.type == child_type:
                return child
        return None

    def find_children_by_type(self, node: TSNode, child_type: str) -> list[TSNode]:
        """
        Find all child nodes of specific type.

        Args:
            node: Parent node
            child_type: Type to find

        Returns:
            List of matching children
        """
        return [child for child in node.children if child.type == child_type]
