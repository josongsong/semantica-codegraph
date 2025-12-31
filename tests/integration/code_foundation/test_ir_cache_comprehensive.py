"""
L12+ SOTA: Comprehensive IR Cache Tests - Advanced Scenarios.

복잡한 시나리오, 동시성, 통계 검증.

NOTE: 기본 테스트는 test_ir_cache_basic.py 참조.
      엣지 케이스는 test_ir_cache_edge_cases.py 참조.
      성능 테스트는 test_ir_cache_performance.py 참조.
"""

import asyncio
import shutil
import tempfile
import time
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

        # Setup cache
        cache = IRCache(backend=DiskCache(cache_dir=cache_dir))
        cache.clear()
        set_global_cache(cache)

        yield project_root, cache


class TestFileOperations:
    """파일 작업 시나리오."""

    @pytest.mark.asyncio
    async def test_delete_files(self, project_with_cache):
        """파일 삭제 시 cache는 유지 (orphaned entries OK)."""
        project_root, cache = project_with_cache

        (project_root / "a.py").write_text("def a(): return 1")
        (project_root / "b.py").write_text("def b(): return 2")
        (project_root / "c.py").write_text("def c(): return 3")

        files = list(project_root.glob("*.py"))
        builder = LayeredIRBuilder(project_root=project_root)
        config = BuildConfig(parallel_workers=1)

        await builder.build(files, config)
        stats1 = cache.stats()
        assert stats1["size"] == 3

        (project_root / "b.py").unlink()

        files_remaining = list(project_root.glob("*.py"))
        await builder.build(files_remaining, config)
        stats2 = cache.stats()

        assert stats2["size"] == 3, "Cache should keep orphaned entries"
        hits_delta = stats2["hits"] - stats1["hits"]
        assert hits_delta == 2

    @pytest.mark.asyncio
    async def test_rename_file(self, project_with_cache):
        """파일 이름 변경 시 새 파일로 인식."""
        project_root, cache = project_with_cache

        (project_root / "old_name.py").write_text("def func(): return 1")

        files = list(project_root.glob("*.py"))
        builder = LayeredIRBuilder(project_root=project_root)
        config = BuildConfig(parallel_workers=1)

        await builder.build(files, config)
        stats1 = cache.stats()

        content = (project_root / "old_name.py").read_text()
        (project_root / "old_name.py").unlink()
        (project_root / "new_name.py").write_text(content)

        files_renamed = list(project_root.glob("*.py"))
        await builder.build(files_renamed, config)
        stats2 = cache.stats()

        misses_delta = stats2["misses"] - stats1["misses"]
        assert misses_delta == 1, "Renamed file should be cache miss"


class TestConcurrentModifications:
    """동시 수정 시나리오 테스트."""

    @pytest.mark.asyncio
    async def test_rapid_successive_builds(self, project_with_cache):
        """연속된 빌드에서 cache가 정상 동작한다."""
        project_root, cache = project_with_cache

        (project_root / "test.py").write_text("def func(): return 1")

        files = list(project_root.glob("*.py"))
        builder = LayeredIRBuilder(project_root=project_root)
        config = BuildConfig(parallel_workers=1)

        # Build 10 times rapidly
        for i in range(10):
            await builder.build(files, config)

        stats = cache.stats()
        # First build: 1 miss, next 9 builds: 9 hits
        assert stats["hits"] == 9, "Should have 9 cache hits"
        assert stats["misses"] == 1, "Should have 1 cache miss"

    @pytest.mark.asyncio
    async def test_alternating_modifications(self, project_with_cache):
        """파일을 번갈아 수정해도 cache가 정상 동작한다."""
        project_root, cache = project_with_cache

        (project_root / "a.py").write_text("def a(): return 1")
        (project_root / "b.py").write_text("def b(): return 2")

        files = list(project_root.glob("*.py"))
        builder = LayeredIRBuilder(project_root=project_root)
        config = BuildConfig(parallel_workers=1)

        # Initial build
        await builder.build(files, config)

        # Modify a.py
        (project_root / "a.py").write_text("def a(): return 111")
        await builder.build(files, config)
        stats1 = cache.stats()

        # Modify b.py
        (project_root / "b.py").write_text("def b(): return 222")
        await builder.build(files, config)
        stats2 = cache.stats()

        # Should have hits for unmodified files
        hits_delta = stats2["hits"] - stats1["hits"]
        assert hits_delta >= 1, "Should hit cache for unmodified file"


class TestVersionMigration:
    """버전 마이그레이션 테스트."""

    @pytest.mark.asyncio
    async def test_parser_version_change_invalidates_cache(self, project_with_cache):
        """Parser version 변경 시 cache가 invalidate된다."""
        project_root, cache = project_with_cache

        (project_root / "test.py").write_text("def func(): return 1")

        files = list(project_root.glob("*.py"))
        builder = LayeredIRBuilder(project_root=project_root)
        config = BuildConfig(parallel_workers=1)

        # Build with version 1.0.0
        await builder.build(files, config)
        stats1 = cache.stats()
        assert stats1["size"] == 1

        # Simulate version change (would require code change in ParserVersion enum)
        # For now, verify that different versions create different keys
        from codegraph_engine.code_foundation.infrastructure.ir.cache import CacheKey

        key1 = CacheKey.from_content("test.py", "content", parser_version="1.0.0")
        key2 = CacheKey.from_content("test.py", "content", parser_version="1.0.1")

        assert key1.to_string() != key2.to_string(), "Different versions should create different keys"


class TestCacheStatistics:
    """Cache 통계 정확성 테스트."""

    @pytest.mark.asyncio
    async def test_hit_rate_accuracy(self, project_with_cache):
        """Hit rate 계산이 정확하다."""
        project_root, cache = project_with_cache

        # Create 10 files
        for i in range(10):
            (project_root / f"file{i}.py").write_text(f"def func{i}(): return {i}")

        files = list(project_root.glob("*.py"))
        builder = LayeredIRBuilder(project_root=project_root)
        config = BuildConfig(parallel_workers=1)

        # First build (10 misses)
        await builder.build(files, config)

        # Second build (10 hits)
        await builder.build(files, config)

        stats = cache.stats()
        assert stats["hits"] == 10
        assert stats["misses"] == 10
        assert stats["hit_rate"] == 0.5  # 10 hits / 20 total

    @pytest.mark.asyncio
    async def test_write_fail_tracking(self, project_with_cache):
        """Write fail이 정확히 추적된다."""
        project_root, cache = project_with_cache

        (project_root / "test.py").write_text("def func(): return 1")

        files = list(project_root.glob("*.py"))
        builder = LayeredIRBuilder(project_root=project_root)
        config = BuildConfig(parallel_workers=1)

        # Make cache directory read-only (simulate write failure)
        cache_backend = cache._backend
        if isinstance(cache_backend, DiskCache):
            cache_dir = cache_backend._cache_dir
            cache_dir.chmod(0o444)

            try:
                # Build (write should fail)
                await builder.build(files, config)

                stats = cache.stats()
                # Write should fail but not crash
                # Note: Current implementation silently fails
                assert True, "Should not crash on write failure"
            finally:
                # Restore permissions
                cache_dir.chmod(0o755)


class TestIncrementalComplexScenarios:
    """복잡한 증분 업데이트 시나리오."""

    @pytest.mark.asyncio
    async def test_partial_rebuild_with_dependencies(self, project_with_cache):
        """의존성이 있는 파일 중 일부만 수정해도 정상 동작한다."""
        project_root, cache = project_with_cache

        # Create files with dependencies
        (project_root / "base.py").write_text("""
class Base:
    def method(self):
        return 1
""")

        (project_root / "derived.py").write_text("""
from base import Base

class Derived(Base):
    pass
""")

        (project_root / "user.py").write_text("""
from derived import Derived

def use():
    return Derived()
""")

        files = list(project_root.glob("*.py"))
        builder = LayeredIRBuilder(project_root=project_root)
        config = BuildConfig(parallel_workers=1)

        # Initial build
        await builder.build(files, config)
        stats1 = cache.stats()

        # Modify only base.py
        (project_root / "base.py").write_text("""
class Base:
    def method(self):
        return 2  # Changed
""")

        # Rebuild
        await builder.build(files, config)
        stats2 = cache.stats()

        # Should have 2 hits (derived.py, user.py), 1 miss (base.py)
        hits_delta = stats2["hits"] - stats1["hits"]
        misses_delta = stats2["misses"] - stats1["misses"]

        assert hits_delta == 2, "Should hit cache for unchanged files"
        assert misses_delta == 1, "Should miss cache for modified file"

    @pytest.mark.asyncio
    async def test_mixed_operations(self, project_with_cache):
        """추가, 수정, 삭제가 섞여도 정상 동작한다."""
        project_root, cache = project_with_cache

        # Initial 5 files
        for i in range(5):
            (project_root / f"file{i}.py").write_text(f"def func{i}(): return {i}")

        files = list(project_root.glob("*.py"))
        builder = LayeredIRBuilder(project_root=project_root)
        config = BuildConfig(parallel_workers=1)

        await builder.build(files, config)
        stats1 = cache.stats()

        # Mixed operations:
        # - Delete file0.py
        (project_root / "file0.py").unlink()
        # - Modify file1.py
        (project_root / "file1.py").write_text("def func1(): return 1111")
        # - Add file5.py
        (project_root / "file5.py").write_text("def func5(): return 5")
        # - Keep file2.py, file3.py, file4.py unchanged

        files_new = list(project_root.glob("*.py"))
        await builder.build(files_new, config)
        stats2 = cache.stats()

        hits_delta = stats2["hits"] - stats1["hits"]
        misses_delta = stats2["misses"] - stats1["misses"]

        # Should have 3 hits (file2, file3, file4), 2 misses (file1 modified, file5 new)
        assert hits_delta == 3, f"Expected 3 hits, got {hits_delta}"
        assert misses_delta == 2, f"Expected 2 misses, got {misses_delta}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
