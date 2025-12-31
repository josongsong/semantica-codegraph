"""
Performance Benchmarks: Kotlin LSP

Measures latency and throughput for Kotlin LSP operations.

Requirements:
    pip install pytest-benchmark

Usage:
    pytest tests/benchmarks/test_kotlin_performance.py --benchmark-only
"""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.lsp.kotlin import KotlinAdapter


class TestKotlinPerformance:
    """Performance benchmarks for Kotlin LSP operations"""

    @pytest.fixture
    def mock_client(self):
        """Create mock client with realistic latency"""
        client = Mock()

        async def mock_hover_with_latency(*args, **kwargs):
            await asyncio.sleep(0.05)  # Simulate 50ms latency
            return {
                "contents": {"value": "```kotlin\nval x: String\n```"},
                "range": {"start": {"line": 0, "character": 0}},
            }

        async def mock_definition_with_latency(*args, **kwargs):
            await asyncio.sleep(0.05)  # Simulate 50ms latency
            return [
                {
                    "uri": "file:///test.kt",
                    "range": {"start": {"line": 0, "character": 0}},
                }
            ]

        async def mock_references_with_latency(*args, **kwargs):
            await asyncio.sleep(0.05)  # Simulate 50ms latency
            return [
                {
                    "uri": "file:///test.kt",
                    "range": {"start": {"line": 0, "character": 0}},
                }
            ]

        client.hover = AsyncMock(side_effect=mock_hover_with_latency)
        client.definition = AsyncMock(side_effect=mock_definition_with_latency)
        client.references = AsyncMock(side_effect=mock_references_with_latency)
        client.diagnostics = AsyncMock(return_value=[])

        return client

    @pytest.mark.asyncio
    @pytest.mark.benchmark(group="hover")
    async def test_hover_latency(self, mock_client, benchmark):
        """Benchmark: Hover latency should be < 200ms"""
        adapter = KotlinAdapter(mock_client)

        async def run_hover():
            return await adapter.hover(Path("/test.kt"), line=10, col=5)

        # Benchmark async function
        start = time.perf_counter()
        result = await run_hover()
        latency = time.perf_counter() - start

        # Assertions
        assert result is not None
        assert latency < 0.2, f"Hover latency {latency:.3f}s exceeds 200ms SLA"

        print(f"\n✓ Hover latency: {latency * 1000:.1f}ms")

    @pytest.mark.asyncio
    @pytest.mark.benchmark(group="definition")
    async def test_definition_latency(self, mock_client, benchmark):
        """Benchmark: Definition latency should be < 150ms"""
        adapter = KotlinAdapter(mock_client)

        async def run_definition():
            return await adapter.definition(Path("/test.kt"), line=10, col=5)

        start = time.perf_counter()
        result = await run_definition()
        latency = time.perf_counter() - start

        # Assertions
        assert result is not None
        assert latency < 0.15, f"Definition latency {latency:.3f}s exceeds 150ms SLA"

        print(f"\n✓ Definition latency: {latency * 1000:.1f}ms")

    @pytest.mark.asyncio
    @pytest.mark.benchmark(group="throughput")
    async def test_concurrent_requests(self, mock_client):
        """Benchmark: Handle 100 concurrent requests < 1s"""
        adapter = KotlinAdapter(mock_client)

        async def make_request(i):
            return await adapter.hover(Path(f"/test{i}.kt"), line=i, col=0)

        # Run 100 concurrent requests
        start = time.perf_counter()
        tasks = [make_request(i) for i in range(100)]
        results = await asyncio.gather(*tasks)
        duration = time.perf_counter() - start

        # Assertions
        assert len(results) == 100
        assert all(r is not None for r in results)
        assert duration < 1.0, f"100 concurrent requests took {duration:.3f}s (> 1s)"

        throughput = 100 / duration
        print(f"\n✓ Throughput: {throughput:.1f} req/s ({duration:.3f}s for 100 requests)")

    @pytest.mark.asyncio
    async def test_memory_efficiency(self, mock_client):
        """Benchmark: Memory usage should be stable"""
        import tracemalloc

        adapter = KotlinAdapter(mock_client)

        # Measure initial memory
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        # Run 1000 requests
        for i in range(1000):
            await adapter.hover(Path("/test.kt"), line=i % 100, col=0)

        # Measure final memory
        snapshot2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Calculate memory diff
        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        total_diff = sum(stat.size_diff for stat in top_stats)

        # Memory growth should be < 5MB for 1000 requests (realistic limit)
        max_growth = 5 * 1024 * 1024  # 5MB
        assert total_diff < max_growth, f"Memory growth {total_diff / 1024:.1f}KB exceeds 5MB"

        print(f"\n✓ Memory growth for 1000 requests: {total_diff / 1024:.1f}KB")


class TestEdgeCasePerformance:
    """Performance tests for edge cases"""

    @pytest.mark.asyncio
    async def test_large_file_handling(self):
        """Benchmark: Large files should not timeout"""
        mock_client = Mock()

        # Simulate large file response
        large_content = "```kotlin\n" + ("val x: String\n" * 10000) + "```"
        mock_client.hover = AsyncMock(
            return_value={
                "contents": {"value": large_content},
            }
        )

        adapter = KotlinAdapter(mock_client)

        start = time.perf_counter()
        result = await adapter.hover(Path("/large.kt"), line=1000, col=0)
        duration = time.perf_counter() - start

        assert result is not None
        assert duration < 1.0, f"Large file handling took {duration:.3f}s (> 1s)"

        print(f"\n✓ Large file (10K lines) handled in {duration * 1000:.1f}ms")

    @pytest.mark.asyncio
    async def test_error_handling_overhead(self):
        """Benchmark: Error handling should add minimal overhead"""
        mock_client = Mock()
        mock_client.hover = AsyncMock(side_effect=RuntimeError("Server error"))

        adapter = KotlinAdapter(mock_client)

        # Measure error path
        start = time.perf_counter()
        result = await adapter.hover(Path("/test.kt"), line=10, col=5)
        duration = time.perf_counter() - start

        assert result is None  # Error returns None
        assert duration < 0.01, f"Error handling took {duration * 1000:.1f}ms (> 10ms)"

        print(f"\n✓ Error handling overhead: {duration * 1000:.3f}ms")


class TestCachePerformance:
    """Performance tests for caching mechanisms"""

    @pytest.mark.asyncio
    async def test_diagnostic_cache_hit_rate(self):
        """Benchmark: Diagnostic cache should have high hit rate"""
        from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp_async import (
            KotlinLSPClientAsync,
        )

        # This would require real LSP server
        # Placeholder for integration test
        pytest.skip("Requires real kotlin-language-server")


if __name__ == "__main__":
    # Run benchmarks
    pytest.main([__file__, "--benchmark-only", "-v"])
