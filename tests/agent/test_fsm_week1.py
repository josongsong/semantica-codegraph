"""Week 1 FSM Integration Tests."""

import pytest

from src.agent.fsm import AgentFSM, ModeTransitionRules
from src.agent.modes.context_nav import ContextNavigationModeSimple
from src.agent.types import AgentMode, Task


@pytest.fixture
def fsm():
    """Create FSM with simple context navigation mode."""
    fsm_instance = AgentFSM()

    # Register simple context navigation mode
    context_nav = ContextNavigationModeSimple(
        mock_results=[
            {
                "file_path": "src/auth/login.py",
                "symbol_name": "login_user",
                "content": "def login_user():...",
            },
            {
                "file_path": "src/auth/models.py",
                "symbol_name": "User",
                "content": "class User:...",
            },
        ]
    )
    fsm_instance.register(AgentMode.CONTEXT_NAV, context_nav)

    return fsm_instance


@pytest.mark.asyncio
async def test_scenario1_context_navigation(fsm):
    """Test basic context navigation flow."""
    # IDLE -> CONTEXT_NAV
    task = Task(query="find login function")
    success = await fsm.transition("search_intent", task)

    assert success, "Transition should succeed"
    assert fsm.current_mode == AgentMode.CONTEXT_NAV

    # Execute search
    result = await fsm.execute(task)

    # Verify results
    assert result.mode == AgentMode.CONTEXT_NAV
    assert result.data["count"] > 0
    assert len(fsm.context.current_files) > 0


@pytest.mark.asyncio
async def test_transition_rules():
    """Test transition rules are properly configured."""
    transition = ModeTransitionRules.get_best_transition(
        current_mode=AgentMode.IDLE, trigger="search_intent", context={}
    )

    assert transition is not None
    assert transition.from_mode == AgentMode.IDLE
    assert transition.to_mode == AgentMode.CONTEXT_NAV
    assert transition.priority == 10


@pytest.mark.asyncio
async def test_invalid_transition(fsm):
    """Test that invalid transitions are rejected."""
    success = await fsm.transition("invalid_trigger")
    assert not success
    assert fsm.current_mode == AgentMode.IDLE
