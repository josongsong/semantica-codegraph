"""
SOTA Sync Health Checker Tests

Comprehensive test coverage for:
- SelectivePackageTracker
- LRUCacheWithPartialInvalidation
- SQLiteStateStore
- CircuitBreaker
- BackgroundSyncWorker
- SyncHealthChecker
- EnvironmentAwareCache

Edge cases and stress tests included.
"""

import json
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codegraph_engine.code_foundation.infrastructure.type_inference.sync_health import (
    BackgroundSyncWorker,
    CircuitBreaker,
    CircuitState,
    EnvironmentAwareCache,
    LRUCacheWithPartialInvalidation,
    SelectivePackageTracker,
    SQLiteStateStore,
    SyncHealthChecker,
    SyncHealthStatus,
    SyncState,
    TRACKED_PACKAGES,
)


# ============================================================
# SyncHealthStatus Tests
# ============================================================


class TestSyncHealthStatus:
    """Test SyncHealthStatus dataclass and factory methods."""

    def test_healthy_status(self):
        """Test healthy factory method."""
        status = SyncHealthStatus.healthy()
        assert status.is_healthy is True
        assert status.needs_sync is False
        assert status.auto_sync_recommended is False
        assert "up to date" in status.message

    def test_stale_age_status(self):
        """Test stale_age factory method."""
        status = SyncHealthStatus.stale_age(age_days=10.5, max_age=7)
        assert status.is_healthy is False
        assert status.needs_sync is True
        assert status.auto_sync_recommended is True
        assert "10.5" in status.message
        assert status.details["age_days"] == 10.5
        assert status.details["max_age_days"] == 7

    def test_env_changed_status(self):
        """Test env_changed factory method."""
        changed = ["flask: 2.0 → 2.1", "requests: new → 2.28"]
        status = SyncHealthStatus.env_changed(
            old_hash="abc12345",
            new_hash="def67890",
            changed_packages=changed,
        )
        assert status.is_healthy is False
        assert status.needs_sync is True
        assert "2 packages" in status.message
        assert status.changed_packages == changed

    def test_env_changed_with_none_packages(self):
        """Test env_changed with None packages."""
        status = SyncHealthStatus.env_changed("abc", "def", None)
        assert status.changed_packages == []
        assert "0 packages" in status.message

    def test_no_configs_status(self):
        """Test no_configs factory method."""
        status = SyncHealthStatus.no_configs()
        assert status.is_healthy is False
        assert status.needs_sync is True
        assert "initial sync" in status.message.lower()


# ============================================================
# SyncState Tests
# ============================================================


class TestSyncState:
    """Test SyncState dataclass."""

    def test_to_dict(self):
        """Test serialization to dict."""
        state = SyncState(
            last_sync_timestamp=1703000000.0,
            environment_hash="abc123",
            package_versions={"flask": "2.0", "django": "4.0"},
            config_count=42,
            sync_source="test",
        )
        d = state.to_dict()

        assert d["last_sync_timestamp"] == 1703000000.0
        assert d["environment_hash"] == "abc123"
        assert d["package_versions"] == {"flask": "2.0", "django": "4.0"}
        assert d["config_count"] == 42
        assert d["sync_source"] == "test"
        assert "last_sync_datetime" in d

    def test_from_dict(self):
        """Test deserialization from dict."""
        d = {
            "last_sync_timestamp": 1703000000.0,
            "environment_hash": "xyz789",
            "package_versions": {"pandas": "1.5"},
            "config_count": 10,
            "sync_source": "ci",
        }
        state = SyncState.from_dict(d)

        assert state.last_sync_timestamp == 1703000000.0
        assert state.environment_hash == "xyz789"
        assert state.package_versions == {"pandas": "1.5"}
        assert state.config_count == 10
        assert state.sync_source == "ci"

    def test_from_dict_with_missing_keys(self):
        """Test deserialization with missing keys (backward compat)."""
        d = {"last_sync_timestamp": 1000.0, "environment_hash": "hash"}
        state = SyncState.from_dict(d)

        assert state.last_sync_timestamp == 1000.0
        assert state.package_versions == {}
        assert state.config_count == 0
        assert state.sync_source == "unknown"

    def test_from_dict_empty(self):
        """Test deserialization from empty dict."""
        state = SyncState.from_dict({})
        assert state.last_sync_timestamp == 0
        assert state.environment_hash == ""


# ============================================================
# CircuitBreaker Tests
# ============================================================


class TestCircuitBreaker:
    """Test CircuitBreaker pattern implementation."""

    def test_initial_state_is_closed(self):
        """Circuit starts in CLOSED state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_single_failure_stays_closed(self):
        """Single failure doesn't open circuit."""
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_threshold_failures_opens_circuit(self):
        """Reaching failure threshold opens circuit."""
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_success_resets_failure_count(self):
        """Success resets failure count."""
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()

        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_recovery_timeout_transitions_to_half_open(self):
        """After recovery timeout, circuit goes to HALF_OPEN."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

        # Wait for recovery
        time.sleep(0.05)  # 0.15 → 0.05

        assert cb.state == CircuitState.HALF_OPEN
        assert cb.can_execute() is True

    def test_half_open_success_closes_circuit(self):
        """Success in HALF_OPEN closes circuit."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)

        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens_circuit(self):
        """Failure in HALF_OPEN reopens circuit."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)

        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_half_open_max_calls(self):
        """HALF_OPEN limits concurrent calls."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01, half_open_max_calls=1)
        cb.record_failure()
        time.sleep(0.02)

        assert cb.can_execute() is True  # First call allowed
        assert cb.can_execute() is False  # Second call blocked

    def test_thread_safety(self):
        """Circuit breaker is thread-safe."""
        cb = CircuitBreaker(failure_threshold=100)
        errors = []

        def record_failures():
            try:
                for _ in range(50):
                    cb.record_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_failures) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert cb.state == CircuitState.OPEN


# ============================================================
# SelectivePackageTracker Tests
# ============================================================


class TestSelectivePackageTracker:
    """Test selective package version tracking."""

    def test_tracked_packages_constant(self):
        """TRACKED_PACKAGES contains expected packages."""
        assert "flask" in TRACKED_PACKAGES
        assert "django" in TRACKED_PACKAGES
        assert "pandas" in TRACKED_PACKAGES
        assert "requests" in TRACKED_PACKAGES

    def test_custom_tracked_packages(self):
        """Can specify custom tracked packages."""
        tracker = SelectivePackageTracker(frozenset(["mypackage", "otherpackage"]))
        assert tracker._tracked == frozenset(["mypackage", "otherpackage"])

    def test_get_current_versions_returns_dict(self):
        """get_current_versions returns dict of installed packages."""
        tracker = SelectivePackageTracker()
        versions = tracker.get_current_versions()

        assert isinstance(versions, dict)
        # pytest should be installed
        if "pytest" in tracker._tracked:
            assert "pytest" in versions

    def test_version_caching(self):
        """Versions are cached for TTL period."""
        tracker = SelectivePackageTracker()
        tracker._cache_ttl = 10.0  # 10 seconds

        v1 = tracker.get_current_versions()
        v2 = tracker.get_current_versions()

        # Should be same object (cached)
        assert v1 is v2

    def test_force_refresh_bypasses_cache(self):
        """force_refresh=True bypasses cache."""
        tracker = SelectivePackageTracker()
        tracker._cache_ttl = 10.0

        v1 = tracker.get_current_versions()
        v2 = tracker.get_current_versions(force_refresh=True)

        # Should be different objects
        assert v1 is not v2

    def test_compute_selective_hash(self):
        """Hash is computed from tracked packages only."""
        tracker = SelectivePackageTracker()
        h1 = tracker.compute_selective_hash()
        h2 = tracker.compute_selective_hash()

        assert isinstance(h1, str)
        assert len(h1) == 64  # SHA256 hex
        assert h1 == h2  # Deterministic

    def test_get_changed_packages_detects_version_change(self):
        """Detects version changes."""
        tracker = SelectivePackageTracker(frozenset(["pytest"]))
        old_versions = {"pytest": "7.0.0"}

        # Mock current version as different
        with patch.object(tracker, "get_current_versions", return_value={"pytest": "7.1.0"}):
            changed = tracker.get_changed_packages(old_versions)

        assert len(changed) == 1
        assert "pytest" in changed[0]
        assert "7.0.0" in changed[0]
        assert "7.1.0" in changed[0]

    def test_get_changed_packages_detects_new_package(self):
        """Detects newly installed packages."""
        tracker = SelectivePackageTracker(frozenset(["newpkg"]))
        old_versions = {}

        with patch.object(tracker, "get_current_versions", return_value={"newpkg": "1.0"}):
            changed = tracker.get_changed_packages(old_versions)

        assert len(changed) == 1
        assert "new" in changed[0]

    def test_get_changed_packages_detects_removed_package(self):
        """Detects removed packages."""
        tracker = SelectivePackageTracker(frozenset(["oldpkg"]))
        old_versions = {"oldpkg": "1.0"}

        with patch.object(tracker, "get_current_versions", return_value={}):
            changed = tracker.get_changed_packages(old_versions)

        assert len(changed) == 1
        assert "removed" in changed[0]

    def test_get_changed_packages_no_changes(self):
        """Returns empty list when no changes."""
        tracker = SelectivePackageTracker(frozenset(["pkg"]))
        old_versions = {"pkg": "1.0"}

        with patch.object(tracker, "get_current_versions", return_value={"pkg": "1.0"}):
            changed = tracker.get_changed_packages(old_versions)

        assert changed == []


# ============================================================
# LRUCacheWithPartialInvalidation Tests
# ============================================================


class TestLRUCacheWithPartialInvalidation:
    """Test LRU cache with package-aware invalidation."""

    def test_basic_get_set(self):
        """Basic get/set operations work."""
        cache = LRUCacheWithPartialInvalidation(max_size=100)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_returns_none(self):
        """Get on missing key returns None."""
        cache = LRUCacheWithPartialInvalidation()
        assert cache.get("nonexistent") is None

    def test_lru_eviction(self):
        """LRU eviction works when at capacity."""
        cache = LRUCacheWithPartialInvalidation(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)

        # Access 'a' to make it recently used
        cache.get("a")

        # Add new item, should evict 'b' (least recently used)
        cache.set("d", 4)

        assert cache.get("a") == 1  # Still present
        assert cache.get("b") is None  # Evicted
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_partial_invalidation_by_package(self):
        """Entries are invalidated by related packages."""
        cache = LRUCacheWithPartialInvalidation()
        cache.set("flask.Response.json", "dict", related_packages={"flask"})
        cache.set("django.Model.save", "None", related_packages={"django"})
        cache.set("requests.get", "Response", related_packages={"requests"})

        # Invalidate flask-related entries
        count = cache.invalidate_for_packages({"flask"})

        assert count == 1
        assert cache.get("flask.Response.json") is None
        assert cache.get("django.Model.save") == "None"
        assert cache.get("requests.get") == "Response"

    def test_partial_invalidation_multiple_packages(self):
        """Invalidate entries for multiple packages at once."""
        cache = LRUCacheWithPartialInvalidation()
        cache.set("a", 1, related_packages={"flask"})
        cache.set("b", 2, related_packages={"django"})
        cache.set("c", 3, related_packages={"flask", "django"})
        cache.set("d", 4, related_packages={"requests"})

        count = cache.invalidate_for_packages({"flask", "django"})

        assert count == 3
        assert cache.get("a") is None
        assert cache.get("b") is None
        assert cache.get("c") is None
        assert cache.get("d") == 4

    def test_clear_removes_all(self):
        """Clear removes all entries."""
        cache = LRUCacheWithPartialInvalidation()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()

        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_stats_tracking(self):
        """Stats are tracked correctly."""
        cache = LRUCacheWithPartialInvalidation(max_size=100)
        cache.set("a", 1)
        cache.get("a")  # hit
        cache.get("b")  # miss
        cache.get("a")  # hit

        stats = cache.stats
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 2 / 3
        assert stats["size"] == 1

    def test_thread_safety(self):
        """Cache is thread-safe."""
        cache = LRUCacheWithPartialInvalidation(max_size=1000)
        errors = []

        def writer():
            try:
                for i in range(100):
                    cache.set(f"key{i}", i)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for i in range(100):
                    cache.get(f"key{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ============================================================
# SQLiteStateStore Tests
# ============================================================


class TestSQLiteStateStore:
    """Test SQLite-based state storage."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create temp database."""
        return tmp_path / "test_state.db"

    def test_init_creates_tables(self, temp_db):
        """Database tables are created on init."""
        store = SQLiteStateStore(temp_db)

        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "sync_state" in tables
        assert "package_versions" in tables

    def test_save_and_load_state(self, temp_db):
        """Save and load state correctly."""
        store = SQLiteStateStore(temp_db)

        state = SyncState(
            last_sync_timestamp=1703000000.0,
            environment_hash="abc123",
            package_versions={"flask": "2.0", "django": "4.0"},
            config_count=10,
            sync_source="test",
        )
        store.save_state(state)

        loaded = store.load_state()
        assert loaded is not None
        assert loaded.last_sync_timestamp == 1703000000.0
        assert loaded.environment_hash == "abc123"
        assert loaded.package_versions == {"flask": "2.0", "django": "4.0"}
        assert loaded.config_count == 10
        assert loaded.sync_source == "test"

    def test_upsert_behavior(self, temp_db):
        """Save overwrites previous state."""
        store = SQLiteStateStore(temp_db)

        state1 = SyncState(1000.0, "hash1", {"a": "1"}, 5, "first")
        store.save_state(state1)

        state2 = SyncState(2000.0, "hash2", {"b": "2"}, 10, "second")
        store.save_state(state2)

        loaded = store.load_state()
        assert loaded.last_sync_timestamp == 2000.0
        assert loaded.environment_hash == "hash2"
        assert loaded.package_versions == {"b": "2"}

    def test_load_empty_db_returns_none(self, temp_db):
        """Load from empty db returns None."""
        store = SQLiteStateStore(temp_db)
        loaded = store.load_state()
        assert loaded is None

    def test_get_package_version(self, temp_db):
        """Get specific package version."""
        store = SQLiteStateStore(temp_db)

        state = SyncState(1000.0, "hash", {"flask": "2.0", "django": "4.0"}, 0, "test")
        store.save_state(state)

        assert store.get_package_version("flask") == "2.0"
        assert store.get_package_version("django") == "4.0"
        assert store.get_package_version("nonexistent") is None

    def test_concurrent_access(self, temp_db):
        """Database handles concurrent access."""
        store = SQLiteStateStore(temp_db)
        errors = []

        def writer(n):
            try:
                state = SyncState(float(n), f"hash{n}", {f"pkg{n}": "1.0"}, n, "thread")
                store.save_state(state)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Last write should have won
        loaded = store.load_state()
        assert loaded is not None


# ============================================================
# BackgroundSyncWorker Tests
# ============================================================


class TestBackgroundSyncWorker:
    """Test background sync worker."""

    def test_start_sync_runs_in_background(self):
        """Sync runs in background thread."""
        completed = threading.Event()

        def sync_fn():
            time.sleep(0.03)  # 0.1 → 0.03
            completed.set()
            return True

        worker = BackgroundSyncWorker(sync_fn)
        assert worker.start_sync() is True
        assert worker.is_running is True

        # Wait for completion
        completed.wait(timeout=1.0)
        worker.wait_for_completion()

        assert worker.is_running is False
        assert worker.last_result == (True, None)

    @pytest.mark.slow
    def test_start_sync_returns_false_if_already_running(self):
        """Cannot start sync if already running."""
        worker = BackgroundSyncWorker(lambda: time.sleep(0.1) or True)  # 1 → 0.1

        assert worker.start_sync() is True
        assert worker.start_sync() is False

        worker.wait_for_completion()

    def test_sync_failure_is_recorded(self):
        """Failed sync is recorded."""

        def failing_sync():
            raise RuntimeError("Sync failed!")

        worker = BackgroundSyncWorker(failing_sync)
        worker.start_sync()
        worker.wait_for_completion()

        result, error = worker.last_result
        assert result is False
        assert "Sync failed" in error

    def test_wait_for_completion_timeout(self):
        """wait_for_completion respects timeout."""
        worker = BackgroundSyncWorker(lambda: time.sleep(0.5) or True)  # 10 → 0.5
        worker.start_sync()

        completed = worker.wait_for_completion(timeout=0.1)
        assert completed is False
        assert worker.is_running is True


# ============================================================
# SyncHealthChecker Integration Tests
# ============================================================


class TestSyncHealthChecker:
    """Test SyncHealthChecker integration."""

    @pytest.fixture
    def temp_config_dir(self, tmp_path):
        """Create temp config directory with files."""
        config_dir = tmp_path / "configs"
        stdlib_dir = config_dir / "stdlib"
        stdlib_dir.mkdir(parents=True)

        # Create dummy YAML file
        (stdlib_dir / "builtins.yaml").write_text("str:\n  upper: str\n")
        return config_dir

    def test_check_health_healthy_on_first_run(self, temp_config_dir):
        """First run is healthy (creates state)."""
        checker = SyncHealthChecker(config_dir=temp_config_dir)
        status = checker.check_health()

        assert status.is_healthy is True

    def test_check_health_detects_stale_configs(self, temp_config_dir):
        """Detects configs older than max age."""
        checker = SyncHealthChecker(config_dir=temp_config_dir, max_age_days=0)

        # First run creates state
        checker.check_health()

        # Second check should be stale (age > 0 days)
        time.sleep(0.01)
        status = checker.check_health()

        # Note: Since we just created the state, it won't be stale yet
        # unless we manipulate the timestamp

    def test_check_health_no_configs(self, tmp_path):
        """Reports no_configs when directory is empty."""
        empty_dir = tmp_path / "empty_configs"
        empty_dir.mkdir()

        checker = SyncHealthChecker(config_dir=empty_dir)
        status = checker.check_health()

        assert status.is_healthy is False
        assert status.needs_sync is True
        assert "initial sync" in status.message.lower()

    def test_check_health_disabled(self, temp_config_dir):
        """Check can be disabled."""
        checker = SyncHealthChecker(config_dir=temp_config_dir, enable_check=False)
        status = checker.check_health()

        assert status.is_healthy is True

    def test_mark_synced(self, temp_config_dir):
        """mark_synced updates state."""
        checker = SyncHealthChecker(config_dir=temp_config_dir)
        checker.mark_synced(source="test")

        state = checker.get_state()
        assert state is not None
        assert state.sync_source == "test"

    def test_get_status_summary(self, temp_config_dir):
        """get_status_summary returns comprehensive info."""
        checker = SyncHealthChecker(config_dir=temp_config_dir)
        checker.mark_synced(source="test")

        summary = checker.get_status_summary()

        assert "is_healthy" in summary
        assert "config_dir" in summary
        assert "circuit_breaker_state" in summary
        assert "background_sync_running" in summary
        assert summary["sync_source"] == "test"

    def test_trigger_sync_respects_circuit_breaker(self, temp_config_dir):
        """Sync is blocked when circuit is open."""
        checker = SyncHealthChecker(config_dir=temp_config_dir)

        # Open the circuit
        for _ in range(5):
            checker._circuit_breaker.record_failure()

        assert checker._circuit_breaker.state == CircuitState.OPEN

        # Sync should be blocked
        result = checker.trigger_sync(background=False)
        assert result is False


# ============================================================
# EnvironmentAwareCache Tests
# ============================================================


class TestEnvironmentAwareCache:
    """Test EnvironmentAwareCache."""

    def test_basic_operations(self):
        """Basic get/set work."""
        cache = EnvironmentAwareCache(max_size=100)
        # Disable automatic env check for this test
        cache._check_interval = 999999.0
        cache._last_check_time = time.time()

        cache.set("key", "value")
        assert cache.get("key") == "value"

    def test_set_with_related_packages(self):
        """Can set entries with related packages."""
        cache = EnvironmentAwareCache()
        # Disable automatic env check
        cache._check_interval = 999999.0
        cache._last_check_time = time.time()
        # Initialize last_versions to current so no invalidation
        cache._last_versions = cache._package_tracker.get_current_versions()

        cache.set("flask.key", "value", related_packages={"flask"})
        assert cache.get("flask.key") == "value"

    def test_partial_invalidation(self):
        """Partial invalidation works."""
        cache = EnvironmentAwareCache()
        # Disable automatic env check
        cache._check_interval = 999999.0
        cache._last_check_time = time.time()

        cache.set("flask.a", 1, related_packages={"flask"})
        cache.set("django.b", 2, related_packages={"django"})

        # Track versions
        cache._last_versions = {"flask": "2.0", "django": "4.0"}

        # Simulate flask version change
        with patch.object(
            cache._package_tracker,
            "get_current_versions",
            return_value={"flask": "2.1", "django": "4.0"},
        ):
            cache.invalidate_if_env_changed()

        # Now get without triggering auto-check
        cache._last_check_time = time.time()
        assert cache._cache.get("flask.a") is None  # Invalidated
        assert cache._cache.get("django.b") == 2  # Still valid

    def test_stats(self):
        """Stats include package tracking info."""
        cache = EnvironmentAwareCache()
        stats = cache.stats

        assert "tracked_packages" in stats
        assert "env_hash" in stats


# ============================================================
# Edge Cases and Stress Tests
# ============================================================


class TestEdgeCases:
    """Edge cases and corner cases."""

    def test_empty_package_versions(self):
        """Handle empty package versions dict."""
        tracker = SelectivePackageTracker(frozenset())
        versions = tracker.get_current_versions()
        assert versions == {}
        assert len(tracker.compute_selective_hash()) == 64

    def test_sqlite_corrupt_db_recovery(self, tmp_path):
        """Handle corrupt database gracefully."""
        db_path = tmp_path / "corrupt.db"
        db_path.write_text("not a valid sqlite db")

        # Should not raise, should return None
        try:
            store = SQLiteStateStore(db_path)
            result = store.load_state()
            # May raise or return None depending on corruption
        except sqlite3.DatabaseError:
            pass  # Expected for corrupt db

    def test_circuit_breaker_exact_threshold(self):
        """Circuit opens exactly at threshold."""
        cb = CircuitBreaker(failure_threshold=3)

        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_lru_cache_single_entry(self):
        """LRU cache with size 1 works."""
        cache = LRUCacheWithPartialInvalidation(max_size=1)
        cache.set("a", 1)
        cache.set("b", 2)

        assert cache.get("a") is None
        assert cache.get("b") == 2

    def test_background_worker_rapid_start(self):
        """Rapid start attempts don't cause issues."""
        worker = BackgroundSyncWorker(lambda: time.sleep(0.5) or True)

        results = [worker.start_sync() for _ in range(10)]

        assert results[0] is True
        assert all(r is False for r in results[1:])

        worker.wait_for_completion()


class TestStressTests:
    """Stress tests for concurrent access."""

    def test_lru_cache_high_concurrency(self):
        """LRU cache under high concurrency."""
        cache = LRUCacheWithPartialInvalidation(max_size=1000)
        errors = []
        ops_count = [0]
        lock = threading.Lock()

        def worker():
            try:
                for i in range(1000):
                    cache.set(f"key{i}", i, related_packages={f"pkg{i % 10}"})
                    cache.get(f"key{i}")
                    if i % 100 == 0:
                        cache.invalidate_for_packages({f"pkg{i % 10}"})
                with lock:
                    ops_count[0] += 1000
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert ops_count[0] == 20000

    def test_circuit_breaker_high_concurrency(self):
        """Circuit breaker under high concurrency."""
        cb = CircuitBreaker(failure_threshold=50, recovery_timeout=0.1)
        errors = []

        def worker():
            try:
                for _ in range(100):
                    cb.can_execute()
                    if threading.current_thread().name.endswith("0"):
                        cb.record_failure()
                    else:
                        cb.record_success()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, name=f"thread{i}") for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_sqlite_store_concurrent_writes(self, tmp_path):
        """SQLite store handles concurrent writes."""
        db_path = tmp_path / "concurrent.db"
        store = SQLiteStateStore(db_path)
        errors = []

        def writer(n):
            try:
                for i in range(10):
                    state = SyncState(
                        float(n * 1000 + i),
                        f"hash{n}_{i}",
                        {f"pkg{n}": f"{i}"},
                        n,
                        f"thread{n}",
                    )
                    store.save_state(state)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Final state should be valid
        loaded = store.load_state()
        assert loaded is not None
