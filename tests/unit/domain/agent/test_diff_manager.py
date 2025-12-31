"""
DiffManager 단위 테스트 (SOTA급)

테스트 커버리지:
1. 기본 diff 생성
2. 여러 hunk 처리
3. 빈 파일 처리
4. 대용량 파일 (1000줄) 성능
5. Color 지원
6. Context lines
7. 에러 처리
8. TypeScript 파일
"""

import time

import pytest

from apps.orchestrator.orchestrator.domain.diff_manager import DiffManager


class TestDiffManagerBasic:
    """기본 diff 생성 테스트"""

    @pytest.fixture
    def diff_manager(self):
        """DiffManager 인스턴스"""
        return DiffManager(context_lines=3)

    @pytest.mark.asyncio
    async def test_should_generate_simple_diff_when_single_line_changed(self, diff_manager):
        """
        Given: 한 줄만 변경된 파일
        When: diff 생성
        Then: 1개 hunk, 정확한 변경사항 반영
        """
        # Given
        old_content = "line1\nline2\nline3\n"
        new_content = "line1\nline2_modified\nline3\n"

        # When
        file_diff = await diff_manager.generate_diff(
            old_content=old_content,
            new_content=new_content,
            file_path="test.py",
        )

        # Then
        assert file_diff.file_path == "test.py"
        assert len(file_diff.hunks) == 1

        hunk = file_diff.hunks[0]
        assert hunk.old_start == 1
        assert hunk.new_start == 1
        assert len(hunk.removed_lines) == 1
        assert len(hunk.added_lines) == 1
        assert "line2" in hunk.removed_lines[0]
        assert "line2_modified" in hunk.added_lines[0]

    @pytest.mark.asyncio
    async def test_should_handle_empty_file_when_old_content_is_empty(self, diff_manager):
        """
        Given: 빈 파일에서 내용 추가
        When: diff 생성
        Then: change_type="added", 모든 라인이 추가됨
        """
        # Given
        old_content = ""
        new_content = "line1\nline2\nline3\n"

        # When
        file_diff = await diff_manager.generate_diff(
            old_content=old_content,
            new_content=new_content,
            file_path="new_file.py",
        )

        # Then
        assert file_diff.change_type == "added"
        assert file_diff.is_new_file
        assert len(file_diff.hunks) == 1
        assert len(file_diff.hunks[0].added_lines) == 3
        assert len(file_diff.hunks[0].removed_lines) == 0

    @pytest.mark.asyncio
    async def test_should_handle_deletion_when_new_content_is_empty(self, diff_manager):
        """
        Given: 파일 내용 전체 삭제
        When: diff 생성
        Then: change_type="deleted", 모든 라인이 삭제됨
        """
        # Given
        old_content = "line1\nline2\nline3\n"
        new_content = ""

        # When
        file_diff = await diff_manager.generate_diff(
            old_content=old_content,
            new_content=new_content,
            file_path="deleted.py",
        )

        # Then
        assert file_diff.change_type == "deleted"
        assert file_diff.is_deleted
        assert len(file_diff.hunks) == 1
        assert len(file_diff.hunks[0].removed_lines) == 3
        assert len(file_diff.hunks[0].added_lines) == 0


class TestDiffManagerMultipleHunks:
    """여러 hunk 처리 테스트"""

    @pytest.fixture
    def diff_manager(self):
        return DiffManager(context_lines=3)

    @pytest.mark.asyncio
    async def test_should_create_multiple_hunks_when_changes_are_far_apart(self, diff_manager):
        """
        Given: 멀리 떨어진 두 곳에서 변경
        When: diff 생성
        Then: 2개 hunk 생성
        """
        # Given
        old_content = "\n".join([f"line{i}" for i in range(1, 21)])  # 20줄
        lines = old_content.split("\n")
        lines[2] = "line3_modified"  # 3번째 줄 변경
        lines[15] = "line16_modified"  # 16번째 줄 변경
        new_content = "\n".join(lines)

        # When
        file_diff = await diff_manager.generate_diff(
            old_content=old_content,
            new_content=new_content,
            file_path="multi_hunk.py",
        )

        # Then
        assert len(file_diff.hunks) == 2
        assert file_diff.hunks[0].old_start < file_diff.hunks[1].old_start
        assert file_diff.total_added == 2
        assert file_diff.total_removed == 2

    @pytest.mark.asyncio
    async def test_should_merge_adjacent_hunks_when_changes_are_close(self, diff_manager):
        """
        Given: 가까운 곳에서 여러 변경
        When: diff 생성
        Then: 1개 hunk로 병합
        """
        # Given
        old_content = "\n".join([f"line{i}" for i in range(1, 11)])  # 10줄
        lines = old_content.split("\n")
        lines[2] = "line3_modified"  # 3번째 줄
        lines[4] = "line5_modified"  # 5번째 줄 (context_lines=3이면 병합됨)
        new_content = "\n".join(lines)

        # When
        file_diff = await diff_manager.generate_diff(
            old_content=old_content,
            new_content=new_content,
            file_path="merged_hunk.py",
        )

        # Then
        assert len(file_diff.hunks) == 1  # 병합됨
        assert file_diff.total_added == 2
        assert file_diff.total_removed == 2


class TestDiffManagerPerformance:
    """성능 테스트"""

    @pytest.fixture
    def diff_manager(self):
        return DiffManager(context_lines=3)

    @pytest.mark.asyncio
    async def test_should_process_large_file_within_one_second(self, diff_manager):
        """
        Given: 1000줄 파일에서 10곳 변경
        When: diff 생성
        Then: 1초 이내 완료
        """
        # Given
        old_lines = [f"line{i}" for i in range(1, 1001)]  # 1000줄
        new_lines = old_lines.copy()

        # 10곳 변경 (고르게 분포)
        for i in range(0, 1000, 100):
            new_lines[i] = f"line{i}_modified"

        old_content = "\n".join(old_lines)
        new_content = "\n".join(new_lines)

        # When
        start_time = time.perf_counter()
        file_diff = await diff_manager.generate_diff(
            old_content=old_content,
            new_content=new_content,
            file_path="large_file.py",
        )
        elapsed = time.perf_counter() - start_time

        # Then
        assert elapsed < 1.0, f"너무 느림: {elapsed:.3f}초"
        assert len(file_diff.hunks) > 0
        assert file_diff.total_added == 10
        assert file_diff.total_removed == 10

    @pytest.mark.asyncio
    async def test_should_handle_identical_content_quickly(self, diff_manager):
        """
        Given: 동일한 내용의 대용량 파일
        When: diff 생성
        Then: 빠르게 처리 (변경 없음)
        """
        # Given
        content = "\n".join([f"line{i}" for i in range(1, 1001)])  # 1000줄

        # When
        start_time = time.perf_counter()
        file_diff = await diff_manager.generate_diff(
            old_content=content,
            new_content=content,
            file_path="identical.py",
        )
        elapsed = time.perf_counter() - start_time

        # Then
        assert elapsed < 0.1, f"너무 느림: {elapsed:.3f}초"
        assert len(file_diff.hunks) == 0
        assert file_diff.total_added == 0
        assert file_diff.total_removed == 0


class TestDiffManagerColorSupport:
    """Color 지원 테스트"""

    @pytest.fixture
    def diff_manager(self):
        return DiffManager(context_lines=3)

    @pytest.mark.asyncio
    async def test_should_include_color_codes_when_colorize_is_true(self, diff_manager):
        """
        Given: 간단한 diff
        When: colorize=True로 포맷팅
        Then: ANSI color code 포함
        """
        # Given
        old_content = "line1\nline2\nline3\n"
        new_content = "line1\nline2_modified\nline3\n"

        file_diff = await diff_manager.generate_diff(
            old_content=old_content,
            new_content=new_content,
            file_path="test.py",
        )

        # When
        formatted = diff_manager.format_file_diff(file_diff, colorize=True)

        # Then
        assert "\033[" in formatted  # ANSI escape code
        assert "test.py" in formatted

    @pytest.mark.asyncio
    async def test_should_not_include_color_codes_when_colorize_is_false(self, diff_manager):
        """
        Given: 간단한 diff
        When: colorize=False로 포맷팅
        Then: ANSI color code 없음
        """
        # Given
        old_content = "line1\nline2\nline3\n"
        new_content = "line1\nline2_modified\nline3\n"

        file_diff = await diff_manager.generate_diff(
            old_content=old_content,
            new_content=new_content,
            file_path="test.py",
        )

        # When
        formatted = diff_manager.format_file_diff(file_diff, colorize=False)

        # Then
        assert "\033[" not in formatted  # ANSI escape code 없음
        assert "test.py" in formatted


class TestDiffManagerContextLines:
    """Context lines 테스트"""

    @pytest.mark.asyncio
    async def test_should_include_context_lines_when_context_lines_is_3(self):
        """
        Given: context_lines=3
        When: 한 줄 변경
        Then: 앞뒤 3줄씩 context 포함
        """
        # Given
        diff_manager = DiffManager(context_lines=3)
        old_content = "\n".join([f"line{i}" for i in range(1, 11)])  # 10줄
        lines = old_content.split("\n")
        lines[5] = "line6_modified"  # 6번째 줄 변경
        new_content = "\n".join(lines)

        # When
        file_diff = await diff_manager.generate_diff(
            old_content=old_content,
            new_content=new_content,
            file_path="test.py",
        )

        # Then
        hunk = file_diff.hunks[0]
        context_count = len(hunk.context_lines)
        assert context_count >= 6  # 앞 3줄 + 뒤 3줄

    @pytest.mark.asyncio
    async def test_should_include_no_context_when_context_lines_is_0(self):
        """
        Given: context_lines=0
        When: 한 줄 변경
        Then: context 없음, 변경된 줄만 포함
        """
        # Given
        diff_manager = DiffManager(context_lines=0)
        old_content = "\n".join([f"line{i}" for i in range(1, 11)])
        lines = old_content.split("\n")
        lines[5] = "line6_modified"
        new_content = "\n".join(lines)

        # When
        file_diff = await diff_manager.generate_diff(
            old_content=old_content,
            new_content=new_content,
            file_path="test.py",
        )

        # Then
        hunk = file_diff.hunks[0]
        assert len(hunk.context_lines) == 0
        assert len(hunk.added_lines) == 1
        assert len(hunk.removed_lines) == 1


class TestDiffManagerErrorHandling:
    """에러 처리 테스트"""

    @pytest.fixture
    def diff_manager(self):
        return DiffManager(context_lines=3)

    @pytest.mark.asyncio
    async def test_should_raise_error_when_file_path_is_empty(self, diff_manager):
        """
        Given: 빈 file_path
        When: diff 생성
        Then: ValueError 발생
        """
        # Given
        old_content = "line1\n"
        new_content = "line2\n"

        # When & Then
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            await diff_manager.generate_diff(
                old_content=old_content,
                new_content=new_content,
                file_path="",
            )

    @pytest.mark.asyncio
    async def test_should_raise_error_when_old_content_is_none(self, diff_manager):
        """
        Given: old_content가 None
        When: diff 생성
        Then: ValueError 발생
        """
        # Given
        new_content = "line1\n"

        # When & Then
        with pytest.raises(ValueError, match="old_content and new_content cannot be None"):
            await diff_manager.generate_diff(
                old_content=None,
                new_content=new_content,
                file_path="test.py",
            )

    @pytest.mark.asyncio
    async def test_should_raise_error_when_new_content_is_none(self, diff_manager):
        """
        Given: new_content가 None
        When: diff 생성
        Then: ValueError 발생
        """
        # Given
        old_content = "line1\n"

        # When & Then
        with pytest.raises(ValueError, match="old_content and new_content cannot be None"):
            await diff_manager.generate_diff(
                old_content=old_content,
                new_content=None,
                file_path="test.py",
            )


class TestDiffManagerTypeScript:
    """TypeScript 파일 테스트"""

    @pytest.fixture
    def diff_manager(self):
        return DiffManager(context_lines=3)

    @pytest.mark.asyncio
    async def test_should_handle_typescript_file_correctly(self, diff_manager):
        """
        Given: TypeScript 파일 변경
        When: diff 생성
        Then: 정확한 diff 생성
        """
        # Given
        old_content = """\
import express from 'express';

const app = express();
app.listen(3000);
"""

        new_content = """\
import express from 'express';
import morgan from 'morgan';

const app = express();
app.use(morgan('dev'));
app.listen(3000);
"""

        # When
        file_diff = await diff_manager.generate_diff(
            old_content=old_content,
            new_content=new_content,
            file_path="server.ts",
        )

        # Then
        assert file_diff.file_path == "server.ts"
        assert len(file_diff.hunks) >= 1
        assert file_diff.total_added >= 2  # import morgan, app.use
        assert "morgan" in str(file_diff.hunks[0].added_lines)
