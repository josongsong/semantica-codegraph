"""Trie Index - O(log N) Prefix/Suffix Matching.

RFC-034: Trie-based index for prefix and suffix wildcards.

Features:
    - PrefixTrie: "subprocess.*" → O(L) lookup
    - SuffixTrie: "*.Cursor" → O(L) lookup (reversed)
    - Memory efficient (shared prefixes)
    - Fast iteration

Usage:
    >>> prefix_idx = PrefixTrieIndex()
    >>> prefix_idx.add_pattern("rule1", "subprocess")
    >>> prefix_idx.search("subprocess.Popen")
    {'rule1'}
"""

from dataclasses import dataclass


@dataclass
class TrieNode:
    """Trie node.

    Attributes:
        children: Child nodes (char → node)
        rule_ids: Rule IDs at this node (terminal nodes)
        is_terminal: Whether this node represents a complete pattern
    """

    children: dict[str, "TrieNode"]
    rule_ids: set[str]
    is_terminal: bool = False

    def __init__(self) -> None:
        """Initialize trie node."""
        self.children = {}
        self.rule_ids = set()
        self.is_terminal = False


@dataclass
class TrieStats:
    """Trie statistics."""

    total_patterns: int = 0
    total_nodes: int = 0
    max_depth: int = 0
    avg_depth: float = 0.0


class PrefixTrieIndex:
    """Prefix trie index for "prefix*" patterns.

    RFC-034: O(L) prefix matching where L = query length.

    Algorithm:
        1. Build trie from patterns
        2. Walk trie with query
        3. Collect all rule_ids from matched node + descendants

    Example:
        >>> idx = PrefixTrieIndex()
        >>> idx.add_pattern("rule1", "subprocess")
        >>> idx.search("subprocess.Popen")
        {'rule1'}
        >>> idx.search("os.system")
        set()
    """

    def __init__(self, case_sensitive: bool = False) -> None:
        """Initialize prefix trie.

        Args:
            case_sensitive: Whether to do case-sensitive matching
        """
        self.case_sensitive = case_sensitive
        self.root = TrieNode()
        self._total_patterns = 0

    def add_pattern(self, rule_id: str, prefix: str) -> None:
        """Add prefix pattern.

        Args:
            rule_id: Rule identifier
            prefix: Prefix to match (without wildcard)

        Example:
            >>> idx = PrefixTrieIndex()
            >>> idx.add_pattern("rule1", "subprocess")
        """
        if not prefix:
            raise ValueError("Prefix cannot be empty")

        # Normalize
        normalized = self._normalize(prefix)

        # Walk/create trie
        node = self.root
        for char in normalized:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]

        # Mark terminal
        node.is_terminal = True
        node.rule_ids.add(rule_id)
        self._total_patterns += 1

    def search(self, query: str) -> set[str]:
        """Search for matching prefixes.

        Args:
            query: Query string

        Returns:
            Set of matching rule IDs

        Example:
            >>> idx = PrefixTrieIndex()
            >>> idx.add_pattern("rule1", "subprocess")
            >>> idx.search("subprocess.Popen")
            {'rule1'}
        """
        if not query:
            return set()

        normalized = self._normalize(query)

        # Walk trie as far as possible
        node = self.root
        matched_rules: set[str] = set()

        for char in normalized:
            # Collect rules at current node (if terminal)
            if node.is_terminal:
                matched_rules.update(node.rule_ids)

            # Continue walking
            if char not in node.children:
                break

            node = node.children[char]

        # Collect rules at final node
        if node.is_terminal:
            matched_rules.update(node.rule_ids)

        return matched_rules

    def size(self) -> int:
        """Get number of patterns.

        Returns:
            Number of indexed patterns
        """
        return self._total_patterns

    def stats(self) -> TrieStats:
        """Get trie statistics.

        Returns:
            Trie statistics
        """
        total_nodes = self._count_nodes(self.root)
        max_depth = self._max_depth(self.root)

        return TrieStats(
            total_patterns=self._total_patterns,
            total_nodes=total_nodes,
            max_depth=max_depth,
            avg_depth=max_depth / max(self._total_patterns, 1),
        )

    def clear(self) -> None:
        """Clear all patterns."""
        self.root = TrieNode()
        self._total_patterns = 0

    def _normalize(self, text: str) -> str:
        """Normalize text.

        Args:
            text: Text to normalize

        Returns:
            Normalized text
        """
        return text if self.case_sensitive else text.lower()

    def _count_nodes(self, node: TrieNode) -> int:
        """Count total nodes in subtree.

        Args:
            node: Root of subtree

        Returns:
            Node count
        """
        count = 1
        for child in node.children.values():
            count += self._count_nodes(child)
        return count

    def _max_depth(self, node: TrieNode, current_depth: int = 0) -> int:
        """Calculate maximum depth.

        Args:
            node: Current node
            current_depth: Current depth

        Returns:
            Maximum depth
        """
        if not node.children:
            return current_depth

        max_child_depth = 0
        for child in node.children.values():
            child_depth = self._max_depth(child, current_depth + 1)
            max_child_depth = max(max_child_depth, child_depth)

        return max_child_depth


class SuffixTrieIndex:
    """Suffix trie index for "*suffix" patterns.

    RFC-034: O(L) suffix matching where L = query length.

    Implementation: Reversed prefix trie.

    Algorithm:
        1. Build trie from reversed patterns
        2. Walk trie with reversed query
        3. Collect all rule_ids from matched node

    Example:
        >>> idx = SuffixTrieIndex()
        >>> idx.add_pattern("rule1", ".Cursor")
        >>> idx.search("sqlite3.Cursor")
        {'rule1'}
    """

    def __init__(self, case_sensitive: bool = False) -> None:
        """Initialize suffix trie.

        Args:
            case_sensitive: Whether to do case-sensitive matching
        """
        self.case_sensitive = case_sensitive
        self.root = TrieNode()
        self._total_patterns = 0

    def add_pattern(self, rule_id: str, suffix: str) -> None:
        """Add suffix pattern.

        Args:
            rule_id: Rule identifier
            suffix: Suffix to match (without wildcard)

        Example:
            >>> idx = SuffixTrieIndex()
            >>> idx.add_pattern("rule1", ".Cursor")
        """
        if not suffix:
            raise ValueError("Suffix cannot be empty")

        # Normalize and reverse
        normalized = self._normalize(suffix)
        reversed_suffix = normalized[::-1]

        # Walk/create trie (reversed)
        node = self.root
        for char in reversed_suffix:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]

        # Mark terminal
        node.is_terminal = True
        node.rule_ids.add(rule_id)
        self._total_patterns += 1

    def search(self, query: str) -> set[str]:
        """Search for matching suffixes.

        Args:
            query: Query string

        Returns:
            Set of matching rule IDs

        Example:
            >>> idx = SuffixTrieIndex()
            >>> idx.add_pattern("rule1", ".Cursor")
            >>> idx.search("sqlite3.Cursor")
            {'rule1'}
        """
        if not query:
            return set()

        normalized = self._normalize(query)
        reversed_query = normalized[::-1]

        # Walk trie as far as possible
        node = self.root
        matched_rules: set[str] = set()

        for char in reversed_query:
            # Collect rules at current node (if terminal)
            if node.is_terminal:
                matched_rules.update(node.rule_ids)

            # Continue walking
            if char not in node.children:
                break

            node = node.children[char]

        # Collect rules at final node
        if node.is_terminal:
            matched_rules.update(node.rule_ids)

        return matched_rules

    def size(self) -> int:
        """Get number of patterns.

        Returns:
            Number of indexed patterns
        """
        return self._total_patterns

    def stats(self) -> TrieStats:
        """Get trie statistics.

        Returns:
            Trie statistics
        """
        total_nodes = self._count_nodes(self.root)
        max_depth = self._max_depth(self.root)

        return TrieStats(
            total_patterns=self._total_patterns,
            total_nodes=total_nodes,
            max_depth=max_depth,
            avg_depth=max_depth / max(self._total_patterns, 1),
        )

    def clear(self) -> None:
        """Clear all patterns."""
        self.root = TrieNode()
        self._total_patterns = 0

    def _normalize(self, text: str) -> str:
        """Normalize text.

        Args:
            text: Text to normalize

        Returns:
            Normalized text
        """
        return text if self.case_sensitive else text.lower()

    def _count_nodes(self, node: TrieNode) -> int:
        """Count total nodes in subtree.

        Args:
            node: Root of subtree

        Returns:
            Node count
        """
        count = 1
        for child in node.children.values():
            count += self._count_nodes(child)
        return count

    def _max_depth(self, node: TrieNode, current_depth: int = 0) -> int:
        """Calculate maximum depth.

        Args:
            node: Current node
            current_depth: Current depth

        Returns:
            Maximum depth
        """
        if not node.children:
            return current_depth

        max_child_depth = 0
        for child in node.children.values():
            child_depth = self._max_depth(child, current_depth + 1)
            max_child_depth = max(max_child_depth, child_depth)

        return max_child_depth
