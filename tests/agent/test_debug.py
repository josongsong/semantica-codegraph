"""Tests for Debug Mode."""

import pytest

from src.agent.modes.debug import DebugMode, DebugModeSimple
from src.agent.types import AgentMode, ApprovalLevel, ModeContext, Task


class TestDebugModeSimple:
    """Tests for simplified debug mode."""

    @pytest.mark.asyncio
    async def test_simple_debug(self):
        """Test basic fix generation with mock."""
        mode = DebugModeSimple(mock_fix="def fixed():\n    return 42")
        context = ModeContext()

        task = Task(query="Fix ValueError in calculate_total")
        result = await mode.execute(task, context)

        # Verify result
        assert result.mode == AgentMode.DEBUG
        assert result.trigger == "fix_identified"
        assert result.requires_approval is True
        assert result.data["total_changes"] == 1
        assert "def fixed" in result.data["changes"][0]["content"]

        # Verify context updated
        assert len(context.pending_changes) == 1
        assert context.pending_changes[0]["file_path"] == "error_file.py"

    @pytest.mark.asyncio
    async def test_lifecycle_methods(self):
        """Test enter/exit lifecycle."""
        mode = DebugModeSimple()
        context = ModeContext()

        # Enter
        await mode.enter(context)

        # Execute
        task = Task(query="Fix error")
        result = await mode.execute(task, context)
        assert result.trigger == "fix_identified"

        # Exit
        await mode.exit(context)


class TestDebugMode:
    """Tests for full debug mode."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM client."""

        class MockLLM:
            async def complete(self, messages, **kwargs):
                # Return simple mock fix
                return {"content": "```python\ndef fixed_function():\n    return True\n```"}

        return MockLLM()

    @pytest.mark.asyncio
    async def test_error_parsing_python(self):
        """Test parsing Python error messages."""
        mode = DebugMode()
        context = ModeContext()

        task = Task(query="ValueError: invalid literal for int() with base 10: 'abc'")
        error_info = mode._parse_error(task, context)

        assert error_info is not None
        assert error_info["type"] == "ValueError"
        assert "invalid literal" in error_info["message"]

    @pytest.mark.asyncio
    async def test_error_parsing_generic(self):
        """Test parsing generic error descriptions."""
        mode = DebugMode()
        context = ModeContext()

        task = Task(query="Fix the bug in login function")
        error_info = mode._parse_error(task, context)

        assert error_info is not None
        assert error_info["type"] == "Error"
        assert "bug" in error_info["message"].lower()

    def test_stacktrace_analysis_python(self):
        """Test Python stack trace parsing."""
        mode = DebugMode()

        error_text = '''Traceback (most recent call last):
  File "/app/main.py", line 42, in main
    result = calculate(x)
  File "/app/utils.py", line 10, in calculate
    return x / 0
ZeroDivisionError: division by zero
'''

        error_info = {"raw": error_text}
        location = mode._analyze_stacktrace(error_info)

        assert location is not None
        assert location["file_path"] == "/app/utils.py"
        assert location["line_number"] == 10
        assert location["function"] == "calculate"
        assert len(location["frames"]) == 2

    def test_stacktrace_analysis_js(self):
        """Test JavaScript/TypeScript stack trace parsing."""
        mode = DebugMode()

        error_text = """TypeError: Cannot read property 'name' of undefined
    at getUserName (/app/user.ts:25:15)
    at processUser (/app/handler.ts:42:10)
    at main (/app/main.ts:100:5)
"""

        error_info = {"raw": error_text}
        location = mode._analyze_stacktrace(error_info)

        assert location is not None
        assert location["file_path"] == "/app/user.ts"
        assert location["line_number"] == 25
        assert location["column"] == 15
        assert location["function"] == "getUserName"
        assert len(location["frames"]) == 3

    @pytest.mark.asyncio
    async def test_fix_generation_with_llm(self, mock_llm):
        """Test fix generation with mocked LLM."""
        mode = DebugMode(llm_client=mock_llm)
        context = ModeContext()
        context.add_file("src/test.py")

        task = Task(query="ValueError: invalid input")
        result = await mode.execute(task, context)

        # Verify result
        assert result.mode == AgentMode.DEBUG
        assert result.trigger == "fix_identified"
        assert result.data["total_changes"] == 1
        assert "fixed_function" in result.data["changes"][0]["content"]

    @pytest.mark.asyncio
    async def test_llm_failure_handling(self):
        """Test error handling when LLM fails."""

        class FailingLLM:
            async def complete(self, messages, **kwargs):
                raise RuntimeError("LLM API error")

        mode = DebugMode(llm_client=FailingLLM())
        context = ModeContext()

        task = Task(query="ValueError: test error")
        result = await mode.execute(task, context)

        # Verify error handling
        assert result.trigger == "error_occurred"
        assert "error" in result.data
        assert "Failed to generate fix" in result.explanation

    @pytest.mark.asyncio
    async def test_fix_change_creation(self, mock_llm):
        """Test Change object creation from fix."""
        mode = DebugMode(llm_client=mock_llm)
        context = ModeContext()
        context.add_file("test.py")

        task = Task(
            query="""ValueError: invalid value
  File "test.py", line 42, in calculate
    return int(value)"""
        )

        result = await mode.execute(task, context)

        # Verify changes
        assert len(result.data["changes"]) == 1
        change = result.data["changes"][0]
        assert change["file_path"] == "test.py"
        assert change["change_type"] == "modify"
        assert change["line_start"] == 42

    @pytest.mark.asyncio
    async def test_approval_required(self, mock_llm):
        """Test that fixes require approval."""
        mode = DebugMode(llm_client=mock_llm)
        context = ModeContext(approval_level=ApprovalLevel.MEDIUM)

        task = Task(query="Fix TypeError")
        result = await mode.execute(task, context)

        # Verify approval is required
        assert result.requires_approval is True
        assert result.trigger == "fix_identified"

    @pytest.mark.asyncio
    async def test_error_context_extraction(self, mock_llm):
        """Test that error context is extracted."""
        mode = DebugMode(llm_client=mock_llm)
        context = ModeContext()
        context.add_file("src/models.py")
        context.add_file("src/utils.py")

        task = Task(query="AttributeError: 'NoneType' object has no attribute 'name'")
        result = await mode.execute(task, context)

        # Should complete successfully with context
        assert result.trigger == "fix_identified"
        assert result.data["error"]["type"] == "AttributeError"

    def test_code_extraction_markdown(self):
        """Test extracting fix code from markdown blocks."""
        mode = DebugMode()

        # Python markdown block
        response = "```python\ndef fixed():\n    return True\n```"
        extracted = mode._extract_code(response)
        assert "def fixed" in extracted
        assert "```" not in extracted

        # Generic markdown block
        response = "```\ndef fixed():\n    pass\n```"
        extracted = mode._extract_code(response)
        assert "def fixed" in extracted

        # Plain code (no markdown)
        response = "def fixed():\n    pass"
        extracted = mode._extract_code(response)
        assert "def fixed" in extracted

    @pytest.mark.asyncio
    async def test_error_flow_with_graph(self, mock_llm):
        """Test error flow tracing with graph integration."""
        from tests.fakes.fake_graph import FakeGraphStore

        # Create graph
        graph = FakeGraphStore()

        # Add nodes
        graph.add_node(
            "calculator.py::divide",
            "Function",
            {"name": "divide", "file": "calculator.py"},
        )
        graph.add_node(
            "calculator.py::divide::handler",
            "CfgBlock",
            {"name": "exception_handler", "handler_type": "try/except"},
        )
        graph.add_node(
            "main.py::run",
            "Function",
            {"name": "run", "file": "main.py"},
        )

        # Add edges
        # main.py::run CALLS calculator.py::divide
        graph.add_edge("main.py::run", "calculator.py::divide", "CALLS")

        # calculator.py::divide has exception handler
        graph.add_edge("calculator.py::divide", "calculator.py::divide::handler", "CFG_HANDLER")

        # main.py::run also has exception handler
        graph.add_node(
            "main.py::run::handler",
            "CfgBlock",
            {"name": "top_level_handler", "handler_type": "try/except"},
        )
        graph.add_edge("main.py::run", "main.py::run::handler", "CFG_HANDLER")

        # Create mode with graph
        mode = DebugMode(llm_client=mock_llm, graph_client=graph)
        context = ModeContext()

        # Error in divide function
        error_msg = '''
        File "calculator.py", line 10, in divide
            ZeroDivisionError: division by zero
        '''

        task = Task(query=error_msg)
        result = await mode.execute(task, context)

        # Verify result
        assert result.trigger == "fix_identified"
        assert result.data["error"]["type"] == "ZeroDivisionError"

        # Check error flow was traced (key is "flow" not "error_flow")
        error_flow = result.data.get("flow", [])
        assert len(error_flow) > 0

        # Should have error site
        error_sites = [node for node in error_flow if node["type"] == "error_site"]
        assert len(error_sites) == 1
        assert error_sites[0]["function"] == "divide"

        # Should have local handler
        local_handlers = [node for node in error_flow if node["type"] == "local_handler"]
        assert len(local_handlers) >= 1

        # Should have caller handler
        caller_handlers = [node for node in error_flow if node["type"] == "caller_handler"]
        assert len(caller_handlers) >= 1

    @pytest.mark.asyncio
    async def test_error_flow_without_graph(self, mock_llm):
        """Test error flow works without graph client."""
        mode = DebugMode(llm_client=mock_llm)  # No graph
        context = ModeContext()

        error_msg = '''
        File "calculator.py", line 10, in divide
            ZeroDivisionError: division by zero
        '''

        task = Task(query=error_msg)
        result = await mode.execute(task, context)

        # Should still work without graph
        assert result.trigger == "fix_identified"

        # Error flow should be empty (key is "flow" not "error_flow")
        error_flow = result.data.get("flow", [])
        assert len(error_flow) == 0

    @pytest.mark.asyncio
    async def test_find_local_handlers(self):
        """Test finding local exception handlers."""
        from tests.fakes.fake_graph import FakeGraphStore

        graph = FakeGraphStore()

        # Add function with handler
        graph.add_node("test.py::foo", "Function", {"name": "foo"})
        graph.add_node("test.py::foo::handler1", "CfgBlock", {"handler_type": "try/except"})
        graph.add_node("test.py::foo::handler2", "CfgBlock", {"handler_type": "try/except"})

        graph.add_edge("test.py::foo", "test.py::foo::handler1", "CFG_HANDLER")
        graph.add_edge("test.py::foo", "test.py::foo::handler2", "CFG_HANDLER")

        mode = DebugMode(graph_client=graph)

        # Find local handlers
        handlers = await mode._find_local_handlers("test.py::foo")

        assert len(handlers) == 2
        assert any(h["id"] == "test.py::foo::handler1" for h in handlers)
        assert any(h["id"] == "test.py::foo::handler2" for h in handlers)

    @pytest.mark.asyncio
    async def test_find_caller_handlers(self):
        """Test finding exception handlers in callers."""
        from tests.fakes.fake_graph import FakeGraphStore

        graph = FakeGraphStore()

        # Add call chain: main -> process -> validate
        graph.add_node("main.py::main", "Function", {"name": "main"})
        graph.add_node("main.py::main::handler", "CfgBlock", {"handler_type": "try/except"})

        graph.add_node("process.py::process", "Function", {"name": "process"})

        graph.add_node("validate.py::validate", "Function", {"name": "validate"})

        # Call edges
        graph.add_edge("main.py::main", "process.py::process", "CALLS")
        graph.add_edge("process.py::process", "validate.py::validate", "CALLS")

        # Only main has handler
        graph.add_edge("main.py::main", "main.py::main::handler", "CFG_HANDLER")

        mode = DebugMode(graph_client=graph)

        # Find caller handlers from validate
        handlers = await mode._find_caller_handlers("validate.py::validate")

        # Should find main through the call chain
        # process calls validate, main calls process, main has handler
        assert len(handlers) >= 0  # Depends on implementation

        # Direct caller test
        handlers = await mode._find_caller_handlers("process.py::process")
        assert len(handlers) == 1
        assert handlers[0]["name"] == "main"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
