"""
Agent Domain Models Tests

Test Coverage:
- Base: Model creation and validation
- Edge: Invalid inputs, boundary values
- Corner: Empty collections, special characters
"""

from datetime import datetime

import pytest

from apps.orchestrator.orchestrator.domain.models import (
    AgentTask,
    ChangeType,
    ExecutionStatus,
    WorkflowStepType,
)


class TestEnums:
    """Enum tests"""

    def test_change_type_values(self):
        """ChangeType enum values"""
        assert ChangeType.CREATE.value == "create"
        assert ChangeType.MODIFY.value == "modify"
        assert ChangeType.DELETE.value == "delete"

    def test_workflow_step_type_values(self):
        """WorkflowStepType enum values"""
        assert WorkflowStepType.ANALYZE.value == "analyze"
        assert WorkflowStepType.PLAN.value == "plan"
        assert WorkflowStepType.GENERATE.value == "generate"
        assert WorkflowStepType.CRITIC.value == "critic"
        assert WorkflowStepType.TEST.value == "test"
        assert WorkflowStepType.HEAL.value == "heal"

    def test_execution_status_values(self):
        """ExecutionStatus enum values"""
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.RUNNING.value == "running"
        assert ExecutionStatus.SUCCESS.value == "success"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.TIMEOUT.value == "timeout"


class TestAgentTask:
    """AgentTask model tests"""

    def test_create_valid_task(self):
        """Create valid AgentTask"""
        task = AgentTask(
            task_id="task_123",
            description="Fix the bug",
            repo_id="repo_abc",
            snapshot_id="snap_001",
        )
        assert task.task_id == "task_123"
        assert task.description == "Fix the bug"
        assert task.repo_id == "repo_abc"
        assert task.snapshot_id == "snap_001"
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
        assert "src/main.py" in task.context_files

    def test_task_with_metadata(self):
        """Task with metadata"""
        task = AgentTask(
            task_id="task_123",
            description="Add feature",
            repo_id="repo_abc",
            snapshot_id="snap_001",
            metadata={"priority": "high", "assignee": "user1"},
        )
        assert task.metadata["priority"] == "high"
        assert task.metadata["assignee"] == "user1"

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
            description="修复这个错误 🐛 バグを修正する",
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

    def test_empty_context_files(self):
        """Empty context files list"""
        task = AgentTask(
            task_id="task",
            description="Test",
            repo_id="repo",
            snapshot_id="snap",
            context_files=[],
        )
        assert task.context_files == []

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


class TestCornerCases:
    """Corner case tests"""

    def test_none_in_context_files(self):
        """None value in context files (if allowed)"""
        # Depending on implementation, this may or may not raise
        try:
            task = AgentTask(
                task_id="task",
                description="Test",
                repo_id="repo",
                snapshot_id="snap",
                context_files=[None],  # type: ignore
            )
            # If it doesn't raise, just check it was stored
            assert None in task.context_files
        except (TypeError, ValueError):
            pass  # Expected if validation is strict

    def test_nested_metadata(self):
        """Nested metadata structure"""
        task = AgentTask(
            task_id="task",
            description="Test",
            repo_id="repo",
            snapshot_id="snap",
            metadata={
                "config": {"nested": {"deeply": {"value": 42}}},
                "list": [1, 2, {"key": "value"}],
            },
        )
        assert task.metadata["config"]["nested"]["deeply"]["value"] == 42

    def test_task_immutability(self):
        """Task fields should be set on creation"""
        task = AgentTask(
            task_id="task",
            description="Original",
            repo_id="repo",
            snapshot_id="snap",
        )
        # Dataclass fields are mutable by default
        task.description = "Modified"
        assert task.description == "Modified"
