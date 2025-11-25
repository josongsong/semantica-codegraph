"""
Agent System - Quick Start Guide

Complete examples for using the Agent System:
1. Basic workflow execution
2. Custom approval logic
3. Step-by-step task execution
4. Production integration

Run: python examples/agent_quick_start.py
"""

import asyncio


# Mock LLM for demonstration (replace with real LLM in production)
class MockLLM:
    """Mock LLM client for demonstration."""

    async def complete(self, messages, temperature=0.2, max_tokens=2000):
        """Mock LLM completion."""
        # In production, this would call OpenAI/Anthropic/etc.
        return {
            "content": """```python
def login(username: str, password: str) -> bool:
    '''
    Authenticate user with username and password.

    Args:
        username: User's username
        password: User's password

    Returns:
        True if authentication successful, False otherwise
    '''
    # Implementation would check database
    if not username or not password:
        return False

    # Hash password and verify
    user = get_user(username)
    if user and verify_password(password, user.password_hash):
        return True

    return False
```"""
        }


async def example_1_basic_workflow():
    """
    Example 1: Basic Workflow Execution

    Demonstrates:
    - Setting up FSM with modes
    - Creating orchestrator
    - Executing complete workflow
    - Auto-transitions and change application
    """
    print("\n" + "=" * 70)
    print("EXAMPLE 1: Basic Workflow Execution")
    print("=" * 70)

    from src.agent import AgentFSM, AgentMode, AgentOrchestrator, Task
    from src.agent.modes import (
        ContextNavigationModeSimple,
        ImplementationModeSimple,
    )

    # Helper: Simple TEST mode
    from src.agent.modes.base import BaseModeHandler

    class SimpleTestMode(BaseModeHandler):
        def __init__(self):
            super().__init__(AgentMode.TEST)

        async def execute(self, task, context):
            return self._create_result(
                data={"tests_passed": True}, trigger=None, explanation="Tests passed"
            )

    # 1. Create FSM and register modes
    fsm = AgentFSM()
    fsm.register(
        AgentMode.CONTEXT_NAV,
        ContextNavigationModeSimple(
            mock_results=[{"file_path": "auth.py", "content": "existing auth code"}]
        ),
    )
    fsm.register(
        AgentMode.IMPLEMENTATION,
        ImplementationModeSimple(mock_code="def login():\n    return True"),
    )
    fsm.register(AgentMode.TEST, SimpleTestMode())

    # 2. Create orchestrator with auto-approve (for demo)
    orchestrator = AgentOrchestrator(
        fsm=fsm, auto_approve=True, base_path="/tmp/agent_demo"
    )

    # 3. Execute workflow
    print("\n📝 Task: Implement login function")
    task = Task(query="implement login function")
    result = await orchestrator.execute_workflow(task, apply_changes=True)

    # 4. Check results
    print("\n✅ Workflow complete:")
    print(f"   Transitions: {result['transitions']}")
    print(f"   Final mode: {result['final_mode']}")
    print(f"   Changes: {result['pending_changes']}")

    if result["application_result"]:
        print(f"   Applied: {result['application_result']['changes']} file(s)")

    # 5. Show execution history
    history = orchestrator.get_execution_history()
    print("\n📊 Execution History:")
    for i, step in enumerate(history, 1):
        print(f"   {i}. {step['mode']}: {step['task'][:40]}...")


async def example_2_custom_approval():
    """
    Example 2: Custom Approval Logic

    Demonstrates:
    - Custom approval callback
    - Approval levels
    - Conditional approval
    """
    print("\n" + "=" * 70)
    print("EXAMPLE 2: Custom Approval Logic")
    print("=" * 70)

    from src.agent import (
        AgentFSM,
        AgentMode,
        AgentOrchestrator,
        ApprovalLevel,
        Change,
        ModeContext,
        Task,
    )
    from src.agent.modes import (
        ContextNavigationModeSimple,
        ImplementationModeSimple,
    )

    # Custom approval function
    async def smart_approval(changes: list[Change], context: ModeContext) -> bool:
        """
        Smart approval logic:
        - Auto-approve LOW risk
        - Auto-approve <= 2 new files
        - Require approval for modifications
        """
        print(f"\n🔍 Reviewing {len(changes)} change(s)...")

        # Auto-approve low-risk operations
        if context.approval_level == ApprovalLevel.LOW:
            print("✅ Auto-approved (LOW risk)")
            return True

        # Auto-approve small additions
        if all(c.change_type == "add" for c in changes) and len(changes) <= 2:
            print("✅ Auto-approved (simple additions)")
            return True

        # Require approval for modifications
        print("⚠️  Requires manual approval (modifications)")
        print("\nChanges:")
        for i, change in enumerate(changes, 1):
            print(f"   {i}. {change.change_type}: {change.file_path}")

        # In production, prompt user here
        # For demo, auto-approve
        print("✅ Approved by user")
        return True

    # Setup
    fsm = AgentFSM()
    fsm.register(AgentMode.CONTEXT_NAV, ContextNavigationModeSimple(mock_results=[]))
    fsm.register(AgentMode.IMPLEMENTATION, ImplementationModeSimple())

    orchestrator = AgentOrchestrator(
        fsm=fsm,
        approval_callback=smart_approval,
        auto_approve=False,  # Use callback
        base_path="/tmp/agent_demo",
    )

    # Execute with HIGH approval level
    orchestrator.fsm.context.approval_level = ApprovalLevel.HIGH

    print("\n📝 Task: Add authentication module")
    task = Task(query="add authentication module")
    result = await orchestrator.execute_workflow(task, apply_changes=True)

    print(f"\n✅ Workflow: {result['success']}")


async def example_3_step_by_step():
    """
    Example 3: Step-by-Step Task Execution

    Demonstrates:
    - Manual mode control
    - Task decomposition
    - Context inspection
    - Manual change application
    """
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Step-by-Step Execution")
    print("=" * 70)

    from src.agent import AgentFSM, AgentMode, AgentOrchestrator, Task
    from src.agent.modes import (
        ContextNavigationModeSimple,
        ImplementationModeSimple,
    )

    # Setup
    fsm = AgentFSM()
    fsm.register(
        AgentMode.CONTEXT_NAV,
        ContextNavigationModeSimple(
            mock_results=[
                {"file_path": "auth/handlers.py", "symbol": "AuthHandler"},
                {"file_path": "auth/models.py", "symbol": "User"},
            ]
        ),
    )
    fsm.register(AgentMode.IMPLEMENTATION, ImplementationModeSimple())

    orchestrator = AgentOrchestrator(fsm=fsm, auto_approve=True, base_path="/tmp/agent_demo")

    # Step 1: Find relevant code
    print("\n🔍 Step 1: Finding relevant code...")
    task1 = Task(query="find authentication code")
    result1 = await orchestrator.execute_task(task1, start_mode=AgentMode.CONTEXT_NAV)

    context = orchestrator.get_context()
    print(f"   Found files: {context.current_files}")
    print(f"   Found symbols: {context.current_symbols}")

    # Step 2: Implement changes
    print("\n🛠️  Step 2: Implementing changes...")
    task2 = Task(query="add logout function")
    result2 = await orchestrator.execute_task(task2, start_mode=AgentMode.IMPLEMENTATION)

    print(f"   Trigger: {result2.trigger}")
    print(f"   Pending changes: {len(context.pending_changes)}")

    # Step 3: Review changes
    print("\n📋 Step 3: Reviewing changes...")
    for i, change in enumerate(context.pending_changes, 1):
        print(f"   {i}. {change['change_type']}: {change['file_path']}")

    # Step 4: Apply changes
    print("\n✅ Step 4: Applying changes...")
    if len(context.pending_changes) > 0:
        result = await orchestrator.apply_pending_changes()
        print(f"   Applied: {result['success']}")


async def example_4_production_setup():
    """
    Example 4: Production Setup

    Demonstrates:
    - Real LLM integration
    - Symbol index integration
    - CLI approval
    - Error handling
    """
    print("\n" + "=" * 70)
    print("EXAMPLE 4: Production Setup (Conceptual)")
    print("=" * 70)

    # This example shows the structure for production use
    # Some components (OpenAI, KuzuSymbolIndex) need actual configuration

    print("\n📚 Production setup requires:")
    print("   1. Real LLM client (OpenAI, Anthropic, etc.)")
    print("   2. Symbol index (KuzuSymbolIndex)")
    print("   3. File system access")
    print("   4. Approval interface (CLI or Web)")

    print("\n💡 Example code:")
    print(
        """
    from src.agent import AgentFSM, AgentMode, AgentOrchestrator, cli_approval
    from src.agent.modes import ContextNavigationMode, ImplementationMode
    from src.infra.llm.openai import OpenAIAdapter
    from src.index.symbol.adapter_kuzu import KuzuSymbolIndex

    # 1. Setup LLM
    llm = OpenAIAdapter(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4")

    # 2. Setup symbol index
    symbol_index = KuzuSymbolIndex(db_path="./kuzu_db")

    # 3. Create modes
    context_nav = ContextNavigationMode(symbol_index=symbol_index)
    implementation = ImplementationMode(
        llm_client=llm,
        approval_callback=None  # Will be set on orchestrator
    )

    # 4. Register modes
    fsm = AgentFSM()
    fsm.register(AgentMode.CONTEXT_NAV, context_nav)
    fsm.register(AgentMode.IMPLEMENTATION, implementation)

    # 5. Create orchestrator with CLI approval
    orchestrator = AgentOrchestrator(
        fsm=fsm,
        approval_callback=cli_approval,
        base_path="./workspace",
        auto_approve=False
    )

    # 6. Execute workflow
    task = Task(query="implement user registration")
    result = await orchestrator.execute_workflow(
        task=task,
        max_transitions=10,
        apply_changes=True
    )

    if result["success"]:
        print(f"✅ Changes applied: {result['application_result']}")
    else:
        print(f"❌ Workflow failed")
    """
    )


async def example_5_error_handling():
    """
    Example 5: Error Handling

    Demonstrates:
    - LLM failure handling
    - Approval rejection
    - Rollback on failure
    """
    print("\n" + "=" * 70)
    print("EXAMPLE 5: Error Handling")
    print("=" * 70)

    from src.agent import AgentFSM, AgentMode, AgentOrchestrator, Change, ModeContext, Task
    from src.agent.modes import ImplementationMode

    # Failing LLM
    class FailingLLM:
        async def complete(self, messages, **kwargs):
            raise RuntimeError("API rate limit exceeded")

    # Rejecting approval
    async def rejecting_approval(changes: list[Change], context: ModeContext) -> bool:
        print("❌ User rejected changes")
        return False

    # Setup
    fsm = AgentFSM()
    impl_mode = ImplementationMode(
        llm_client=FailingLLM(), approval_callback=rejecting_approval
    )
    fsm.register(AgentMode.IMPLEMENTATION, impl_mode)

    orchestrator = AgentOrchestrator(fsm=fsm, base_path="/tmp/agent_demo")

    # Test 1: LLM failure
    print("\n🧪 Test 1: LLM Failure Handling")
    try:
        await orchestrator.execute_task(
            Task(query="implement feature"), start_mode=AgentMode.IMPLEMENTATION
        )
        print("   LLM error handled gracefully")
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")

    # Test 2: Approval rejection
    print("\n🧪 Test 2: Approval Rejection")
    orchestrator.fsm.context.approval_level = "high"
    result = await orchestrator.execute_task(
        Task(query="add feature"), start_mode=AgentMode.IMPLEMENTATION
    )

    if result.trigger == "rejected":
        print("   ✅ Rejection handled (would transition to CONTEXT_NAV)")


async def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print(" Agent System - Quick Start Examples")
    print("=" * 70)

    await example_1_basic_workflow()
    await example_2_custom_approval()
    await example_3_step_by_step()
    await example_4_production_setup()
    await example_5_error_handling()

    print("\n" + "=" * 70)
    print("✅ All examples complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("   1. Review code in examples/agent_quick_start.py")
    print("   2. Read _AGENT_DAY4_COMPLETE.md for detailed docs")
    print("   3. Implement your own modes and workflows")
    print("   4. Integrate with your LLM and infrastructure")


if __name__ == "__main__":
    asyncio.run(main())
