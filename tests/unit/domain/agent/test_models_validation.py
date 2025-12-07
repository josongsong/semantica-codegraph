"""
Domain Model 검증 테스트

Week 1 검증:
- AgentTask 비즈니스 로직 동작
- CodeChange 영향도 계산
- WorkflowState 상태 전이 규칙
"""

import pytest

from src.agent.domain.models import (
    AgentTask,
    ChangeType,
    CodeChange,
    WorkflowState,
    WorkflowStep,
)


class TestAgentTask:
    """AgentTask 비즈니스 로직 검증"""

    def test_estimate_complexity_simple(self):
        """단순 작업 복잡도 추정"""
        task = AgentTask(
            task_id="test-1",
            description="Fix typo in README",
            repo_id="test-repo",
            snapshot_id="abc123",
            context_files=["README.md"],
        )

        complexity = task.estimate_complexity()
        assert 1 <= complexity <= 3, "단순 작업은 복잡도 1-3"

    def test_estimate_complexity_complex(self):
        """복잡한 작업 복잡도 추정"""
        task = AgentTask(
            task_id="test-2",
            description="Refactor authentication system across multiple modules with extensive testing and documentation updates",
            repo_id="test-repo",
            snapshot_id="abc123",
            context_files=[f"module_{i}.py" for i in range(15)],
        )

        complexity = task.estimate_complexity()
        assert 8 <= complexity <= 10, "복잡한 작업은 복잡도 8-10"

    def test_requires_clarification_question_mark(self):
        """물음표 포함 시 명확화 필요"""
        task = AgentTask(
            task_id="test-3",
            description="Should we use async or sync?",
            repo_id="test-repo",
            snapshot_id="abc123",
        )

        assert task.requires_clarification() is True

    def test_requires_clarification_too_short(self):
        """설명이 너무 짧으면 명확화 필요"""
        task = AgentTask(
            task_id="test-4",
            description="Fix it",
            repo_id="test-repo",
            snapshot_id="abc123",
        )

        assert task.requires_clarification() is True

    def test_requires_clarification_clear_task(self):
        """명확한 작업은 명확화 불필요"""
        task = AgentTask(
            task_id="test-5",
            description="Add email validation to User model using regex pattern",
            repo_id="test-repo",
            snapshot_id="abc123",
        )

        assert task.requires_clarification() is False

    def test_calculate_priority_urgent(self):
        """긴급 작업 우선순위"""
        task = AgentTask(
            task_id="test-6",
            description="URGENT: Production hotfix for critical bug",
            repo_id="test-repo",
            snapshot_id="abc123",
        )

        priority = task.calculate_priority()
        assert priority >= 8, "긴급 작업은 우선순위 8 이상"

    def test_calculate_priority_bug_fix(self):
        """버그 수정 우선순위"""
        task = AgentTask(
            task_id="test-7",
            description="Fix bug in payment processing",
            repo_id="test-repo",
            snapshot_id="abc123",
        )

        priority = task.calculate_priority()
        assert priority >= 7, "버그 수정은 우선순위 7 이상"


class TestCodeChange:
    """CodeChange 비즈니스 로직 검증"""

    def test_impact_score_delete(self):
        """삭제는 높은 영향도"""
        change = CodeChange(
            file_path="old_module.py",
            change_type=ChangeType.DELETE,
            original_lines=["def old_function():", "    pass"],
        )

        impact = change.calculate_impact_score()
        assert impact >= 0.7, "삭제는 영향도 0.7 이상"

    def test_impact_score_create(self):
        """신규 생성은 낮은 영향도"""
        change = CodeChange(
            file_path="new_module.py",
            change_type=ChangeType.CREATE,
            new_lines=["def new_function():", "    pass"],
        )

        impact = change.calculate_impact_score()
        assert impact <= 0.4, "신규 생성은 영향도 0.4 이하"

    def test_impact_score_minor_modify(self):
        """소규모 수정은 낮은 영향도"""
        original = ["def calculate(a, b):", "    return a + b", "    # TODO: validation"]
        new = ["def calculate(a, b):", "    return a + b", "    # Added validation", "    assert a > 0"]

        change = CodeChange(
            file_path="utils.py",
            change_type=ChangeType.MODIFY,
            original_lines=original,
            new_lines=new,
        )

        impact = change.calculate_impact_score()
        assert impact <= 0.3, "소규모 수정은 영향도 0.3 이하"

    def test_impact_score_major_rewrite(self):
        """대규모 재작성은 높은 영향도"""
        original = ["def old_impl():", "    pass"]
        new = ["def new_impl():", "    # Complete rewrite"] + [f"    line_{i}" for i in range(20)]

        change = CodeChange(
            file_path="core.py",
            change_type=ChangeType.MODIFY,
            original_lines=original,
            new_lines=new,
        )

        impact = change.calculate_impact_score()
        assert impact >= 0.7, "대규모 재작성은 영향도 0.7 이상"

    def test_is_breaking_change_delete_public_api(self):
        """Public API 삭제는 breaking change"""
        change = CodeChange(
            file_path="src/api/__init__.py",
            change_type=ChangeType.DELETE,
            original_lines=["def public_function():", "    pass"],
        )

        assert change.is_breaking_change() is True

    def test_is_breaking_change_signature_change(self):
        """함수 시그니처 변경은 breaking change"""
        change = CodeChange(
            file_path="src/api/interface.py",
            change_type=ChangeType.MODIFY,
            original_lines=["def process(data):"],
            new_lines=["def process(data, extra_param):"],
        )

        assert change.is_breaking_change() is True

    def test_is_not_breaking_change_internal(self):
        """내부 구현 변경은 breaking change 아님"""
        change = CodeChange(
            file_path="src/internal/helper.py",
            change_type=ChangeType.MODIFY,
            original_lines=["def _internal():"],
            new_lines=["def _internal_v2():"],
        )

        assert change.is_breaking_change() is False

    def test_needs_review_breaking_change(self):
        """Breaking change는 리뷰 필요"""
        change = CodeChange(
            file_path="src/api/core.py",
            change_type=ChangeType.DELETE,
            original_lines=["class PublicAPI:"],
        )

        assert change.needs_review() is True

    def test_needs_review_high_impact(self):
        """높은 영향도는 리뷰 필요"""
        change = CodeChange(
            file_path="src/core.py",
            change_type=ChangeType.MODIFY,
            original_lines=["line"] * 10,
            new_lines=["new_line"] * 200,  # 큰 변경
        )

        assert change.needs_review() is True

    def test_get_loc_delta_increase(self):
        """LOC 증가"""
        change = CodeChange(
            file_path="test.py",
            change_type=ChangeType.MODIFY,
            original_lines=["line1", "line2"],
            new_lines=["line1", "line2", "line3", "line4"],
        )

        assert change.get_loc_delta() == 2

    def test_get_loc_delta_decrease(self):
        """LOC 감소"""
        change = CodeChange(
            file_path="test.py",
            change_type=ChangeType.MODIFY,
            original_lines=["line1", "line2", "line3"],
            new_lines=["line1"],
        )

        assert change.get_loc_delta() == -2


class TestWorkflowState:
    """WorkflowState 비즈니스 로직 검증"""

    def test_can_transition_to_test_without_changes(self):
        """코드 변경 없이 test 단계 전이 불가"""
        task = AgentTask(
            task_id="test-8",
            description="Test task",
            repo_id="test-repo",
            snapshot_id="abc123",
        )

        state = WorkflowState(
            task=task,
            current_step=WorkflowStep.GENERATE,
            changes=[],  # 변경 없음
        )

        assert state.can_transition_to(WorkflowStep.TEST) is False

    def test_can_transition_to_test_with_changes(self):
        """코드 변경 있으면 test 단계 전이 가능"""
        task = AgentTask(
            task_id="test-9",
            description="Test task",
            repo_id="test-repo",
            snapshot_id="abc123",
        )

        change = CodeChange(
            file_path="test.py",
            change_type=ChangeType.MODIFY,
            original_lines=["old"],
            new_lines=["new"],
        )

        state = WorkflowState(
            task=task,
            current_step=WorkflowStep.GENERATE,
            changes=[change],
        )

        assert state.can_transition_to(WorkflowStep.TEST) is True

    def test_can_transition_max_iterations(self):
        """Max iteration 초과 시 전이 불가"""
        task = AgentTask(
            task_id="test-10",
            description="Test task",
            repo_id="test-repo",
            snapshot_id="abc123",
        )

        state = WorkflowState(
            task=task,
            current_step=WorkflowStep.GENERATE,
            iteration=5,
            max_iterations=5,
        )

        assert state.can_transition_to(WorkflowStep.TEST) is False

    def test_should_replan_many_errors(self):
        """에러 많으면 재계획"""
        task = AgentTask(
            task_id="test-11",
            description="Test task",
            repo_id="test-repo",
            snapshot_id="abc123",
        )

        state = WorkflowState(
            task=task,
            current_step=WorkflowStep.HEAL,
            errors=["error1", "error2", "error3"],
        )

        assert state.should_replan() is True

    def test_should_exit_early_success(self):
        """테스트 성공 시 early exit"""
        from src.agent.domain.models import ExecutionResult

        task = AgentTask(
            task_id="test-12",
            description="Test task",
            repo_id="test-repo",
            snapshot_id="abc123",
        )

        change = CodeChange(
            file_path="test.py",
            change_type=ChangeType.MODIFY,
            original_lines=["old"],
            new_lines=["new"],
        )

        state = WorkflowState(
            task=task,
            current_step=WorkflowStep.TEST,
            changes=[change],
            test_results=[ExecutionResult(stdout="OK", stderr="", exit_code=0, execution_time_ms=100)],
        )

        assert state.should_exit_early() is True

    def test_get_total_loc_delta(self):
        """전체 LOC 변화량"""
        task = AgentTask(
            task_id="test-13",
            description="Test task",
            repo_id="test-repo",
            snapshot_id="abc123",
        )

        changes = [
            CodeChange(
                file_path="test1.py",
                change_type=ChangeType.MODIFY,
                original_lines=["a", "b"],
                new_lines=["a", "b", "c"],
            ),  # +1
            CodeChange(
                file_path="test2.py",
                change_type=ChangeType.MODIFY,
                original_lines=["x", "y", "z"],
                new_lines=["x"],
            ),  # -2
        ]

        state = WorkflowState(task=task, current_step=WorkflowStep.GENERATE, changes=changes)

        assert state.get_total_loc_delta() == -1

    def test_get_affected_files(self):
        """영향받은 파일 목록"""
        task = AgentTask(
            task_id="test-14",
            description="Test task",
            repo_id="test-repo",
            snapshot_id="abc123",
        )

        changes = [
            CodeChange(file_path="a.py", change_type=ChangeType.MODIFY, new_lines=["new"]),
            CodeChange(file_path="b.py", change_type=ChangeType.MODIFY, new_lines=["new"]),
            CodeChange(file_path="a.py", change_type=ChangeType.MODIFY, new_lines=["new2"]),
        ]

        state = WorkflowState(task=task, current_step=WorkflowStep.GENERATE, changes=changes)

        affected = state.get_affected_files()
        assert affected == {"a.py", "b.py"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
