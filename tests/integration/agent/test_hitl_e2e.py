"""
Human-in-the-Loop E2E 테스트 (SOTA급)

전체 워크플로우 시나리오:
1. 단일 파일 수정 → Diff → 승인 → 커밋
2. 여러 파일 수정 → 부분 승인 → Partial commit
3. 자동 승인 규칙 → 테스트 파일 자동 승인
4. 거부 후 재시도 → 수정 → 재승인
5. 대용량 변경 → Shadow branch → Rollback
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.orchestrator.orchestrator.domain.approval_manager import (
    ApprovalCriteria,
    ApprovalDecision,
    ApprovalManager,
    ApprovalSession,
)
from apps.orchestrator.orchestrator.domain.diff_manager import DiffManager
from apps.orchestrator.orchestrator.domain.partial_committer import PartialCommitter


@pytest.fixture
def temp_git_repo():
    """임시 Git 저장소"""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        import subprocess

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        # 초기 파일
        (repo_path / "src").mkdir()
        (repo_path / "src" / "utils.py").write_text(
            "def calculate_total(price, discount_rate):\n    return price - discount_rate\n"
        )
        (repo_path / "src" / "models.py").write_text(
            "class User:\n    def __init__(self, name):\n        self.name = name\n"
        )
        (repo_path / "tests").mkdir()
        (repo_path / "tests" / "test_utils.py").write_text("def test_calculate_total():\n    assert True\n")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True)

        yield repo_path


class TestE2EScenario1:
    """시나리오 1: 단일 파일 수정 → Diff → 승인 → 커밋"""

    @pytest.mark.asyncio
    async def test_full_workflow_single_file(self, temp_git_repo):
        """
        Given: 1개 파일 수정
        When: Diff → 승인 → 커밋
        Then: 변경사항이 Git에 반영됨
        """
        # Given: 파일 수정
        utils_file = temp_git_repo / "src" / "utils.py"
        old_content = utils_file.read_text()
        new_content = old_content.replace(
            "return price - discount_rate",
            "discount = price * discount_rate\n    return price - discount",
        )

        # Step 1: Diff 생성
        diff_manager = DiffManager(context_lines=3)
        file_diff = diff_manager.generate_diff(
            file_path="src/utils.py",
            old_content=old_content,
            new_content=new_content,
        )

        assert len(file_diff.hunks) == 1
        assert file_diff.total_added == 2
        assert file_diff.total_removed == 1

        # Step 2: 승인
        approval_manager = ApprovalManager(
            ui_adapter=None,
            criteria=ApprovalCriteria(),
        )

        session = ApprovalSession(
            session_id="test-session-1",
            file_diffs=[file_diff],
        )

        session.add_decision(
            ApprovalDecision(
                file_path="src/utils.py",
                action="approve",
            )
        )

        approved = session.get_approved_file_diffs()
        assert len(approved) == 1

        # Step 3: 커밋
        utils_file.write_text(new_content)  # 실제 파일 변경

        committer = PartialCommitter(repo_path=str(temp_git_repo))
        result = await committer.apply_partial(
            approved_file_diffs=approved,
            commit_message="Fix: calculate_total discount logic",
            branch_name=None,
            create_shadow=False,
        )

        # Then
        assert result.success is True
        assert result.commit_sha is not None
        assert "src/utils.py" in result.applied_files

        # Git log 확인
        import subprocess

        log = subprocess.check_output(
            ["git", "log", "-1", "--pretty=%s"],
            cwd=temp_git_repo,
            text=True,
        )
        assert "Fix: calculate_total" in log


class TestE2EScenario2:
    """시나리오 2: 여러 파일 수정 → 부분 승인 → Partial commit"""

    @pytest.mark.asyncio
    async def test_partial_approval_multiple_files(self, temp_git_repo):
        """
        Given: 3개 파일 수정
        When: 2개만 승인
        Then: 승인된 2개만 커밋됨
        """
        # Given: 3개 파일 수정
        utils_file = temp_git_repo / "src" / "utils.py"
        models_file = temp_git_repo / "src" / "models.py"
        test_file = temp_git_repo / "tests" / "test_utils.py"

        old_utils = utils_file.read_text()
        old_models = models_file.read_text()
        old_test = test_file.read_text()

        new_utils = old_utils.replace("discount_rate", "discount_percent")
        new_models = old_models.replace("self.name = name", "self.name = name  # noqa")
        new_test = old_test.replace("assert True", "assert 1 + 1 == 2")

        # Step 1: Diff 생성
        diff_manager = DiffManager(context_lines=3)

        diff_utils = diff_manager.generate_diff("src/utils.py", old_utils, new_utils)
        diff_models = diff_manager.generate_diff("src/models.py", old_models, new_models)
        diff_test = diff_manager.generate_diff("tests/test_utils.py", old_test, new_test)

        # Step 2: 2개만 승인 (utils, test)
        session = ApprovalSession(
            session_id="test-session-2",
            file_diffs=[diff_utils, diff_models, diff_test],
        )

        session.add_decision(ApprovalDecision(file_path="src/utils.py", action="approve"))
        session.add_decision(ApprovalDecision(file_path="src/models.py", action="reject", reason="Unnecessary comment"))
        session.add_decision(ApprovalDecision(file_path="tests/test_utils.py", action="approve"))

        approved = session.get_approved_file_diffs()
        assert len(approved) == 2
        assert {f.file_path for f in approved} == {"src/utils.py", "tests/test_utils.py"}

        # Step 3: Partial commit
        utils_file.write_text(new_utils)
        test_file.write_text(new_test)
        # models는 변경하지 않음

        committer = PartialCommitter(repo_path=str(temp_git_repo))
        result = await committer.apply_partial(
            approved_file_diffs=approved,
            commit_message="Partial: utils and test only",
            branch_name=None,
            create_shadow=False,
        )

        # Then
        assert result.success is True
        assert len(result.applied_files) == 2
        assert "src/utils.py" in result.applied_files
        assert "tests/test_utils.py" in result.applied_files

        # models.py는 변경 안 됨
        assert models_file.read_text() == old_models


class TestE2EScenario3:
    """시나리오 3: 자동 승인 규칙 → 테스트 파일 자동 승인"""

    @pytest.mark.asyncio
    async def test_auto_approve_test_files(self, temp_git_repo):
        """
        Given: 테스트 파일 수정 + auto_approve_tests=True
        When: Diff 생성
        Then: 자동 승인됨
        """
        # Given
        test_file = temp_git_repo / "tests" / "test_utils.py"
        old_test = test_file.read_text()
        new_test = old_test.replace("assert True", "assert calculate_total(100, 0.1) == 90")

        # Step 1: Diff 생성
        diff_manager = DiffManager(context_lines=3)
        diff_test = diff_manager.generate_diff("tests/test_utils.py", old_test, new_test)

        # Step 2: 자동 승인 체크
        approval_manager = ApprovalManager(
            ui_adapter=None,
            criteria=ApprovalCriteria(
                auto_approve_tests=True,
                auto_approve_docs=False,
                max_lines_auto=100,
            ),
        )

        should_auto = approval_manager.should_auto_approve(diff_test)
        assert should_auto is True

        # Step 3: 자동 승인 세션
        session = ApprovalSession(
            session_id="test-session-3",
            file_diffs=[diff_test],
        )

        # 자동 승인 (UI 없이)
        session.add_decision(
            ApprovalDecision(
                file_path="tests/test_utils.py",
                action="approve",
                reason="Auto-approved: test file",
            )
        )

        approved = session.get_approved_file_diffs()
        assert len(approved) == 1

        # Step 4: 커밋
        test_file.write_text(new_test)

        committer = PartialCommitter(repo_path=str(temp_git_repo))
        result = await committer.apply_partial(
            approved_file_diffs=approved,
            commit_message="Test: update test_utils (auto-approved)",
            branch_name=None,
            create_shadow=False,
        )

        # Then
        assert result.success is True


class TestE2EScenario4:
    """시나리오 4: 거부 후 재시도 → 수정 → 재승인"""

    @pytest.mark.asyncio
    async def test_reject_then_retry_workflow(self, temp_git_repo):
        """
        Given: 변경사항 제출
        When: 거부 → 수정 → 재제출 → 승인
        Then: 최종 승인된 버전이 커밋됨
        """
        # Given: 첫 번째 시도
        utils_file = temp_git_repo / "src" / "utils.py"
        old_content = utils_file.read_text()
        wrong_content = old_content.replace("discount_rate", "disc_rate")  # 잘못된 변경

        diff_manager = DiffManager(context_lines=3)

        # Step 1: 첫 번째 Diff (거부될 예정)
        diff_wrong = diff_manager.generate_diff("src/utils.py", old_content, wrong_content)

        session_1 = ApprovalSession(
            session_id="test-session-4-attempt1",
            file_diffs=[diff_wrong],
        )

        # 거부
        session_1.add_decision(
            ApprovalDecision(
                file_path="src/utils.py",
                action="reject",
                reason="Variable name too short",
            )
        )

        approved_1 = session_1.get_approved_file_diffs()
        assert len(approved_1) == 0  # 거부됨

        # Step 2: 수정 후 재시도
        correct_content = old_content.replace("discount_rate", "discount_percentage")

        diff_correct = diff_manager.generate_diff("src/utils.py", old_content, correct_content)

        session_2 = ApprovalSession(
            session_id="test-session-4-attempt2",
            file_diffs=[diff_correct],
        )

        # 승인
        session_2.add_decision(
            ApprovalDecision(
                file_path="src/utils.py",
                action="approve",
            )
        )

        approved_2 = session_2.get_approved_file_diffs()
        assert len(approved_2) == 1

        # Step 3: 커밋
        utils_file.write_text(correct_content)

        committer = PartialCommitter(repo_path=str(temp_git_repo))
        result = await committer.apply_partial(
            approved_file_diffs=approved_2,
            commit_message="Fix: use discount_percentage (v2 after review)",
            branch_name=None,
            create_shadow=False,
        )

        # Then
        assert result.success is True
        assert "discount_percentage" in utils_file.read_text()


class TestE2EScenario5:
    """시나리오 5: 대용량 변경 → Shadow branch → Rollback"""

    @pytest.mark.asyncio
    async def test_large_change_with_rollback(self, temp_git_repo):
        """
        Given: 대규모 변경사항
        When: Shadow branch 생성 → 문제 발견 → Rollback
        Then: 원래 상태로 복구됨
        """
        # Given: 여러 파일 대규모 변경
        utils_file = temp_git_repo / "src" / "utils.py"
        models_file = temp_git_repo / "src" / "models.py"

        old_utils = utils_file.read_text()
        old_models = models_file.read_text()

        # 대규모 변경
        new_utils = "# Refactored version\n" + old_utils + "\n\ndef new_function():\n    pass\n"
        new_models = old_models + "\n\nclass Admin(User):\n    pass\n"

        diff_manager = DiffManager(context_lines=3)

        diff_utils = diff_manager.generate_diff("src/utils.py", old_utils, new_utils)
        diff_models = diff_manager.generate_diff("src/models.py", old_models, new_models)

        # Step 1: 승인
        session = ApprovalSession(
            session_id="test-session-5",
            file_diffs=[diff_utils, diff_models],
        )

        session.add_decision(ApprovalDecision(file_path="src/utils.py", action="approve"))
        session.add_decision(ApprovalDecision(file_path="src/models.py", action="approve"))

        approved = session.get_approved_file_diffs()

        # Step 2: 실제 파일 변경
        utils_file.write_text(new_utils)
        models_file.write_text(new_models)

        # Step 3: Shadow branch 생성하여 커밋
        committer = PartialCommitter(repo_path=str(temp_git_repo))
        result = await committer.apply_partial(
            approved_file_diffs=approved,
            commit_message="Major refactor: add new features",
            branch_name=None,
            create_shadow=True,  # Shadow branch 생성
        )

        assert result.success is True
        assert result.rollback_sha is not None

        rollback_sha = result.rollback_sha

        # 변경 확인
        assert "new_function" in utils_file.read_text()
        assert "Admin" in models_file.read_text()

        # Step 4: 문제 발견 → Rollback
        rollback_result = await committer.rollback_to_shadow(rollback_sha)

        # Then
        assert rollback_result.success is True

        # 원래 내용으로 복구됨
        assert utils_file.read_text() == old_utils
        assert models_file.read_text() == old_models
