"""
BloomFilter - Probabilistic Existence Check (SOTA)

Fast O(1) existence check with small memory footprint.
Allows false positives (configurable), no false negatives.

Use Cases:
1. Quick "definitely not exists" check before expensive lookup
2. Edge existence pre-filter
3. Path reachability quick-reject

Performance:
- Check: O(k) where k = hash functions (typically 3-7)
- Memory: ~10 bits per element for 1% FPR
- Build: O(n) where n = elements

SOTA Reference:
- Google Guava BloomFilter
- Redis Bloom Filter Module
"""

import hashlib
import math
from typing import Iterable


class BloomFilter:
    """
    Memory-efficient probabilistic set membership filter.

    Features:
    - O(1) membership check
    - Configurable false positive rate
    - No false negatives
    - ~1.44 log2(1/fpr) bits per element

    Usage:
        bf = BloomFilter(expected_elements=10000, fpr=0.01)
        bf.add("node:123")
        if "node:456" in bf:  # Fast check
            # May be present (check actual index)
        else:
            # Definitely not present (skip lookup)
    """

    def __init__(self, expected_elements: int = 10000, fpr: float = 0.01):
        """
        Initialize Bloom Filter.

        Args:
            expected_elements: Expected number of elements
            fpr: Desired false positive rate (default 1%)

        Raises:
            ValueError: If parameters are invalid
        """
        if expected_elements <= 0:
            raise ValueError("expected_elements must be positive")
        if not (0 < fpr < 1):
            raise ValueError("fpr must be between 0 and 1")

        self._expected = expected_elements
        self._fpr = fpr

        # Calculate optimal size and hash count
        # m = -n * ln(p) / (ln(2)^2)
        # k = (m/n) * ln(2)
        self._size = self._optimal_size(expected_elements, fpr)
        self._hash_count = self._optimal_hash_count(self._size, expected_elements)

        # Bit array (using bytearray for memory efficiency)
        self._bits = bytearray((self._size + 7) // 8)
        self._count = 0

    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        """Calculate optimal bit array size"""
        m = -n * math.log(p) / (math.log(2) ** 2)
        return max(64, int(math.ceil(m)))  # Minimum 64 bits

    @staticmethod
    def _optimal_hash_count(m: int, n: int) -> int:
        """Calculate optimal number of hash functions"""
        k = (m / n) * math.log(2)
        return max(1, min(10, int(round(k))))  # 1-10 hash functions

    def _get_bit_positions(self, item: str) -> list[int]:
        """
        Get bit positions for item using double hashing.

        Uses double hashing technique:
        h(i) = h1 + i * h2 (mod m)

        This is more efficient than computing k independent hashes.
        """
        # Use SHA256 for good distribution
        h = hashlib.sha256(item.encode()).digest()

        # Extract two 64-bit hashes from digest
        h1 = int.from_bytes(h[:8], "big")
        h2 = int.from_bytes(h[8:16], "big")

        positions = []
        for i in range(self._hash_count):
            pos = (h1 + i * h2) % self._size
            positions.append(pos)

        return positions

    def add(self, item: str) -> None:
        """
        Add item to filter.

        Args:
            item: String to add

        Time: O(k) where k = hash count
        """
        for pos in self._get_bit_positions(item):
            byte_idx = pos // 8
            bit_idx = pos % 8
            self._bits[byte_idx] |= 1 << bit_idx
        self._count += 1

    def add_many(self, items: Iterable[str]) -> int:
        """
        Add multiple items efficiently.

        Args:
            items: Iterable of strings

        Returns:
            Number of items added
        """
        count = 0
        for item in items:
            self.add(item)
            count += 1
        return count

    def __contains__(self, item: str) -> bool:
        """
        Check if item might be in filter.

        Returns:
            True: Item might be present (check actual index)
            False: Item definitely not present

        Time: O(k)
        """
        for pos in self._get_bit_positions(item):
            byte_idx = pos // 8
            bit_idx = pos % 8
            if not (self._bits[byte_idx] & (1 << bit_idx)):
                return False
        return True

    def might_contain(self, item: str) -> bool:
        """Alias for __contains__ (explicit naming)"""
        return item in self

    def definitely_not_contains(self, item: str) -> bool:
        """Inverse check - more explicit for pre-filtering"""
        return item not in self

    def clear(self) -> None:
        """Clear all bits"""
        self._bits = bytearray((self._size + 7) // 8)
        self._count = 0

    @property
    def count(self) -> int:
        """Number of items added"""
        return self._count

    @property
    def size_bits(self) -> int:
        """Size in bits"""
        return self._size

    @property
    def size_bytes(self) -> int:
        """Size in bytes"""
        return len(self._bits)

    @property
    def estimated_fpr(self) -> float:
        """
        Estimate current false positive rate.

        Formula: (1 - e^(-kn/m))^k
        """
        if self._count == 0:
            return 0.0
        exponent = -self._hash_count * self._count / self._size
        return (1 - math.exp(exponent)) ** self._hash_count

    def get_stats(self) -> dict:
        """Get filter statistics"""
        return {
            "expected_elements": self._expected,
            "target_fpr": self._fpr,
            "size_bits": self._size,
            "size_bytes": self.size_bytes,
            "hash_count": self._hash_count,
            "items_added": self._count,
            "estimated_fpr": round(self.estimated_fpr, 6),
            "fill_ratio": round(self._count / self._expected, 3) if self._expected > 0 else 0,
        }


class EdgeBloomFilter:
    """
    Specialized Bloom Filter for edge existence checks.

    Encodes edges as "from_node:to_node" strings.
    Useful for quick "is there an edge?" queries.

    Usage:
        ebf = EdgeBloomFilter(expected_edges=50000)
        ebf.add_edge("node:1", "node:2")

        if ebf.might_have_edge("node:1", "node:2"):
            # Check actual edge index
    """

    def __init__(self, expected_edges: int = 50000, fpr: float = 0.01):
        self._filter = BloomFilter(expected_edges, fpr)

    def _encode_edge(self, from_node: str, to_node: str) -> str:
        """Encode edge as string"""
        return f"{from_node}→{to_node}"

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add edge to filter"""
        self._filter.add(self._encode_edge(from_node, to_node))

    def might_have_edge(self, from_node: str, to_node: str) -> bool:
        """Check if edge might exist"""
        return self._encode_edge(from_node, to_node) in self._filter

    def definitely_no_edge(self, from_node: str, to_node: str) -> bool:
        """Check if edge definitely doesn't exist"""
        return not self.might_have_edge(from_node, to_node)

    def get_stats(self) -> dict:
        return self._filter.get_stats()


class ReachabilityBloomFilter:
    """
    Bloom Filter for node reachability pre-checking.

    Stores "can reach X" information per node.
    Used to quickly reject impossible paths.

    Algorithm:
    1. During graph build, record reachable nodes per source
    2. Before path search: check if target might be reachable
    3. If definitely_unreachable: skip expensive traversal

    Usage:
        rbf = ReachabilityBloomFilter()
        rbf.add_reachable("source", "target")

        if rbf.might_reach("source", "target"):
            # Do expensive path search
        else:
            # Skip - definitely unreachable
    """

    def __init__(self, expected_pairs: int = 100000, fpr: float = 0.001):
        """
        Initialize with lower FPR for reachability (0.1% default).

        Lower FPR because false positives mean wasted path searches.
        """
        self._filter = BloomFilter(expected_pairs, fpr)

    def _encode_pair(self, source: str, target: str) -> str:
        return f"{source}⇝{target}"

    def add_reachable(self, source: str, target: str) -> None:
        """Record that source can reach target"""
        self._filter.add(self._encode_pair(source, target))

    def might_reach(self, source: str, target: str) -> bool:
        """Check if source might reach target"""
        return self._encode_pair(source, target) in self._filter

    def definitely_unreachable(self, source: str, target: str) -> bool:
        """Check if source definitely cannot reach target"""
        return not self.might_reach(source, target)

    def get_stats(self) -> dict:
        return self._filter.get_stats()
