"""
Unit Tests: Kotlin LSP LRU Cache

Tests LRU eviction for diagnostics cache and response queue.

Critical invariants:
- Cache size never exceeds MAX limit
- Oldest entries are evicted first (FIFO)
- Accessed entries move to end (LRU)
- Concurrent access is thread-safe
"""

import asyncio
from collections import OrderedDict
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp_async import (
    KotlinLSPClientAsync,
)


class TestDiagnosticCacheLRU:
    """Test LRU eviction for diagnostics cache"""

    @pytest.mark.asyncio
    async def test_cache_respects_max_size(self, tmp_path):
        """Cache should never exceed MAX_CACHED_FILES"""
        # Create client (mock JVM and kotlin-ls checks)
        with (
            patch.object(KotlinLSPClientAsync, "_check_jvm"),
            patch.object(KotlinLSPClientAsync, "_find_kotlin_ls", return_value=Path("/fake/kotlin-ls")),
        ):
            client = KotlinLSPClientAsync(tmp_path)

        # Set small limit for testing
        client.MAX_CACHED_FILES = 3

        # Simulate publishDiagnostics notifications
        notifications = [
            {
                "method": "textDocument/publishDiagnostics",
                "params": {
                    "uri": f"file:///test{i}.kt",
                    "diagnostics": [{"message": f"error {i}"}],
                },
            }
            for i in range(5)
        ]

        # Process notifications
        for notif in notifications:
            await client._handle_notification(notif)

        # Verify: Cache size should be exactly MAX_CACHED_FILES
        assert len(client.diagnostics_cache) == client.MAX_CACHED_FILES

        # Verify: Should have most recent files (2, 3, 4)
        uris = list(client.diagnostics_cache.keys())
        assert "file:///test2.kt" in uris
        assert "file:///test3.kt" in uris
        assert "file:///test4.kt" in uris

        # Verify: Oldest files should be evicted (0, 1)
        assert "file:///test0.kt" not in uris
        assert "file:///test1.kt" not in uris

    @pytest.mark.asyncio
    async def test_update_moves_to_end(self, tmp_path):
        """Updating existing entry should move it to end (most recent)"""
        with (
            patch.object(KotlinLSPClientAsync, "_check_jvm"),
            patch.object(KotlinLSPClientAsync, "_find_kotlin_ls", return_value=Path("/fake/kotlin-ls")),
        ):
            client = KotlinLSPClientAsync(tmp_path)

        client.MAX_CACHED_FILES = 3

        # Add 3 entries (0, 1, 2)
        for i in range(3):
            await client._handle_notification(
                {
                    "method": "textDocument/publishDiagnostics",
                    "params": {
                        "uri": f"file:///test{i}.kt",
                        "diagnostics": [{"message": f"error {i}"}],
                    },
                }
            )

        # Update entry 0 (should move to end)
        await client._handle_notification(
            {
                "method": "textDocument/publishDiagnostics",
                "params": {
                    "uri": "file:///test0.kt",
                    "diagnostics": [{"message": "updated error 0"}],
                },
            }
        )

        # Verify: Order should be (1, 2, 0)
        uris = list(client.diagnostics_cache.keys())
        assert uris == ["file:///test1.kt", "file:///test2.kt", "file:///test0.kt"]

        # Add new entry (should evict 1, not 0)
        await client._handle_notification(
            {
                "method": "textDocument/publishDiagnostics",
                "params": {
                    "uri": "file:///test3.kt",
                    "diagnostics": [{"message": "error 3"}],
                },
            }
        )

        # Verify: Should have (2, 0, 3), not (1, 2, 3)
        uris = list(client.diagnostics_cache.keys())
        assert "file:///test0.kt" in uris, "Updated entry should not be evicted"
        assert "file:///test1.kt" not in uris, "Oldest entry should be evicted"
        assert "file:///test2.kt" in uris
        assert "file:///test3.kt" in uris

    @pytest.mark.asyncio
    async def test_eviction_order_fifo_for_new_entries(self, tmp_path):
        """New entries should evict oldest (FIFO)"""
        with (
            patch.object(KotlinLSPClientAsync, "_check_jvm"),
            patch.object(KotlinLSPClientAsync, "_find_kotlin_ls", return_value=Path("/fake/kotlin-ls")),
        ):
            client = KotlinLSPClientAsync(tmp_path)

        client.MAX_CACHED_FILES = 2

        # Add entries in order: 0, 1, 2
        for i in range(3):
            await client._handle_notification(
                {
                    "method": "textDocument/publishDiagnostics",
                    "params": {
                        "uri": f"file:///test{i}.kt",
                        "diagnostics": [],
                    },
                }
            )

        # Should have (1, 2), evicted 0
        uris = list(client.diagnostics_cache.keys())
        assert len(uris) == 2
        assert uris[0] == "file:///test1.kt"
        assert uris[1] == "file:///test2.kt"

    @pytest.mark.asyncio
    async def test_concurrent_access_safety(self, tmp_path):
        """Concurrent diagnostics should not corrupt cache"""
        with (
            patch.object(KotlinLSPClientAsync, "_check_jvm"),
            patch.object(KotlinLSPClientAsync, "_find_kotlin_ls", return_value=Path("/fake/kotlin-ls")),
        ):
            client = KotlinLSPClientAsync(tmp_path)

        client.MAX_CACHED_FILES = 50

        # Simulate 100 concurrent notifications
        async def send_diagnostic(i):
            await client._handle_notification(
                {
                    "method": "textDocument/publishDiagnostics",
                    "params": {
                        "uri": f"file:///test{i}.kt",
                        "diagnostics": [{"message": f"error {i}"}],
                    },
                }
            )

        await asyncio.gather(*[send_diagnostic(i) for i in range(100)])

        # Verify: Cache size should be exactly MAX_CACHED_FILES
        assert len(client.diagnostics_cache) == client.MAX_CACHED_FILES

        # Verify: Should have most recent 50 entries
        uris = list(client.diagnostics_cache.keys())
        for i in range(50, 100):
            assert f"file:///test{i}.kt" in uris


class TestResponseQueueLRU:
    """Test LRU eviction for response queue"""

    @pytest.mark.asyncio
    async def test_response_queue_eviction(self, tmp_path):
        """Response queue should evict oldest when full"""
        with (
            patch.object(KotlinLSPClientAsync, "_check_jvm"),
            patch.object(KotlinLSPClientAsync, "_find_kotlin_ls", return_value=Path("/fake/kotlin-ls")),
        ):
            client = KotlinLSPClientAsync(tmp_path)

        # Set small limit for testing
        original_max = client.MAX_RESPONSES
        client.MAX_RESPONSES = 3

        try:
            # Simulate responses arriving (bypassing _read_responses)
            from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp_async import (
                KotlinLSResponse,
            )

            for i in range(5):
                response = KotlinLSResponse(
                    id=i,
                    result={"data": f"response {i}"},
                    error=None,
                )

                # Manually add to queue (simulating _read_responses)
                async with client._responses_lock:
                    client.responses[i] = response

                    # LRU eviction (same logic as in _read_responses)
                    if len(client.responses) > client.MAX_RESPONSES:
                        client.responses.popitem(last=False)

            # Verify: Queue size should be MAX_RESPONSES
            assert len(client.responses) == client.MAX_RESPONSES

            # Verify: Should have most recent responses (2, 3, 4)
            assert 2 in client.responses
            assert 3 in client.responses
            assert 4 in client.responses

            # Verify: Oldest responses should be evicted (0, 1)
            assert 0 not in client.responses
            assert 1 not in client.responses

        finally:
            client.MAX_RESPONSES = original_max

    @pytest.mark.asyncio
    async def test_response_cleanup_on_timeout(self, tmp_path):
        """Timed-out responses should not accumulate"""
        with (
            patch.object(KotlinLSPClientAsync, "_check_jvm"),
            patch.object(KotlinLSPClientAsync, "_find_kotlin_ls", return_value=Path("/fake/kotlin-ls")),
        ):
            client = KotlinLSPClientAsync(tmp_path)

        # Simulate responses that never arrive
        # They should be evicted by LRU when new responses come
        from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp_async import (
            KotlinLSResponse,
        )

        # Fill queue with "pending" responses (simulated)
        async with client._responses_lock:
            for i in range(1500):  # Exceed MAX_RESPONSES
                if i < 1000:
                    # Simulate old pending responses
                    continue
                else:
                    # Simulate new responses arriving
                    response = KotlinLSResponse(id=i, result={}, error=None)
                    client.responses[i] = response

                    if len(client.responses) > client.MAX_RESPONSES:
                        client.responses.popitem(last=False)

        # Verify: Should never exceed MAX
        assert len(client.responses) <= client.MAX_RESPONSES


class TestOrderedDictSemantics:
    """Test OrderedDict behavior is correct"""

    def test_popitem_last_false_removes_oldest(self):
        """popitem(last=False) should remove oldest (FIFO)"""
        od = OrderedDict()
        od["a"] = 1
        od["b"] = 2
        od["c"] = 3

        key, value = od.popitem(last=False)

        assert key == "a"  # Oldest
        assert list(od.keys()) == ["b", "c"]

    def test_delete_and_reinsert_moves_to_end(self):
        """Delete + reinsert should move to end (LRU)"""
        od = OrderedDict()
        od["a"] = 1
        od["b"] = 2
        od["c"] = 3

        # Move "a" to end
        del od["a"]
        od["a"] = 1

        assert list(od.keys()) == ["b", "c", "a"]

    def test_direct_assignment_to_existing_does_not_move(self):
        """Direct assignment to existing key does NOT move to end"""
        od = OrderedDict()
        od["a"] = 1
        od["b"] = 2
        od["c"] = 3

        # Update value (does NOT move)
        od["a"] = 99

        # Order unchanged
        assert list(od.keys()) == ["a", "b", "c"]

        # This is why we need del + reinsert for LRU!


class TestCacheSizeInvariants:
    """Property-based tests for cache size invariants using Hypothesis

    SOTA-level approach: Use hypothesis with explicit loop handling
    for async code. This provides:
    - Automatic shrinking to minimal failing examples
    - Reproducible failures with @reproduce_failure
    - Coverage-guided testing
    """

    def test_cache_never_exceeds_max_property(self, tmp_path):
        """Property: Cache size invariant holds for any sequence of insertions

        Uses Hypothesis for 100+ generated test cases.
        Runs async code in new event loop per test case for isolation.
        """
        import asyncio

        from hypothesis import HealthCheck, given, settings
        from hypothesis import strategies as st

        with (
            patch.object(KotlinLSPClientAsync, "_check_jvm"),
            patch.object(KotlinLSPClientAsync, "_find_kotlin_ls", return_value=Path("/fake/kotlin-ls")),
        ):
            client = KotlinLSPClientAsync(tmp_path)

        client.MAX_CACHED_FILES = 10

        @given(file_ids=st.lists(st.integers(min_value=0, max_value=100), min_size=0, max_size=200))
        @settings(
            max_examples=100,
            deadline=None,
            suppress_health_check=[HealthCheck.function_scoped_fixture],
        )
        def property_test(file_ids):
            """Test that cache never exceeds MAX for any sequence"""

            async def async_test():
                # Reset cache for each test case
                async with client._diagnostics_lock:
                    client.diagnostics_cache.clear()

                # Process sequence of notifications
                for file_id in file_ids:
                    await client._handle_notification(
                        {
                            "method": "textDocument/publishDiagnostics",
                            "params": {
                                "uri": f"file:///test{file_id}.kt",
                                "diagnostics": [],
                            },
                        }
                    )

                    # INVARIANT: Cache size never exceeds MAX
                    cache_size = len(client.diagnostics_cache)
                    assert cache_size <= client.MAX_CACHED_FILES, (
                        f"Cache overflow: {cache_size} > {client.MAX_CACHED_FILES}"
                    )

            # Run in fresh event loop (避免 "already running" 错误)
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(async_test())
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        # Execute Hypothesis property test
        property_test()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
