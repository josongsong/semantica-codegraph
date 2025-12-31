"""
ApprovalManager 단위 테스트 (SOTA급)

테스트 커버리지:
1. 파일 단위 승인
2. Hunk 단위 승인
3. 부분 승인 (일부만)
4. 자동 승인 규칙
5. 거부 처리
6. 통계 생성
7. CLI UI 통합
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.orchestrator.orchestrator.domain.approval_manager import (
    ApprovalCriteria,
    ApprovalDecision,
    ApprovalManager,
    ApprovalSession,
    CLIApprovalAdapter,
)
from apps.orchestrator.orchestrator.domain.diff_manager import DiffHunk, DiffManager, FileDiff


class TestApprovalManagerFileLevel:
    """파일 단위 승인 테스트"""

    @pytest.fixture
    def approval_manager(self):
        """ApprovalManager 인스턴스 (자동 승인 없음)"""
        criteria = ApprovalCriteria(
            auto_approve_tests=False,
            auto_approve_docs=False,
            max_lines_auto=0,
        )
        return ApprovalManager(ui_adapter=None, criteria=criteria)

    @pytest.mark.asyncio
    async def test_should_approve_entire_file_when_file_level_approval(self, approval_manager):
        """
        Given: 여러 파일의 변경사항
        When: 파일 단위로 승인
        Then: 전체 파일 변경이 승인됨
        """
        # Given
        diff_manager = DiffManager(context_lines=3)
        file_diff1 = await diff_manager.generate_diff(
            file_path="utils.py",
            old_content="def foo(): pass\n",
            new_content="def foo(): return 42\n",
        )
        file_diff2 = await diff_manager.generate_diff(
            file_path="module.py",
            old_content="x = 1\n",
            new_content="x = 2\n",
        )
        sample_file_diffs = [file_diff1, file_diff2]

        session = ApprovalSession(
            session_id="test-session",
            file_diffs=sample_file_diffs,
        )

        # When: 첫 번째 파일 승인
        decision = ApprovalDecision(
            file_path="utils.py",
            hunk_index=None,  # 파일 전체
            action="approve",
        )
        session.add_decision(decision)

        # Then
        approved = session.get_approved_file_diffs()
        assert len(approved) == 1
        assert approved[0].file_path == "utils.py"
        assert len(approved[0].hunks) > 0  # 모든 hunk 포함

    @pytest.mark.asyncio
    async def test_should_reject_file_when_file_level_rejection(self, approval_manager):
        """
        Given: 여러 파일의 변경사항
        When: 파일 단위로 거부
        Then: 해당 파일이 승인 목록에서 제외됨
        """
        # Given
        diff_manager = DiffManager(context_lines=3)
        file_diff1 = await diff_manager.generate_diff(
            file_path="utils.py",
            old_content="def foo(): pass\n",
            new_content="def foo(): return 42\n",
        )
        file_diff2 = await diff_manager.generate_diff(
            file_path="module.py",
            old_content="x = 1\n",
            new_content="x = 2\n",
        )
        sample_file_diffs = [file_diff1, file_diff2]

        session = ApprovalSession(
            session_id="test-session",
            file_diffs=sample_file_diffs,
        )

        # When: 첫 번째 파일 거부
        decision = ApprovalDecision(
            file_path="utils.py",
            hunk_index=None,
            action="reject",
            reason="Logic error",
        )
        session.add_decision(decision)

        # Then
        approved = session.get_approved_file_diffs()
        assert len(approved) == 0  # 승인된 파일 없음
        assert session.decisions[0].is_rejected()
        assert session.decisions[0].reason == "Logic error"


class TestApprovalManagerHunkLevel:
    """Hunk 단위 승인 테스트"""

    @pytest.fixture
    def approval_manager(self):
        criteria = ApprovalCriteria(auto_approve_tests=False)
        return ApprovalManager(ui_adapter=None, criteria=criteria)

    @pytest.mark.asyncio
    async def test_should_approve_specific_hunk_when_hunk_level_approval(self, approval_manager):
        """
        Given: 3개 hunk을 가진 파일
        When: 특정 hunk만 승인
        Then: 해당 hunk만 승인됨
        """
        # Given: 3개 hunk을 가진 파일 생성
        diff_manager = DiffManager(context_lines=3)
        old_content = "\n".join([f"line{i}" for i in range(1, 31)])
        lines = old_content.split("\n")
        lines[2] = "line3_modified"
        lines[15] = "line16_modified"
        lines[25] = "line26_modified"
        new_content = "\n".join(lines)
        multi_hunk_diff = await diff_manager.generate_diff(
            file_path="large.py",
            old_content=old_content,
            new_content=new_content,
        )

        session = ApprovalSession(
            session_id="test-session",
            file_diffs=[multi_hunk_diff],
        )

        # When: 첫 번째 hunk만 승인
        decision = ApprovalDecision(
            file_path="large.py",
            hunk_index=0,
            action="approve",
        )
        session.add_decision(decision)

        # Then
        approved = session.get_approved_file_diffs()
        assert len(approved) == 1
        assert len(approved[0].hunks) == 1  # 1개 hunk만
        assert approved[0].hunks[0] == multi_hunk_diff.hunks[0]

    @pytest.mark.asyncio
    async def test_should_approve_multiple_hunks_when_multiple_approvals(self, approval_manager):
        """
        Given: 3개 hunk을 가진 파일
        When: 2개 hunk 승인
        Then: 2개 hunk만 승인됨
        """
        # Given: 3개 hunk을 가진 파일 생성
        diff_manager = DiffManager(context_lines=3)
        old_content = "\n".join([f"line{i}" for i in range(1, 31)])
        lines = old_content.split("\n")
        lines[2] = "line3_modified"
        lines[15] = "line16_modified"
        lines[25] = "line26_modified"
        new_content = "\n".join(lines)
        multi_hunk_diff = await diff_manager.generate_diff(
            file_path="large.py",
            old_content=old_content,
            new_content=new_content,
        )

        session = ApprovalSession(
            session_id="test-session",
            file_diffs=[multi_hunk_diff],
        )

        # When: hunk 0, 2 승인
        session.add_decision(ApprovalDecision(file_path="large.py", hunk_index=0, action="approve"))
        session.add_decision(ApprovalDecision(file_path="large.py", hunk_index=2, action="approve"))

        # Then
        approved = session.get_approved_file_diffs()
        assert len(approved) == 1
        assert len(approved[0].hunks) == 2  # 2개 hunk
        assert approved[0].hunks[0] == multi_hunk_diff.hunks[0]
        assert approved[0].hunks[1] == multi_hunk_diff.hunks[2]


class TestApprovalManagerPartialApproval:
    """부분 승인 테스트"""

    @pytest.fixture
    def approval_manager(self):
        return ApprovalManager(ui_adapter=None, criteria=ApprovalCriteria())

    @pytest.mark.asyncio
    async def test_should_support_partial_approval_of_multiple_files(self, approval_manager):
        """
        Given: 3개 파일의 변경사항
        When: 2개 파일만 승인
        Then: 승인된 2개 파일만 반환됨
        """
        # Given
        diff_manager = DiffManager(context_lines=3)

        file_diffs = [
            await diff_manager.generate_diff("old1\n", "new1\n", "file1.py"),
            await diff_manager.generate_diff("old2\n", "new2\n", "file2.py"),
            await diff_manager.generate_diff("old3\n", "new3\n", "file3.py"),
        ]

        session = ApprovalSession(
            session_id="test-session",
            file_diffs=file_diffs,
        )

        # When: file1, file3만 승인
        session.add_decision(ApprovalDecision(file_path="file1.py", hunk_index=None, action="approve"))
        session.add_decision(ApprovalDecision(file_path="file3.py", hunk_index=None, action="approve"))

        # Then
        approved = session.get_approved_file_diffs()
        assert len(approved) == 2
        assert {f.file_path for f in approved} == {"file1.py", "file3.py"}


class TestApprovalManagerAutoApproval:
    """자동 승인 규칙 테스트"""

    @pytest.mark.asyncio
    async def test_should_auto_approve_test_files_when_auto_approve_tests_is_true(self):
        """
        Given: auto_approve_tests=True
        When: 테스트 파일 변경
        Then: 자동 승인됨
        """
        # Given
        criteria = ApprovalCriteria(
            auto_approve_tests=True,
            auto_approve_docs=False,
            max_lines_auto=100,
        )
        manager = ApprovalManager(ui_adapter=None, criteria=criteria)

        diff_manager = DiffManager(context_lines=3)
        file_diff = await diff_manager.generate_diff(
            file_path="test_foo.py",
            old_content="def test_old(): pass\n",
            new_content="def test_new(): pass\n",
        )

        # When
        should_auto = manager.should_auto_approve(file_diff)

        # Then
        assert should_auto is True

    @pytest.mark.asyncio
    async def test_should_auto_approve_docs_when_auto_approve_docs_is_true(self):
        """
        Given: auto_approve_docs=True
        When: 문서 파일 변경
        Then: 자동 승인됨
        """
        # Given
        criteria = ApprovalCriteria(
            auto_approve_tests=False,
            auto_approve_docs=True,
            max_lines_auto=100,
        )
        manager = ApprovalManager(ui_adapter=None, criteria=criteria)

        diff_manager = DiffManager(context_lines=3)
        file_diff = await diff_manager.generate_diff(
            file_path="README.md",
            old_content="# Old\n",
            new_content="# New\n",
        )

        # When
        should_auto = manager.should_auto_approve(file_diff)

        # Then
        assert should_auto is True

    @pytest.mark.asyncio
    async def test_should_auto_approve_small_changes_when_within_max_lines(self):
        """
        Given: max_lines_auto=20
        When: 10줄 변경
        Then: 자동 승인됨
        """
        # Given
        criteria = ApprovalCriteria(
            auto_approve_tests=False,
            auto_approve_docs=False,
            max_lines_auto=20,
        )
        manager = ApprovalManager(ui_adapter=None, criteria=criteria)

        diff_manager = DiffManager(context_lines=3)
        old_content = "\n".join([f"line{i}" for i in range(1, 11)])  # 10줄
        new_content = "\n".join([f"modified{i}" for i in range(1, 11)])

        file_diff = await diff_manager.generate_diff(
            file_path="small.py",
            old_content=old_content,
            new_content=new_content,
        )

        # When
        should_auto = manager.should_auto_approve(file_diff)

        # Then
        assert should_auto is True

    @pytest.mark.asyncio
    async def test_should_not_auto_approve_large_changes_when_exceeds_max_lines(self):
        """
        Given: max_lines_auto=20
        When: 30줄 변경
        Then: 자동 승인 안 됨
        """
        # Given
        criteria = ApprovalCriteria(
            auto_approve_tests=False,
            auto_approve_docs=False,
            max_lines_auto=20,
        )
        manager = ApprovalManager(ui_adapter=None, criteria=criteria)

        diff_manager = DiffManager(context_lines=3)
        old_content = "\n".join([f"line{i}" for i in range(1, 31)])  # 30줄
        new_content = "\n".join([f"modified{i}" for i in range(1, 31)])

        file_diff = await diff_manager.generate_diff(
            file_path="large.py",
            old_content=old_content,
            new_content=new_content,
        )

        # When
        should_auto = manager.should_auto_approve(file_diff)

        # Then
        assert should_auto is False


class TestApprovalManagerRejection:
    """거부 처리 테스트"""

    @pytest.fixture
    def approval_manager(self):
        return ApprovalManager(ui_adapter=None, criteria=ApprovalCriteria())

    @pytest.mark.asyncio
    async def test_should_record_rejection_reason_when_rejected(self, approval_manager):
        """
        Given: 변경사항
        When: 이유와 함께 거부
        Then: 거부 이유가 기록됨
        """
        # Given
        diff_manager = DiffManager(context_lines=3)
        file_diff = await diff_manager.generate_diff("old\n", "new\n", "test.py")

        session = ApprovalSession(
            session_id="test-session",
            file_diffs=[file_diff],
        )

        # When
        decision = ApprovalDecision(
            file_path="test.py",
            action="reject",
            reason="Security concern: potential SQL injection",
        )
        session.add_decision(decision)

        # Then
        assert session.decisions[0].is_rejected()
        assert "SQL injection" in session.decisions[0].reason


class TestApprovalManagerStatistics:
    """통계 생성 테스트"""

    @pytest.fixture
    def approval_manager(self):
        return ApprovalManager(ui_adapter=None, criteria=ApprovalCriteria())

    @pytest.mark.asyncio
    async def test_should_generate_statistics_when_session_has_decisions(self, approval_manager):
        """
        Given: 여러 결정이 포함된 세션
        When: 통계 생성
        Then: 승인/거부/스킵 통계가 정확함
        """
        # Given
        diff_manager = DiffManager(context_lines=3)

        import asyncio

        file_diffs = await asyncio.gather(
            *[diff_manager.generate_diff("old\n", "new\n", f"file{i}.py") for i in range(5)]
        )

        session = ApprovalSession(
            session_id="test-session",
            file_diffs=file_diffs,
        )

        # 2개 승인, 1개 거부, 1개 스킵, 1개 미결정
        session.add_decision(ApprovalDecision(file_path="file0.py", action="approve"))
        session.add_decision(ApprovalDecision(file_path="file1.py", action="approve"))
        session.add_decision(ApprovalDecision(file_path="file2.py", action="reject"))
        session.add_decision(ApprovalDecision(file_path="file3.py", action="skip"))

        # When
        stats = session.get_statistics()

        # Then
        assert stats["total_files"] == 5
        assert stats["approved"] == 2
        assert stats["rejected"] == 1
        assert stats["skipped"] == 1
        assert stats["pending"] == 1


class TestCLIApprovalAdapter:
    """CLI UI 통합 테스트"""

    @pytest.mark.asyncio
    async def test_should_format_diff_with_color_when_colorize_is_true(self):
        """
        Given: FileDiff
        When: CLI UI로 포맷팅 (colorize=True)
        Then: 색상 코드 포함
        """
        # Given
        adapter = CLIApprovalAdapter(colorize=True)
        diff_manager = DiffManager(context_lines=3)

        file_diff = await diff_manager.generate_diff(
            file_path="test.py",
            old_content="old line\n",
            new_content="new line\n",
        )

        # When: show_diff는 출력만 하고 반환값이 없으므로 캡처
        import io
        import sys
        from unittest.mock import patch

        captured_output = io.StringIO()
        with patch("sys.stdout", captured_output):
            await adapter.show_diff(file_diff)
        formatted = captured_output.getvalue()

        # Then
        assert "\033[" in formatted  # ANSI color code

    @pytest.mark.asyncio
    async def test_should_format_diff_without_color_when_colorize_is_false(self):
        """
        Given: FileDiff
        When: CLI UI로 포맷팅 (colorize=False)
        Then: 색상 코드 없음
        """
        # Given
        adapter = CLIApprovalAdapter(colorize=False)
        diff_manager = DiffManager(context_lines=3)

        file_diff = await diff_manager.generate_diff(
            old_content="old line\n",
            new_content="new line\n",
            file_path="test.py",
        )

        # When: show_diff는 출력만 하고 반환값이 없으므로 캡처
        import io
        import sys
        from unittest.mock import patch

        captured_output = io.StringIO()
        with patch("sys.stdout", captured_output):
            await adapter.show_diff(file_diff)
        formatted = captured_output.getvalue()

        # Then
        assert "\033[" not in formatted  # ANSI color code 없음
        assert "test.py" in formatted
