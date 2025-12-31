#!/usr/bin/env python3
"""V8 Agent CLI - SOTA

Dynamic Routing + System 1/2 + ToT + Reflection

Usage:
    python -m src.cli.agent_v8 "fix null pointer in payment.py"
    python -m src.cli.agent_v8 "refactor auth logic" --slow
    python -m src.cli.agent_v8 "add validation" --repo my-app
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from codegraph_shared.common.logging_config import setup_cli_logging

# Add project root
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from apps.orchestrator.orchestrator.domain.models import AgentTask  # noqa: E402
from apps.orchestrator.orchestrator.orchestrator import DeepReasoningRequest  # noqa: E402
from codegraph_shared.container import Container  # noqa: E402


async def execute_v8_request(
    description: str,
    repo_path: str = ".",
    force_slow: bool = False,
    verbose: bool = False,
):
    """V8 Agent 실행"""

    logger, log_file = setup_cli_logging(verbose)

    logger.info(f"V8 CLI started: {description}")

    print()
    print("=" * 80)
    print("🚀 Semantica V8 Agent - SOTA")
    print("=" * 80)
    print()
    if verbose:
        print(f"📋 Log file: {log_file}")
        print()

    # Setup
    container = Container()
    orchestrator = container.agent_orchestrator  # V8

    # Display request
    print(f"📥 Task:        {description}")
    print(f"📂 Repository:  {repo_path}")
    print(f"⚡ Mode:        {'System 2 (ToT+Reflection)' if force_slow else 'Auto (Dynamic Router)'}")
    print()

    # Create task
    task = AgentTask(
        task_id=f"cli_{__import__('uuid').uuid4().hex[:8]}",
        repo_id=repo_path,
        snapshot_id=None,
        description=description,
        context_files=[],  # Auto-detect
        metadata={},
    )

    # Create request
    request = DeepReasoningRequest(
        task=task,
        force_system_2=force_slow,
    )

    # Execute
    print("⏳ Processing...")
    print()

    try:
        logger.info("Executing V8 orchestrator")
        response = await orchestrator.execute(request)

        logger.info(
            f"Execution completed: success={response.success}, "
            f"path={response.reasoning_decision.path.value}, "
            f"time={response.execution_time_ms}ms"
        )

        # Display results
        print("=" * 80)
        print("📤 Results")
        print("=" * 80)
        print()
        print(f"  Success:      {'✅ Yes' if response.success else '❌ No'}")
        print(f"  Path:         {response.reasoning_decision.path.value}")
        print(f"  Confidence:   {response.reasoning_decision.confidence:.2%}")
        print(f"  Complexity:   {response.reasoning_decision.complexity_score:.2f}")
        print(f"  Risk:         {response.reasoning_decision.risk_score:.2f}")
        print()
        print(f"  Time:         {response.execution_time_ms:.0f}ms")
        print(f"  Cost:         ${response.cost_usd:.4f}")
        print()

        if response.reflection_verdict:
            print(f"  Reflection:   {response.reflection_verdict.value}")
            print()

        if response.commit_sha:
            print(f"  Commit:       {response.commit_sha[:8]}")
            print()

        if verbose and response.workflow_result:
            print("  Workflow:")
            print(f"    Changes:    {len(response.workflow_result.changes)}")
            print(f"    Errors:     {len(response.workflow_result.errors)}")
            print()

        print("=" * 80)
        if verbose:
            print(f"📋 Full log: {log_file}")
        print()

        return 0 if response.success else 1

    except KeyboardInterrupt:
        logger = logging.getLogger(__name__)
        logger.info("User interrupted")
        print("\n⚠️  Interrupted by user")
        return 130

    except TimeoutError as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Timeout: {e}")
        print("\n⏱️  Timeout: Task took too long")
        print("    Try with --slow for complex tasks")
        return 124

    except ConnectionError as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Connection failed: {e}")
        print("\n🔌 Connection Error: Check LLM/API availability")
        print("    Verify .env configuration")
        return 1

    except ValueError as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Invalid input: {e}")
        print(f"\n❌ Invalid Input: {e}")
        return 22

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error")
        print(f"\n❌ Unexpected Error: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        return 1


def main():
    """CLI 메인"""
    parser = argparse.ArgumentParser(
        description="Semantica V8 Agent - SOTA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.cli.agent_v8 "fix null pointer in payment.py"
  python -m src.cli.agent_v8 "refactor authentication logic" --slow
  python -m src.cli.agent_v8 "add input validation" --repo ./my-app

Router Decision:
  Auto mode: Dynamic Router decides System 1 (fast) or System 2 (slow)
  --slow:    Force System 2 (ToT + Reflection) for complex tasks
        """,
    )

    parser.add_argument(
        "description",
        help="Task description (e.g., 'fix bug in payment.py')",
    )

    parser.add_argument(
        "--repo",
        default=".",
        help="Repository path (default: current directory)",
    )

    parser.add_argument(
        "--slow",
        action="store_true",
        help="Force System 2 (ToT + Reflection) instead of auto-routing",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output (show workflow details)",
    )

    args = parser.parse_args()

    try:
        exit_code = asyncio.run(
            execute_v8_request(
                description=args.description,
                repo_path=args.repo,
                force_slow=args.slow,
                verbose=args.verbose,
            )
        )
        sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
        sys.exit(130)


if __name__ == "__main__":
    main()
