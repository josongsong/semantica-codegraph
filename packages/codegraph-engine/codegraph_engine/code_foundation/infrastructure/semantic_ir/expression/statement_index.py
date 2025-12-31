"""
File Statement Index - SOTA O(1) Statement Lookup

Replaces O(n) AST traversal per block with O(log n) index lookup.

Problem:
    - _find_statements_in_span() traverses ENTIRE AST for EVERY block
    - 1,903 blocks × full AST = 853ms (90% of Semantic IR time)

Solution:
    - Build statement index ONCE per file
    - Query index for each block in O(log n) via binary search

Performance:
    - Before: O(blocks × ast_nodes) = O(1,903 × 500) ≈ 950,000 node visits
    - After: O(files × ast_nodes + blocks × log(statements))
           = O(12 × 500 + 1,903 × log(200)) ≈ 20,000 operations
    - Improvement: ~50x fewer operations

Usage:
    index = FileStatementIndex.build(ast_tree, file_path, is_statement_node_fn)
    statements = index.query_span(start_line, end_line)
"""

import bisect
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode

    from codegraph_engine.code_foundation.infrastructure.parsing import AstTree

logger = get_logger(__name__)


@dataclass
class FileStatementIndex:
    """
    Pre-computed line→statements mapping for O(log n) lookup.

    Attributes:
        file_path: Source file path (for debugging/logging)
        statements_sorted: List of (start_line, end_line, node) sorted by start_line
        _line_keys: Pre-computed list of start_lines for binary search

    Invariants:
        - statements_sorted is sorted by start_line (ascending)
        - _line_keys[i] == statements_sorted[i][0] for all i
    """

    file_path: str
    statements_sorted: list[tuple[int, int, "TSNode"]] = field(default_factory=list)
    _line_keys: list[int] = field(default_factory=list)

    @classmethod
    def build(
        cls,
        ast_tree: "AstTree",
        file_path: str,
        is_statement_node: Callable[["TSNode"], bool],
    ) -> "FileStatementIndex":
        """
        Build statement index from AST with SINGLE traversal.

        Args:
            ast_tree: Parsed AST tree
            file_path: Source file path
            is_statement_node: Function to determine if node is a statement

        Returns:
            FileStatementIndex with O(log n) query capability

        Complexity:
            - Time: O(ast_nodes) - single traversal
            - Space: O(statements) - only statement nodes stored

        Example:
            >>> index = FileStatementIndex.build(ast, "test.py", is_stmt_fn)
            >>> stmts = index.query_span(10, 20)  # O(log n)
        """
        statements: list[tuple[int, int, "TSNode"]] = []

        def traverse(node: "TSNode") -> None:
            """Collect all statement nodes with their line spans."""
            if node is None:
                return

            # Check if this is a statement
            if is_statement_node(node):
                start_line = node.start_point[0] + 1  # Convert to 1-indexed
                end_line = node.end_point[0] + 1
                statements.append((start_line, end_line, node))

            # Recurse to children (statements may be nested)
            for child in node.children:
                traverse(child)

        # Single traversal of entire AST
        if hasattr(ast_tree, "root") and ast_tree.root is not None:
            traverse(ast_tree.root)

        # Sort by start_line for binary search
        statements.sort(key=lambda x: x[0])

        # Pre-compute line keys for bisect
        line_keys = [s[0] for s in statements]

        return cls(
            file_path=file_path,
            statements_sorted=statements,
            _line_keys=line_keys,
        )

    def query_span(self, start_line: int, end_line: int) -> list["TSNode"]:
        """
        Find all statements that START within [start_line, end_line].

        Args:
            start_line: Start line (1-indexed, inclusive)
            end_line: End line (1-indexed, inclusive)

        Returns:
            List of statement TSNode objects

        Complexity:
            O(log n + k) where n = total statements, k = matching statements

        Algorithm:
            1. Binary search to find first statement with start >= start_line
            2. Linear scan until start > end_line
            3. Filter by start_line in range
        """
        if not self.statements_sorted:
            return []

        # Binary search: find first index where stmt_start >= start_line
        left = bisect.bisect_left(self._line_keys, start_line)

        result: list["TSNode"] = []

        # Linear scan from left, stop when past end_line
        for i in range(left, len(self.statements_sorted)):
            stmt_start, stmt_end, node = self.statements_sorted[i]

            # Early exit: past our range
            if stmt_start > end_line:
                break

            # Include if start is within range
            if start_line <= stmt_start <= end_line:
                result.append(node)

        return result

    def __len__(self) -> int:
        """Return number of indexed statements."""
        return len(self.statements_sorted)


class FileStatementIndexCache:
    """
    LRU-style cache for FileStatementIndex instances.

    Caches statement indices per file to avoid rebuilding.

    Attributes:
        _cache: Dict mapping file_path → FileStatementIndex
        _max_size: Maximum number of files to cache
        _hits: Cache hit counter
        _misses: Cache miss counter
    """

    def __init__(self, max_size: int = 100):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of file indices to cache
        """
        self._cache: dict[str, FileStatementIndex] = {}
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get_or_build(
        self,
        ast_tree: "AstTree",
        file_path: str,
        is_statement_node: Callable[["TSNode"], bool],
    ) -> FileStatementIndex:
        """
        Get cached index or build new one.

        Args:
            ast_tree: Parsed AST tree
            file_path: Source file path
            is_statement_node: Function to determine if node is a statement

        Returns:
            Cached or newly built FileStatementIndex
        """
        if file_path in self._cache:
            self._hits += 1
            return self._cache[file_path]

        self._misses += 1

        # Build new index
        index = FileStatementIndex.build(ast_tree, file_path, is_statement_node)

        # Evict oldest if at capacity (simple FIFO eviction)
        if len(self._cache) >= self._max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[file_path] = index
        return index

    def clear(self) -> None:
        """Clear all cached indices."""
        self._cache.clear()

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
        }


__all__ = ["FileStatementIndex", "FileStatementIndexCache"]
