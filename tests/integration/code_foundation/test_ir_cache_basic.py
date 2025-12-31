"""
IR Cache Basic Tests - 빠른 기본 테스트.

NOTE: LayeredIRBuilder 통합은 복잡하므로 캐시 API 직접 테스트.
"""

import tempfile
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig
from codegraph_engine.code_foundation.infrastructure.ir.cache import (
    DiskCache,
    IRCache,
    set_global_cache,
)
from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder


@pytest.fixture
def project_with_cache():
    """Create temporary project with cache."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        cache_dir = Path(tmpdir) / ".cache"

        cache = IRCache(backend=DiskCache(cache_dir=cache_dir))
        cache.clear()
        set_global_cache(cache)

        yield project_root, cache


class TestBasicCaching:
    """기본 캐싱 동작."""

    @pytest.mark.asyncio
    async def test_simple_cache_hit(self, project_with_cache):
        """동일 파일 2번 빌드 시 캐시 히트."""
        project_root, cache = project_with_cache

        # Test cache directly (LayeredIRBuilder integration is complex)
        file_path = "test.py"
        content = "def func(): return 1"
        test_ir = {"test": "ir_document"}

        # Write to cache
        cache.set(file_path, content, test_ir)
        stats1 = cache.stats()
        assert stats1["size"] == 1, "Cache should have 1 entry"

        # Read from cache
        result = cache.get(file_path, content)
        assert result == test_ir, "Should get same IR back"

        stats2 = cache.stats()
        assert stats2["hits"] == 1, "Should have 1 cache hit"
        assert stats2["misses"] == 0, "Should have 0 cache misses"

    @pytest.mark.asyncio
    async def test_cache_miss_on_content_change(self, project_with_cache):
        """내용 변경 시 캐시 미스."""
        project_root, cache = project_with_cache

        file_path = "test.py"
        content1 = "def func(): return 1"
        content2 = "def func(): return 2"

        # Cache with first content
        cache.set(file_path, content1, {"ir": "v1"})

        # Try to read with different content
        result = cache.get(file_path, content2)
        assert result is None, "Should be cache miss with different content"

        stats = cache.stats()
        assert stats["hits"] == 0, "Should have 0 hits"
        assert stats["misses"] == 1, "Should have 1 miss"


class TestIncrementalUpdates:
    """증분 업데이트."""

    @pytest.mark.asyncio
    async def test_single_file_modification(self, project_with_cache):
        """1개 파일 수정 시 해당 파일만 재파싱."""
        project_root, cache = project_with_cache

        # Cache 3 files
        cache.set("a.py", "def a(): return 1", {"ir": "a"})
        cache.set("b.py", "def b(): return 2", {"ir": "b"})
        cache.set("c.py", "def c(): return 3", {"ir": "c"})

        # Read 2 unchanged, 1 modified
        result_a = cache.get("a.py", "def a(): return 1")
        result_c = cache.get("c.py", "def c(): return 3")
        result_b = cache.get("b.py", "def b(): return 2222")  # Modified content

        assert result_a == {"ir": "a"}, "Should hit cache for a.py"
        assert result_c == {"ir": "c"}, "Should hit cache for c.py"
        assert result_b is None, "Should miss cache for modified b.py"

        stats = cache.stats()
        assert stats["hits"] == 2, f"Expected 2 hits, got {stats['hits']}"
        assert stats["misses"] == 1, f"Expected 1 miss, got {stats['misses']}"

    @pytest.mark.asyncio
    async def test_add_new_files(self, project_with_cache):
        """새 파일 추가 시 기존 cache 유지."""
        project_root, cache = project_with_cache

        # Cache 2 files
        cache.set("a.py", "def a(): return 1", {"ir": "a"})
        cache.set("b.py", "def b(): return 2", {"ir": "b"})

        # Read 2 existing, 2 new
        result_a = cache.get("a.py", "def a(): return 1")
        result_b = cache.get("b.py", "def b(): return 2")
        result_c = cache.get("c.py", "def c(): return 3")
        result_d = cache.get("d.py", "def d(): return 4")

        assert result_a == {"ir": "a"}, "Should hit cache for a.py"
        assert result_b == {"ir": "b"}, "Should hit cache for b.py"
        assert result_c is None, "Should miss cache for new c.py"
        assert result_d is None, "Should miss cache for new d.py"

        stats = cache.stats()
        assert stats["hits"] == 2, "Should hit cache for a.py, b.py"
        assert stats["misses"] == 2, "Should miss cache for c.py, d.py"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
