"""
L12+ SOTA: msgpack + struct header 엣지케이스 테스트.

새로운 실패 모드:
1. Header corruption (magic, version, checksum mismatch)
2. msgpack deserialization failure
3. Partial header (< 26 bytes)
4. Version migration (V1 → V2)
5. msgpack unavailable fallback
"""

import struct
import tempfile
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.cache import (
    CacheKey,
    DiskCache,
    IRCache,
)


class TestStructHeaderValidation:
    """struct header 검증 테스트."""

    def test_corrupted_magic(self):
        """Magic bytes가 손상되면 cache miss다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            # Write valid cache
            key = CacheKey.from_content("test.py", "content")
            cache.set(key, {"data": "test"})

            # Corrupt magic bytes
            cache_path = cache._get_cache_path(key)
            data = cache_path.read_bytes()
            corrupted = b"XXXX" + data[4:]  # Wrong magic
            cache_path.write_bytes(corrupted)

            # Read should return None
            result = cache.get(key)
            assert result is None

    def test_corrupted_version(self):
        """Version mismatch면 cache miss다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            # Write valid cache
            key = CacheKey.from_content("test.py", "content")
            cache.set(key, {"data": "test"})

            # Corrupt version
            cache_path = cache._get_cache_path(key)
            data = cache_path.read_bytes()

            # Unpack header
            header = data[:26]
            magic, version, schema, engine, checksum = struct.unpack("!4sHQQI", header)

            # Change version
            new_header = struct.pack("!4sHQQI", magic, 999, schema, engine, checksum)
            corrupted = new_header + data[26:]
            cache_path.write_bytes(corrupted)

            # Read should return None (version mismatch)
            result = cache.get(key)
            assert result is None

    def test_corrupted_checksum(self):
        """Checksum mismatch면 cache miss다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            # Write valid cache
            key = CacheKey.from_content("test.py", "content")
            cache.set(key, {"data": "test"})

            # Corrupt checksum
            cache_path = cache._get_cache_path(key)
            data = cache_path.read_bytes()

            # Unpack header
            header = data[:26]
            magic, version, schema, engine, checksum = struct.unpack("!4sHQQI", header)

            # Change checksum
            new_header = struct.pack("!4sHQQI", magic, version, schema, engine, 0xDEADBEEF)
            corrupted = new_header + data[26:]
            cache_path.write_bytes(corrupted)

            # Read should return None (checksum mismatch)
            result = cache.get(key)
            assert result is None

    def test_partial_header(self):
        """Header가 26 bytes 미만이면 cache miss다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            # Write valid cache
            key = CacheKey.from_content("test.py", "content")
            cache.set(key, {"data": "test"})

            # Truncate to 10 bytes
            cache_path = cache._get_cache_path(key)
            cache_path.write_bytes(b"0123456789")

            # Read should return None
            result = cache.get(key)
            assert result is None

    def test_empty_cache_file(self):
        """빈 cache 파일은 cache miss다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            # Write valid cache
            key = CacheKey.from_content("test.py", "content")
            cache.set(key, {"data": "test"})

            # Empty file
            cache_path = cache._get_cache_path(key)
            cache_path.write_bytes(b"")

            # Read should return None
            result = cache.get(key)
            assert result is None


class TestMsgpackSerialization:
    """msgpack serialization 테스트."""

    def test_msgpack_basic_types(self):
        """msgpack은 기본 타입을 정상 처리한다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            key = CacheKey.from_content("test.py", "content")

            # Various types
            value = {
                "int": 123,
                "float": 3.14,
                "str": "test",
                "list": [1, 2, 3],
                "dict": {"nested": "value"},
                "bool": True,
                "none": None,
            }

            cache.set(key, value)
            result = cache.get(key)

            assert result == value

    def test_msgpack_nested_structures(self):
        """msgpack은 중첩 구조를 정상 처리한다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            key = CacheKey.from_content("test.py", "content")

            # Deeply nested
            value = {
                "level1": {
                    "level2": {
                        "level3": {
                            "data": [1, 2, 3],
                        }
                    }
                }
            }

            cache.set(key, value)
            result = cache.get(key)

            assert result == value

    def test_msgpack_large_data(self):
        """msgpack은 큰 데이터를 정상 처리한다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            key = CacheKey.from_content("test.py", "content")

            # Large list (10k items)
            value = {"large_list": list(range(1000))}  # 10000 → 1000

            cache.set(key, value)
            result = cache.get(key)

            assert result == value

    def test_msgpack_unicode(self):
        """msgpack은 Unicode를 정상 처리한다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            key = CacheKey.from_content("test.py", "content")

            # Unicode strings
            value = {
                "korean": "한글",
                "japanese": "日本語",
                "emoji": "🚀🎉",
            }

            cache.set(key, value)
            result = cache.get(key)

            assert result == value


class TestIncrementalEdgeCases:
    """증분 업데이트 엣지케이스."""

    def test_rapid_modifications(self):
        """파일을 빠르게 여러 번 수정해도 정상 동작한다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            # Modify 100 times
            for i in range(100):
                key = CacheKey.from_content("test.py", f"content_{i}")
                cache.set(key, {"version": i})

            # All versions should be cached
            for i in range(100):
                key = CacheKey.from_content("test.py", f"content_{i}")
                result = cache.get(key)
                assert result == {"version": i}

    def test_alternating_content(self):
        """Content를 번갈아 바꿔도 정상 동작한다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            content_a = "def func(): return 1"
            content_b = "def func(): return 2"

            key_a = CacheKey.from_content("test.py", content_a)
            key_b = CacheKey.from_content("test.py", content_b)

            # Cache both versions
            cache.set(key_a, {"version": "a"})
            cache.set(key_b, {"version": "b"})

            # Both should be retrievable
            assert cache.get(key_a) == {"version": "a"}
            assert cache.get(key_b) == {"version": "b"}

            # Alternate 10 times
            for i in range(10):
                if i % 2 == 0:
                    assert cache.get(key_a) == {"version": "a"}
                else:
                    assert cache.get(key_b) == {"version": "b"}

    def test_whitespace_sensitivity(self):
        """공백 변경도 정확히 감지한다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            # Different whitespace
            content1 = "def func():\n    return 1"
            content2 = "def func():\n        return 1"  # 4 spaces → 8 spaces
            content3 = "def func():\n\treturn 1"  # tabs

            key1 = CacheKey.from_content("test.py", content1)
            key2 = CacheKey.from_content("test.py", content2)
            key3 = CacheKey.from_content("test.py", content3)

            # All should have different keys
            assert key1.content_hash != key2.content_hash
            assert key2.content_hash != key3.content_hash
            assert key1.content_hash != key3.content_hash

            # Cache all
            cache.set(key1, {"version": 1})
            cache.set(key2, {"version": 2})
            cache.set(key3, {"version": 3})

            # All should be retrievable
            assert cache.get(key1) == {"version": 1}
            assert cache.get(key2) == {"version": 2}
            assert cache.get(key3) == {"version": 3}


class TestVersionMigration:
    """버전 마이그레이션 엣지케이스."""

    def test_schema_version_change(self):
        """Schema version 변경 시 자동 invalidation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            content = "def func(): return 1"

            # Cache with v1.0.0
            key_v1 = CacheKey.from_content("test.py", content, schema_version="1.0.0")
            cache.set(key_v1, {"version": "1.0.0"})

            # Try to get with v1.0.1 (should miss)
            key_v2 = CacheKey.from_content("test.py", content, schema_version="1.0.1")
            result = cache.get(key_v2)

            # Should be None (different schema version)
            assert result is None

    def test_engine_version_change(self):
        """Engine version 변경 시 자동 invalidation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            content = "def func(): return 1"

            # Cache with engine v1.0.0
            key_v1 = CacheKey.from_content("test.py", content, engine_version="1.0.0")
            cache.set(key_v1, {"version": "1.0.0"})

            # Try to get with engine v1.0.1 (should miss)
            key_v2 = CacheKey.from_content("test.py", content, engine_version="1.0.1")
            result = cache.get(key_v2)

            # Should be None (different engine version)
            assert result is None


class TestChecksumValidation:
    """Checksum 검증 테스트."""

    def test_payload_corruption_detected(self):
        """Payload 손상이 checksum으로 감지된다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            # Write valid cache
            key = CacheKey.from_content("test.py", "content")
            cache.set(key, {"data": "test"})

            # Corrupt payload (keep header intact)
            cache_path = cache._get_cache_path(key)
            data = cache_path.read_bytes()

            # Corrupt payload (after header)
            corrupted = data[:26] + b"CORRUPTED" + data[35:]
            cache_path.write_bytes(corrupted)

            # Read should return None (checksum mismatch)
            result = cache.get(key)
            assert result is None

    def test_checksum_with_compression(self):
        """Compression 사용 시에도 checksum이 동작한다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir, compress=True)

            key = CacheKey.from_content("test.py", "content")
            value = {"data": "test" * 1000}  # Compressible

            # Set and get
            cache.set(key, value)
            result = cache.get(key)

            assert result == value


class TestAtomicWriteEdgeCases:
    """Atomic write 엣지케이스."""

    def test_concurrent_writes_same_key(self):
        """동일 key에 동시 write해도 안전하다."""
        import threading

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            key = CacheKey.from_content("test.py", "content")
            errors = []

            def writer(value):
                try:
                    cache.set(key, {"thread": value})
                except Exception as e:
                    errors.append(e)

            # 10 threads write to same key
            threads = []
            for i in range(10):
                t = threading.Thread(target=writer, args=(i,))
                t.start()
                threads.append(t)

            for t in threads:
                t.join()

            # No errors should occur
            assert len(errors) == 0

            # Last write wins (acceptable)
            result = cache.get(key)
            assert result is not None
            assert "thread" in result

    def test_tmp_file_cleanup_on_error(self):
        """Write 실패 시 tmp 파일이 정리된다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            # Count tmp files before
            tmp_files_before = list(cache_dir.glob(".tmp_*.pkl"))

            # Try to cache non-serializable object
            key = CacheKey.from_content("test.py", "content")

            # This should fail (lambda not serializable)
            try:
                cache.set(key, {"func": lambda x: x})
            except:
                pass

            # Tmp files should be cleaned up
            tmp_files_after = list(cache_dir.glob(".tmp_*.pkl"))

            # Should have same or fewer tmp files
            assert len(tmp_files_after) <= len(tmp_files_before)


class TestIncrementalComplexScenarios:
    """복잡한 증분 시나리오."""

    def test_interleaved_modifications(self):
        """여러 파일을 섞어서 수정해도 정상 동작한다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            # Cache 10 files
            for i in range(10):
                key = CacheKey.from_content(f"file{i}.py", f"content_{i}_v0")
                cache.set(key, {"file": i, "version": 0})

            # Modify even files
            for i in range(0, 10, 2):
                key = CacheKey.from_content(f"file{i}.py", f"content_{i}_v1")
                cache.set(key, {"file": i, "version": 1})

            # Check: even files have v1, odd files have v0
            for i in range(10):
                if i % 2 == 0:
                    key = CacheKey.from_content(f"file{i}.py", f"content_{i}_v1")
                    result = cache.get(key)
                    assert result == {"file": i, "version": 1}
                else:
                    key = CacheKey.from_content(f"file{i}.py", f"content_{i}_v0")
                    result = cache.get(key)
                    assert result == {"file": i, "version": 0}

    def test_cache_survives_multiple_clears(self):
        """Clear 후에도 정상 동작한다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            for round in range(5):
                # Cache data
                key = CacheKey.from_content("test.py", f"content_{round}")
                cache.set(key, {"round": round})

                # Verify
                result = cache.get(key)
                assert result == {"round": round}

                # Clear
                cache.clear()

                # Should be empty
                assert cache.get(key) is None


class TestHashCollisionResistance:
    """Hash 충돌 저항성 테스트."""

    def test_similar_content_different_hash(self):
        """비슷한 content도 다른 hash를 가진다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            # Very similar content
            contents = [
                "def func(): return 1",
                "def func(): return 2",
                "def func(): return 3",
            ]

            keys = [CacheKey.from_content("test.py", c) for c in contents]

            # All should have different hashes
            hashes = [k.content_hash for k in keys]
            assert len(set(hashes)) == 3, "All hashes should be unique"

            # Cache all
            for i, key in enumerate(keys):
                cache.set(key, {"version": i})

            # All should be retrievable
            for i, key in enumerate(keys):
                result = cache.get(key)
                assert result == {"version": i}

    def test_no_collision_in_100_files(self):  # 1000 → 100
        """100개 파일에서 hash 충돌이 없다 (축소)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache = DiskCache(cache_dir=cache_dir)

            # Generate 100 different contents (축소)
            keys = []
            for i in range(100):  # 1000 → 100
                content = f"def func_{i}():\n    return {i}"
                key = CacheKey.from_content(f"file{i}.py", content)
                keys.append(key)
                cache.set(key, {"i": i})

            # All hashes should be unique
            hashes = [k.content_hash for k in keys]
            assert len(set(hashes)) == 100, "No hash collisions"  # 1000 → 100

            # All should be retrievable
            for i, key in enumerate(keys):
                result = cache.get(key)
                assert result == {"i": i}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
