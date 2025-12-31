"""
IR Cache Edge Cases - 엣지 케이스 테스트.

NOTE: 캐시 API 직접 테스트 (LayeredIRBuilder 통합 제외).
"""

import shutil
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


class TestExtremeEdgeCases:
    """극한 엣지 케이스."""

    @pytest.mark.asyncio
    async def test_empty_file(self, project_with_cache):
        """빈 파일도 정상 캐싱."""
        project_root, cache = project_with_cache

        # Test with empty content
        cache.set("empty.py", "", {"ir": "empty"})
        result = cache.get("empty.py", "")

        assert result == {"ir": "empty"}, "Empty file should be cached"
        stats = cache.stats()
        assert stats["hits"] == 1

    @pytest.mark.asyncio
    async def test_unicode_and_special_chars(self, project_with_cache):
        """Unicode, 특수문자 정상 처리."""
        project_root, cache = project_with_cache

        unicode_content = """
# 한글 주석
def 함수():
    return "🚀 테스트"

def 関数():
    return "テスト"

def функция():
    return "тест"
"""

        # Test with unicode content
        cache.set("unicode.py", unicode_content, {"ir": "unicode"})
        result = cache.get("unicode.py", unicode_content)

        assert result == {"ir": "unicode"}, "Unicode file should be cached"
        stats = cache.stats()
        assert stats["hits"] == 1

    @pytest.mark.asyncio
    async def test_syntax_error_file(self, project_with_cache):
        """문법 오류 파일도 cache 동작."""
        project_root, cache = project_with_cache

        # Cache valid file
        cache.set("valid.py", "def valid(): return 1", {"ir": "valid"})

        # Invalid file won't be cached (parsing fails), but valid file should work
        result = cache.get("valid.py", "def valid(): return 1")

        assert result == {"ir": "valid"}, "Valid file should be cached"
        stats = cache.stats()
        assert stats["hits"] == 1

    @pytest.mark.asyncio
    async def test_whitespace_only_change(self, project_with_cache):
        """공백 변경도 재파싱."""
        project_root, cache = project_with_cache

        content1 = "def func():\n    return 1"
        content2 = "def func():\n        return 1"  # More spaces

        # Cache with first content
        cache.set("test.py", content1, {"ir": "v1"})

        # Try to read with different whitespace
        result = cache.get("test.py", content2)

        assert result is None, "Whitespace change should invalidate cache"
        stats = cache.stats()
        assert stats["misses"] == 1


class TestCacheCorruption:
    """캐시 손상 복구."""

    @pytest.mark.asyncio
    async def test_corrupted_cache_file_recovery(self, project_with_cache):
        """손상된 cache 파일 복구."""
        project_root, cache = project_with_cache

        (project_root / "test.py").write_text("def func(): return 1")

        files = list(project_root.glob("*.py"))
        builder = LayeredIRBuilder(project_root=project_root)
        config = BuildConfig(parallel_workers=1)

        await builder.build(files, config)

        # Corrupt cache
        cache_backend = cache._backend
        if isinstance(cache_backend, DiskCache):
            cache_dir = cache_backend._cache_dir
            for cache_file in cache_dir.glob("*.pkl"):
                cache_file.write_bytes(b"CORRUPTED DATA!!!")

        result = await builder.build(files, config)
        assert len(result.ir_documents) == 1

    @pytest.mark.asyncio
    async def test_cache_directory_deleted_recovery(self, project_with_cache):
        """Cache directory 삭제 복구."""
        project_root, cache = project_with_cache

        (project_root / "test.py").write_text("def func(): return 1")

        files = list(project_root.glob("*.py"))
        builder = LayeredIRBuilder(project_root=project_root)
        config = BuildConfig(parallel_workers=1)

        await builder.build(files, config)

        # Delete cache
        cache_backend = cache._backend
        if isinstance(cache_backend, DiskCache):
            cache_dir = cache_backend._cache_dir
            if cache_dir.exists():
                shutil.rmtree(cache_dir)

        result = await builder.build(files, config)
        assert len(result.ir_documents) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
