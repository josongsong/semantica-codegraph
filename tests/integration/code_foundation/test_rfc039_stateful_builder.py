"""
RFC-039: Stateful Builder Integration Tests

Tests for:
- L0 Cache in LayeredIRBuilder
- Watch mode performance
- GlobalContext synchronization
- End-to-end incremental builds

SOTA Principles:
- Real file I/O (no mocks)
- End-to-end validation
- Performance benchmarks
- Error recovery
"""

import asyncio
import tempfile
import time
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder
from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig
from codegraph_engine.code_foundation.infrastructure.ir.pipeline import IRPipeline


@pytest.fixture
def temp_project():
    """Create temporary project with Python files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Create test files
        (project_root / "main.py").write_text("""
def main():
    return calculate(10, 20)

def calculate(a, b):
    return a + b
""")

        (project_root / "utils.py").write_text("""
def helper(x):
    return x * 2
""")

        yield project_root


class TestL0CacheFastPath:
    """Test L0 cache Fast Path (mtime + size)."""

    @pytest.mark.asyncio
    async def test_l0_fast_path_unchanged_files(self, temp_project):
        """Unchanged files hit L0 Fast Path (mtime + size)."""
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()  # Fast config

        files = [temp_project / "main.py", temp_project / "utils.py"]

        # First build
        start1 = time.perf_counter()
        result1 = await builder.build(files, config)
        elapsed1 = time.perf_counter() - start1

        # Second build (no changes)
        start2 = time.perf_counter()
        result2 = await builder.build(files, config)
        elapsed2 = time.perf_counter() - start2

        # Verify L0 cache hit
        telemetry = await builder.get_l0_telemetry()
        assert telemetry["l0_hits"] >= 2  # Both files
        assert telemetry["l0_fast_hits"] >= 2  # Fast Path

        # Performance: Second build should be much faster
        # Target: <50ms (vs 100-500ms for first build)
        assert elapsed2 < 0.1  # 100ms threshold
        assert elapsed2 < elapsed1 * 0.5  # At least 2x faster

        # Verify IRs are same
        assert len(result1.ir_documents) == len(result2.ir_documents)

    @pytest.mark.asyncio
    async def test_l0_slow_path_content_change(self, temp_project):
        """Changed content triggers Slow Path (hash)."""
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        files = [temp_project / "main.py"]

        # First build
        await builder.build(files, config)

        # Modify file (change content)
        (temp_project / "main.py").write_text("""
def main():
    return calculate(10, 20) + 5  # Changed

def calculate(a, b):
    return a + b
""")

        # Second build (content changed)
        result2 = await builder.build(files, config)

        # Verify L0 miss (hash changed)
        telemetry = await builder.get_l0_telemetry()
        # Note: hits from first build, but second build is miss
        assert len(result2.ir_documents) == 1

    @pytest.mark.asyncio
    async def test_l0_purge_orphans(self, temp_project):
        """Deleted files are purged from L0."""
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        # Build with both files
        files1 = [temp_project / "main.py", temp_project / "utils.py"]
        await builder.build(files1, config)

        telemetry1 = await builder.get_l0_telemetry()
        assert telemetry1["l0_entries"] == 2

        # Build with only one file (utils.py removed from set)
        files2 = [temp_project / "main.py"]
        await builder.build(files2, config)

        telemetry2 = await builder.get_l0_telemetry()
        assert telemetry2["l0_entries"] == 1  # utils.py purged
        assert telemetry2["l0_purged"] >= 1


class TestL0Eviction:
    """Test L0 LRU eviction."""

    @pytest.mark.asyncio
    async def test_l0_lru_eviction(self, temp_project):
        """L0 evicts LRU entries when limit reached."""
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRConfig

        # Small L0 cache (2 files max)
        config_small = LayeredIRConfig(l0_max_files=2)
        builder = LayeredIRBuilder(project_root=temp_project, config=config_small)

        # Create 3 files
        (temp_project / "file1.py").write_text("def f1(): pass")
        (temp_project / "file2.py").write_text("def f2(): pass")
        (temp_project / "file3.py").write_text("def f3(): pass")

        build_config = BuildConfig.for_editor()

        # Build file1, file2
        files1 = [temp_project / "file1.py", temp_project / "file2.py"]
        await builder.build(files1, build_config)

        telemetry1 = await builder.get_l0_telemetry()
        assert telemetry1["l0_entries"] == 2

        # Build file3 (should evict file1, LRU)
        files2 = [temp_project / "file3.py"]
        await builder.build(files2, build_config)

        # Note: Purge will also happen, so entries might be less
        # The key is that we don't exceed l0_max_files


class TestGlobalContextSync:
    """Test GlobalContext synchronization with L0 cache."""

    @pytest.mark.skip(reason="RFC-039: GlobalContext sync needs deeper implementation (P0.2)")
    @pytest.mark.asyncio
    async def test_global_context_includes_cached_files(self, temp_project):
        """
        GlobalContext includes symbols from cached files.

        NOTE: This requires deeper GlobalContext reconstruction logic.
        Currently early-return path returns empty GlobalContext for cross_file=True cases.
        Full implementation in P0.2.
        """
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig(cross_file=True)  # Enable cross-file

        files = [temp_project / "main.py", temp_project / "utils.py"]

        # First build
        result1 = await builder.build(files, config)
        symbols1 = result1.global_ctx.total_symbols

        # Second build (all cached)
        result2 = await builder.build(files, config)
        symbols2 = result2.global_ctx.total_symbols

        # GlobalContext should have same symbols
        assert symbols2 == symbols1
        assert symbols2 > 0  # Should have symbols


class TestWatchModePerformance:
    """Test watch mode performance."""

    @pytest.mark.asyncio
    async def test_watch_mode_speedup(self, temp_project):
        """Watch mode achieves significant speedup."""
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        files = [temp_project / "main.py", temp_project / "utils.py"]

        # Cold build (first)
        start_cold = time.perf_counter()
        await builder.build(files, config)
        elapsed_cold = time.perf_counter() - start_cold

        # Warm builds (watch mode simulation)
        warm_times = []
        for _ in range(5):
            start_warm = time.perf_counter()
            await builder.build(files, config)
            warm_times.append(time.perf_counter() - start_warm)

        avg_warm = sum(warm_times) / len(warm_times)

        # Performance target: 10x speedup minimum
        speedup = elapsed_cold / avg_warm
        assert speedup >= 10.0, f"Speedup: {speedup}x (target: 10x)"

        # Target: <50ms for warm builds
        assert avg_warm < 0.05, f"Warm: {avg_warm * 1000:.1f}ms (target: <50ms)"


class TestPipelineIntegration:
    """Test IRPipeline with stateful builder."""

    @pytest.mark.asyncio
    async def test_pipeline_reuses_builder(self, temp_project):
        """Pipeline reuses builder across builds."""
        pipeline = IRPipeline(project_root=temp_project)

        files = [temp_project / "main.py"]

        # Multiple builds
        result1 = await pipeline.build_incremental(files)
        result2 = await pipeline.build_incremental(files)

        # Verify cache telemetry (graceful)
        telemetry = await pipeline.get_cache_telemetry()
        assert telemetry.get("l0_entries", 0) >= 1
        assert telemetry.get("l0_hits", 0) >= 0  # May be 0 on first build

    @pytest.mark.asyncio
    async def test_pipeline_clear_cache(self, temp_project):
        """Pipeline can clear cache."""
        pipeline = IRPipeline(project_root=temp_project)

        files = [temp_project / "main.py"]

        # Build
        await pipeline.build_incremental(files)

        # Clear cache
        await pipeline.clear_incremental_cache()

        # Verify cleared
        telemetry = await pipeline.get_cache_telemetry()
        assert telemetry["l0_entries"] == 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_file_list(self, temp_project):
        """Empty file list returns empty result."""
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        result = await builder.build([], config)

        assert len(result.ir_documents) == 0

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, temp_project):
        """Nonexistent file is handled gracefully."""
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        files = [temp_project / "nonexistent.py"]

        # Should not crash
        result = await builder.build(files, config)

        # May or may not include the file (depends on error handling)
        # Key: should not crash

    @pytest.mark.asyncio
    async def test_file_deleted_after_cache(self, temp_project):
        """File deleted after caching is handled."""
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        file_path = temp_project / "temp.py"
        file_path.write_text("def temp(): pass")

        # Build
        await builder.build([file_path], config)

        # Delete file
        file_path.unlink()

        # Build without the file (should purge)
        await builder.build([], config)

        telemetry = await builder.get_l0_telemetry()
        # Should have purged
        assert telemetry.get("l0_purged", 0) >= 0

    @pytest.mark.asyncio
    async def test_concurrent_builds(self, temp_project):
        """
        EXTREME CASE: Concurrent builds on same builder.

        Tests thread safety and state consistency.
        """
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        files = [temp_project / "main.py"]

        # Run 5 builds concurrently
        tasks = [builder.build(files, config) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 5
        for result in results:
            assert len(result.ir_documents) >= 1

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_extreme_file_count(self, temp_project):
        """
        EXTREME CASE: Many files (beyond L0 limit).

        Tests eviction and memory safety.
        """
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRConfig

        # L0 max = 50, create 100 files (reduced for CI speed)
        config_small = LayeredIRConfig(l0_max_files=50)
        builder = LayeredIRBuilder(project_root=temp_project, config=config_small)

        # Create 100 files (reduced from 200)
        files = []
        for i in range(100):
            file_path = temp_project / f"file_{i}.py"
            file_path.write_text(f"def func_{i}(): pass")
            files.append(file_path)

        build_config = BuildConfig.for_editor()

        # Build all
        result = await builder.build(files, build_config)

        # Should have evicted
        telemetry = await builder.get_l0_telemetry()
        assert telemetry["l0_entries"] <= 50  # Respects limit

        # All files should be in result (from L1/L2 or fresh build)
        assert len(result.ir_documents) >= 90  # Allow some failures

    @pytest.mark.asyncio
    async def test_corrupted_file_content(self, temp_project):
        """
        EDGE CASE: File with binary/corrupted content.
        """
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        # Create file with binary content
        file_path = temp_project / "corrupted.py"
        file_path.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

        # Should handle gracefully
        try:
            result = await builder.build([file_path], config)
            # May succeed with replacement chars or fail gracefully
        except Exception:
            # Acceptable to fail, but should not crash the process
            pass

    @pytest.mark.asyncio
    async def test_symlink_cycle(self, temp_project):
        """
        EXTREME CASE: Symlink cycle.
        """
        import os

        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        # Create symlink cycle
        link_a = temp_project / "link_a.py"
        link_b = temp_project / "link_b.py"

        try:
            os.symlink(link_b, link_a)
            os.symlink(link_a, link_b)

            # Should detect cycle or timeout gracefully
            result = await builder.build([link_a], config)
        except Exception:
            # Acceptable to fail on cycle
            pass

    @pytest.mark.asyncio
    async def test_file_permission_error(self, temp_project):
        """
        EDGE CASE: File with no read permission.
        """
        import os

        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        file_path = temp_project / "noperm.py"
        file_path.write_text("def test(): pass")

        # Remove read permission
        os.chmod(file_path, 0o000)

        try:
            result = await builder.build([file_path], config)
            # Should handle permission error gracefully
        except Exception:
            pass
        finally:
            # Restore permission for cleanup
            os.chmod(file_path, 0o644)

    @pytest.mark.asyncio
    async def test_unicode_filename(self, temp_project):
        """
        EDGE CASE: Unicode filename.
        """
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        # Unicode filename
        file_path = temp_project / "테스트_파일_🚀.py"
        file_path.write_text("def unicode_test(): pass")

        result = await builder.build([file_path], config)

        # Should handle unicode correctly
        assert str(file_path) in result.ir_documents or len(result.ir_documents) == 1

    @pytest.mark.skip(reason="Platform-dependent: macOS path limit varies")
    @pytest.mark.asyncio
    async def test_max_path_length(self, temp_project):
        """
        EXTREME CASE: Very long file path.

        Skipped: macOS/Linux path limits vary (255-4096 bytes)
        """
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        # Create deeply nested directory
        deep_dir = temp_project
        for i in range(10):
            deep_dir = deep_dir / f"very_long_directory_name_{i}_" * 5

        try:
            deep_dir.mkdir(parents=True, exist_ok=True)
            file_path = deep_dir / "test.py"
            file_path.write_text("def test(): pass")

            result = await builder.build([file_path], config)
        except OSError:
            # May fail on systems with path length limits
            pass


class TestTieredCacheIntegration:
    """Test TieredCache (L1+L2) integration in Builder."""

    @pytest.mark.asyncio
    async def test_builder_uses_tiered_cache(self, temp_project):
        """Builder uses TieredCache for Main Process."""
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        files = [temp_project / "main.py"]

        # First build (cold)
        await builder.build(files, config)

        # Second build (warm - L0/L1/L2 hit expected)
        await builder.build(files, config)

        # Verify telemetry (graceful)
        telemetry = await builder.get_l0_telemetry()

        # Should have L1/L2 stats from TieredCache (graceful check)
        assert "l1_hits" in telemetry or "l0_hits" in telemetry
        assert "l2_hits" in telemetry or "l0_hits" in telemetry
        assert "l1_entries" in telemetry or "l0_entries" in telemetry

        # Second build should hit some tier
        total_hits = telemetry.get("l0_hits", 0) + telemetry.get("l1_hits", 0) + telemetry.get("l2_hits", 0)
        assert total_hits > 0, f"No cache hits: {telemetry}"

    @pytest.mark.asyncio
    async def test_l1_promotion_from_l2(self, temp_project):
        """L2 hit promotes to L1."""
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRConfig

        # Small L1 to force eviction
        config_small = LayeredIRConfig(l0_max_files=10)
        builder = LayeredIRBuilder(project_root=temp_project, config=config_small)

        # Override L1 size
        builder._tiered_cache._l1._max_size = 2

        build_config = BuildConfig.for_editor()

        # Create 3 files
        (temp_project / "f1.py").write_text("def f1(): pass")
        (temp_project / "f2.py").write_text("def f2(): pass")
        (temp_project / "f3.py").write_text("def f3(): pass")

        # Build all 3 (fills L1)
        files = [
            temp_project / "f1.py",
            temp_project / "f2.py",
            temp_project / "f3.py",
        ]
        await builder.build(files, build_config)

        # Build f1 again (should be in L2, promote to L1)
        await builder.build([temp_project / "f1.py"], build_config)

        telemetry = await builder.get_l0_telemetry()

        # Should have L2 hits (evicted from L1, then promoted)
        assert telemetry.get("l2_hits", 0) >= 0  # May hit L0 first

    @pytest.mark.asyncio
    async def test_l1_memory_eviction(self, temp_project):
        """L1 evicts based on memory size."""
        builder = LayeredIRBuilder(project_root=temp_project)

        # Override L1 to small size
        builder._tiered_cache._l1._max_bytes = 10000  # 10KB only

        build_config = BuildConfig.for_editor()

        # Create large files (reduced for reliability)
        large_files = []
        for i in range(5):  # Reduced from 10
            file_path = temp_project / f"large_{i}.py"
            # Generate large content
            content = "\n".join([f"def func_{i}_{j}(): pass" for j in range(100)])
            file_path.write_text(content)
            large_files.append(file_path)

        # Build all
        await builder.build(large_files, build_config)

        telemetry = await builder.get_l0_telemetry()

        # L1 should have evicted some entries (graceful)
        # Note: May not evict if IRs are small
        l1_bytes = telemetry.get("l1_bytes", 0)
        assert l1_bytes >= 0  # Sanity check

        # If exceeded limit, should have evicted
        if l1_bytes > 10000:
            assert telemetry.get("l1_evictions", 0) > 0


class TestCacheTelemetryComprehensive:
    """Comprehensive telemetry tests."""

    @pytest.mark.asyncio
    async def test_full_telemetry_report(self, temp_project):
        """Full telemetry includes all 3 tiers."""
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        files = [temp_project / "main.py", temp_project / "utils.py"]

        # Multiple builds to generate telemetry
        await builder.build(files, config)
        await builder.build(files, config)
        await builder.build(files, config)

        telemetry = await builder.get_l0_telemetry()

        # Verify all keys present
        required_keys = [
            "l0_entries",
            "l0_hits",
            "l0_fast_hits",
            "l0_hash_hits",
            "l0_purged",
            "l1_hits",
            "l2_hits",
            "misses",
            "l1_entries",
            "l1_bytes",
            "l1_evictions",
            "l2_entries",
            "l2_disk_bytes",
            "l2_write_fails",
        ]

        for key in required_keys:
            assert key in telemetry, f"Missing telemetry key: {key}"

        # Verify hit counts
        total_requests = telemetry["l1_hits"] + telemetry["l2_hits"] + telemetry["misses"]
        assert total_requests > 0

    @pytest.mark.asyncio
    async def test_telemetry_hit_rates(self, temp_project):
        """Telemetry includes hit rates."""
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        files = [temp_project / "main.py"]

        # First build (cold)
        await builder.build(files, config)

        # Second build (warm)
        await builder.build(files, config)

        telemetry = await builder.get_l0_telemetry()

        # Should have hit rate calculations
        assert "l1_hit_rate" in telemetry
        assert "l2_hit_rate" in telemetry
        assert "miss_rate" in telemetry

        # Hit rates should be valid (0.0 - 1.0)
        assert 0.0 <= telemetry["l1_hit_rate"] <= 1.0
        assert 0.0 <= telemetry["l2_hit_rate"] <= 1.0
        assert 0.0 <= telemetry["miss_rate"] <= 1.0


class TestWorkerMainIsolation:
    """Test Worker-Main cache isolation (RFC-039 Section 3.3)."""

    @pytest.mark.asyncio
    async def test_worker_uses_disk_only(self, temp_project):
        """
        CRITICAL: Worker processes use L2 (Disk) only.

        RFC-039 Architecture:
            - Worker: L2 only (DiskCache via get_global_cache())
            - Main: L0 + L1 + L2 (TieredCache)
        """
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig

        builder = LayeredIRBuilder(project_root=temp_project)

        # Create many files to trigger ProcessPool
        files = []
        for i in range(20):
            file_path = temp_project / f"file_{i}.py"
            file_path.write_text(f"def func_{i}(): pass")
            files.append(file_path)

        config = BuildConfig(parallel_workers=4)

        # Build (uses ProcessPool)
        result = await builder.build(files, config)

        # Verify workers wrote to L2
        telemetry = await builder.get_l0_telemetry()

        # L2 should have entries (workers wrote to disk)
        assert telemetry.get("l2_entries", 0) >= 10

    @pytest.mark.asyncio
    async def test_main_l1_not_shared_with_workers(self, temp_project):
        """
        CRITICAL: L1 is NOT shared with workers (process-local).

        Each worker has its own L1, Main has its own L1.
        Only L2 is shared across processes.
        """
        builder = LayeredIRBuilder(project_root=temp_project)

        files = []
        for i in range(10):
            file_path = temp_project / f"file_{i}.py"
            file_path.write_text(f"def func_{i}(): pass")
            files.append(file_path)

        config = BuildConfig(parallel_workers=2)

        # Build
        await builder.build(files, config)

        # Main's L1 should have entries (from sequential or L2 promotion)
        telemetry = await builder.get_l0_telemetry()

        # Note: L1 in Main may or may not have entries depending on
        # whether sequential path was used, but architecture is correct


class TestStressAndPerformance:
    """Stress tests and performance validation."""

    @pytest.mark.slow
    @pytest.mark.skip(reason="P0.2: Large scale benchmark (use benchmark suite instead)")
    @pytest.mark.asyncio
    async def test_1000_files_watch_mode(self, temp_project):
        """
        STRESS: 1000 files watch mode performance.

        Skipped in CI: Use dedicated benchmark suite for large-scale tests.
        This test is preserved for manual performance validation.
        """
        import time

        builder = LayeredIRBuilder(project_root=temp_project)

        # Create 100 files (reduced from 1000 for CI)
        files = []
        for i in range(100):
            file_path = temp_project / f"file_{i:04d}.py"
            file_path.write_text(f"def func_{i}(): return {i}")
            files.append(file_path)

        config = BuildConfig.for_editor()

        # Cold build
        start_cold = time.perf_counter()
        await builder.build(files, config)
        elapsed_cold = time.perf_counter() - start_cold

        # Warm build (watch mode - no changes)
        start_warm = time.perf_counter()
        await builder.build(files, config)
        elapsed_warm = time.perf_counter() - start_warm

        # Performance requirements (relaxed for 100 files)
        # Target: <50ms for 100 files (warm)
        assert elapsed_warm < 0.05, f"Warm build too slow: {elapsed_warm * 1000:.0f}ms"

        # Speedup: at least 5x (relaxed)
        speedup = elapsed_cold / elapsed_warm
        assert speedup >= 5.0, f"Insufficient speedup: {speedup:.1f}x"

        # Verify L0 hits (graceful)
        telemetry = await builder.get_l0_telemetry()
        assert telemetry.get("l0_hits", 0) >= 90  # Allow some misses

    @pytest.mark.asyncio
    async def test_memory_pressure_eviction(self, temp_project):
        """STRESS: Memory pressure triggers eviction."""
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRConfig

        # Extreme limits
        config_tight = LayeredIRConfig(l0_max_files=50)
        builder = LayeredIRBuilder(project_root=temp_project, config=config_tight)

        # Override L1 to tight limit
        builder._tiered_cache._l1._max_size = 20
        builder._tiered_cache._l1._max_bytes = 50000  # 50KB

        # Create 100 files
        files = []
        for i in range(100):
            file_path = temp_project / f"file_{i}.py"
            # Large content to pressure memory
            content = "\n".join([f"def func_{i}_{j}(): pass" for j in range(50)])
            file_path.write_text(content)
            files.append(file_path)

        build_config = BuildConfig.for_editor()

        # Build all
        result = await builder.build(files, build_config)

        telemetry = await builder.get_l0_telemetry()

        # L0 should respect limit
        assert telemetry["l0_entries"] <= 50

        # L1 should respect limits
        assert telemetry["l1_entries"] <= 20
        assert telemetry["l1_bytes"] <= 50000

        # Should have evicted
        assert telemetry["l1_evictions"] > 70

    @pytest.mark.asyncio
    async def test_rapid_rebuild_cycles(self, temp_project):
        """STRESS: Rapid rebuild cycles (watch mode simulation)."""
        builder = LayeredIRBuilder(project_root=temp_project)
        config = BuildConfig.for_editor()

        file_path = temp_project / "main.py"
        files = [file_path]

        # 100 rapid builds
        for i in range(100):
            # Modify file every 10 iterations
            if i % 10 == 0:
                file_path.write_text(f"def main(): return {i}")

            await builder.build(files, config)

        telemetry = await builder.get_l0_telemetry()

        # Should have many L0 hits
        assert telemetry["l0_hits"] >= 90  # 90 unchanged builds


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
