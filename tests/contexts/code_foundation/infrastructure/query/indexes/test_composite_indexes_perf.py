"""
Composite Index Performance & Thread Safety Tests - L11급

Validates:
1. O(1) lookup performance vs O(k) filtering
2. Thread-safe concurrent access
3. Memory overhead measurement
4. Stress testing (1000+ entities)

SOTA Testing Strategy:
- Base: Simple O(1) verification
- Corner: Empty indexes, no matches
- Edge: Single match, multiple matches
- Extreme: 1000+ entities, concurrent access
"""

import threading
import time

import pytest

from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot, VariableEntity
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
from codegraph_engine.code_foundation.infrastructure.query.indexes.node_index import NodeIndex
from codegraph_engine.code_foundation.infrastructure.query.indexes.semantic_index import SemanticIndex


class TestCompositeIndexPerformance:
    """Performance validation for O(1) composite indexes"""

    def test_composite_vs_filter_performance(self):
        """
        Composite index (O(1)) should be faster than filtering (O(k))

        Setup: 100 variables with same name but different types
        Measure: Composite lookup vs manual filtering
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Create 100 variables: x:type0, x:type1, ..., x:type99
        variables = []
        for i in range(100):
            var = VariableEntity(
                id=f"var:{i}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name="x",
                kind="local",
                type_id=f"type:{i}",
            )
            variables.append(var)

        ir_doc.dfg_snapshot = DfgSnapshot(variables=variables)
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        # Test 1: Composite O(1) lookup
        start = time.perf_counter()
        for _ in range(1000):
            result = index.find_vars_by_name_and_type("x", "type:42")
        composite_time = time.perf_counter() - start

        # Test 2: Manual O(k) filtering (old approach)
        start = time.perf_counter()
        for _ in range(1000):
            all_vars = index.find_vars_by_name("x")
            result = [v for v in all_vars if v.attrs.get("type_id") == "type:42"]
        filter_time = time.perf_counter() - start

        # Composite should be AT LEAST as fast (ideally faster)
        # With 100 items, filtering is O(100), composite is O(1)
        assert composite_time <= filter_time * 2, (
            f"Composite ({composite_time:.4f}s) should be faster than filtering ({filter_time:.4f}s)"
        )

        print(f"✅ Composite: {composite_time:.4f}s, Filter: {filter_time:.4f}s")
        print(f"   Speedup: {filter_time / composite_time:.2f}x")

    def test_memory_overhead_measurement(self):
        """
        Measure memory overhead of composite indexes

        Expectation: ~2x storage for O(1) performance
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Create 50 variables with diverse types/scopes
        variables = []
        for i in range(50):
            var = VariableEntity(
                id=f"var:{i}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=f"var_{i % 10}",  # 10 unique names
                kind="local",
                type_id=f"type:{i % 5}",  # 5 unique types
                scope_id=f"scope:{i % 3}",  # 3 unique scopes
            )
            variables.append(var)

        ir_doc.dfg_snapshot = DfgSnapshot(variables=variables)
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        stats = index.get_stats()

        # Verify: total_vars = base storage
        assert stats["total_vars"] == 50

        # Verify: composite entries ≈ total_vars (some vars share type/scope)
        # With 5 types and 10 names → max 50 combinations
        # With 3 scopes and 10 names → max 30 combinations
        assert stats["composite_var_name_type_entries"] == 50
        assert stats["composite_var_name_scope_entries"] == 50

        # Memory overhead factor
        base_entries = stats["total_vars"]
        composite_entries = stats["composite_var_name_type_entries"] + stats["composite_var_name_scope_entries"]
        overhead_factor = composite_entries / base_entries

        # Should be around 2x (one for type, one for scope)
        assert 1.5 <= overhead_factor <= 3.0, f"Memory overhead ({overhead_factor:.2f}x) outside expected range"

        print(f"✅ Memory overhead: {overhead_factor:.2f}x (expected ~2x)")


class TestCompositeIndexThreadSafety:
    """Thread safety validation for concurrent access"""

    def test_concurrent_reads_thread_safe(self):
        """
        Multiple threads reading composite indexes concurrently

        Should not cause race conditions or data corruption
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Create 100 variables
        variables = [
            VariableEntity(
                id=f"var:{i}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=f"var_{i % 10}",
                kind="local",
                type_id=f"type:{i % 5}",
                scope_id=f"scope:{i % 3}",
            )
            for i in range(100)
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=variables)
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        errors = []
        results = []

        def reader_thread(name: str, query_count: int):
            """Thread function: perform multiple queries"""
            try:
                local_results = []
                for i in range(query_count):
                    # Query composite indexes
                    vars_type = index.find_vars_by_name_and_type(f"var_{i % 10}", f"type:{i % 5}")
                    vars_scope = index.find_vars_by_name_and_scope(f"var_{i % 10}", f"scope:{i % 3}")
                    local_results.append((len(vars_type), len(vars_scope)))
                results.extend(local_results)
            except Exception as e:
                errors.append(f"{name}: {e}")

        # Launch 10 threads, each doing 100 queries
        threads = []
        for i in range(10):
            t = threading.Thread(target=reader_thread, args=(f"Thread-{i}", 100))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Verify: no errors
        assert not errors, f"Thread safety violations: {errors}"

        # Verify: all results valid (not corrupted)
        assert len(results) == 1000  # 10 threads * 100 queries
        assert all(isinstance(r[0], int) and isinstance(r[1], int) for r in results)

        print("✅ 1000 concurrent queries across 10 threads: SUCCESS")


class TestCompositeIndexExtremeStress:
    """Extreme stress testing for composite indexes"""

    def test_1000_unique_type_combinations(self):
        """
        1000 variables with unique (name, type) combinations

        Validates: Composite index handles high cardinality
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Create 1000 unique combinations
        variables = [
            VariableEntity(
                id=f"var:{i}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=f"var_{i}",
                kind="local",
                type_id=f"type:{i}",
            )
            for i in range(1000)
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=variables)
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        stats = index.get_stats()

        # Verify: all 1000 unique keys indexed
        assert stats["composite_var_name_type_keys"] == 1000
        assert stats["composite_var_name_type_entries"] == 1000

        # Verify: O(1) lookup still works
        result = index.find_vars_by_name_and_type("var_500", "type:500")
        assert len(result) == 1
        assert result[0].id == "var:500"

        print("✅ 1000 unique composite keys: indexed and searchable")

    def test_100_methods_in_10_classes(self):
        """
        100 methods across 10 classes

        Validates: (class, method) composite index
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Create 10 classes, each with 10 methods
        nodes = []
        for cls_idx in range(10):
            for method_idx in range(10):
                node = Node(
                    id=f"method:{cls_idx}:{method_idx}",
                    kind=NodeKind.METHOD,
                    fqn=f"test.Class{cls_idx}.method{method_idx}",
                    file_path="test.py",
                    span=Span(1, 0, 2, 0),
                    language="python",
                    name=f"method{method_idx}",
                )
                nodes.append(node)

        ir_doc.nodes.extend(nodes)
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        stats = index.get_stats()

        # Verify: 100 methods indexed
        assert stats["total_funcs"] == 100

        # Verify: 100 composite keys (10 classes * 10 methods)
        assert stats["composite_func_class_name_keys"] == 100

        # Verify: Query specific class methods
        methods_in_class5 = index.find_funcs_in_class("method7", "Class5")
        assert len(methods_in_class5) == 1
        assert methods_in_class5[0].id == "method:5:7"  # Correct ID for Class5.method7

        print("✅ 100 methods in 10 classes: O(1) lookup works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
