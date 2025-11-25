"""End-to-End Agent Flow Tests."""

import pytest

from src.agent.fsm import AgentFSM
from src.agent.modes import (
    ContextNavigationModeSimple,
    DebugModeSimple,
    ImplementationModeSimple,
    TestModeSimple,
)
from src.agent.types import AgentMode, Task


@pytest.fixture
def full_fsm():
    """Create FSM with multiple modes registered."""
    fsm = AgentFSM()

    # Register Context Navigation mode
    context_nav = ContextNavigationModeSimple(
        mock_results=[
            {"file_path": "src/user.py", "symbol_name": "User", "content": "class User:..."},
            {"file_path": "src/auth.py", "symbol_name": "validate", "content": "def validate():..."},
        ]
    )
    fsm.register(AgentMode.CONTEXT_NAV, context_nav)

    # Register Implementation mode
    implementation = ImplementationModeSimple(mock_code="def validate_email(email: str) -> bool:\n    return '@' in email")
    fsm.register(AgentMode.IMPLEMENTATION, implementation)

    # Register Debug mode
    debug = DebugModeSimple(mock_fix="def fixed_validate_email(email: str) -> bool:\n    if not email:\n        return False\n    return '@' in email")
    fsm.register(AgentMode.DEBUG, debug)

    # Register Test mode
    test_mode = TestModeSimple(mock_test_code="def test_validate_email():\n    assert validate_email('test@example.com')")
    fsm.register(AgentMode.TEST, test_mode)

    return fsm


@pytest.mark.asyncio
async def test_complete_flow_search_to_implementation(full_fsm):
    """Test complete flow: IDLE -> CONTEXT_NAV -> IMPLEMENTATION."""
    # Step 1: Start from IDLE
    assert full_fsm.current_mode == AgentMode.IDLE

    # Step 2: Transition to CONTEXT_NAV
    await full_fsm.transition("search_intent")
    assert full_fsm.current_mode == AgentMode.CONTEXT_NAV

    # Step 3: Execute search
    search_task = Task(query="find User class")
    search_result = await full_fsm.execute(search_task)

    # Verify search results
    assert search_result.trigger == "target_found"
    assert search_result.data["count"] > 0

    # Step 4: Auto-transition to IMPLEMENTATION
    assert full_fsm.current_mode == AgentMode.IMPLEMENTATION

    # Step 5: Execute implementation
    impl_task = Task(query="add validate_email method")
    impl_result = await full_fsm.execute(impl_task)

    # Verify implementation results
    assert impl_result.trigger == "code_complete"
    assert impl_result.data["total_changes"] == 1

    # Verify context state
    assert len(full_fsm.context.current_files) > 0
    assert len(full_fsm.context.pending_changes) == 1


@pytest.mark.asyncio
async def test_mode_suggestion(full_fsm):
    """Test mode suggestion based on user query."""
    assert full_fsm.suggest_next_mode("find login function") == AgentMode.CONTEXT_NAV
    assert full_fsm.suggest_next_mode("add validate_email method") == AgentMode.IMPLEMENTATION
    assert full_fsm.suggest_next_mode("run tests") == AgentMode.TEST


@pytest.mark.asyncio
async def test_context_preservation_across_modes(full_fsm):
    """Test that context is preserved across mode transitions."""
    # Execute search
    await full_fsm.transition("search_intent")
    search_task = Task(query="find User class")
    await full_fsm.execute(search_task)

    # Verify context has files
    files_after_search = full_fsm.context.current_files.copy()
    assert len(files_after_search) > 0

    # Auto-transition to implementation
    assert full_fsm.current_mode == AgentMode.IMPLEMENTATION

    # Execute implementation
    impl_task = Task(query="add method")
    await full_fsm.execute(impl_task)

    # Verify context still has files from search
    assert full_fsm.context.current_files == files_after_search


@pytest.mark.asyncio
async def test_fsm_reset(full_fsm):
    """Test that FSM reset clears all state."""
    # Execute operations
    await full_fsm.transition("search_intent")
    search_task = Task(query="find class")
    await full_fsm.execute(search_task)

    # Verify state exists
    assert full_fsm.current_mode != AgentMode.IDLE
    assert len(full_fsm.transition_history) > 0

    # Reset
    full_fsm.reset()

    # Verify reset
    assert full_fsm.current_mode == AgentMode.IDLE
    assert len(full_fsm.transition_history) == 0


@pytest.mark.asyncio
async def test_error_recovery_flow(full_fsm):
    """Test error recovery flow: IMPLEMENTATION -> DEBUG -> IMPLEMENTATION."""
    # Step 1: Start in IMPLEMENTATION mode (skip CONTEXT_NAV for this test)
    await full_fsm.transition_to(AgentMode.IMPLEMENTATION)
    assert full_fsm.current_mode == AgentMode.IMPLEMENTATION

    # Step 2: Simulate an error occurring during implementation
    # Manually transition to DEBUG using error_occurred trigger
    await full_fsm.transition("error_occurred")
    assert full_fsm.current_mode == AgentMode.DEBUG

    # Step 3: Execute debug to generate fix
    debug_task = Task(query="ValueError: email validation failed")
    debug_result = await full_fsm.execute(debug_task)

    # Verify debug results
    assert debug_result.trigger == "fix_identified"
    assert debug_result.requires_approval is True
    assert debug_result.data["total_changes"] == 1

    # Step 4: Auto-transition back to IMPLEMENTATION
    assert full_fsm.current_mode == AgentMode.IMPLEMENTATION

    # Verify context has the fix
    assert len(full_fsm.context.pending_changes) == 1
    fix_change = full_fsm.context.pending_changes[0]
    assert "fixed_validate_email" in fix_change["content"]


@pytest.mark.asyncio
async def test_implementation_to_test_flow(full_fsm):
    """Test flow: IMPLEMENTATION -> TEST (code_complete trigger)."""
    # Step 1: Start in IMPLEMENTATION mode
    await full_fsm.transition_to(AgentMode.IMPLEMENTATION)
    assert full_fsm.current_mode == AgentMode.IMPLEMENTATION

    # Step 2: Execute implementation
    impl_task = Task(query="add validate_email method")
    impl_result = await full_fsm.execute(impl_task)

    # Verify implementation completed
    assert impl_result.trigger == "code_complete"

    # Step 3: Auto-transition to TEST mode
    assert full_fsm.current_mode == AgentMode.TEST

    # Step 4: Execute test generation
    test_task = Task(query="generate tests for validate_email")
    test_result = await full_fsm.execute(test_task)

    # Verify test generation
    assert test_result.trigger == "code_complete"
    assert test_result.data["total_changes"] == 1
    assert "test_validate_email" in test_result.data["generated_tests"]

    # Verify context has both implementation and test changes
    assert len(full_fsm.context.pending_changes) == 2


@pytest.mark.asyncio
async def test_test_execution_flow(full_fsm):
    """Test flow: TEST execution with pass/fail."""
    # Step 1: Start in TEST mode
    await full_fsm.transition_to(AgentMode.TEST)
    assert full_fsm.current_mode == AgentMode.TEST

    # Step 2: Execute tests (should pass by default)
    test_task = Task(query="run tests")
    test_result = await full_fsm.execute(test_task)

    # Verify test execution
    assert test_result.trigger == "tests_passed"
    assert test_result.data["test_results"]["all_passed"] is True
    assert test_result.data["test_results"]["total_tests"] == 3

    # Verify context has test results
    assert full_fsm.context.test_results["all_passed"] is True


@pytest.mark.asyncio
async def test_test_failed_flow(full_fsm):
    """Test flow: TEST -> test_failed -> IMPLEMENTATION."""
    from src.agent.types import TestResults

    # Register test mode with failing tests
    test_mode_fail = TestModeSimple(
        mock_results=TestResults(
            all_passed=False,
            total_tests=5,
            passed_tests=3,
            failed_tests=2,
            details={},
        )
    )
    full_fsm.register(AgentMode.TEST, test_mode_fail)

    # Step 1: Start in TEST mode
    await full_fsm.transition_to(AgentMode.TEST)
    assert full_fsm.current_mode == AgentMode.TEST

    # Step 2: Execute tests (will fail)
    test_task = Task(query="run tests")
    test_result = await full_fsm.execute(test_task)

    # Verify test failed
    assert test_result.trigger == "test_failed"
    assert test_result.data["test_results"]["failed_tests"] == 2

    # Step 3: Auto-transition to IMPLEMENTATION
    assert full_fsm.current_mode == AgentMode.IMPLEMENTATION

    # Verify context has test failure info
    assert full_fsm.context.test_results["all_passed"] is False
    assert full_fsm.context.test_results["failed"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
