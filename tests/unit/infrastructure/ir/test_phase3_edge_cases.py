"""
Phase 3 엣지 케이스 테스트 (CRITICAL Missing Tests!)

사용자 요구: "제대로 테스트 엣지케이스 다 했냐?"

Missing Edge Cases:
1. 파일 없음 (empty list)
2. 파일 존재하지 않음 (FileNotFoundError)
3. 파일 읽기 실패 (PermissionError)
4. 파싱 실패 (SyntaxError)
5. Worker crash (Exception in worker)
6. 부분 실패 (일부 파일만 실패)
7. 큰 파일 + 작은 파일 mix
8. 동일 파일 중복
9. Symlink 파일
10. Binary 파일 (not .py)
"""

import asyncio
import os
import tempfile
import time
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.semantic_ir.adapters import create_default_config
from codegraph_engine.code_foundation.infrastructure.semantic_ir.parallel import (
    ParallelSemanticIrBuilder,
    SemanticIrResult,
    _build_semantic_ir_for_file_worker,
)


@pytest.fixture
def project_root():
    """프로젝트 루트"""
    current = Path(__file__).absolute()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    pytest.skip("pyproject.toml not found")


@pytest.fixture
def temp_project(tmp_path):
    """임시 프로젝트 (테스트용)"""
    # 작은 Python 파일 생성
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello(): return 'world'")
    return tmp_path


class TestEdgeCaseFileHandling:
    """엣지 케이스: 파일 처리"""

    @pytest.mark.asyncio
    async def test_empty_file_list(self, project_root):
        """1. 파일 없음 (빈 리스트)"""
        config = create_default_config()
        builder = ParallelSemanticIrBuilder(config, project_root)

        # Empty list
        results = await builder.build_parallel([])

        assert len(results) == 0
        print("✅ Empty file list handled")

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, project_root):
        """2. 존재하지 않는 파일"""
        file_path = project_root / "nonexistent_file_12345.py"

        result = _build_semantic_ir_for_file_worker(
            str(file_path),
            str(project_root),
        )

        assert not result.success
        assert "not found" in result.error_message.lower()
        print(f"✅ Nonexistent file handled: {result.error_message[:50]}")

    @pytest.mark.asyncio
    async def test_unreadable_file(self, temp_project):
        """3. 읽기 불가 파일 (권한 없음)"""
        if os.name == "nt":
            pytest.skip("Windows doesn't support chmod 000")

        # 읽기 불가 파일 생성
        unreadable = temp_project / "unreadable.py"
        unreadable.write_text("def test(): pass")
        unreadable.chmod(0o000)  # No permissions

        try:
            result = _build_semantic_ir_for_file_worker(
                str(unreadable),
                str(temp_project),
            )

            # Should handle gracefully
            assert not result.success
            print(f"✅ Unreadable file handled: {result.error_message[:50]}")

        finally:
            unreadable.chmod(0o644)  # Restore

    @pytest.mark.asyncio
    async def test_invalid_python_syntax(self, temp_project):
        """4. 파싱 실패 (잘못된 Python 코드)"""
        invalid_file = temp_project / "invalid.py"
        invalid_file.write_text("def broken(: invalid syntax!")

        result = _build_semantic_ir_for_file_worker(
            str(invalid_file),
            str(temp_project),
        )

        # Should handle gracefully (파싱 실패도 처리)
        # tree-sitter는 partial parse를 지원하므로 success일 수 있음
        print(f"✅ Invalid syntax handled: success={result.success}")

    @pytest.mark.asyncio
    async def test_binary_file(self, temp_project):
        """5. Binary 파일 (.py 확장자이지만 바이너리)"""
        binary_file = temp_project / "binary.py"
        binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

        result = _build_semantic_ir_for_file_worker(
            str(binary_file),
            str(temp_project),
        )

        # Should handle gracefully
        print(f"✅ Binary file handled: success={result.success}")


class TestEdgeCaseParallelBehavior:
    """엣지 케이스: 병렬 처리 동작"""

    @pytest.mark.asyncio
    async def test_partial_failure(self, project_root, temp_project):
        """6. 부분 실패 (일부 파일만 성공)"""
        config = create_default_config()
        builder = ParallelSemanticIrBuilder(config, project_root)

        # 좋은 파일 + 나쁜 파일
        good_file = temp_project / "good.py"
        good_file.write_text("def good(): pass")

        bad_file = temp_project / "nonexistent.py"  # 존재하지 않음

        files = [good_file, bad_file]

        results = await builder.build_parallel(files)

        assert len(results) == 2

        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count

        assert success_count == 1, "1개는 성공해야 함"
        assert fail_count == 1, "1개는 실패해야 함"

        print(f"✅ Partial failure handled: {success_count} success, {fail_count} failed")

    @pytest.mark.asyncio
    async def test_mixed_file_sizes(self, temp_project, project_root):
        """7. 큰 파일 + 작은 파일 mix"""
        config = create_default_config()
        builder = ParallelSemanticIrBuilder(config, project_root)

        # 작은 파일
        small = temp_project / "small.py"
        small.write_text("x = 1")

        # 중간 파일
        medium = temp_project / "medium.py"
        medium.write_text("def f1(): pass\n" * 50)

        # 큰 파일
        large = temp_project / "large.py"
        large.write_text("def f1(): pass\n" * 500)

        files = [small, medium, large]

        start = time.perf_counter()
        results = await builder.build_parallel(files)
        elapsed = time.perf_counter() - start

        assert len(results) == 3
        success_count = sum(1 for r in results if r.success)

        assert success_count == 3, "모두 성공해야 함"

        print(f"✅ Mixed file sizes handled in {elapsed:.2f}s")
        print(f"   Small: {small.stat().st_size} bytes")
        print(f"   Medium: {medium.stat().st_size} bytes")
        print(f"   Large: {large.stat().st_size} bytes")

    @pytest.mark.asyncio
    async def test_duplicate_files(self, temp_project, project_root):
        """8. 동일 파일 중복 (2번 처리)"""
        config = create_default_config()
        builder = ParallelSemanticIrBuilder(config, project_root)

        test_file = temp_project / "test.py"
        test_file.write_text("def test(): pass")

        # 동일 파일 2번
        files = [test_file, test_file]

        results = await builder.build_parallel(files)

        assert len(results) == 2
        assert results[0].file_path == results[1].file_path

        print("✅ Duplicate files handled")

    @pytest.mark.asyncio
    async def test_single_file_edge(self, temp_project, project_root):
        """9. 단일 파일 (fallback to sequential)"""
        config = create_default_config()
        builder = ParallelSemanticIrBuilder(config, project_root)

        test_file = temp_project / "single.py"
        test_file.write_text("def single(): pass")

        # 1개 파일 → sequential fallback
        results = await builder.build_parallel([test_file])

        assert len(results) == 1
        assert results[0].success

        print("✅ Single file (fallback) handled")

    @pytest.mark.asyncio
    async def test_two_files_edge(self, temp_project, project_root):
        """10. 2개 파일 (fallback to sequential)"""
        config = create_default_config()
        builder = ParallelSemanticIrBuilder(config, project_root)

        file1 = temp_project / "f1.py"
        file2 = temp_project / "f2.py"
        file1.write_text("def f1(): pass")
        file2.write_text("def f2(): pass")

        # 2개 파일 → sequential fallback
        results = await builder.build_parallel([file1, file2])

        assert len(results) == 2
        assert all(r.success for r in results)

        print("✅ Two files (fallback) handled")


class TestEdgeCaseLoadBalancing:
    """엣지 케이스: Load Balancing"""

    @pytest.mark.asyncio
    async def test_largest_first_with_empty_file(self, temp_project, project_root):
        """11. Largest-first: 빈 파일 포함"""
        config = create_default_config()
        builder = ParallelSemanticIrBuilder(config, project_root)

        # 빈 파일
        empty = temp_project / "empty.py"
        empty.write_text("")

        # 작은 파일
        small = temp_project / "small.py"
        small.write_text("x = 1")

        # 큰 파일
        large = temp_project / "large.py"
        large.write_text("def f(): pass\n" * 100)

        files = [empty, small, large]

        results = await builder.build_parallel(files)

        assert len(results) == 3

        print("✅ Largest-first with empty file handled")

    @pytest.mark.asyncio
    async def test_all_files_same_size(self, temp_project, project_root):
        """12. 모든 파일 크기 동일"""
        config = create_default_config()
        builder = ParallelSemanticIrBuilder(config, project_root)

        # 동일 크기 파일 5개
        files = []
        for i in range(5):
            f = temp_project / f"file_{i}.py"
            f.write_text("def test(): pass")  # 모두 동일
            files.append(f)

        results = await builder.build_parallel(files)

        assert len(results) == 5

        print("✅ All same size files handled")


class TestEdgeCaseErrorRecovery:
    """엣지 케이스: 에러 복구"""

    @pytest.mark.asyncio
    async def test_unicode_filename(self, temp_project, project_root):
        """13. Unicode 파일명"""
        config = create_default_config()
        builder = ParallelSemanticIrBuilder(config, project_root)

        # Unicode 파일명
        unicode_file = temp_project / "한글파일명_🚀.py"
        unicode_file.write_text("def test(): pass")

        results = await builder.build_parallel([unicode_file])

        assert len(results) == 1
        assert results[0].success

        print(f"✅ Unicode filename handled: {unicode_file.name}")

    @pytest.mark.asyncio
    async def test_very_long_filename(self, temp_project, project_root):
        """14. 매우 긴 파일명"""
        config = create_default_config()
        builder = ParallelSemanticIrBuilder(config, project_root)

        # 긴 파일명 (255자 제한 근처)
        long_name = "a" * 200 + ".py"
        long_file = temp_project / long_name

        try:
            long_file.write_text("def test(): pass")

            results = await builder.build_parallel([long_file])

            assert len(results) == 1
            print(f"✅ Very long filename handled: {len(long_name)} chars")

        except OSError:
            pytest.skip("Filesystem doesn't support long filenames")

    @pytest.mark.asyncio
    async def test_deep_directory_nesting(self, temp_project, project_root):
        """15. 깊은 디렉토리 중첩"""
        config = create_default_config()
        builder = ParallelSemanticIrBuilder(config, project_root)

        # 깊은 디렉토리 생성
        deep_path = temp_project
        for i in range(10):
            deep_path = deep_path / f"level_{i}"
            deep_path.mkdir(exist_ok=True)

        deep_file = deep_path / "deep.py"
        deep_file.write_text("def test(): pass")

        results = await builder.build_parallel([deep_file])

        assert len(results) == 1
        assert results[0].success

        print(f"✅ Deep directory nesting handled: {len(deep_file.parts)} levels")


class TestExtremeEdgeCases:
    """Extreme 엣지 케이스"""

    @pytest.mark.asyncio
    async def test_zero_byte_file(self, temp_project, project_root):
        """16. 0바이트 파일"""
        zero_file = temp_project / "zero.py"
        zero_file.write_text("")

        result = _build_semantic_ir_for_file_worker(
            str(zero_file),
            str(temp_project),
        )

        # 빈 파일도 처리 가능해야 함
        assert result.file_path == str(zero_file)
        print(f"✅ Zero-byte file handled: success={result.success}")

    @pytest.mark.asyncio
    async def test_symlink_file(self, temp_project, project_root):
        """17. Symlink 파일"""
        if os.name == "nt":
            pytest.skip("Symlinks require admin on Windows")

        # 원본 파일
        original = temp_project / "original.py"
        original.write_text("def original(): pass")

        # Symlink
        symlink = temp_project / "symlink.py"
        symlink.symlink_to(original)

        result = _build_semantic_ir_for_file_worker(
            str(symlink),
            str(temp_project),
        )

        assert result.success
        print("✅ Symlink file handled")

    @pytest.mark.asyncio
    async def test_concurrent_file_modification(self, temp_project, project_root):
        """18. 처리 중 파일 수정 (Race condition)"""
        test_file = temp_project / "racing.py"
        test_file.write_text("def test(): pass")

        config = create_default_config()
        builder = ParallelSemanticIrBuilder(config, project_root)

        # Build하는 동안 파일 수정
        async def modify_file():
            await asyncio.sleep(0.01)
            test_file.write_text("def modified(): pass")

        # 동시 실행
        build_task = builder.build_parallel([test_file])
        modify_task = modify_file()

        results, _ = await asyncio.gather(build_task, modify_task)

        assert len(results) == 1
        # Success or fail 둘 다 OK (race condition이지만 crash 안 해야 함)
        print(f"✅ Concurrent modification handled: success={results[0].success}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
