"""
Tests for Context Navigation Mode

Verifies:
1. Basic context navigation execution
2. Symbol search integration
3. Context updates (files, symbols)
4. Trigger generation (target_found)
5. Action history tracking
6. Simple mode for testing
"""

import pytest

from src.agent import AgentMode, ModeContext, Task
from src.agent.modes.context_nav import ContextNavigationMode, ContextNavigationModeSimple


class MockSymbolIndex:
    """Mock symbol index for testing."""

    def __init__(self, mock_hits: list[dict] | None = None):
        self.mock_hits = mock_hits or []
        self.search_called = False
        self.last_query = None

    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 10):
        """Mock search method"""
        self.search_called = True
        self.last_query = query

        # Return mock hits
        return [MockSearchHit(hit) for hit in self.mock_hits]


class MockSearchHit:
    """Mock search hit."""

    def __init__(self, data: dict):
        self.chunk_id = data.get("chunk_id", "chunk:1")
        self.score = data.get("score", 0.9)
        self.file_path = data.get("file_path") or data.get("metadata", {}).get("file_path")
        self.metadata = data.get("metadata", {})


@pytest.mark.asyncio
async def test_context_nav_no_symbol_index():
    """Test context navigation without symbol index."""
    mode = ContextNavigationMode()

    context = ModeContext()
    task = Task(query="find login function")

    result = await mode.execute(task, context)

    # Without symbol index, should return empty results
    assert result.mode == AgentMode.CONTEXT_NAV
    assert result.data["total_count"] == 0
    assert result.trigger is None  # No results, no trigger
    assert "No results found" in result.explanation


@pytest.mark.asyncio
async def test_context_nav_with_symbol_index():
    """Test context navigation with symbol index."""
    # Setup mock symbol index
    mock_hits = [
        {
            "chunk_id": "chunk:login",
            "metadata": {
                "name": "login",
                "kind": "function",
                "fqn": "auth.handlers.login",
                "file_path": "src/auth/handlers.py",
            },
            "content": "def login(username, password): ...",
            "score": 0.95,
        },
        {
            "chunk_id": "chunk:authenticate",
            "metadata": {
                "name": "authenticate",
                "kind": "function",
                "fqn": "auth.service.authenticate",
                "file_path": "src/auth/service.py",
            },
            "content": "def authenticate(user): ...",
            "score": 0.85,
        },
    ]

    symbol_index = MockSymbolIndex(mock_hits)
    mode = ContextNavigationMode(symbol_index=symbol_index)

    context = ModeContext()
    task = Task(query="login")

    result = await mode.execute(task, context)

    # Verify symbol search was called
    assert symbol_index.search_called
    assert symbol_index.last_query == "login"

    # Verify results
    assert result.mode == AgentMode.CONTEXT_NAV
    assert result.data["total_count"] == 2
    assert len(result.data["symbols"]) == 2
    assert "login" in result.data["symbols"]
    assert "authenticate" in result.data["symbols"]

    # Verify trigger
    assert result.trigger == "target_found"
    assert "Found 2 relevant items" in result.explanation

    # Verify context updates
    assert "src/auth/handlers.py" in context.current_files
    assert "src/auth/service.py" in context.current_files
    assert "login" in context.current_symbols
    assert "authenticate" in context.current_symbols

    # Verify action history
    assert len(context.action_history) == 1
    action = context.action_history[0]
    assert action["type"] == "search"
    assert action["query"] == "login"
    assert action["results_count"] == 2


@pytest.mark.asyncio
async def test_context_nav_enter_exit():
    """Test context navigation enter/exit lifecycle."""
    mode = ContextNavigationMode()
    context = ModeContext()
    context.current_task = "test task"

    # Enter
    await mode.enter(context)
    # (Just verify no errors)

    # Exit
    await mode.exit(context)
    # (Just verify no errors)


@pytest.mark.asyncio
async def test_context_nav_symbol_search_error():
    """Test context navigation handles symbol search errors gracefully."""

    class ErrorSymbolIndex:
        async def search(self, *args, **kwargs):
            raise Exception("Symbol index error")

    mode = ContextNavigationMode(symbol_index=ErrorSymbolIndex())
    context = ModeContext()
    task = Task(query="test")

    # Should not raise, should handle gracefully
    result = await mode.execute(task, context)

    assert result.data["total_count"] == 0
    assert result.trigger is None


@pytest.mark.asyncio
async def test_context_nav_simple_mode():
    """Test simplified context navigation mode."""
    mock_results = [
        {"file_path": "test1.py", "content": "test content 1"},
        {"file_path": "test2.py", "content": "test content 2"},
    ]

    mode = ContextNavigationModeSimple(mock_results=mock_results)
    context = ModeContext()
    task = Task(query="test query")

    result = await mode.execute(task, context)

    # Verify results
    assert result.mode == AgentMode.CONTEXT_NAV
    assert result.data["count"] == 2
    assert result.trigger == "target_found"

    # Verify context updates
    assert "test1.py" in context.current_files
    assert "test2.py" in context.current_files
    assert context.current_task == "test query"


@pytest.mark.asyncio
async def test_context_nav_simple_mode_no_results():
    """Test simplified mode with no results."""
    mode = ContextNavigationModeSimple(mock_results=[])
    context = ModeContext()
    task = Task(query="nothing")

    result = await mode.execute(task, context)

    assert result.data["count"] == 0
    assert result.trigger is None  # No results, no trigger


@pytest.mark.asyncio
async def test_context_nav_deduplicates_files():
    """Test that context navigation deduplicates file paths."""
    mock_hits = [
        {
            "chunk_id": "chunk:1",
            "metadata": {
                "name": "func1",
                "file_path": "same_file.py",
            },
            "content": "def func1(): ...",
        },
        {
            "chunk_id": "chunk:2",
            "metadata": {
                "name": "func2",
                "file_path": "same_file.py",  # Same file
            },
            "content": "def func2(): ...",
        },
    ]

    symbol_index = MockSymbolIndex(mock_hits)
    mode = ContextNavigationMode(symbol_index=symbol_index)

    context = ModeContext()
    task = Task(query="test")

    result = await mode.execute(task, context)

    # Should have 2 symbols but only 1 unique file
    assert len(result.data["files"]) == 1
    assert "same_file.py" in result.data["files"]

    # Context should also have only 1 file (deduped by add_file)
    assert len(context.current_files) == 1


@pytest.mark.asyncio
async def test_context_nav_updates_current_task():
    """Test that context navigation updates current task."""
    mode = ContextNavigationModeSimple()
    context = ModeContext()
    context.current_task = "old task"

    task = Task(query="new task")
    await mode.execute(task, context)

    assert context.current_task == "new task"


@pytest.mark.asyncio
async def test_context_nav_result_structure():
    """Test that result has correct structure."""
    mock_results = [{"file_path": "test.py"}]
    mode = ContextNavigationModeSimple(mock_results=mock_results)

    context = ModeContext()
    task = Task(query="test")

    result = await mode.execute(task, context)

    # Verify result structure
    assert hasattr(result, "mode")
    assert hasattr(result, "data")
    assert hasattr(result, "trigger")
    assert hasattr(result, "explanation")
    assert hasattr(result, "requires_approval")

    # Verify data structure
    assert "results" in result.data
    assert "count" in result.data

    # Navigation is read-only, never requires approval
    assert result.requires_approval is False
