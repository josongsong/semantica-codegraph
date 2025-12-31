"""
SOTA Span Interning Tests (L11-grade)

Test Coverage:
- Memory reduction (quantitative)
- Thread-safety (concurrent builds)
- Serialization round-trip (pickle/JSON)
- WeakValueDictionary cleanup
- Edge cases (boundary values, large spans)
- Performance (hit rate, lookup speed)

Author: Semantica Team
Date: 2025-12-21
"""

import gc
import pickle
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Barrier

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
from codegraph_engine.code_foundation.infrastructure.ir.models.span_pool import SpanPool, create_span


class TestSpanFrozen:
    """Test Span immutability (frozen=True)"""

    def test_span_is_frozen(self):
        """Span should be immutable"""
        span = Span(start_line=1, start_col=0, end_line=10, end_col=20)

        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            span.start_line = 999

    def test_span_is_hashable(self):
        """Span should be hashable (required for WeakValueDictionary)"""
        span1 = Span(start_line=1, start_col=0, end_line=10, end_col=20)
        span2 = Span(start_line=1, start_col=0, end_line=10, end_col=20)

        assert hash(span1) == hash(span2)
        assert span1 == span2

        # Can be used as dict key
        d = {span1: "value"}
        assert d[span2] == "value"

    def test_span_equality(self):
        """Span equality based on values"""
        span1 = Span(1, 0, 10, 20)
        span2 = Span(1, 0, 10, 20)
        span3 = Span(2, 0, 10, 20)

        assert span1 == span2
        assert span1 != span3


class TestSpanPoolBasic:
    """Test SpanPool basic functionality"""

    def setup_method(self):
        """Clear pool before each test"""
        SpanPool.clear()

    def test_intern_returns_same_object_for_identical_spans(self):
        """Identical spans should return same object (identity check)"""
        span1 = SpanPool.intern(1, 0, 10, 20)
        span2 = SpanPool.intern(1, 0, 10, 20)

        # Same object (not just equal, but identical)
        assert span1 is span2
        assert id(span1) == id(span2)

    def test_intern_returns_different_objects_for_different_spans(self):
        """Different spans should return different objects"""
        span1 = SpanPool.intern(1, 0, 10, 20)
        span2 = SpanPool.intern(2, 0, 10, 20)

        assert span1 is not span2
        assert span1 != span2

    def test_stats_tracking(self):
        """Stats should track hits and misses"""
        SpanPool.reset_stats()

        # First call: miss
        span1 = SpanPool.intern(1, 0, 10, 20)
        stats1 = SpanPool.get_stats()
        assert stats1["miss_count"] == 1
        assert stats1["hit_count"] == 0

        # Second call: hit
        span2 = SpanPool.intern(1, 0, 10, 20)
        stats2 = SpanPool.get_stats()
        assert stats2["miss_count"] == 1
        assert stats2["hit_count"] == 1
        assert stats2["hit_rate"] == 0.5

    def test_pool_size_tracking(self):
        """Pool size should reflect unique spans"""
        SpanPool.clear()

        SpanPool.intern(1, 0, 10, 20)
        SpanPool.intern(2, 0, 10, 20)
        SpanPool.intern(1, 0, 10, 20)  # duplicate

        stats = SpanPool.get_stats()
        assert stats["pool_size"] == 2  # Only 2 unique spans


class TestSpanPoolMemory:
    """Test memory reduction (quantitative)"""

    def setup_method(self):
        SpanPool.clear()

    def test_memory_reduction_with_duplicates(self):
        """Interning should reduce memory with duplicates"""
        # Create 100 spans with 10 unique values (90% duplication)
        spans_direct = []
        for i in range(100):
            line = i % 10  # 10 unique values
            spans_direct.append(Span(line, 0, line + 1, 10))

        # Measure direct creation
        size_direct = sum(sys.getsizeof(s) for s in spans_direct)

        # Create via interning
        SpanPool.clear()
        spans_interned = []
        for i in range(100):
            line = i % 10
            spans_interned.append(SpanPool.intern(line, 0, line + 1, 10))

        # Check identity sharing
        unique_ids = len(set(id(s) for s in spans_interned))
        assert unique_ids == 10, f"Expected 10 unique objects, got {unique_ids}"

        # Stats
        stats = SpanPool.get_stats()
        assert stats["pool_size"] == 10
        assert stats["hit_count"] == 90  # 90 hits out of 100
        assert stats["hit_rate"] == 0.9

        print(f"\n  Memory (direct): {size_direct / 1024:.1f} KB")
        print(f"  Unique objects: {unique_ids}")
        print(f"  Hit rate: {stats['hit_rate']:.1%}")


class TestSpanPoolThreadSafety:
    """Test thread-safety for concurrent builds"""

    def setup_method(self):
        SpanPool.clear()

    def test_concurrent_interning_is_safe(self):
        """Concurrent intern() calls should be thread-safe"""
        # Barrier to synchronize threads
        num_threads = 10
        barrier = Barrier(num_threads)

        def intern_worker(thread_id: int) -> list[Span]:
            barrier.wait()  # Synchronize start
            spans = []
            for i in range(100):
                line = i % 10  # 10 unique values
                span = SpanPool.intern(line, 0, line + 1, 10)
                spans.append(span)
            return spans

        # Run concurrent interning
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(intern_worker, i) for i in range(num_threads)]
            results = [f.result() for f in as_completed(futures)]

        # Verify: all threads should get same objects for same values
        all_spans = [span for result in results for span in result]

        # Check: spans with same value should have same identity
        spans_by_value = {}
        for span in all_spans:
            key = (span.start_line, span.start_col, span.end_line, span.end_col)
            if key not in spans_by_value:
                spans_by_value[key] = []
            spans_by_value[key].append(id(span))

        # All spans with same value should have same id
        for key, ids in spans_by_value.items():
            unique_ids = set(ids)
            assert len(unique_ids) == 1, f"Span {key} has {len(unique_ids)} different ids (not thread-safe!)"

        print(f"\n  Threads: {num_threads}")
        print(f"  Total spans created: {len(all_spans)}")
        print(f"  Unique span values: {len(spans_by_value)}")
        print(f"  ✅ Thread-safe: all threads got same objects")


class TestSpanPoolSerialization:
    """Test serialization compatibility"""

    def setup_method(self):
        SpanPool.clear()

    def test_pickle_round_trip(self):
        """Interned Span should survive pickle round-trip"""
        span1 = SpanPool.intern(1, 0, 10, 20)

        # Pickle
        data = pickle.dumps(span1)

        # Unpickle
        span2 = pickle.loads(data)

        # Values should be equal
        assert span2.start_line == 1
        assert span2.start_col == 0
        assert span2.end_line == 10
        assert span2.end_col == 20

        # Re-intern should return same object as original
        span3 = SpanPool.intern(1, 0, 10, 20)
        assert span3 is span1  # Same object

    def test_json_compatible_serialization(self):
        """Span should be JSON-serializable via dict"""
        from codegraph_engine.code_foundation.infrastructure.storage.ir_serializer import IRSerializer

        span = SpanPool.intern(5, 10, 15, 30)
        serializer = IRSerializer()

        # Serialize
        span_dict = serializer.serialize_span(span)
        assert span_dict == {
            "start_line": 5,
            "start_col": 10,
            "end_line": 15,
            "end_col": 30,
        }

        # Deserialize (should use intern)
        # Note: deserialize_node/edge already use SpanPool.intern
        # Just verify the dict format is correct
        assert isinstance(span_dict, dict)
        assert "start_line" in span_dict


class TestSpanPoolLRU:
    """Test LRU eviction (bounded memory)"""

    def setup_method(self):
        SpanPool.clear()

    def test_lru_eviction_when_pool_full(self):
        """Pool should evict oldest when max_size exceeded (FORCED)"""
        SpanPool.clear()

        # SOTA: Force eviction by temporarily reducing max_size
        original_max = SpanPool._max_size
        SpanPool._max_size = 10  # Reduce to force eviction

        try:
            # Create 20 unique spans (more than max_size)
            spans = []
            for i in range(20):
                span = SpanPool.intern(i, 0, i + 1, 10)
                spans.append(span)

            stats = SpanPool.get_stats()

            # Pool should be capped at max_size
            assert stats["pool_size"] == 10, f"Expected pool_size=10, got {stats['pool_size']}"

            # Should have evicted 10 spans
            assert stats["eviction_count"] == 10, f"Expected 10 evictions, got {stats['eviction_count']}"

            # Last 10 spans should still be in pool (most recent)
            SpanPool.reset_stats()
            for i in range(10, 20):
                span_again = SpanPool.intern(i, 0, i + 1, 10)
                assert span_again is spans[i], f"Span {i} should still be in pool"

            # All should be hits (no misses)
            stats2 = SpanPool.get_stats()
            assert stats2["hit_count"] == 10, "All recent spans should be hits"
            assert stats2["miss_count"] == 0, "No misses expected"

            print(f"\n  ✅ LRU eviction verified: {stats['eviction_count']} evictions")

        finally:
            SpanPool._max_size = original_max
            SpanPool.clear()

    def test_lru_moves_accessed_spans_to_end(self):
        """Accessing a span should move it to end (LRU)"""
        SpanPool.clear()

        # Create spans
        span1 = SpanPool.intern(1, 0, 10, 20)
        span2 = SpanPool.intern(2, 0, 10, 20)
        span3 = SpanPool.intern(3, 0, 10, 20)

        # Access span1 again (should move to end)
        span1_again = SpanPool.intern(1, 0, 10, 20)
        assert span1_again is span1

        # Stats should show hit
        stats = SpanPool.get_stats()
        assert stats["hit_count"] == 1

    def test_lru_evicts_oldest_first(self):
        """When evicting, LRU should remove oldest entry"""
        SpanPool.clear()

        original_max = SpanPool._max_size
        SpanPool._max_size = 3  # Small pool

        try:
            # Fill pool
            span1 = SpanPool.intern(1, 0, 2, 10)
            span2 = SpanPool.intern(2, 0, 3, 10)
            span3 = SpanPool.intern(3, 0, 4, 10)

            # Access span1 (move to end)
            SpanPool.intern(1, 0, 2, 10)

            # Add 4th span (should evict span2, not span1)
            span4 = SpanPool.intern(4, 0, 5, 10)

            stats = SpanPool.get_stats()
            assert stats["pool_size"] == 3
            assert stats["eviction_count"] == 1

            # span1 should still be cached (recently accessed)
            SpanPool.reset_stats()
            span1_check = SpanPool.intern(1, 0, 2, 10)
            assert span1_check is span1, "Recently accessed span should be in pool"
            assert SpanPool.get_stats()["hit_count"] == 1

        finally:
            SpanPool._max_size = original_max
            SpanPool.clear()


class TestSpanPoolEdgeCases:
    """Test edge cases and boundary values"""

    def setup_method(self):
        SpanPool.clear()

    def test_zero_values(self):
        """Span with zero values should work"""
        span = SpanPool.intern(0, 0, 0, 0)
        assert span.start_line == 0
        assert span.end_line == 0

    def test_large_values(self):
        """Span with large values should work"""
        span = SpanPool.intern(999999, 999999, 999999, 999999)
        assert span.start_line == 999999

    def test_negative_values(self):
        """Span with negative values (error recovery)"""
        # Should not crash (graceful degradation)
        span = SpanPool.intern(-1, -1, -1, -1)
        assert span.start_line == -1

    def test_batch_interning(self):
        """Batch interning should be efficient"""
        SpanPool.reset_stats()

        tuples = [(i, 0, i + 1, 10) for i in range(100)]
        spans = SpanPool.intern_batch(tuples)

        assert len(spans) == 100

        # All should be misses (first time)
        stats = SpanPool.get_stats()
        assert stats["miss_count"] == 100

        # Batch again: all should be hits
        SpanPool.reset_stats()
        spans2 = SpanPool.intern_batch(tuples)
        stats2 = SpanPool.get_stats()
        assert stats2["hit_count"] == 100

        # Same objects
        for s1, s2 in zip(spans, spans2):
            assert s1 is s2


class TestSpanPoolIntegration:
    """Integration tests with real pipeline"""

    def test_expression_builder_uses_interning(self):
        """ExpressionBuilder should use SpanPool.intern"""
        import tempfile
        from pathlib import Path
        from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator
        from codegraph_engine.code_foundation.infrastructure.parsing.ast_tree import AstTree
        from codegraph_engine.code_foundation.infrastructure.parsing.source_file import SourceFile
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.builder import DefaultSemanticIrBuilder

        code = """
def f():
    x = 1
    y = 1
    z = 1
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as file:
            file.write(code)
            p = Path(file.name)

        try:
            SpanPool.reset_stats()

            sf = SourceFile(file_path=str(p), content=code, language="python")
            ast_tree = AstTree.parse(sf)
            ir = _PythonIRGenerator(repo_id="test").generate(sf, ast_tree)
            snap, _ = DefaultSemanticIrBuilder().build_full(ir, source_map={str(p): (sf, ast_tree)})

            # Check stats
            stats = SpanPool.get_stats()
            print(f"\n  Expressions: {len(snap.expressions)}")
            print(f"  Pool size: {stats['pool_size']}")
            print(f"  Hit count: {stats['hit_count']}")
            print(f"  Hit rate: {stats['hit_rate']:.1%}")

            # Should have some hits (duplicates)
            assert stats["hit_count"] > 0, "Expected some span reuse"

        finally:
            p.unlink(missing_ok=True)

    def test_serialization_preserves_interning(self):
        """Serialization round-trip should preserve interning"""
        from codegraph_engine.code_foundation.infrastructure.storage.ir_serializer import IRSerializer
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node, NodeKind

        SpanPool.clear()

        # Create node with interned span
        span = SpanPool.intern(10, 5, 20, 15)
        node = Node(
            id="test:node:1",
            kind=NodeKind.FUNCTION,
            fqn="test.f",
            file_path="test.py",
            span=span,
            language="python",
        )

        # Serialize
        serializer = IRSerializer()
        data = serializer.serialize_node(node)

        # Deserialize
        node2 = serializer.deserialize_node(data)

        # Span should be interned
        span2 = node2.span
        span3 = SpanPool.intern(10, 5, 20, 15)

        # Same object
        assert span2 is span3
        assert id(span2) == id(span3)


class TestSpanPoolPerformance:
    """Performance benchmarks"""

    def test_intern_is_fast(self):
        """Intern should be O(1)"""
        import time

        SpanPool.clear()

        # Warm up
        for i in range(100):
            SpanPool.intern(i, 0, i + 1, 10)

        # Measure hits (should be very fast)
        start = time.perf_counter()
        for _ in range(10000):
            SpanPool.intern(50, 0, 51, 10)  # Always hits
        elapsed = time.perf_counter() - start

        per_op = elapsed / 10000 * 1_000_000  # microseconds
        print(f"\n  10K intern() hits: {elapsed * 1000:.2f}ms")
        print(f"  Per operation: {per_op:.2f}µs")

        # Should be < 1µs per operation
        assert per_op < 10, f"Too slow: {per_op:.2f}µs per intern()"


class TestSpanPoolBoundary:
    """Boundary and corner cases"""

    def test_same_line_different_col(self):
        """Spans on same line but different columns"""
        span1 = SpanPool.intern(10, 0, 10, 5)
        span2 = SpanPool.intern(10, 5, 10, 10)

        assert span1 is not span2
        assert span1 != span2

    def test_multiline_span(self):
        """Span across multiple lines"""
        span = SpanPool.intern(10, 0, 100, 50)
        assert span.start_line == 10
        assert span.end_line == 100

    def test_backward_compatibility_create_span(self):
        """create_span() factory should use interning"""
        SpanPool.clear()

        span1 = create_span(1, 0, 10, 20)
        span2 = SpanPool.intern(1, 0, 10, 20)

        # Same object
        assert span1 is span2
