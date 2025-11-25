"""Tests for Implementation Mode."""

import pytest

from src.agent.modes.implementation import ImplementationMode, ImplementationModeSimple
from src.agent.types import AgentMode, ApprovalLevel, ModeContext, Task


class TestImplementationModeSimple:
    """Tests for simplified implementation mode."""

    @pytest.mark.asyncio
    async def test_simple_implementation(self):
        """Test basic code generation with mock."""
        mode = ImplementationModeSimple(mock_code="def test():\n    return 42")
        context = ModeContext()

        task = Task(query="Create a test function")
        result = await mode.execute(task, context)

        # Verify result
        assert result.mode == AgentMode.IMPLEMENTATION
        assert result.trigger == "code_complete"
        assert result.data["total_changes"] == 1
        assert "def test" in result.data["changes"][0]["content"]

        # Verify context updated
        assert len(context.pending_changes) == 1
        assert context.pending_changes[0]["file_path"] == "test.py"

    @pytest.mark.asyncio
    async def test_lifecycle_methods(self):
        """Test enter/exit lifecycle."""
        mode = ImplementationModeSimple()
        context = ModeContext(current_task="Test task")

        # Enter
        await mode.enter(context)

        # Execute
        task = Task(query="Test")
        result = await mode.execute(task, context)
        assert result.trigger == "code_complete"

        # Exit
        await mode.exit(context)


class TestImplementationMode:
    """Tests for full implementation mode."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM client."""

        class MockLLM:
            async def complete(self, messages, **kwargs):
                # Return simple mock code
                return {"content": "```python\ndef example():\n    return True\n```"}

        return MockLLM()

    @pytest.mark.asyncio
    async def test_code_generation_with_llm(self, mock_llm):
        """Test code generation with mocked LLM."""
        mode = ImplementationMode(llm_client=mock_llm)
        context = ModeContext()
        context.add_file("src/test.py")

        task = Task(query="Add a validation function")
        result = await mode.execute(task, context)

        # Verify result
        assert result.mode == AgentMode.IMPLEMENTATION
        assert result.trigger == "code_complete"
        assert result.data["total_changes"] == 1
        assert "def example" in result.data["generated_code"]

    @pytest.mark.asyncio
    async def test_human_approval_required(self, mock_llm):
        """Test that approval is required for MEDIUM approval level."""
        approved_changes = []

        async def approval_callback(changes, context):
            approved_changes.extend(changes)
            return True

        mode = ImplementationMode(llm_client=mock_llm, approval_callback=approval_callback)
        context = ModeContext(approval_level=ApprovalLevel.MEDIUM)

        task = Task(query="Add function")
        result = await mode.execute(task, context)

        # Verify approval was requested
        assert len(approved_changes) == 1
        assert result.trigger == "code_complete"

    @pytest.mark.asyncio
    async def test_approval_rejection(self, mock_llm):
        """Test rejection flow."""

        async def reject_callback(changes, context):
            return False

        mode = ImplementationMode(llm_client=mock_llm, approval_callback=reject_callback)
        context = ModeContext(approval_level=ApprovalLevel.MEDIUM)

        task = Task(query="Add function")
        result = await mode.execute(task, context)

        # Verify rejection
        assert result.trigger == "rejected"
        assert result.data["status"] == "rejected"
        assert len(context.pending_changes) == 0  # No changes added

    @pytest.mark.asyncio
    async def test_low_approval_level_skips_approval(self, mock_llm):
        """Test that LOW approval level auto-approves."""
        approval_called = False

        async def approval_callback(changes, context):
            nonlocal approval_called
            approval_called = True
            return True

        mode = ImplementationMode(llm_client=mock_llm, approval_callback=approval_callback)
        context = ModeContext(approval_level=ApprovalLevel.LOW)

        task = Task(query="Add function")
        result = await mode.execute(task, context)

        # Verify approval was NOT called
        assert not approval_called
        assert result.trigger == "code_complete"

    @pytest.mark.asyncio
    async def test_llm_failure_handling(self):
        """Test error handling when LLM fails."""

        class FailingLLM:
            async def complete(self, messages, **kwargs):
                raise RuntimeError("LLM API error")

        mode = ImplementationMode(llm_client=FailingLLM())
        context = ModeContext()

        task = Task(query="Add function")
        result = await mode.execute(task, context)

        # Verify error handling
        assert result.trigger == "error_occurred"
        assert "error" in result.data
        assert "Failed to generate code" in result.explanation

    @pytest.mark.asyncio
    async def test_context_code_extraction(self, mock_llm):
        """Test that related code is extracted from context."""
        mode = ImplementationMode(llm_client=mock_llm)
        context = ModeContext()
        context.add_file("src/models.py")
        context.add_file("src/utils.py")
        context.add_symbol("User")
        context.add_symbol("validate_email")

        task = Task(query="Add method")
        result = await mode.execute(task, context)

        # Should complete successfully
        assert result.trigger == "code_complete"

    def test_code_extraction_markdown(self):
        """Test extracting code from markdown blocks."""
        mode = ImplementationMode()

        # Python markdown block
        response = "```python\ndef foo():\n    pass\n```"
        extracted = mode._extract_code(response)
        assert "def foo" in extracted
        assert "```" not in extracted

        # Generic markdown block
        response = "```\ndef bar():\n    pass\n```"
        extracted = mode._extract_code(response)
        assert "def bar" in extracted

        # Plain code (no markdown)
        response = "def baz():\n    pass"
        extracted = mode._extract_code(response)
        assert "def baz" in extracted

    def test_change_creation(self, mock_llm):
        """Test Change object creation."""
        mode = ImplementationMode(llm_client=mock_llm)
        context = ModeContext()
        context.add_file("test.py")

        generated_code = "def new_function():\n    return 42"
        changes = mode._create_changes(generated_code, context)

        assert len(changes) == 1
        assert changes[0].file_path == "test.py"
        assert changes[0].content == generated_code
        assert changes[0].change_type == "modify"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
