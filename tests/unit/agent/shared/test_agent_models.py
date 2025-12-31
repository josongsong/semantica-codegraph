"""
Agent Shared Models Tests

Test Coverage:
- Enums: ChangeType, WorkflowStepType, ExecutionStatus
- Models: AgentTask with validation
- Business logic: complexity estimation, priority
"""

from datetime import datetime

import pytest

from apps.orchestrator.orchestrator.shared.models.agent_models import (
    AgentTask,
    ChangeType,
    ExecutionStatus,
    WorkflowStepType,
)


class TestChangeType:
    """ChangeType enum tests"""

    def test_all_types_defined(self):
        """All change types exist"""
        assert ChangeType.CREATE.value == "create"
        assert ChangeType.MODIFY.value == "modify"
        assert ChangeType.DELETE.value == "delete"

    def test_enum_count(self):
        """Expected number of change types"""
        assert len(ChangeType) == 3


class TestWorkflowStepType:
    """WorkflowStepType enum tests"""

    def test_all_steps_defined(self):
        """All workflow steps exist"""
        assert WorkflowStepType.ANALYZE.value == "analyze"
        assert WorkflowStepType.PLAN.value == "plan"
        assert WorkflowStepType.GENERATE.value == "generate"
        assert WorkflowStepType.CRITIC.value == "critic"
        assert WorkflowStepType.TEST.value == "test"
        assert WorkflowStepType.HEAL.value == "heal"

    def test_enum_count(self):
        """Expected number of workflow steps"""
        assert len(WorkflowStepType) == 6


class TestExecutionStatus:
    """ExecutionStatus enum tests"""

    def test_all_statuses_defined(self):
        """All execution statuses exist"""
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.RUNNING.value == "running"
        assert ExecutionStatus.SUCCESS.value == "success"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.TIMEOUT.value == "timeout"


class TestAgentTask:
    """AgentTask model tests"""

    def test_create_valid_task(self):
        """Create valid task"""
        task = AgentTask(
            task_id="task_123",
            description="Fix the bug",
            repo_id="repo_abc",
            snapshot_id="snap_001",
        )
        assert task.task_id == "task_123"
        assert task.description == "Fix the bug"
        assert isinstance(task.created_at, datetime)

    def test_task_with_context_files(self):
        """Task with context files"""
        task = AgentTask(
            task_id="task_123",
            description="Refactor",
            repo_id="repo_abc",
            snapshot_id="snap_001",
            context_files=["src/main.py", "src/utils.py"],
        )
        assert len(task.context_files) == 2

    def test_empty_task_id_raises(self):
        """Empty task_id raises ValueError"""
        with pytest.raises(ValueError, match="task_id"):
            AgentTask(
                task_id="",
                description="Test",
                repo_id="repo",
                snapshot_id="snap",
            )

    def test_empty_repo_id_raises(self):
        """Empty repo_id raises ValueError"""
        with pytest.raises(ValueError, match="repo_id"):
            AgentTask(
                task_id="task",
                description="Test",
                repo_id="",
                snapshot_id="snap",
            )

    def test_whitespace_task_id_raises(self):
        """Whitespace-only task_id raises ValueError"""
        with pytest.raises(ValueError, match="task_id"):
            AgentTask(
                task_id="   ",
                description="Test",
                repo_id="repo",
                snapshot_id="snap",
            )


class TestEdgeCases:
    """Edge case tests"""

    def test_very_long_description(self):
        """Very long description"""
        long_desc = "x" * 10000
        task = AgentTask(
            task_id="task",
            description=long_desc,
            repo_id="repo",
            snapshot_id="snap",
        )
        assert len(task.description) == 10000

    def test_unicode_in_description(self):
        """Unicode characters in description"""
        task = AgentTask(
            task_id="task",
            description="버그 수정하기 🐛",
            repo_id="repo",
            snapshot_id="snap",
        )
        assert "🐛" in task.description

    def test_special_characters_in_task_id(self):
        """Special characters in task_id"""
        task = AgentTask(
            task_id="task-123_abc.xyz",
            description="Test",
            repo_id="repo-1",
            snapshot_id="snap-1",
        )
        assert task.task_id == "task-123_abc.xyz"

    def test_empty_metadata(self):
        """Empty metadata dict"""
        task = AgentTask(
            task_id="task",
            description="Test",
            repo_id="repo",
            snapshot_id="snap",
            metadata={},
        )
        assert task.metadata == {}

    def test_nested_metadata(self):
        """Nested metadata structure"""
        task = AgentTask(
            task_id="task",
            description="Test",
            repo_id="repo",
            snapshot_id="snap",
            metadata={
                "config": {"nested": {"value": 42}},
                "tags": ["urgent", "bug"],
            },
        )
        assert task.metadata["config"]["nested"]["value"] == 42
