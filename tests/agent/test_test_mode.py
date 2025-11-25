"""Tests for Test Mode."""

import pytest

from src.agent.modes.test import TestMode, TestModeSimple
from src.agent.types import AgentMode, ModeContext, Task, TestResults


class TestTestModeSimple:
    """Tests for simplified test mode."""

    @pytest.mark.asyncio
    async def test_simple_test_generation(self):
        """Test basic test generation with mock."""
        mode = TestModeSimple(mock_test_code="def test_calc():\n    assert 1 + 1 == 2")
        context = ModeContext()

        task = Task(query="Generate tests for calculate function")
        result = await mode.execute(task, context)

        # Verify result
        assert result.mode == AgentMode.TEST
        assert result.trigger == "code_complete"
        assert result.requires_approval is True
        assert result.data["total_changes"] == 1
        assert "test_calc" in result.data["generated_tests"]

        # Verify context updated
        assert len(context.pending_changes) == 1
        assert context.pending_changes[0]["file_path"] == "tests/test_generated.py"

    @pytest.mark.asyncio
    async def test_simple_test_execution(self):
        """Test basic test execution with mock results."""
        mock_results = TestResults(
            all_passed=True,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
            details={},
        )
        mode = TestModeSimple(mock_results=mock_results)
        context = ModeContext()

        task = Task(query="Run tests")
        result = await mode.execute(task, context)

        # Verify result
        assert result.mode == AgentMode.TEST
        assert result.trigger == "tests_passed"
        assert result.requires_approval is False
        assert result.data["test_results"]["total_tests"] == 10
        assert result.data["test_results"]["all_passed"] is True

        # Verify context updated
        assert context.test_results["all_passed"] is True
        assert context.test_results["total"] == 10

    @pytest.mark.asyncio
    async def test_simple_test_execution_failed(self):
        """Test test execution with failures."""
        mock_results = TestResults(
            all_passed=False,
            total_tests=10,
            passed_tests=8,
            failed_tests=2,
            details={},
        )
        mode = TestModeSimple(mock_results=mock_results)
        context = ModeContext()

        task = Task(query="Run tests")
        result = await mode.execute(task, context)

        # Verify result
        assert result.trigger == "test_failed"
        assert result.data["test_results"]["failed_tests"] == 2

    @pytest.mark.asyncio
    async def test_lifecycle_methods(self):
        """Test enter/exit lifecycle."""
        mode = TestModeSimple()
        context = ModeContext()

        # Enter
        await mode.enter(context)

        # Execute
        task = Task(query="Run tests")
        result = await mode.execute(task, context)
        assert result.trigger == "tests_passed"

        # Exit
        await mode.exit(context)


class TestTestMode:
    """Tests for full test mode."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM client."""

        class MockLLM:
            async def complete(self, messages, **kwargs):
                # Return simple mock test
                return {"content": "```python\ndef test_example():\n    assert True\n```"}

        return MockLLM()

    @pytest.fixture
    def mock_bash(self):
        """Create mock bash executor."""

        class MockBash:
            async def execute(self, command):
                if "pytest" in command:
                    return "5 passed in 1.23s"
                elif "coverage" in command:
                    return ""

        return MockBash()

    def test_mode_determination_generate(self):
        """Test mode determination for test generation."""
        mode = TestMode()

        assert mode._determine_mode(Task(query="generate tests")) == "generate"
        assert mode._determine_mode(Task(query="create test cases")) == "generate"
        assert mode._determine_mode(Task(query="write tests")) == "generate"

    def test_mode_determination_run(self):
        """Test mode determination for test execution."""
        mode = TestMode()

        assert mode._determine_mode(Task(query="run tests")) == "run"
        assert mode._determine_mode(Task(query="execute tests")) == "run"
        assert mode._determine_mode(Task(query="check tests")) == "run"

    @pytest.mark.asyncio
    async def test_test_generation_with_llm(self, mock_llm):
        """Test test generation with mocked LLM."""
        mode = TestMode(llm_client=mock_llm)
        context = ModeContext()
        context.add_file("src/calculator.py")

        task = Task(query="generate tests for calculator")
        result = await mode.execute(task, context)

        # Verify result
        assert result.mode == AgentMode.TEST
        assert result.trigger == "code_complete"
        assert result.data["total_changes"] == 1
        assert "test_example" in result.data["generated_tests"]

    @pytest.mark.asyncio
    async def test_test_execution_with_bash(self, mock_bash):
        """Test test execution with mocked bash."""
        mode = TestMode(bash_executor=mock_bash)
        context = ModeContext()

        task = Task(query="run tests")
        result = await mode.execute(task, context)

        # Verify result
        assert result.mode == AgentMode.TEST
        assert result.trigger == "tests_passed"
        assert result.data["test_results"]["total_tests"] == 5

    def test_pytest_output_parsing_passed(self):
        """Test parsing pytest output for passed tests."""
        mode = TestMode()

        output = "tests/test_example.py::test_one PASSED\n5 passed in 1.23s"
        results = mode._parse_test_results(output)

        assert results.all_passed is True
        assert results.total_tests == 5
        assert results.passed_tests == 5
        assert results.failed_tests == 0

    def test_pytest_output_parsing_failed(self):
        """Test parsing pytest output for failed tests."""
        mode = TestMode()

        output = "tests/test_example.py::test_one PASSED\n3 passed, 2 failed in 1.23s"
        results = mode._parse_test_results(output)

        assert results.all_passed is False
        assert results.total_tests == 5
        assert results.passed_tests == 3
        assert results.failed_tests == 2

    @pytest.mark.asyncio
    async def test_llm_failure_handling(self):
        """Test error handling when LLM fails."""

        class FailingLLM:
            async def complete(self, messages, **kwargs):
                raise RuntimeError("LLM API error")

        mode = TestMode(llm_client=FailingLLM())
        context = ModeContext()

        task = Task(query="generate tests")
        result = await mode.execute(task, context)

        # Verify error handling
        assert result.trigger == "error_occurred"
        assert "error" in result.data
        assert "Failed to generate tests" in result.explanation

    def test_test_count(self):
        """Test counting tests in test code."""
        mode = TestMode()

        test_code = """
def test_one():
    assert True

def test_two():
    assert True

def test_three():
    assert True
"""
        count = mode._count_tests(test_code)
        assert count == 3

    def test_test_file_name_generation(self):
        """Test generating test file names from source files."""
        mode = TestMode()

        assert mode._get_test_file_name("src/calculator.py") == "tests/test_calculator.py"
        assert mode._get_test_file_name("utils/helpers.py") == "tests/test_helpers.py"
        assert mode._get_test_file_name("models.py") == "tests/test_models.py"

    def test_code_extraction_markdown(self):
        """Test extracting test code from markdown blocks."""
        mode = TestMode()

        # Python markdown block
        response = "```python\ndef test_example():\n    assert True\n```"
        extracted = mode._extract_code(response)
        assert "def test_example" in extracted
        assert "```" not in extracted

        # Generic markdown block
        response = "```\ndef test_another():\n    pass\n```"
        extracted = mode._extract_code(response)
        assert "def test_another" in extracted

        # Plain code (no markdown)
        response = "def test_plain():\n    pass"
        extracted = mode._extract_code(response)
        assert "def test_plain" in extracted

    @pytest.mark.asyncio
    async def test_approval_required_for_generation(self, mock_llm):
        """Test that generated tests require approval."""
        mode = TestMode(llm_client=mock_llm)
        context = ModeContext()

        task = Task(query="generate tests")
        result = await mode.execute(task, context)

        # Verify approval is required
        assert result.requires_approval is True
        assert result.trigger == "code_complete"

    @pytest.mark.asyncio
    async def test_no_approval_for_execution(self, mock_bash):
        """Test that test execution does not require approval."""
        mode = TestMode(bash_executor=mock_bash)
        context = ModeContext()

        task = Task(query="run tests")
        result = await mode.execute(task, context)

        # Verify no approval required
        assert result.requires_approval is False

    @pytest.mark.asyncio
    async def test_context_code_extraction(self, mock_llm):
        """Test that code context is extracted for test generation."""
        mode = TestMode(llm_client=mock_llm)
        context = ModeContext()
        context.add_file("src/models.py")
        context.add_file("src/utils.py")

        task = Task(query="generate tests")
        result = await mode.execute(task, context)

        # Should complete successfully with context
        assert result.trigger == "code_complete"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
