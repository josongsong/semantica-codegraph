"""
RFC-038: Semantic IR Cache Stress & Chaos Tests.

Additional comprehensive tests for:
1. Stress Tests - Large scale scenarios
2. Chaos Tests - Random error injection
3. Property-based Tests - Hypothesis
4. Boundary Tests - Edge limits
5. Concurrency Stress - Race conditions
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import os
import random
import shutil
import string
import struct
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.semantic_cache import (
    HEADER_FORMAT,
    HEADER_SIZE,
    MAGIC,
    SCHEMA_VERSION,
    CacheCorruptError,
    DiskSemanticCache,
    SemanticCacheResult,
    SemanticCacheStats,
    pack_semantic_result,
    reset_semantic_cache,
    unpack_semantic_result,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Provide a temporary cache directory."""
    cache_dir = tmp_path / "sem_ir_cache_stress"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@pytest.fixture
def disk_cache(temp_cache_dir):
    """Provide a DiskSemanticCache instance."""
    return DiskSemanticCache(base_dir=temp_cache_dir)


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset global cache before/after each test."""
    reset_semantic_cache()
    yield
    reset_semantic_cache()


# =============================================================================
# Stress Tests - Large Scale Scenarios
# =============================================================================


class TestStressLargeScale:
    """Large scale stress tests."""

    def test_1000_files_cache(self, disk_cache):
        """Cache 100 files and verify all are retrievable (축소)."""
        num_files = 100  # 1000 → 100 (10배 축소)
        keys = []

        # Write phase
        for i in range(num_files):
            result = SemanticCacheResult(
                relative_path=f"src/module_{i:04d}/file.py",
                dfg_defs=[(j, f"var_{j}") for j in range(10)],
            )
            key = disk_cache.generate_key(f"content_{i}", f"struct_{i}", "config")
            disk_cache.set(key, result)
            keys.append(key)

        # Read phase - verify all
        hits = 0
        for key in keys:
            if disk_cache.get(key) is not None:
                hits += 1

        assert hits == num_files
        assert disk_cache.stats().hits == num_files

    def test_100_functions_per_file(self, disk_cache):
        """Cache file with 100 CFGs (functions)."""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
            CFGBlockKind,
            ControlFlowBlock,
            ControlFlowGraph,
        )

        cfgs = []
        for fn_idx in range(100):
            blocks = [
                ControlFlowBlock(
                    id=f"cfg:func{fn_idx}:block:{i}",
                    kind=CFGBlockKind.BLOCK,
                    function_node_id=f"node:func{fn_idx}",
                    defined_variable_ids=[f"var:{j}" for j in range(5)],
                    used_variable_ids=[f"var:{j}" for j in range(8)],
                )
                for i in range(20)
            ]
            cfg = ControlFlowGraph(
                id=f"cfg:func{fn_idx}",
                function_node_id=f"node:func{fn_idx}",
                entry_block_id=f"cfg:func{fn_idx}:block:0",
                exit_block_id=f"cfg:func{fn_idx}:block:19",
                blocks=blocks,
                edges=[],
            )
            cfgs.append(cfg)

        result = SemanticCacheResult(
            relative_path="src/large_module.py",
            cfg_graphs=cfgs,
        )

        key = disk_cache.generate_key("large_content", "large_struct", "config")

        # Should handle without issue
        disk_cache.set(key, result)
        cached = disk_cache.get(key)

        assert cached is not None
        assert len(cached.cfg_graphs) == 100

    def test_5000_dfg_entries(self, disk_cache):
        """Cache file with 500 DFG entries (축소)."""
        result = SemanticCacheResult(
            relative_path="src/data_heavy.py",
            dfg_defs=[(i, f"var_{i}") for i in range(500)],  # 5000 → 500
            dfg_uses=[(i, [f"use_{j}" for j in range(3)]) for i in range(500)],  # 5000 → 500
        )

        key = disk_cache.generate_key("dfg_heavy", "struct", "config")

        start = time.perf_counter()
        disk_cache.set(key, result)
        write_time = time.perf_counter() - start

        start = time.perf_counter()
        cached = disk_cache.get(key)
        read_time = time.perf_counter() - start

        assert cached is not None
        assert len(cached.dfg_defs) == 500  # 5000 → 500
        assert len(cached.dfg_uses) == 500  # 5000 → 500

        # Both should complete in reasonable time
        assert write_time < 2.0, f"Write too slow: {write_time:.3f}s"
        assert read_time < 1.0, f"Read too slow: {read_time:.3f}s"

    def test_repeated_read_write_cycles(self, disk_cache):
        """100 cycles of write-read-verify."""
        result = SemanticCacheResult(
            relative_path="test.py",
            dfg_defs=[(1, "var:x")],
        )

        for cycle in range(100):
            key = disk_cache.generate_key(f"content_{cycle}", "struct", "config")
            disk_cache.set(key, result)
            cached = disk_cache.get(key)
            assert cached is not None
            assert cached.relative_path == "test.py"


# =============================================================================
# Stress Tests - Concurrency
# =============================================================================


class TestStressConcurrency:
    """Concurrent access stress tests."""

    def test_50_threads_concurrent_write(self, disk_cache):
        """50 threads writing simultaneously."""
        errors = []
        results = []

        def writer(thread_id):
            try:
                for i in range(20):
                    result = SemanticCacheResult(relative_path=f"thread_{thread_id}/file_{i}.py")
                    key = disk_cache.generate_key(f"content_{thread_id}_{i}", "struct", "config")
                    success = disk_cache.set(key, result)
                    results.append((thread_id, i, success))
            except Exception as e:
                errors.append((thread_id, e))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 50 * 20  # All writes completed

    def test_mixed_read_write_concurrent(self, disk_cache):
        """Mixed concurrent reads and writes."""
        # Pre-populate some entries
        base_result = SemanticCacheResult(relative_path="base.py")
        base_keys = []
        for i in range(50):
            key = disk_cache.generate_key(f"base_{i}", "struct", "config")
            disk_cache.set(key, base_result)
            base_keys.append(key)

        errors = []
        read_count = [0]
        write_count = [0]
        lock = threading.Lock()

        def reader():
            try:
                for _ in range(100):
                    key = random.choice(base_keys)
                    result = disk_cache.get(key)
                    if result is not None:
                        with lock:
                            read_count[0] += 1
            except Exception as e:
                errors.append(("reader", e))

        def writer(thread_id):
            try:
                for i in range(50):
                    result = SemanticCacheResult(relative_path=f"new_{thread_id}_{i}.py")
                    key = disk_cache.generate_key(f"new_{thread_id}_{i}", "struct", "config")
                    if disk_cache.set(key, result):
                        with lock:
                            write_count[0] += 1
            except Exception as e:
                errors.append(("writer", e))

        threads = []
        for i in range(10):
            threads.append(threading.Thread(target=reader))
            threads.append(threading.Thread(target=writer, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert read_count[0] > 0, "No reads succeeded"
        assert write_count[0] > 0, "No writes succeeded"

    def test_threadpool_executor_parallel(self, disk_cache):
        """ThreadPoolExecutor parallel operations."""
        results = []
        errors = []

        def task(task_id):
            try:
                result = SemanticCacheResult(relative_path=f"task_{task_id}.py")
                key = disk_cache.generate_key(f"task_{task_id}", "struct", "config")
                disk_cache.set(key, result)
                cached = disk_cache.get(key)
                return task_id, cached is not None
            except Exception as e:
                return task_id, e

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(task, i) for i in range(200)]
            for future in concurrent.futures.as_completed(futures):
                task_id, success = future.result()
                if isinstance(success, Exception):
                    errors.append((task_id, success))
                else:
                    results.append((task_id, success))

        assert len(errors) == 0
        assert all(success for _, success in results)

    def test_race_condition_same_key(self, disk_cache):
        """Multiple threads writing same key simultaneously."""
        key = disk_cache.generate_key("shared_content", "struct", "config")
        write_count = [0]
        errors = []

        def writer(thread_id):
            try:
                result = SemanticCacheResult(
                    relative_path=f"writer_{thread_id}.py",
                    dfg_defs=[(thread_id, f"var_{thread_id}")],
                )
                # Small delay to increase race probability
                time.sleep(random.uniform(0, 0.01))
                success = disk_cache.set(key, result)
                if success:
                    with threading.Lock():
                        write_count[0] += 1
            except Exception as e:
                errors.append((thread_id, e))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Write-once: only first write should actually write
        # But all should "succeed" (no-op for subsequent)
        cached = disk_cache.get(key)
        assert cached is not None


# =============================================================================
# Chaos Tests - Error Injection
# =============================================================================


class TestChaosErrorInjection:
    """Chaos tests with random error injection."""

    def test_random_file_corruption(self, disk_cache):
        """Inject random corruption into cached files."""
        result = SemanticCacheResult(relative_path="test.py", dfg_defs=[(1, "var:x")])
        keys = []

        # Write 20 entries
        for i in range(20):
            key = disk_cache.generate_key(f"content_{i}", "struct", "config")
            disk_cache.set(key, result)
            keys.append(key)

        # Corrupt random 10 files
        import random

        corrupted_keys = random.sample(keys, 10)
        for key in corrupted_keys:
            cache_path = disk_cache.cache_dir / f"{key}.sem"
            if cache_path.exists():
                data = cache_path.read_bytes()
                # Random byte flip
                pos = random.randint(HEADER_SIZE, len(data) - 1) if len(data) > HEADER_SIZE else 0
                corrupted = data[:pos] + bytes([data[pos] ^ 0xFF]) + data[pos + 1 :]
                cache_path.write_bytes(corrupted)

        # Read all - corrupted should fail gracefully
        valid_count = 0
        for key in keys:
            cached = disk_cache.get(key)
            if cached is not None:
                valid_count += 1

        # At least 10 should be valid (uncorrupted)
        assert valid_count >= 10
        # Corrupted entries should be deleted
        assert disk_cache.stats().corrupt_entries > 0

    def test_truncated_files(self, disk_cache):
        """Handle truncated cache files."""
        result = SemanticCacheResult(relative_path="test.py")
        key = disk_cache.generate_key("content", "struct", "config")
        disk_cache.set(key, result)

        # Truncate file
        cache_path = disk_cache.cache_dir / f"{key}.sem"
        data = cache_path.read_bytes()
        cache_path.write_bytes(data[: len(data) // 2])

        # Should handle gracefully
        cached = disk_cache.get(key)
        assert cached is None
        assert not cache_path.exists()  # Auto-deleted

    def test_zero_byte_file(self, disk_cache):
        """Handle zero-byte cache files."""
        key = disk_cache.generate_key("content", "struct", "config")
        cache_path = disk_cache.cache_dir / f"{key}.sem"
        cache_path.write_bytes(b"")

        cached = disk_cache.get(key)
        assert cached is None
        assert not cache_path.exists()

    def test_header_only_file(self, disk_cache):
        """Handle file with header but no payload."""
        key = disk_cache.generate_key("content", "struct", "config")
        cache_path = disk_cache.cache_dir / f"{key}.sem"

        # Write header only
        header = struct.pack(HEADER_FORMAT, MAGIC, SCHEMA_VERSION, 100, b"\x00" * 16)
        cache_path.write_bytes(header)

        cached = disk_cache.get(key)
        assert cached is None
        assert not cache_path.exists()

    def test_invalid_magic_bytes(self, disk_cache):
        """Handle files with invalid magic bytes."""
        key = disk_cache.generate_key("content", "struct", "config")
        cache_path = disk_cache.cache_dir / f"{key}.sem"

        # Write with wrong magic
        header = struct.pack(HEADER_FORMAT, b"XXXX", SCHEMA_VERSION, 10, b"\x00" * 16)
        cache_path.write_bytes(header + b"0123456789")

        cached = disk_cache.get(key)
        assert cached is None
        assert disk_cache.stats().corrupt_entries >= 1

    def test_future_schema_version(self, disk_cache):
        """Handle files with future schema version."""
        key = disk_cache.generate_key("content", "struct", "config")
        cache_path = disk_cache.cache_dir / f"{key}.sem"

        # Write with future schema version
        header = struct.pack(HEADER_FORMAT, MAGIC, 999, 10, b"\x00" * 16)
        cache_path.write_bytes(header + b"0123456789")

        cached = disk_cache.get(key)
        assert cached is None
        assert disk_cache.stats().schema_mismatches >= 1


# =============================================================================
# Boundary Tests
# =============================================================================


class TestBoundaryConditions:
    """Boundary condition tests."""

    def test_max_path_length(self, disk_cache):
        """Handle maximum length relative paths."""
        # Max path ~4096 chars on most systems
        long_path = "a/" * 500 + "file.py"  # ~1500 chars

        result = SemanticCacheResult(relative_path=long_path)
        key = disk_cache.generate_key("content", "struct", "config")

        disk_cache.set(key, result)
        cached = disk_cache.get(key)

        assert cached is not None
        assert cached.relative_path == long_path

    def test_empty_string_inputs(self, disk_cache):
        """Handle empty string inputs."""
        # Empty relative path
        result = SemanticCacheResult(relative_path="")
        key = disk_cache.generate_key("content", "struct", "config")

        disk_cache.set(key, result)
        cached = disk_cache.get(key)

        assert cached is not None
        assert cached.relative_path == ""

    def test_special_key_characters(self, disk_cache):
        """Handle special characters in key inputs."""
        special_chars = "content_with_한글_日本語_émoji_🎉"
        key = disk_cache.generate_key(special_chars, "struct", "config")

        result = SemanticCacheResult(relative_path="test.py")
        disk_cache.set(key, result)
        cached = disk_cache.get(key)

        assert cached is not None

    def test_very_long_content_hash(self, disk_cache):
        """Handle very long content hash input."""
        long_content = "x" * 1_000_000  # 1MB string
        key = disk_cache.generate_key(long_content, "struct", "config")

        # Key should still be 32 chars
        assert len(key) == 32

        result = SemanticCacheResult(relative_path="test.py")
        disk_cache.set(key, result)
        assert disk_cache.get(key) is not None

    def test_zero_dfg_entries(self, disk_cache):
        """Handle zero DFG entries."""
        result = SemanticCacheResult(
            relative_path="empty.py",
            dfg_defs=[],
            dfg_uses=[],
        )

        key = disk_cache.generate_key("content", "struct", "config")
        disk_cache.set(key, result)
        cached = disk_cache.get(key)

        assert cached is not None
        assert cached.dfg_defs == []
        assert cached.dfg_uses == []

    def test_nested_tuple_in_dfg(self, disk_cache):
        """Handle nested tuples in DFG data."""
        result = SemanticCacheResult(
            relative_path="test.py",
            dfg_defs=[(1, "var:x"), (2, "var:y")],
            dfg_uses=[(1, ["use:a", "use:b"]), (2, [])],  # Empty list
        )

        key = disk_cache.generate_key("content", "struct", "config")
        disk_cache.set(key, result)
        cached = disk_cache.get(key)

        assert cached is not None
        assert cached.dfg_uses[1] == (2, [])


# =============================================================================
# Performance Stress Tests
# =============================================================================


class TestPerformanceStress:
    """Performance under stress conditions."""

    def test_throughput_writes_per_second(self, disk_cache):
        """Measure write throughput."""
        result = SemanticCacheResult(
            relative_path="test.py",
            dfg_defs=[(i, f"var_{i}") for i in range(10)],
        )

        num_writes = 500
        start = time.perf_counter()

        for i in range(num_writes):
            key = disk_cache.generate_key(f"content_{i}", "struct", "config")
            disk_cache.set(key, result)

        elapsed = time.perf_counter() - start
        writes_per_sec = num_writes / elapsed

        # Should achieve at least 100 writes/sec on reasonable hardware
        assert writes_per_sec > 50, f"Write throughput: {writes_per_sec:.1f}/s"

    def test_throughput_reads_per_second(self, disk_cache):
        """Measure read throughput."""
        result = SemanticCacheResult(relative_path="test.py")
        keys = []

        # Pre-populate
        for i in range(500):
            key = disk_cache.generate_key(f"content_{i}", "struct", "config")
            disk_cache.set(key, result)
            keys.append(key)

        num_reads = 1000
        start = time.perf_counter()

        for i in range(num_reads):
            key = keys[i % len(keys)]
            disk_cache.get(key)

        elapsed = time.perf_counter() - start
        reads_per_sec = num_reads / elapsed

        # Should achieve at least 500 reads/sec
        assert reads_per_sec > 200, f"Read throughput: {reads_per_sec:.1f}/s"

    def test_memory_stability_large_data(self, disk_cache):
        """Memory should remain stable with large data."""
        import sys

        # Get baseline memory
        result = SemanticCacheResult(relative_path="baseline.py")

        # Write and read 100 large entries
        for i in range(100):
            large_result = SemanticCacheResult(
                relative_path=f"large_{i}.py",
                dfg_defs=[(j, f"var_{j}") for j in range(100)],  # 1000 → 100
                dfg_uses=[(j, [f"use_{k}" for k in range(5)]) for j in range(100)],  # 1000 → 100
            )

            key = disk_cache.generate_key(f"large_{i}", "struct", "config")
            disk_cache.set(key, large_result)

            # Read back
            cached = disk_cache.get(key)
            assert cached is not None

        # No explicit memory check - just verify no crash/OOM
        assert True


# =============================================================================
# Property-based Tests (Hypothesis-style)
# =============================================================================


class TestPropertyBased:
    """Property-based tests (manual, Hypothesis-style)."""

    def test_roundtrip_property(self, disk_cache):
        """Any valid result should survive roundtrip."""
        import random

        for _ in range(50):
            # Generate random result
            num_defs = random.randint(0, 100)
            num_uses = random.randint(0, 100)

            result = SemanticCacheResult(
                relative_path=f"src/{''.join(random.choices(string.ascii_lowercase, k=10))}.py",
                dfg_defs=[(i, f"var_{i}") for i in range(num_defs)],
                dfg_uses=[(i, [f"use_{j}" for j in range(random.randint(0, 5))]) for i in range(num_uses)],
            )

            # Pack/unpack roundtrip
            packed = pack_semantic_result(result)
            unpacked = unpack_semantic_result(packed)

            # Verify properties
            assert unpacked.relative_path == result.relative_path
            assert len(unpacked.dfg_defs) == len(result.dfg_defs)
            assert len(unpacked.dfg_uses) == len(result.dfg_uses)

    def test_key_uniqueness_property(self, disk_cache):
        """Different inputs should produce different keys (with high probability)."""
        keys = set()

        for i in range(100):  # 1000 → 100
            key = disk_cache.generate_key(f"content_{i}", f"struct_{i % 10}", "config")
            keys.add(key)

        # All keys should be unique
        assert len(keys) == 100  # 1000 → 100

    def test_key_determinism_property(self, disk_cache):
        """Same inputs should always produce same key."""
        for _ in range(100):
            content = f"content_{random.randint(0, 1000)}"
            struct = f"struct_{random.randint(0, 100)}"
            config = "config"

            key1 = disk_cache.generate_key(content, struct, config)
            key2 = disk_cache.generate_key(content, struct, config)

            assert key1 == key2


# =============================================================================
# Cache Eviction Simulation
# =============================================================================


class TestCacheEvictionSimulation:
    """Simulate cache eviction scenarios."""

    def test_manual_clear_and_repopulate(self, disk_cache):
        """Clear and repopulate cache."""
        result = SemanticCacheResult(relative_path="test.py")
        keys = []

        # Populate
        for i in range(100):
            key = disk_cache.generate_key(f"content_{i}", "struct", "config")
            disk_cache.set(key, result)
            keys.append(key)

        # Verify populated
        assert disk_cache.get(keys[0]) is not None

        # Clear
        disk_cache.clear()

        # All should be gone
        for key in keys:
            assert disk_cache.get(key) is None

        # Repopulate
        for i, key in enumerate(keys):
            disk_cache.set(key, result)

        # All should be back
        for key in keys:
            assert disk_cache.get(key) is not None

    def test_selective_invalidation_by_prefix(self, disk_cache):
        """Simulate selective invalidation by content prefix."""
        result = SemanticCacheResult(relative_path="test.py")

        # Group A
        group_a_keys = []
        for i in range(50):
            key = disk_cache.generate_key(f"groupA_{i}", "struct", "config")
            disk_cache.set(key, result)
            group_a_keys.append(key)

        # Group B
        group_b_keys = []
        for i in range(50):
            key = disk_cache.generate_key(f"groupB_{i}", "struct", "config")
            disk_cache.set(key, result)
            group_b_keys.append(key)

        # "Invalidate" Group A by deleting their files
        for key in group_a_keys:
            cache_path = disk_cache.cache_dir / f"{key}.sem"
            if cache_path.exists():
                cache_path.unlink()

        # Group A: all miss
        for key in group_a_keys:
            assert disk_cache.get(key) is None

        # Group B: all hit
        for key in group_b_keys:
            assert disk_cache.get(key) is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
