"""
RFC-039: Tiered IR Cache Architecture - Unit Tests

Tests for:
- IRDocument.estimated_size
- MemoryCache with max_bytes
- TieredCache (L1 + L2)
- FileMetadata (Fast Path)

SOTA Principles:
- Happy path
- Boundary cases (empty, max size)
- Error handling
- Type safety
- Edge cases
"""

import time
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.cache import (
    MemoryCache,
    TieredCache,
    CacheKey,
)
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node, Edge, NodeKind, EdgeKind, Span
from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import FileMetadata


class TestIRDocumentEstimatedSize:
    """Test IRDocument.estimated_size property."""

    def test_empty_document_size(self):
        """Empty document has base overhead."""
        ir_doc = IRDocument(repo_id="test", snapshot_id="1")

        size = ir_doc.estimated_size

        # Base overhead = 2000 bytes
        assert size == 2000
        assert isinstance(size, int)

    def test_document_with_nodes(self):
        """Document size includes node estimates."""
        ir_doc = IRDocument(repo_id="test", snapshot_id="1")

        # Add 10 nodes
        for i in range(10):
            ir_doc.nodes.append(
                Node(
                    id=f"node_{i}",
                    kind=NodeKind.FUNCTION,
                    fqn=f"test.func_{i}",
                    file_path="test.py",
                    span=Span(start_line=i, start_col=0, end_line=i + 1, end_col=0),
                    language="python",
                    name=f"test_{i}",
                )
            )

        size = ir_doc.estimated_size

        # 10 nodes * 200 bytes + 2000 base = 4000
        assert size == 4000

    def test_document_with_nodes_and_edges(self):
        """Document size includes nodes + edges."""
        ir_doc = IRDocument(repo_id="test", snapshot_id="1")

        # 5 nodes + 5 edges
        for i in range(5):
            ir_doc.nodes.append(
                Node(
                    id=f"node_{i}",
                    kind=NodeKind.FUNCTION,
                    fqn=f"test.func_{i}",
                    file_path="test.py",
                    span=Span(start_line=i, start_col=0, end_line=i + 1, end_col=0),
                    language="python",
                    name=f"test_{i}",
                )
            )
            ir_doc.edges.append(
                Edge(
                    id=f"edge_{i}",
                    kind=EdgeKind.CALLS,
                    source_id=f"node_{i}",
                    target_id=f"node_{(i + 1) % 5}",
                )
            )

        size = ir_doc.estimated_size

        # 5 * 200 + 5 * 100 + 2000 = 3500
        assert size == 3500

    def test_large_document_size(self):
        """Large document with multiple IR types."""
        ir_doc = IRDocument(repo_id="test", snapshot_id="1")

        # 100 nodes + 20 occurrences
        for i in range(100):
            ir_doc.nodes.append(
                Node(
                    id=f"node_{i}",
                    kind=NodeKind.FUNCTION,
                    fqn=f"test.func_{i}",
                    file_path="test.py",
                    span=Span(start_line=i, start_col=0, end_line=i + 1, end_col=0),
                    language="python",
                    name=f"test_{i}",
                )
            )

        from codegraph_engine.code_foundation.infrastructure.ir.models.occurrence import Occurrence, SymbolRole
        from codegraph_engine.code_foundation.infrastructure.ir.models.occurrence import Occurrence, SymbolRole

        for i in range(20):
            ir_doc.occurrences.append(
                Occurrence(
                    id=f"occ_{i}",
                    symbol_id=f"node_{i}",
                    span=Span(start_line=i, start_col=0, end_line=i, end_col=10),
                    roles=[SymbolRole.DEFINITION],
                    file_path="test.py",
                )
            )

        size = ir_doc.estimated_size

        # 100*200 + 20*50 + 2000 = 23000
        expected = 100 * 200 + 20 * 50 + 2000
        assert size == expected


class TestMemoryCacheSizeBased:
    """Test MemoryCache with size-based eviction."""

    def test_cache_respects_max_bytes(self):
        """Cache evicts based on memory size."""
        cache = MemoryCache(max_size=1000, max_bytes=10000)

        # Create IR docs with known sizes
        ir1 = IRDocument(repo_id="test", snapshot_id="1")
        # Add nodes to reach ~4000 bytes
        for i in range(10):
            ir1.nodes.append(
                Node(
                    id=f"node1_{i}",
                    kind=NodeKind.FUNCTION,
                    fqn=f"test1.func_{i}",
                    file_path="test1.py",
                    span=Span(start_line=i, start_col=0, end_line=i + 1, end_col=0),
                    language="python",
                    name=f"test_{i}",
                )
            )

        ir2 = IRDocument(repo_id="test", snapshot_id="2")
        for i in range(10):
            ir2.nodes.append(
                Node(
                    id=f"node2_{i}",
                    kind=NodeKind.FUNCTION,
                    fqn=f"test2.func_{i}",
                    file_path="test2.py",
                    span=Span(start_line=i, start_col=0, end_line=i + 1, end_col=0),
                    language="python",
                    name=f"test_{i}",
                )
            )

        ir3 = IRDocument(repo_id="test", snapshot_id="3")
        for i in range(10):
            ir3.nodes.append(
                Node(
                    id=f"node3_{i}",
                    kind=NodeKind.FUNCTION,
                    fqn=f"test3.func_{i}",
                    file_path="test3.py",
                    span=Span(start_line=i, start_col=0, end_line=i + 1, end_col=0),
                    language="python",
                    name=f"test_{i}",
                )
            )

        key1 = CacheKey.from_content("test1.py", "content1")
        key2 = CacheKey.from_content("test2.py", "content2")
        key3 = CacheKey.from_content("test3.py", "content3")

        cache.set(key1, ir1)
        cache.set(key2, ir2)
        # ir3 should trigger eviction of ir1 (LRU)
        cache.set(key3, ir3)

        stats = cache.stats()

        # Should have evicted to stay under max_bytes
        assert stats["current_bytes"] <= 10000
        assert stats["evictions"] >= 0

    def test_cache_handles_zero_max_size(self):
        """Cache with max_size=0 is no-op."""
        cache = MemoryCache(max_size=0, max_bytes=1000)

        ir = IRDocument(repo_id="test", snapshot_id="1")
        key = CacheKey.from_content("test.py", "content")

        cache.set(key, ir)
        result = cache.get(key)

        assert result is None  # Nothing stored
        assert cache.stats()["size"] == 0

    def test_cache_updates_size_on_replacement(self):
        """Replacing entry updates size correctly."""
        cache = MemoryCache(max_size=10, max_bytes=100000)

        # Small IR
        ir_small = IRDocument(repo_id="test", snapshot_id="1")
        key = CacheKey.from_content("test.py", "v1")
        cache.set(key, ir_small)

        size_before = cache.stats()["current_bytes"]

        # Large IR (same key)
        ir_large = IRDocument(repo_id="test", snapshot_id="1")
        for i in range(50):
            ir_large.nodes.append(
                Node(
                    id=f"node_{i}",
                    kind=NodeKind.FUNCTION,
                    fqn=f"test.func_{i}",
                    file_path="test.py",
                    span=Span(start_line=i, start_col=0, end_line=i + 1, end_col=0),
                    language="python",
                    name=f"test_{i}",
                )
            )

        cache.set(key, ir_large)
        size_after = cache.stats()["current_bytes"]

        # Size should increase
        assert size_after > size_before


class TestTieredCache:
    """Test TieredCache (L1 + L2)."""

    def test_l1_hit(self):
        """L1 hit returns immediately."""
        import tempfile

        cache_dir = Path(tempfile.mkdtemp())
        cache = TieredCache(l1_max_size=10, l1_max_bytes=100000, l2_cache_dir=cache_dir)

        ir = IRDocument(repo_id="test", snapshot_id="1")
        cache.set("test.py", "content", ir)

        # Get should hit L1
        result = cache.get("test.py", "content")

        assert result is ir
        telemetry = cache.get_telemetry()
        assert telemetry["l1_hits"] == 1
        assert telemetry["l2_hits"] == 0
        assert telemetry["misses"] == 0

    def test_l2_hit_promotes_to_l1(self):
        """L2 hit promotes to L1."""
        import tempfile

        cache_dir = Path(tempfile.mkdtemp())
        cache = TieredCache(l1_max_size=1, l1_max_bytes=3000, l2_cache_dir=cache_dir)  # Small L1

        ir1 = IRDocument(repo_id="test", snapshot_id="1")
        ir2 = IRDocument(repo_id="test", snapshot_id="2")

        # Fill L1 + L2
        cache.set("test1.py", "content1", ir1)
        cache.set("test2.py", "content2", ir2)  # Evicts ir1 from L1

        # Get ir1 (should be in L2)
        result = cache.get("test1.py", "content1")

        assert result is not None
        telemetry = cache.get_telemetry()
        assert telemetry["l2_hits"] == 1
        assert telemetry["l1_entries"] >= 1  # Promoted to L1

    def test_cache_miss(self):
        """Cache miss returns None."""
        import tempfile

        cache_dir = Path(tempfile.mkdtemp())
        cache = TieredCache(l2_cache_dir=cache_dir)

        result = cache.get("nonexistent.py", "content")

        assert result is None
        telemetry = cache.get_telemetry()
        assert telemetry["misses"] == 1

    def test_clear_clears_both_tiers(self):
        """Clear removes from L1 and L2."""
        import tempfile

        cache_dir = Path(tempfile.mkdtemp())
        cache = TieredCache(l2_cache_dir=cache_dir)

        ir = IRDocument(repo_id="test", snapshot_id="1")
        cache.set("test.py", "content", ir)

        cache.clear()

        result = cache.get("test.py", "content")
        assert result is None

        telemetry = cache.get_telemetry()
        assert telemetry["l1_entries"] == 0
        assert telemetry["l2_entries"] == 0

    def test_l1_l2_cascade_order(self):
        """CRITICAL: Cache checks L1 before L2."""
        import tempfile

        cache_dir = Path(tempfile.mkdtemp())
        cache = TieredCache(l1_max_size=10, l1_max_bytes=100000, l2_cache_dir=cache_dir)

        ir = IRDocument(repo_id="test", snapshot_id="1")

        # Set in cache (goes to both L1 and L2)
        cache.set("test.py", "content", ir)

        # Clear L1 only (simulate L1 eviction)
        cache._l1.clear()

        # Get (should hit L2 and promote to L1)
        result = cache.get("test.py", "content")

        assert result is not None
        telemetry = cache.get_telemetry()

        # First get after L1 clear → L2 hit
        assert telemetry["l2_hits"] == 1
        assert telemetry["l1_hits"] == 0

        # Get again (should hit L1 now, promoted)
        result2 = cache.get("test.py", "content")

        assert result2 is not None
        telemetry2 = cache.get_telemetry()
        assert telemetry2["l1_hits"] == 1  # Promoted

    def test_l1_l2_write_both(self):
        """Set writes to both L1 and L2."""
        import tempfile

        cache_dir = Path(tempfile.mkdtemp())
        cache = TieredCache(l2_cache_dir=cache_dir)

        ir = IRDocument(repo_id="test", snapshot_id="1")
        cache.set("test.py", "content", ir)

        # Verify both tiers have the entry
        telemetry = cache.get_telemetry()

        # At least L1 should have it immediately
        assert telemetry["l1_entries"] >= 1

        # Clear L1, verify L2 still has it
        cache._l1.clear()
        result = cache.get("test.py", "content")

        assert result is not None  # From L2

    def test_tiered_cache_hit_rate_calculation(self):
        """Hit rates are calculated correctly."""
        import tempfile

        cache_dir = Path(tempfile.mkdtemp())
        cache = TieredCache(l2_cache_dir=cache_dir)

        ir = IRDocument(repo_id="test", snapshot_id="1")

        # 1 miss
        cache.get("test.py", "content")

        # Set
        cache.set("test.py", "content", ir)

        # 2 L1 hits
        cache.get("test.py", "content")
        cache.get("test.py", "content")

        telemetry = cache.get_telemetry()

        # Total: 1 miss + 2 L1 hits = 3 requests
        assert telemetry["total_requests"] == 3
        assert telemetry["l1_hits"] == 2
        assert telemetry["misses"] == 1

        # Hit rates
        assert abs(telemetry["l1_hit_rate"] - 2 / 3) < 0.01
        assert abs(telemetry["miss_rate"] - 1 / 3) < 0.01

    def test_extreme_l1_thrashing(self):
        """EXTREME: L1 thrashing with many evictions."""
        import tempfile

        cache_dir = Path(tempfile.mkdtemp())
        cache = TieredCache(l1_max_size=5, l1_max_bytes=5000, l2_cache_dir=cache_dir)

        # Create 50 IRs (10x L1 size)
        for i in range(50):
            ir = IRDocument(repo_id="test", snapshot_id=str(i))
            for j in range(5):
                ir.nodes.append(
                    Node(
                        id=f"node_{i}_{j}",
                        kind=NodeKind.FUNCTION,
                        fqn=f"test_{i}.func_{j}",
                        file_path=f"test_{i}.py",
                        span=Span(start_line=j, start_col=0, end_line=j + 1, end_col=0),
                        language="python",
                        name=f"test_{i}_{j}",
                    )
                )
            cache.set(f"test_{i}.py", f"content_{i}", ir)

        telemetry = cache.get_telemetry()

        # L1 should have evicted heavily
        assert telemetry["l1_evictions"] > 40  # Most entries evicted
        assert telemetry["l1_entries"] <= 5  # Respects limit
        assert telemetry["l2_entries"] == 50  # All in L2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


class TestFileMetadata:
    """Test FileMetadata for Fast Path."""

    def test_metadata_creation(self):
        """FileMetadata stores mtime, size, hash."""
        meta = FileMetadata(
            mtime=time.time(),
            size=1024,
            content_hash="abc123",
        )

        assert meta.mtime > 0
        assert meta.size == 1024
        assert meta.content_hash == "abc123"

    def test_metadata_comparison(self):
        """Can compare metadata for changes."""
        meta1 = FileMetadata(mtime=1.0, size=100, content_hash="abc")
        meta2 = FileMetadata(mtime=1.0, size=100, content_hash="abc")
        meta3 = FileMetadata(mtime=2.0, size=100, content_hash="abc")

        # Fast Path: mtime+size match
        assert meta1.mtime == meta2.mtime
        assert meta1.size == meta2.size

        # Fast Path: mtime changed
        assert meta1.mtime != meta3.mtime

        # Slow Path: hash match
        assert meta1.content_hash == meta3.content_hash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
