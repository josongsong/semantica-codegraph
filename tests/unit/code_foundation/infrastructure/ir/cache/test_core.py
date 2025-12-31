"""
RFC-039 P0.1.5: Tests for Common Cache Infrastructure (core.py)
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.cache.core import (
    # Exceptions
    CacheError,
    CacheCorruptError,
    CacheVersionMismatchError,
    CacheSerializationError,
    CacheDiskFullError,
    CachePermissionError,
    # Stats
    BaseCacheStats,
    ExtendedCacheStats,
    # Version
    BaseVersionEnum,
    # Checksum
    compute_xxh3_128,
    compute_xxh3_128_hex,
    compute_xxh32,
    compute_content_hash,
    HAS_XXHASH,
)


class TestExceptionHierarchy:
    """Exception hierarchy tests."""

    def test_cache_error_is_base(self):
        """All cache errors inherit from CacheError."""
        assert issubclass(CacheCorruptError, CacheError)
        assert issubclass(CacheVersionMismatchError, CacheError)
        assert issubclass(CacheSerializationError, CacheError)
        assert issubclass(CacheDiskFullError, CacheError)
        assert issubclass(CachePermissionError, CacheError)

    def test_cache_corrupt_error_with_path(self):
        """CacheCorruptError stores cache_path."""
        from pathlib import Path

        err = CacheCorruptError("Checksum mismatch", cache_path=Path("/tmp/cache.pkl"))
        assert err.cache_path == Path("/tmp/cache.pkl")
        assert "Checksum mismatch" in str(err)

    def test_version_mismatch_error(self):
        """CacheVersionMismatchError stores version info."""
        err = CacheVersionMismatchError(found_version=1, expected_version=2)
        assert err.found_version == 1
        assert err.expected_version == 2
        assert "found 1" in str(err)
        assert "expected 2" in str(err)


class TestBaseCacheStats:
    """BaseCacheStats tests."""

    def test_initial_values(self):
        """Stats start at zero."""
        stats = BaseCacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.write_fails == 0
        assert stats.corrupt_entries == 0
        assert stats.evictions == 0

    def test_hit_rate_calculation(self):
        """Hit rate is calculated correctly."""
        stats = BaseCacheStats(hits=7, misses=3)
        assert stats.hit_rate == pytest.approx(0.7)

    def test_hit_rate_zero_division(self):
        """Hit rate is 0 when no requests."""
        stats = BaseCacheStats()
        assert stats.hit_rate == 0.0

    def test_total_requests(self):
        """Total requests = hits + misses."""
        stats = BaseCacheStats(hits=10, misses=5)
        assert stats.total_requests == 15

    def test_to_dict(self):
        """to_dict() returns all fields."""
        stats = BaseCacheStats(hits=10, misses=5, write_fails=2)
        d = stats.to_dict()
        assert d["hits"] == 10
        assert d["misses"] == 5
        assert d["write_fails"] == 2
        assert d["hit_rate"] == pytest.approx(0.6667, rel=0.01)
        assert d["total_requests"] == 15

    def test_reset(self):
        """reset() clears all stats."""
        stats = BaseCacheStats(hits=10, misses=5, write_fails=2)
        stats.reset()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.write_fails == 0


class TestExtendedCacheStats:
    """ExtendedCacheStats tests."""

    def test_inherits_base(self):
        """ExtendedCacheStats inherits from BaseCacheStats."""
        assert issubclass(ExtendedCacheStats, BaseCacheStats)

    def test_additional_fields(self):
        """Extended stats have additional fields."""
        stats = ExtendedCacheStats(
            hits=10,
            misses=5,
            schema_mismatches=2,
            disk_full_errors=1,
            total_saved_ms=1500.5,
        )
        assert stats.schema_mismatches == 2
        assert stats.disk_full_errors == 1
        assert stats.total_saved_ms == 1500.5

    def test_to_dict_includes_extended(self):
        """to_dict() includes extended fields."""
        stats = ExtendedCacheStats(
            hits=10,
            misses=5,
            schema_mismatches=2,
            total_saved_ms=1500.5,
        )
        d = stats.to_dict()
        assert d["schema_mismatches"] == 2
        assert d["total_saved_ms"] == 1500.5
        assert d["hits"] == 10  # Base field still present

    def test_reset_clears_extended(self):
        """reset() clears extended fields too."""
        stats = ExtendedCacheStats(
            hits=10,
            schema_mismatches=5,
            total_saved_ms=1000.0,
        )
        stats.reset()
        assert stats.schema_mismatches == 0
        assert stats.total_saved_ms == 0.0


class TestBaseVersionEnum:
    """BaseVersionEnum tests."""

    def test_current_returns_latest(self):
        """current() returns the last enum value."""

        class TestVersion(BaseVersionEnum):
            V1 = "v1"
            V2 = "v2"
            V3 = "v3"

        assert TestVersion.current() == "v3"

    def test_all_versions(self):
        """all_versions() returns all values."""

        class TestVersion(BaseVersionEnum):
            V1 = "v1"
            V2 = "v2"

        assert TestVersion.all_versions() == ["v1", "v2"]


class TestChecksumUtilities:
    """Checksum utility tests."""

    def test_xxh3_128_returns_16_bytes(self):
        """compute_xxh3_128 returns 16-byte checksum."""
        result = compute_xxh3_128(b"hello world")
        assert len(result) == 16
        assert isinstance(result, bytes)

    def test_xxh3_128_hex_returns_32_chars(self):
        """compute_xxh3_128_hex returns 32-char hex string."""
        result = compute_xxh3_128_hex(b"hello world")
        assert len(result) == 32
        assert isinstance(result, str)
        # Valid hex
        int(result, 16)

    def test_xxh32_returns_int(self):
        """compute_xxh32 returns 32-bit integer."""
        result = compute_xxh32(b"hello world")
        assert isinstance(result, int)
        assert 0 <= result <= 0xFFFFFFFF

    def test_content_hash_str_input(self):
        """compute_content_hash handles string input."""
        result = compute_content_hash("hello world")
        assert len(result) >= 32
        assert isinstance(result, str)

    def test_content_hash_bytes_input(self):
        """compute_content_hash handles bytes input."""
        result = compute_content_hash(b"hello world")
        assert len(result) >= 32
        assert isinstance(result, str)

    def test_content_hash_consistency(self):
        """Same content produces same hash."""
        hash1 = compute_content_hash("test content")
        hash2 = compute_content_hash("test content")
        assert hash1 == hash2

    def test_content_hash_uniqueness(self):
        """Different content produces different hash."""
        hash1 = compute_content_hash("content A")
        hash2 = compute_content_hash("content B")
        assert hash1 != hash2

    def test_xxh3_128_deterministic(self):
        """xxh3_128 is deterministic."""
        data = b"test data for hashing"
        hash1 = compute_xxh3_128(data)
        hash2 = compute_xxh3_128(data)
        assert hash1 == hash2

    def test_xxh32_deterministic(self):
        """xxh32 is deterministic."""
        data = b"test data for hashing"
        hash1 = compute_xxh32(data)
        hash2 = compute_xxh32(data)
        assert hash1 == hash2


class TestHasXxhash:
    """HAS_XXHASH flag tests."""

    def test_has_xxhash_is_bool(self):
        """HAS_XXHASH is a boolean."""
        assert isinstance(HAS_XXHASH, bool)

    @pytest.mark.skipif(not HAS_XXHASH, reason="xxhash not available")
    def test_xxhash_available(self):
        """When xxhash is available, HAS_XXHASH is True."""
        import xxhash

        assert HAS_XXHASH is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
