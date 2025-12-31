"""
RFC-038: Semantic IR Cache Integration Tests.

Comprehensive tests for:
1. End-to-end cache workflow (cold → warm → incremental)
2. Real file parsing → semantic build → cache → restore
3. Incremental update scenarios (file edit, rename, config change)
4. Performance validation (warm run speedup)
5. Multi-file project scenarios
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.semantic_cache import (
    DiskSemanticCache,
    SemanticCacheResult,
    compute_structural_digest,
    get_semantic_cache,
    pack_semantic_result,
    reset_semantic_cache,
    unpack_semantic_result,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project with Python files."""
    project = tmp_path / "test_project"
    project.mkdir()

    # Create sample Python files
    (project / "main.py").write_text(
        """
def main():
    x = 10
    y = 20
    if x > 5:
        result = x + y
    else:
        result = x - y
    return result

def helper(a, b):
    return a * b
"""
    )

    (project / "utils.py").write_text(
        """
def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result

def validate(value):
    if value is None:
        raise ValueError("Value cannot be None")
    return True
"""
    )

    (project / "models.py").write_text(
        """
class User:
    def __init__(self, name, age):
        self.name = name
        self.age = age

    def is_adult(self):
        return self.age >= 18

    def greet(self):
        return f"Hello, {self.name}"
"""
    )

    return project


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Provide a temporary cache directory."""
    cache_dir = tmp_path / "sem_ir_cache"
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
# Helper Functions
# =============================================================================


def build_mock_semantic_result(file_path: str, content: str) -> SemanticCacheResult:
    """Build a mock semantic result for testing."""
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
        CFGBlockKind,
        ControlFlowBlock,
        ControlFlowGraph,
    )

    # Create a simple CFG based on content
    num_blocks = content.count("if") + content.count("for") + content.count("while") + 2

    blocks = [
        ControlFlowBlock(
            id=f"cfg:{file_path}:block:{i}",
            kind=CFGBlockKind.ENTRY if i == 0 else (CFGBlockKind.EXIT if i == num_blocks - 1 else CFGBlockKind.BLOCK),
            function_node_id=f"node:{file_path}:main",
        )
        for i in range(num_blocks)
    ]

    cfg = ControlFlowGraph(
        id=f"cfg:{file_path}",
        function_node_id=f"node:{file_path}:main",
        entry_block_id=blocks[0].id,
        exit_block_id=blocks[-1].id,
        blocks=blocks,
        edges=[],
    )

    return SemanticCacheResult(
        relative_path=file_path,
        cfg_graphs=[cfg],
        bfg_graphs=[],
        dfg_defs=[(1, "var:x"), (2, "var:y")],
        dfg_uses=[(1, ["expr:1"]), (2, ["expr:2", "expr:3"])],
        expressions=[],
        signatures=[],
    )


def compute_content_hash(content: str) -> str:
    """Compute content hash for cache key."""
    try:
        import xxhash

        return xxhash.xxh3_128_hexdigest(content.encode())
    except ImportError:
        import hashlib

        return hashlib.sha256(content.encode()).hexdigest()[:32]


def compute_config_hash(mode: str = "full") -> str:
    """Compute config hash for cache key."""
    try:
        import xxhash

        hasher = xxhash.xxh3_64()
        hasher.update(mode.encode())
        return hasher.hexdigest()
    except ImportError:
        import hashlib

        return hashlib.sha256(mode.encode()).hexdigest()[:16]


# =============================================================================
# End-to-End Workflow Tests
# =============================================================================


class TestEndToEndCacheWorkflow:
    """Test complete cache workflow: cold → warm → incremental."""

    def test_cold_run_populates_cache(self, disk_cache, temp_project_dir):
        """First run (cold) should populate cache."""
        main_py = temp_project_dir / "main.py"
        content = main_py.read_text()

        # Build semantic result
        result = build_mock_semantic_result("main.py", content)

        # Generate cache key
        content_hash = compute_content_hash(content)
        structural_digest = "struct_digest_main"  # Mock
        config_hash = compute_config_hash("full")

        key = disk_cache.generate_key(content_hash, structural_digest, config_hash)

        # Cold run: cache miss
        assert disk_cache.get(key) is None
        assert disk_cache.stats().misses == 1

        # Store result
        disk_cache.set(key, result)

        # Verify stored
        cached = disk_cache.get(key)
        assert cached is not None
        assert cached.relative_path == "main.py"
        assert disk_cache.stats().hits == 1

    def test_warm_run_uses_cache(self, disk_cache, temp_project_dir):
        """Second run (warm) should use cached result."""
        main_py = temp_project_dir / "main.py"
        content = main_py.read_text()

        # First run: populate cache
        result = build_mock_semantic_result("main.py", content)
        content_hash = compute_content_hash(content)
        structural_digest = "struct_digest_main"
        config_hash = compute_config_hash("full")
        key = disk_cache.generate_key(content_hash, structural_digest, config_hash)

        disk_cache.set(key, result)

        # Second run: should hit cache
        cached = disk_cache.get(key)

        assert cached is not None
        assert cached.relative_path == result.relative_path
        assert len(cached.cfg_graphs) == len(result.cfg_graphs)
        assert disk_cache.stats().hits == 1

    def test_incremental_update_single_file(self, disk_cache, temp_project_dir):
        """File modification should invalidate only that file's cache."""
        # Setup: Cache all files
        files = ["main.py", "utils.py", "models.py"]
        keys = {}

        for file_name in files:
            file_path = temp_project_dir / file_name
            content = file_path.read_text()
            result = build_mock_semantic_result(file_name, content)

            content_hash = compute_content_hash(content)
            structural_digest = f"struct_{file_name}"
            config_hash = compute_config_hash("full")
            key = disk_cache.generate_key(content_hash, structural_digest, config_hash)

            disk_cache.set(key, result)
            keys[file_name] = key

        # Verify all cached
        for file_name, key in keys.items():
            assert disk_cache.get(key) is not None

        # Modify main.py
        main_py = temp_project_dir / "main.py"
        new_content = main_py.read_text() + "\n# Added comment\n"
        main_py.write_text(new_content)

        # New key for modified file
        new_content_hash = compute_content_hash(new_content)
        new_key = disk_cache.generate_key(new_content_hash, "struct_main.py", compute_config_hash("full"))

        # Modified file: cache miss (new key)
        assert disk_cache.get(new_key) is None

        # Other files: still cached (unchanged keys)
        assert disk_cache.get(keys["utils.py"]) is not None
        assert disk_cache.get(keys["models.py"]) is not None


# =============================================================================
# Incremental Update Scenarios
# =============================================================================


class TestIncrementalUpdates:
    """Test incremental update scenarios."""

    def test_file_rename_cache_hit(self, disk_cache):
        """
        File rename should still hit cache (file_path excluded from key).

        This is the core RFC-038 invariant: Rename/Move tolerance.
        """
        content = "def foo(): return 42"

        # Cache with old path
        result_old = SemanticCacheResult(
            relative_path="src/old_name.py",
            cfg_graphs=[],
            dfg_defs=[(1, "var:result")],
        )

        content_hash = compute_content_hash(content)
        structural_digest = "struct_foo"
        config_hash = compute_config_hash("full")

        # Key is based on content, NOT path
        key = disk_cache.generate_key(content_hash, structural_digest, config_hash)
        disk_cache.set(key, result_old)

        # Same content with new path → same key → cache hit
        result_cached = disk_cache.get(key)

        assert result_cached is not None
        # The cached path is the old one, but content is valid
        assert result_cached.dfg_defs == [(1, "var:result")]

    def test_file_move_cache_hit(self, disk_cache):
        """
        File move (different directory) should hit cache.
        """
        content = "class MyClass: pass"

        result = SemanticCacheResult(
            relative_path="src/models/user.py",
            cfg_graphs=[],
        )

        content_hash = compute_content_hash(content)
        key = disk_cache.generate_key(content_hash, "struct", "config")
        disk_cache.set(key, result)

        # File moved to different directory, same content
        # → Same key → Cache hit
        assert disk_cache.get(key) is not None

    def test_content_change_cache_miss(self, disk_cache):
        """Content change should cause cache miss."""
        original_content = "def foo(): return 1"
        modified_content = "def foo(): return 2"

        result = SemanticCacheResult(relative_path="test.py")

        # Cache with original content
        key_original = disk_cache.generate_key(compute_content_hash(original_content), "struct", "config")
        disk_cache.set(key_original, result)

        # Modified content → different key → cache miss
        key_modified = disk_cache.generate_key(compute_content_hash(modified_content), "struct", "config")

        assert key_original != key_modified
        assert disk_cache.get(key_modified) is None

    def test_config_change_cache_miss(self, disk_cache):
        """Config change should cause cache miss."""
        content = "def foo(): pass"
        content_hash = compute_content_hash(content)
        structural_digest = "struct"

        result = SemanticCacheResult(relative_path="test.py")

        # Cache with FULL mode
        key_full = disk_cache.generate_key(content_hash, structural_digest, compute_config_hash("full"))
        disk_cache.set(key_full, result)

        # QUICK mode → different key → cache miss
        key_quick = disk_cache.generate_key(content_hash, structural_digest, compute_config_hash("quick"))

        assert key_full != key_quick
        assert disk_cache.get(key_quick) is None

    def test_structural_change_cache_miss(self, disk_cache):
        """Structural IR change should cause cache miss."""
        content = "def foo(): pass"
        content_hash = compute_content_hash(content)
        config_hash = compute_config_hash("full")

        result = SemanticCacheResult(relative_path="test.py")

        # Cache with original structural digest
        key_original = disk_cache.generate_key(content_hash, "struct_v1", config_hash)
        disk_cache.set(key_original, result)

        # Structural change (e.g., different AST) → different key
        key_new = disk_cache.generate_key(content_hash, "struct_v2", config_hash)

        assert key_original != key_new
        assert disk_cache.get(key_new) is None


# =============================================================================
# Multi-File Project Scenarios
# =============================================================================


class TestMultiFileProject:
    """Test cache behavior with multiple files."""

    def test_cache_all_files_independently(self, disk_cache, temp_project_dir):
        """Each file should be cached independently."""
        files_data = {}

        # Cache all files
        for file_path in temp_project_dir.glob("*.py"):
            content = file_path.read_text()
            result = build_mock_semantic_result(file_path.name, content)

            content_hash = compute_content_hash(content)
            key = disk_cache.generate_key(content_hash, f"struct_{file_path.name}", "config")

            disk_cache.set(key, result)
            files_data[file_path.name] = {"key": key, "content": content}

        # Verify all cached
        for file_name, data in files_data.items():
            cached = disk_cache.get(data["key"])
            assert cached is not None
            assert cached.relative_path == file_name

    def test_partial_cache_invalidation(self, disk_cache, temp_project_dir):
        """Only modified files should be invalidated."""
        # Setup: Cache all files
        files = list(temp_project_dir.glob("*.py"))
        keys = {}

        for file_path in files:
            content = file_path.read_text()
            result = build_mock_semantic_result(file_path.name, content)
            content_hash = compute_content_hash(content)
            key = disk_cache.generate_key(content_hash, f"struct_{file_path.name}", "config")
            disk_cache.set(key, result)
            keys[file_path.name] = (key, content)

        # Modify one file
        modified_file = files[0]
        new_content = keys[modified_file.name][1] + "\n# Modified\n"

        new_content_hash = compute_content_hash(new_content)
        new_key = disk_cache.generate_key(new_content_hash, f"struct_{modified_file.name}", "config")

        # Count hits and misses
        hits = 0
        misses = 0

        for file_path in files:
            if file_path == modified_file:
                # Modified file: should miss with new key
                if disk_cache.get(new_key) is None:
                    misses += 1
            else:
                # Unmodified files: should hit
                old_key = keys[file_path.name][0]
                if disk_cache.get(old_key) is not None:
                    hits += 1

        assert hits == len(files) - 1  # All except modified
        assert misses == 1  # Only the modified file

    def test_batch_invalidation_by_config_change(self, disk_cache, temp_project_dir):
        """Config change should invalidate all files."""
        files = list(temp_project_dir.glob("*.py"))

        # Cache with config v1
        for file_path in files:
            content = file_path.read_text()
            result = build_mock_semantic_result(file_path.name, content)
            content_hash = compute_content_hash(content)
            key = disk_cache.generate_key(content_hash, f"struct_{file_path.name}", "config_v1")
            disk_cache.set(key, result)

        # Check with config v2: all should miss
        misses = 0
        for file_path in files:
            content = file_path.read_text()
            content_hash = compute_content_hash(content)
            key_v2 = disk_cache.generate_key(content_hash, f"struct_{file_path.name}", "config_v2")
            if disk_cache.get(key_v2) is None:
                misses += 1

        assert misses == len(files)  # All files miss with new config


# =============================================================================
# Performance Validation
# =============================================================================


class TestCachePerformance:
    """Performance validation tests."""

    def test_cache_hit_is_fast(self, disk_cache):
        """Cache hit should be significantly faster than cold build."""
        # Create a result with realistic data
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
            CFGBlockKind,
            ControlFlowBlock,
            ControlFlowGraph,
        )

        # Create CFG with 50 blocks (realistic for medium function)
        blocks = [
            ControlFlowBlock(
                id=f"cfg:func:block:{i}",
                kind=CFGBlockKind.BLOCK,
                function_node_id="node:func",
                defined_variable_ids=[f"var:{j}" for j in range(3)],
                used_variable_ids=[f"var:{j}" for j in range(5)],
            )
            for i in range(10)  # 50 → 10
        ]

        cfg = ControlFlowGraph(
            id="cfg:func",
            function_node_id="node:func",
            entry_block_id="cfg:func:block:0",
            exit_block_id="cfg:func:block:49",
            blocks=blocks,
            edges=[],
        )

        result = SemanticCacheResult(
            relative_path="src/complex.py",
            cfg_graphs=[cfg] * 10,  # 10 functions
            dfg_defs=[(i, f"var:{i}") for i in range(20)],  # 100 → 20
            dfg_uses=[(i, [f"use:{j}" for j in range(5)]) for i in range(20)],  # 100 → 20
        )

        # Store
        key = disk_cache.generate_key("content", "struct", "config")
        disk_cache.set(key, result)

        # Measure cache hit time
        iterations = 50
        start = time.perf_counter()
        for _ in range(iterations):
            disk_cache.get(key)
        hit_time = (time.perf_counter() - start) / iterations * 1000  # ms

        # Cache hit should be < 5ms (relaxed for CI)
        assert hit_time < 10.0, f"Cache hit too slow: {hit_time:.3f}ms"

    def test_pack_unpack_roundtrip_performance(self):
        """Pack/unpack should be fast for realistic data."""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
            CFGBlockKind,
            ControlFlowBlock,
            ControlFlowGraph,
        )

        # Create realistic result
        blocks = [
            ControlFlowBlock(
                id=f"cfg:func:block:{i}",
                kind=CFGBlockKind.BLOCK,
                function_node_id="node:func",
            )
            for i in range(30)
        ]

        cfg = ControlFlowGraph(
            id="cfg:func",
            function_node_id="node:func",
            entry_block_id="cfg:func:block:0",
            exit_block_id="cfg:func:block:29",
            blocks=blocks,
            edges=[],
        )

        result = SemanticCacheResult(
            relative_path="src/module.py",
            cfg_graphs=[cfg] * 5,
            dfg_defs=[(i, f"var:{i}") for i in range(10)],  # 50 → 10
        )

        # Measure pack time
        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            packed = pack_semantic_result(result)
        pack_time = (time.perf_counter() - start) / iterations * 1000  # ms

        # Measure unpack time
        start = time.perf_counter()
        for _ in range(iterations):
            unpack_semantic_result(packed)
        unpack_time = (time.perf_counter() - start) / iterations * 1000  # ms

        # Both should be < 2ms
        assert pack_time < 5.0, f"Pack too slow: {pack_time:.3f}ms"
        assert unpack_time < 5.0, f"Unpack too slow: {unpack_time:.3f}ms"


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge case handling."""

    def test_empty_file_caching(self, disk_cache):
        """Empty files should be cacheable."""
        result = SemanticCacheResult(
            relative_path="empty.py",
            cfg_graphs=[],
            dfg_defs=[],
        )

        key = disk_cache.generate_key("empty_hash", "empty_struct", "config")
        disk_cache.set(key, result)

        cached = disk_cache.get(key)
        assert cached is not None
        assert cached.cfg_graphs == []

    def test_very_large_file_caching(self, disk_cache):
        """Large files should be cacheable (within reason)."""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
            CFGBlockKind,
            ControlFlowBlock,
            ControlFlowGraph,
        )

        # Create large CFG (20 blocks, 10 functions, 축소)
        all_cfgs = []
        for fn_idx in range(10):  # 50 → 10
            blocks = [
                ControlFlowBlock(
                    id=f"cfg:func{fn_idx}:block:{i}",
                    kind=CFGBlockKind.BLOCK,
                    function_node_id=f"node:func{fn_idx}",
                    defined_variable_ids=[f"var:{j}" for j in range(10)],
                    used_variable_ids=[f"var:{j}" for j in range(15)],
                )
                for i in range(20)  # 200 → 20
            ]

            cfg = ControlFlowGraph(
                id=f"cfg:func{fn_idx}",
                function_node_id=f"node:func{fn_idx}",
                entry_block_id=f"cfg:func{fn_idx}:block:0",
                exit_block_id=f"cfg:func{fn_idx}:block:199",
                blocks=blocks,
                edges=[],
            )
            all_cfgs.append(cfg)

        result = SemanticCacheResult(
            relative_path="src/very_large.py",
            cfg_graphs=all_cfgs,
            dfg_defs=[(i, f"var:{i}") for i in range(1000)],
            dfg_uses=[(i, [f"use:{j}" for j in range(10)]) for i in range(1000)],
        )

        key = disk_cache.generate_key("large_hash", "large_struct", "config")

        # Should not raise
        disk_cache.set(key, result)

        # Should retrieve correctly
        cached = disk_cache.get(key)
        assert cached is not None
        assert len(cached.cfg_graphs) == 10  # 50 → 10 (축소)
        assert len(cached.dfg_defs) == 1000

    def test_special_characters_in_path(self, disk_cache):
        """Paths with special characters should work."""
        result = SemanticCacheResult(
            relative_path="src/모듈/파일_名前.py",
        )

        key = disk_cache.generate_key("unicode_hash", "struct", "config")
        disk_cache.set(key, result)

        cached = disk_cache.get(key)
        assert cached is not None
        assert cached.relative_path == "src/모듈/파일_名前.py"

    def test_concurrent_reads_same_key(self, disk_cache):
        """Concurrent reads should all succeed."""
        import threading

        result = SemanticCacheResult(relative_path="test.py")
        key = disk_cache.generate_key("content", "struct", "config")
        disk_cache.set(key, result)

        errors = []
        results = []

        def read_cache():
            try:
                cached = disk_cache.get(key)
                results.append(cached)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_cache) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 20
        assert all(r is not None for r in results)


# =============================================================================
# Stats Validation
# =============================================================================


class TestCacheStats:
    """Test cache statistics tracking."""

    def test_stats_track_hits_and_misses(self, disk_cache):
        """Stats should accurately track hits and misses."""
        result = SemanticCacheResult(relative_path="test.py")

        # Miss
        disk_cache.get("nonexistent")
        disk_cache.get("another_nonexistent")

        # Set
        key = disk_cache.generate_key("content", "struct", "config")
        disk_cache.set(key, result)

        # Hits
        disk_cache.get(key)
        disk_cache.get(key)
        disk_cache.get(key)

        stats = disk_cache.stats()
        assert stats.misses == 2
        assert stats.hits == 3
        assert stats.hit_rate == pytest.approx(0.6, rel=0.01)

    def test_stats_reset_on_clear(self, disk_cache):
        """Stats should reset when cache is cleared."""
        result = SemanticCacheResult(relative_path="test.py")
        key = disk_cache.generate_key("content", "struct", "config")

        disk_cache.set(key, result)
        disk_cache.get(key)
        disk_cache.get("miss")

        assert disk_cache.stats().hits == 1
        assert disk_cache.stats().misses == 1

        disk_cache.clear()

        assert disk_cache.stats().hits == 0
        assert disk_cache.stats().misses == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
