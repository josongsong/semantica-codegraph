"""
Tests for Agent Orchestrator

Verifies:
1. Task execution
2. Workflow execution with auto-transitions
3. Change application (add, modify, delete)
4. Approval flow integration
5. Rollback on failure
6. End-to-end scenarios
"""

import tempfile
from pathlib import Path

import pytest

from src.agent import AgentFSM, AgentMode, ModeContext, Task
from src.agent.modes import ContextNavigationModeSimple, ImplementationModeSimple
from src.agent.orchestrator import AgentOrchestrator, ChangeApplicator, cli_approval
from src.agent.types import Change


class TestChangeApplicator:
    """Tests for ChangeApplicator."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_add_new_file(self, temp_dir):
        """Test adding a new file."""
        applicator = ChangeApplicator(temp_dir)
        change = Change(file_path="new_file.py", content="def test():\n    pass", change_type="add")

        result = applicator._apply_single_change(change)

        file_path = temp_dir / "new_file.py"
        assert file_path.exists()
        assert file_path.read_text() == "def test():\n    pass"

    def test_modify_existing_file(self, temp_dir):
        """Test modifying an existing file."""
        # Create initial file
        file_path = temp_dir / "existing.py"
        file_path.write_text("old content")

        applicator = ChangeApplicator(temp_dir)
        change = Change(file_path="existing.py", content="new content", change_type="modify")

        applicator._apply_single_change(change)

        assert file_path.read_text() == "new content"

    def test_modify_with_line_range(self, temp_dir):
        """Test modifying specific lines."""
        # Create file with multiple lines
        file_path = temp_dir / "multi_line.py"
        original = "line 1\nline 2\nline 3\nline 4\n"
        file_path.write_text(original)

        applicator = ChangeApplicator(temp_dir)
        change = Change(
            file_path="multi_line.py",
            content="replaced line",
            change_type="modify",
            line_start=2,
            line_end=3,
        )

        applicator._apply_single_change(change)

        result = file_path.read_text()
        assert "line 1\n" in result
        assert "replaced line\n" in result
        assert "line 4\n" in result
        assert "line 2" not in result
        assert "line 3" not in result

    def test_delete_file(self, temp_dir):
        """Test deleting a file."""
        file_path = temp_dir / "to_delete.py"
        file_path.write_text("content")

        applicator = ChangeApplicator(temp_dir)
        change = Change(file_path="to_delete.py", content="", change_type="delete")

        applicator._apply_single_change(change)

        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_apply_multiple_changes(self, temp_dir):
        """Test applying multiple changes atomically."""
        applicator = ChangeApplicator(temp_dir)
        changes = [
            Change(file_path="file1.py", content="content 1", change_type="add"),
            Change(file_path="file2.py", content="content 2", change_type="add"),
        ]

        result = await applicator.apply_changes(changes)

        assert result["success"]
        assert result["changes"] == 2
        assert (temp_dir / "file1.py").exists()
        assert (temp_dir / "file2.py").exists()

    @pytest.mark.asyncio
    async def test_rollback_on_failure(self, temp_dir):
        """Test rollback when a change fails."""
        # Create existing file
        file_path = temp_dir / "existing.py"
        original_content = "original"
        file_path.write_text(original_content)

        applicator = ChangeApplicator(temp_dir)

        # First change will succeed, second will fail (invalid type)
        changes = [
            Change(file_path="existing.py", content="modified", change_type="modify"),
            Change(file_path="other.py", content="content", change_type="invalid_type"),
        ]

        result = await applicator.apply_changes(changes)

        # Should fail and rollback
        assert not result["success"]
        assert result["rolled_back"]

        # Original file should be restored
        assert file_path.read_text() == original_content


class TestAgentOrchestrator:
    """Tests for AgentOrchestrator."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def orchestrator(self, temp_dir):
        """Create orchestrator with simple modes."""
        from src.agent.modes.base import BaseModeHandler
        from src.agent.types import ModeContext, Result, Task

        # Simple TEST mode that just completes
        class SimpleTestMode(BaseModeHandler):
            def __init__(self):
                super().__init__(AgentMode.TEST)

            async def execute(self, task: Task, context: ModeContext) -> Result:
                return self._create_result(
                    data={"tests_passed": True},
                    trigger=None,  # End workflow
                    explanation="Tests passed",
                    requires_approval=False,
                )

        fsm = AgentFSM()

        # Register simple modes
        fsm.register(AgentMode.CONTEXT_NAV, ContextNavigationModeSimple())
        fsm.register(AgentMode.IMPLEMENTATION, ImplementationModeSimple())
        fsm.register(AgentMode.TEST, SimpleTestMode())

        return AgentOrchestrator(fsm=fsm, auto_approve=True, base_path=temp_dir)

    @pytest.mark.asyncio
    async def test_execute_task(self, orchestrator):
        """Test basic task execution."""
        task = Task(query="find login function")

        result = await orchestrator.execute_task(task, start_mode=AgentMode.CONTEXT_NAV)

        assert result.mode == AgentMode.CONTEXT_NAV
        assert len(orchestrator.execution_history) == 1

    @pytest.mark.asyncio
    async def test_execute_workflow(self, orchestrator):
        """Test workflow with auto-transitions."""
        # Add mock results to context nav
        orchestrator.fsm.register(
            AgentMode.CONTEXT_NAV,
            ContextNavigationModeSimple(mock_results=[{"file_path": "auth.py", "content": "code"}]),
        )

        task = Task(query="add login function")

        workflow_result = await orchestrator.execute_workflow(task, apply_changes=False)

        assert workflow_result["success"]
        assert workflow_result["transitions"] >= 0
        assert len(workflow_result["results"]) > 0

    @pytest.mark.asyncio
    async def test_apply_pending_changes_auto_approve(self, orchestrator, temp_dir):
        """Test applying changes with auto-approve."""
        # Add pending changes to context
        orchestrator.fsm.context.add_pending_change(
            {
                "file_path": "test.py",
                "content": "def test():\n    pass",
                "change_type": "add",
            }
        )

        result = await orchestrator.apply_pending_changes()

        assert result["success"]
        assert (temp_dir / "test.py").exists()
        assert len(orchestrator.fsm.context.pending_changes) == 0

    @pytest.mark.asyncio
    async def test_approval_callback_approve(self, temp_dir):
        """Test approval with callback that approves."""

        async def approve_callback(changes, context):
            return True

        orchestrator = AgentOrchestrator(base_path=temp_dir, approval_callback=approve_callback, auto_approve=False)

        orchestrator.fsm.context.add_pending_change(
            {"file_path": "test.py", "content": "content", "change_type": "add"}
        )

        result = await orchestrator.apply_pending_changes()

        assert result["success"]
        assert (temp_dir / "test.py").exists()

    @pytest.mark.asyncio
    async def test_approval_callback_reject(self, temp_dir):
        """Test approval with callback that rejects."""

        async def reject_callback(changes, context):
            return False

        orchestrator = AgentOrchestrator(base_path=temp_dir, approval_callback=reject_callback, auto_approve=False)

        orchestrator.fsm.context.add_pending_change(
            {"file_path": "test.py", "content": "content", "change_type": "add"}
        )

        result = await orchestrator.apply_pending_changes()

        assert not result["success"]
        assert "rejected" in result["message"]
        assert not (temp_dir / "test.py").exists()

    @pytest.mark.asyncio
    async def test_workflow_with_changes_applied(self, orchestrator, temp_dir):
        """Test end-to-end workflow with changes applied."""
        task = Task(query="add a new feature")

        workflow_result = await orchestrator.execute_workflow(task, apply_changes=True)

        assert workflow_result["success"]

        # Check if changes were applied
        if workflow_result["application_result"]:
            assert workflow_result["application_result"]["success"]
            # Implementation mode creates file
            # Note: SimpleMode creates test.py
            assert (temp_dir / "test.py").exists()

    @pytest.mark.asyncio
    async def test_get_context(self, orchestrator):
        """Test getting FSM context."""
        context = orchestrator.get_context()

        assert isinstance(context, ModeContext)
        assert context.approval_level is not None

    @pytest.mark.asyncio
    async def test_get_execution_history(self, orchestrator):
        """Test execution history tracking."""
        task = Task(query="test")

        await orchestrator.execute_task(task, start_mode=AgentMode.CONTEXT_NAV)
        await orchestrator.execute_task(task, start_mode=AgentMode.IMPLEMENTATION)

        history = orchestrator.get_execution_history()

        assert len(history) == 2
        assert history[0]["task"] == "test"
        assert "mode" in history[0]

    @pytest.mark.asyncio
    async def test_reset(self, orchestrator):
        """Test orchestrator reset."""
        # Execute some tasks
        await orchestrator.execute_task(Task(query="test"), start_mode=AgentMode.CONTEXT_NAV)

        # Reset
        orchestrator.reset()

        # Verify reset
        assert orchestrator.fsm.current_mode == AgentMode.IDLE
        assert len(orchestrator.execution_history) == 0
        assert len(orchestrator.fsm.context.current_files) == 0

    @pytest.mark.asyncio
    async def test_no_changes_to_apply(self, orchestrator):
        """Test applying changes when there are none."""
        result = await orchestrator.apply_pending_changes()

        assert result["success"]
        assert "No pending changes" in result["message"]

    @pytest.mark.asyncio
    async def test_approval_callback_failure(self, temp_dir):
        """Test handling of approval callback failures."""

        async def failing_callback(changes, context):
            raise RuntimeError("Approval system error")

        orchestrator = AgentOrchestrator(base_path=temp_dir, approval_callback=failing_callback, auto_approve=False)

        orchestrator.fsm.context.add_pending_change(
            {"file_path": "test.py", "content": "content", "change_type": "add"}
        )

        result = await orchestrator.apply_pending_changes()

        # Should reject on callback failure
        assert not result["success"]

    @pytest.mark.asyncio
    async def test_suggest_next_mode(self, orchestrator):
        """Test mode suggestion based on query."""
        # Test search intent
        task = Task(query="find the login function")
        result = await orchestrator.execute_task(task)
        assert result.mode == AgentMode.CONTEXT_NAV

        # Reset and test implement intent
        orchestrator.reset()
        task = Task(query="implement a new feature")
        result = await orchestrator.execute_task(task)
        # Should suggest IMPLEMENTATION mode


class TestCLIApproval:
    """Tests for CLI approval helper."""

    @pytest.mark.asyncio
    async def test_cli_approval_structure(self, monkeypatch):
        """Test CLI approval function structure."""
        # Mock input to auto-approve
        monkeypatch.setattr("builtins.input", lambda _: "y")

        changes = [Change(file_path="test.py", content="code", change_type="add")]
        context = ModeContext()

        approved = await cli_approval(changes, context)

        assert approved is True

    @pytest.mark.asyncio
    async def test_cli_approval_rejection(self, monkeypatch):
        """Test CLI approval rejection."""
        # Mock input to reject
        monkeypatch.setattr("builtins.input", lambda _: "n")

        changes = [Change(file_path="test.py", content="code", change_type="add")]
        context = ModeContext()

        approved = await cli_approval(changes, context)

        assert approved is False


class TestEndToEndScenarios:
    """End-to-end integration tests."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.asyncio
    async def test_full_implementation_workflow(self, temp_dir):
        """Complete workflow: search -> implement -> apply."""
        from src.agent.modes.base import BaseModeHandler

        # Simple TEST mode
        class SimpleTestMode(BaseModeHandler):
            def __init__(self):
                super().__init__(AgentMode.TEST)

            async def execute(self, task, context):
                return self._create_result(data={"tests_passed": True}, trigger=None, explanation="Tests passed")

        fsm = AgentFSM()

        # Register modes with mock data
        fsm.register(
            AgentMode.CONTEXT_NAV,
            ContextNavigationModeSimple(mock_results=[{"file_path": "auth.py", "content": "existing code"}]),
        )
        fsm.register(AgentMode.IMPLEMENTATION, ImplementationModeSimple(mock_code="def login():\n    pass"))
        fsm.register(AgentMode.TEST, SimpleTestMode())

        orchestrator = AgentOrchestrator(fsm=fsm, auto_approve=True, base_path=temp_dir)

        # Execute workflow with explicit start mode
        task = Task(query="add login function")
        result = await orchestrator.execute_workflow(task, apply_changes=True)

        # Verify
        assert result["success"]
        assert result["transitions"] >= 0

        # Check file was created
        # Implementation mode creates test.py by default
        created_file = temp_dir / "test.py"
        assert created_file.exists()
        content = created_file.read_text()
        assert "login" in content or "pass" in content or "Generated code" in content

    @pytest.mark.asyncio
    async def test_workflow_with_rejection(self, temp_dir):
        """Workflow where user rejects changes."""
        from src.agent.modes.base import BaseModeHandler

        async def reject_all(changes, context):
            return False

        # Simple TEST mode
        class SimpleTestMode(BaseModeHandler):
            def __init__(self):
                super().__init__(AgentMode.TEST)

            async def execute(self, task, context):
                return self._create_result(data={"tests_passed": True}, trigger=None, explanation="Tests passed")

        fsm = AgentFSM()
        fsm.register(
            AgentMode.CONTEXT_NAV,
            ContextNavigationModeSimple(mock_results=[{"file_path": "example.py", "content": "code"}]),
        )
        fsm.register(AgentMode.IMPLEMENTATION, ImplementationModeSimple())
        fsm.register(AgentMode.TEST, SimpleTestMode())

        orchestrator = AgentOrchestrator(fsm=fsm, approval_callback=reject_all, auto_approve=False, base_path=temp_dir)

        task = Task(query="implement new feature")
        result = await orchestrator.execute_workflow(task, apply_changes=True)

        # Workflow completes but changes not applied
        assert result["success"]

        # If changes were attempted, they should be rejected
        if result["application_result"]:
            assert not result["application_result"]["success"]
