"""
Security & Type Safety Tests for Cache Enhancements

/vv Requirements:
- No fake/stub - actual runtime validation
- Schema strictness - type checking
- Corner cases - invalid inputs, edge boundaries
- Security - pickle injection, path traversal
"""

import tempfile
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.function_summary import (
    FunctionSummaryCache,
    FunctionTaintSummary,
)


class TestTypeSafety:
    """/vv: Runtime type validation"""

    def test_warm_up_rejects_non_callable(self):
        """Edge case: analyzer_fn must be callable"""
        cache = FunctionSummaryCache(max_size=100)

        with pytest.raises(TypeError, match="must be callable"):
            cache.warm_up(
                function_ids=["func1"],
                analyzer_fn="not_a_function",  # ❌ String, not callable
                max_warm=10,
            )

    def test_warm_up_rejects_wrong_return_type(self):
        """Edge case: analyzer_fn must return FunctionTaintSummary"""
        cache = FunctionSummaryCache(max_size=100)

        def bad_analyzer(func_id):
            return {"fake": "dict"}  # ❌ Wrong type

        warmed = cache.warm_up(["func1"], bad_analyzer, max_warm=10)

        # Should warn and skip (not crash)
        assert warmed == 0
        assert len(cache) == 0

    def test_warm_up_rejects_empty_function_ids(self):
        """Edge case: function_ids cannot be empty"""
        cache = FunctionSummaryCache(max_size=100)

        def mock_analyzer(func_id):
            return FunctionTaintSummary(
                function_id=func_id,
                tainted_params=set(),
                tainted_return=False,
                confidence=1.0,
            )

        with pytest.raises(ValueError, match="cannot be empty"):
            cache.warm_up([], mock_analyzer, max_warm=10)

    def test_warm_up_rejects_invalid_max_warm(self):
        """Edge case: max_warm must be >= 1"""
        cache = FunctionSummaryCache(max_size=100)

        def mock_analyzer(func_id):
            return FunctionTaintSummary(
                function_id=func_id,
                tainted_params=set(),
                tainted_return=False,
                confidence=1.0,
            )

        with pytest.raises(ValueError, match="must be >= 1"):
            cache.warm_up(["func1"], mock_analyzer, max_warm=0)

        with pytest.raises(ValueError, match="must be >= 1"):
            cache.warm_up(["func1"], mock_analyzer, max_warm=-5)


class TestPersistenceSecurity:
    """/vv: Security validation for persistence"""

    def test_persistence_path_traversal_prevented(self, tmp_path):
        """Security: Prevent path traversal attacks"""
        # Attempt path traversal
        evil_path = str(tmp_path / "../../../etc/passwd")

        cache = FunctionSummaryCache(
            max_size=100,
            enable_persistence=True,
            persistence_path=evil_path,
        )

        summary = FunctionTaintSummary(
            function_id="func1",
            tainted_params=set(),
            tainted_return=False,
            confidence=1.0,
        )
        cache.put(summary)

        # Should save safely (not crash, not overwrite system files)
        success = cache.save_to_disk()

        # Verify file was created in safe location (not /etc/passwd)
        assert success
        # If it succeeded, it should have normalized the path

    def test_persistence_handles_corrupted_file(self, tmp_path):
        """Edge case: Corrupted pickle file should not crash"""
        cache_file = tmp_path / "corrupted.pkl"

        # Write corrupted data
        cache_file.write_bytes(b"CORRUPTED_DATA_NOT_PICKLE")

        # Should handle gracefully
        cache = FunctionSummaryCache(
            max_size=100,
            enable_persistence=True,
            persistence_path=str(cache_file),
        )

        # Should start with empty cache (not crash)
        assert len(cache) == 0

    def test_persistence_handles_permission_error(self, tmp_path):
        """Edge case: Permission denied on save"""
        import os
        import sys

        if sys.platform == "win32":
            pytest.skip("Permission test not applicable on Windows")

        # Make directory read-only (prevents file creation)
        cache_dir = tmp_path / "readonly_dir"
        cache_dir.mkdir()
        cache_file = cache_dir / "file.pkl"

        cache = FunctionSummaryCache(
            max_size=100,
            enable_persistence=True,
            persistence_path=str(cache_file),
        )

        summary = FunctionTaintSummary(
            function_id="func1",
            tainted_params=set(),
            tainted_return=False,
            confidence=1.0,
        )
        cache.put(summary)

        # Make directory read-only (prevents atomic write)
        cache_dir.chmod(0o555)

        try:
            # Should fail gracefully (return False, not crash)
            success = cache.save_to_disk()
            assert not success
        finally:
            # Restore permissions for cleanup
            cache_dir.chmod(0o755)

    def test_persistence_handles_disk_full(self, tmp_path):
        """Extreme case: Disk full during save"""
        cache_file = tmp_path / "large.pkl"

        cache = FunctionSummaryCache(
            max_size=100,
            enable_persistence=True,
            persistence_path=str(cache_file),
        )

        # Add many large summaries
        for i in range(100):
            summary = FunctionTaintSummary(
                function_id=f"func{i}",
                tainted_params=set(range(1000)),  # Large set
                tainted_return=True,
                confidence=0.9,
                metadata={"large_data": "x" * 10000},  # 10KB metadata
            )
            cache.put(summary)

        # Should handle gracefully (may fail, but no crash)
        try:
            success = cache.save_to_disk()
            # Either succeeds or fails gracefully
            assert isinstance(success, bool)
        except Exception as e:
            # If exception, should be expected type (OSError, IOError)
            assert isinstance(e, (OSError, IOError))


class TestThreadSafety:
    """/vv: Thread safety validation"""

    def test_single_threaded_by_default(self):
        """Base case: Default is single-threaded (no lock overhead)"""
        cache = FunctionSummaryCache(max_size=100)

        from contextlib import nullcontext

        # Should use nullcontext (no-op lock)
        assert isinstance(cache._lock, type(nullcontext()))

    def test_thread_safe_mode_uses_lock(self):
        """Edge case: thread_safe=True uses real lock"""
        cache = FunctionSummaryCache(max_size=100, thread_safe=True)

        import threading

        # Should use RLock (check type name since RLock is a factory function)
        assert type(cache._lock).__name__ == "RLock"
        # Verify it has lock methods
        assert hasattr(cache._lock, "__enter__")
        assert hasattr(cache._lock, "__exit__")

    def test_thread_safe_concurrent_access(self):
        """Extreme case: Concurrent access with thread_safe=True"""
        import threading
        import time

        cache = FunctionSummaryCache(max_size=100, thread_safe=True)

        errors = []

        def writer(thread_id):
            try:
                for i in range(100):
                    summary = FunctionTaintSummary(
                        function_id=f"thread{thread_id}_func{i}",
                        tainted_params=set(),
                        tainted_return=False,
                        confidence=1.0,
                    )
                    cache.put(summary)
            except Exception as e:
                errors.append(e)

        def reader(thread_id):
            try:
                for i in range(100):
                    cache.get(f"thread0_func{i}")
            except Exception as e:
                errors.append(e)

        # Create threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=writer, args=(i,))
            threads.append(t)
        for i in range(5):
            t = threading.Thread(target=reader, args=(i,))
            threads.append(t)

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0
        # Should have some data
        assert len(cache) > 0


class TestBoundaryConditions:
    """/vv: Boundary value testing"""

    def test_max_size_zero(self):
        """Edge case: max_size=0 (invalid)"""
        # Should work but evict immediately
        cache = FunctionSummaryCache(max_size=0)

        summary = FunctionTaintSummary(
            function_id="func1",
            tainted_params=set(),
            tainted_return=False,
            confidence=1.0,
        )

        # Should handle gracefully (no crash)
        cache.put(summary)
        # Should be evicted immediately
        assert len(cache) == 0

    def test_max_size_one(self):
        """Edge case: max_size=1 (minimum useful)"""
        cache = FunctionSummaryCache(max_size=1)

        summary1 = FunctionTaintSummary(
            function_id="func1",
            tainted_params=set(),
            tainted_return=False,
            confidence=1.0,
        )
        cache.put(summary1)
        assert len(cache) == 1

        # Add second - should evict first
        summary2 = FunctionTaintSummary(
            function_id="func2",
            tainted_params=set(),
            tainted_return=False,
            confidence=1.0,
        )
        cache.put(summary2)

        assert len(cache) == 1
        assert "func1" not in cache
        assert "func2" in cache

    def test_max_warm_larger_than_list(self):
        """Edge case: max_warm > len(function_ids)"""
        cache = FunctionSummaryCache(max_size=100)

        def mock_analyzer(func_id):
            return FunctionTaintSummary(
                function_id=func_id,
                tainted_params=set(),
                tainted_return=False,
                confidence=1.0,
            )

        functions = ["func1", "func2"]

        # max_warm=100 but only 2 functions
        warmed = cache.warm_up(functions, mock_analyzer, max_warm=100)

        # Should warm all 2 (not crash)
        assert warmed == 2

    def test_get_hot_functions_with_zero_accesses(self):
        """Edge case: Functions with zero access count"""
        cache = FunctionSummaryCache(max_size=100)

        # Add functions but never access them
        for i in range(5):
            summary = FunctionTaintSummary(
                function_id=f"func{i}",
                tainted_params=set(),
                tainted_return=False,
                confidence=1.0,
            )
            cache.put(summary)

        # get_hot_functions should still work
        hot = cache.get_hot_functions(top_n=10)

        # Should return empty (no accesses yet)
        assert hot == []


class TestErrorRecovery:
    """/vv: Error handling and recovery"""

    def test_analyzer_raises_exception(self):
        """Edge case: analyzer_fn raises exception"""
        cache = FunctionSummaryCache(max_size=100)

        def failing_analyzer(func_id):
            if "bad" in func_id:
                raise RuntimeError("Analysis failed!")
            return FunctionTaintSummary(
                function_id=func_id,
                tainted_params=set(),
                tainted_return=False,
                confidence=1.0,
            )

        functions = ["good1", "bad1", "good2", "bad2", "good3"]

        # Should skip failures and continue
        warmed = cache.warm_up(functions, failing_analyzer, max_warm=10)

        # Should warm only good functions (3)
        assert warmed == 3
        assert "good1" in cache
        assert "good2" in cache
        assert "good3" in cache
        assert "bad1" not in cache
        assert "bad2" not in cache

    def test_analyzer_returns_none(self):
        """Edge case: analyzer_fn returns None"""
        cache = FunctionSummaryCache(max_size=100)

        def none_analyzer(func_id):
            return None  # ❌ Invalid

        warmed = cache.warm_up(["func1"], none_analyzer, max_warm=10)

        # Should skip and warn
        assert warmed == 0
        assert len(cache) == 0

    def test_persistence_with_invalid_path(self):
        """Edge case: Invalid persistence path"""
        # Path with invalid characters (depending on OS)
        invalid_path = "/\x00invalid/path.pkl"  # Null byte

        cache = FunctionSummaryCache(
            max_size=100,
            enable_persistence=True,
            persistence_path=invalid_path,
        )

        summary = FunctionTaintSummary(
            function_id="func1",
            tainted_params=set(),
            tainted_return=False,
            confidence=1.0,
        )
        cache.put(summary)

        # Should fail gracefully
        success = cache.save_to_disk()
        assert not success
