"""Agent CLI

간단한 명령줄 인터페이스

Usage:
    python -m src.cli.agent "fix bug in payment.py"
    python -m src.cli.agent "add feature for authentication" --repo my-repo
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.agent.adapters.context_adapter import ContextAdapter
from src.agent.orchestrator import AgentOrchestrator, OrchestratorConfig
from src.agent.router.intent_classifier import IntentClassifier
from src.agent.router.router import Router
from src.agent.task_graph.planner import TaskGraphPlanner
from src.agent.workflow.state_machine import WorkflowStateMachine
from src.infra.config.settings import Settings


def setup_orchestrator(use_real_llm: bool = False):
    """Orchestrator 설정"""

    if use_real_llm:
        # 실제 LLM 사용 (Phase 1)
        try:
            from src.infra.llm.litellm_adapter import LiteLLMAdapter

            settings = Settings()
            llm = LiteLLMAdapter(
                model=settings.llm.default_model or "gpt-4o-mini",
                api_base=settings.llm.local_llm_base_url if settings.llm.local_llm_base_url else None,
            )
            print(f"📡 Using real LLM: {llm.model}")
        except Exception as e:
            print(f"⚠️  Real LLM failed: {e}")
            print("   Falling back to Mock LLM")
            use_real_llm = False

    if not use_real_llm:
        # Mock LLM (데모용)
        class MockLLM:
            async def complete(self, prompt: str, **kwargs) -> str:
                prompt_lower = prompt.lower()
                if "authentication" in prompt_lower or ("add" in prompt_lower and "feature" in prompt_lower):
                    return '{"intent": "add_feature", "reasoning": "Feature request", "confidence": 0.90}'
                elif "refactor" in prompt_lower:
                    return '{"intent": "refactor", "reasoning": "Refactor request", "confidence": 0.88}'
                elif "bug" in prompt_lower or "fix" in prompt_lower:
                    return '{"intent": "fix_bug", "reasoning": "Bug fix", "confidence": 0.95}'
                return '{"intent": "unknown", "reasoning": "Unclear", "confidence": 0.3}'

        llm = MockLLM()
        print("🤖 Using Mock LLM (for demo)")

    # Create components
    classifier = IntentClassifier(llm)
    router = Router(classifier)
    planner = TaskGraphPlanner()
    workflow = WorkflowStateMachine(max_iterations=3)
    context_adapter = ContextAdapter()

    # Create orchestrator
    config = OrchestratorConfig(
        max_retries=3,
        enable_fallback=True,
    )

    orchestrator = AgentOrchestrator(
        router=router,
        task_planner=planner,
        workflow=workflow,
        context_adapter=context_adapter,
        config=config,
    )

    return orchestrator


async def execute_request(
    request: str,
    repo_id: str = "default",
    use_real_llm: bool = False,
    verbose: bool = False,
):
    """요청 실행"""

    print()
    print("=" * 70)
    print("🤖 Semantica Agent CLI")
    print("=" * 70)
    print()

    # Setup
    orchestrator = setup_orchestrator(use_real_llm)

    # Display request
    print(f"📥 Request: {request}")
    print(f"📂 Repo:    {repo_id}")
    print()

    # Execute
    print("⏳ Processing...")
    print()

    result = await orchestrator.execute(user_request=request, context={"repo_id": repo_id})

    # Display results
    print("=" * 70)
    print("📤 Results")
    print("=" * 70)
    print()
    print(f"  Intent:       {result.intent.value}")
    print(f"  Confidence:   {result.confidence:.2f}")
    print(f"  Status:       {result.status.value}")
    print(f"  Success:      {'✅ Yes' if result.is_success() else '❌ No'}")
    print()
    print(f"  Tasks:        {len(result.tasks_completed)} completed")
    for task in result.tasks_completed:
        print(f"    - {task}")
    print()
    print(f"  Execution:    {result.execution_time_ms:.0f}ms")
    print()

    if verbose and result.metadata:
        print("  Metadata:")
        for key, value in result.metadata.items():
            print(f"    {key}: {value}")
        print()

    if result.result:
        print("  Result:")
        result_str = str(result.result)
        if len(result_str) > 500:
            print(f"    {result_str[:500]}...")
            print(f"    (... {len(result_str) - 500} more characters)")
        else:
            print(f"    {result_str}")
        print()

    if result.error:
        print(f"  ❌ Error: {result.error}")
        print()

    print("=" * 70)
    print()


def main():
    """CLI 메인"""
    parser = argparse.ArgumentParser(
        description="Semantica Agent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.cli.agent "fix bug in payment.py"
  python -m src.cli.agent "add authentication feature" --repo my-app
  python -m src.cli.agent "refactor code" --real-llm
        """,
    )

    parser.add_argument("request", help="User request (e.g., 'fix bug in payment.py')")

    parser.add_argument("--repo", default="default", help="Repository ID (default: 'default')")

    parser.add_argument("--real-llm", action="store_true", help="Use real LLM instead of Mock (requires .env config)")

    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output (show metadata)")

    args = parser.parse_args()

    try:
        asyncio.run(
            execute_request(
                request=args.request,
                repo_id=args.repo,
                use_real_llm=args.real_llm,
                verbose=args.verbose,
            )
        )
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
