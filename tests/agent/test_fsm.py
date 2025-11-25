"""
Tests for Agent FSM (Finite State Machine)

Verifies:
1. Basic FSM operations (transition, execute, reset)
2. Mode handler registration
3. Auto-transitions based on triggers
4. Context management across transitions
5. Transition history tracking
"""

import pytest

from src.agent import AgentFSM, AgentMode, ModeContext, Result, Task


class SimpleModeHandler:
    """Simple mode handler for testing."""

    def __init__(self, mode: AgentMode, return_trigger: str | None = None):
        self.mode = mode
        self.return_trigger = return_trigger
        self.enter_called = False
        self.exit_called = False
        self.execute_count = 0

    async def enter(self, context: ModeContext) -> None:
        self.enter_called = True

    async def execute(self, task: Task, context: ModeContext) -> Result:
        self.execute_count += 1
        return Result(
            mode=self.mode,
            data={"executed": True, "count": self.execute_count},
            trigger=self.return_trigger,
            explanation=f"Executed {self.mode.value}",
        )

    async def exit(self, context: ModeContext) -> None:
        self.exit_called = True


@pytest.mark.asyncio
async def test_fsm_initialization():
    """Test FSM starts in IDLE mode."""
    fsm = AgentFSM()

    assert fsm.current_mode == AgentMode.IDLE
    assert len(fsm.handlers) == 0
    assert len(fsm.transition_history) == 0


@pytest.mark.asyncio
async def test_mode_handler_registration():
    """Test registering mode handlers."""
    fsm = AgentFSM()

    handler = SimpleModeHandler(AgentMode.CONTEXT_NAV)
    fsm.register(AgentMode.CONTEXT_NAV, handler)

    assert AgentMode.CONTEXT_NAV in fsm.handlers
    assert fsm.handlers[AgentMode.CONTEXT_NAV] is handler


@pytest.mark.asyncio
async def test_mode_transition():
    """Test basic mode transition."""
    fsm = AgentFSM()

    idle_handler = SimpleModeHandler(AgentMode.IDLE)
    context_nav_handler = SimpleModeHandler(AgentMode.CONTEXT_NAV)

    fsm.register(AgentMode.IDLE, idle_handler)
    fsm.register(AgentMode.CONTEXT_NAV, context_nav_handler)

    # Transition from IDLE to CONTEXT_NAV
    await fsm.transition_to(AgentMode.CONTEXT_NAV, trigger="user_request")

    # Verify transition
    assert fsm.current_mode == AgentMode.CONTEXT_NAV
    assert idle_handler.exit_called
    assert context_nav_handler.enter_called

    # Verify transition history
    history = fsm.get_transition_history()
    assert len(history) == 1
    assert history[0] == ("idle", "context_navigation", "user_request")


@pytest.mark.asyncio
async def test_execute_mode():
    """Test executing a mode."""
    fsm = AgentFSM()

    handler = SimpleModeHandler(AgentMode.CONTEXT_NAV)
    fsm.register(AgentMode.CONTEXT_NAV, handler)

    # Transition to mode
    await fsm.transition_to(AgentMode.CONTEXT_NAV)

    # Execute task
    task = Task(query="find login function")
    result = await fsm.execute(task)

    # Verify execution
    assert handler.execute_count == 1
    assert result.mode == AgentMode.CONTEXT_NAV
    assert result.data["executed"] is True


@pytest.mark.asyncio
async def test_auto_transition_on_trigger():
    """Test automatic mode transition based on result trigger."""
    fsm = AgentFSM()

    # Context nav returns "target_found" trigger
    context_nav_handler = SimpleModeHandler(AgentMode.CONTEXT_NAV, return_trigger="target_found")
    impl_handler = SimpleModeHandler(AgentMode.IMPLEMENTATION)

    fsm.register(AgentMode.CONTEXT_NAV, context_nav_handler)
    fsm.register(AgentMode.IMPLEMENTATION, impl_handler)

    # Start in CONTEXT_NAV
    await fsm.transition_to(AgentMode.CONTEXT_NAV)

    # Execute (should auto-transition to IMPLEMENTATION)
    task = Task(query="implement feature")
    result = await fsm.execute(task)

    # Verify auto-transition happened
    assert fsm.current_mode == AgentMode.IMPLEMENTATION
    assert result.trigger == "target_found"
    assert impl_handler.enter_called


@pytest.mark.asyncio
async def test_context_persistence_across_transitions():
    """Test that context persists across mode transitions."""
    fsm = AgentFSM()

    handler1 = SimpleModeHandler(AgentMode.CONTEXT_NAV)
    handler2 = SimpleModeHandler(AgentMode.IMPLEMENTATION)

    fsm.register(AgentMode.CONTEXT_NAV, handler1)
    fsm.register(AgentMode.IMPLEMENTATION, handler2)

    # Add data to context
    fsm.context.add_file("test.py")
    fsm.context.add_symbol("TestClass")
    fsm.context.current_task = "test task"

    # Transition
    await fsm.transition_to(AgentMode.CONTEXT_NAV)
    await fsm.transition_to(AgentMode.IMPLEMENTATION)

    # Verify context persisted
    assert "test.py" in fsm.context.current_files
    assert "TestClass" in fsm.context.current_symbols
    assert fsm.context.current_task == "test task"

    # Verify mode history
    assert AgentMode.CONTEXT_NAV in fsm.context.mode_history
    assert AgentMode.IMPLEMENTATION in fsm.context.mode_history


@pytest.mark.asyncio
async def test_fsm_reset():
    """Test FSM reset functionality."""
    fsm = AgentFSM()

    handler = SimpleModeHandler(AgentMode.CONTEXT_NAV)
    fsm.register(AgentMode.CONTEXT_NAV, handler)

    # Transition and add context
    await fsm.transition_to(AgentMode.CONTEXT_NAV)
    fsm.context.add_file("test.py")

    # Reset
    fsm.reset()

    # Verify reset
    assert fsm.current_mode == AgentMode.IDLE
    assert len(fsm.context.current_files) == 0
    assert len(fsm.transition_history) == 0


@pytest.mark.asyncio
async def test_mode_transition_chain():
    """Test multiple mode transitions forming a chain."""
    fsm = AgentFSM()

    # Setup handlers with auto-transition triggers
    context_nav = SimpleModeHandler(AgentMode.CONTEXT_NAV, return_trigger="target_found")
    impl = SimpleModeHandler(AgentMode.IMPLEMENTATION, return_trigger="code_complete")
    test = SimpleModeHandler(AgentMode.TEST)

    fsm.register(AgentMode.CONTEXT_NAV, context_nav)
    fsm.register(AgentMode.IMPLEMENTATION, impl)
    fsm.register(AgentMode.TEST, test)

    # Start chain
    await fsm.transition_to(AgentMode.CONTEXT_NAV)

    # Execute (should trigger: CONTEXT_NAV -> IMPLEMENTATION)
    await fsm.execute(Task(query="find code"))

    # Execute again (should trigger: IMPLEMENTATION -> TEST)
    await fsm.execute(Task(query="implement"))

    # Verify final state
    assert fsm.current_mode == AgentMode.TEST
    assert len(fsm.transition_history) == 3  # initial + 2 auto-transitions


@pytest.mark.asyncio
async def test_execute_without_handler_raises_error():
    """Test that executing a mode without a handler raises ValueError."""
    fsm = AgentFSM()

    # Transition to CONTEXT_NAV without registering handler
    fsm.current_mode = AgentMode.CONTEXT_NAV

    # Should raise ValueError
    with pytest.raises(ValueError, match="No handler registered"):
        await fsm.execute(Task(query="test"))


@pytest.mark.asyncio
async def test_same_mode_transition_skipped():
    """Test that transitioning to the same mode is skipped."""
    fsm = AgentFSM()

    handler = SimpleModeHandler(AgentMode.CONTEXT_NAV)
    fsm.register(AgentMode.CONTEXT_NAV, handler)

    # Transition to CONTEXT_NAV
    await fsm.transition_to(AgentMode.CONTEXT_NAV)
    handler.enter_called = False  # Reset flag

    # Transition to same mode again
    await fsm.transition_to(AgentMode.CONTEXT_NAV)

    # Verify no re-entry
    assert not handler.enter_called
    assert fsm.current_mode == AgentMode.CONTEXT_NAV


def test_mode_context_helpers():
    """Test ModeContext helper methods."""
    context = ModeContext()

    # Test add_file (no duplicates)
    context.add_file("test1.py")
    context.add_file("test1.py")  # Duplicate
    context.add_file("test2.py")

    assert len(context.current_files) == 2
    assert "test1.py" in context.current_files
    assert "test2.py" in context.current_files

    # Test add_symbol (no duplicates)
    context.add_symbol("Symbol1")
    context.add_symbol("Symbol1")  # Duplicate
    context.add_symbol("Symbol2")

    assert len(context.current_symbols) == 2

    # Test add_action
    context.add_action({"type": "search", "query": "test"})
    assert len(context.action_history) == 1

    # Test add_pending_change and clear
    context.add_pending_change({"file": "test.py", "action": "modify"})
    assert len(context.pending_changes) == 1

    context.clear_pending_changes()
    assert len(context.pending_changes) == 0


def test_mode_context_to_dict():
    """Test ModeContext serialization."""
    context = ModeContext()
    context.add_file("test.py")
    context.add_symbol("TestClass")
    context.mode_history.append(AgentMode.CONTEXT_NAV)

    data = context.to_dict()

    assert data["current_files"] == ["test.py"]
    assert data["current_symbols"] == ["TestClass"]
    assert data["mode_history"] == ["context_navigation"]
    assert isinstance(data, dict)
