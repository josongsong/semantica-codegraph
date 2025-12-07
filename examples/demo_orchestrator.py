"""Orchestrator 데모 스크립트

실제 Agent를 실행해보는 간단한 예제
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.adapters.context_adapter import ContextAdapter
from src.agent.orchestrator import AgentOrchestrator
from src.agent.router.intent_classifier import IntentClassifier
from src.agent.router.router import Router
from src.agent.task_graph.planner import TaskGraphPlanner
from src.agent.workflow.state_machine import WorkflowStateMachine
from src.infra.config.settings import Settings
from src.infra.llm.litellm_adapter import LiteLLMAdapter


async def demo_basic():
    """기본 데모: Mock LLM 사용"""
    print("=" * 70)
    print("🎯 Orchestrator 기본 데모 (Mock LLM)")
    print("=" * 70)
    print()

    # Mock LLM for demo
    class MockLLM:
        async def complete(self, prompt: str, **kwargs) -> str:
            if "calculate_total" in prompt.lower():
                return '{"intent": "fix_bug", "reasoning": "Bug fix needed", "confidence": 0.95}'
            return '{"intent": "unknown", "reasoning": "Unclear", "confidence": 0.3}'

    # Setup components
    llm = MockLLM()
    classifier = IntentClassifier(llm)
    router = Router(classifier)
    planner = TaskGraphPlanner()
    workflow = WorkflowStateMachine(max_iterations=1)
    context_adapter = ContextAdapter()

    # Create orchestrator
    orchestrator = AgentOrchestrator(
        router=router,
        task_planner=planner,
        workflow=workflow,
        context_adapter=context_adapter,
    )

    # Execute
    print("📥 User Request: fix bug in calculate_total function")
    print()

    result = await orchestrator.execute(
        user_request="fix bug in calculate_total function", context={"repo_id": "demo-repo"}
    )

    # Display results
    print("📤 Results:")
    print(f"  Intent:       {result.intent.value}")
    print(f"  Confidence:   {result.confidence:.2f}")
    print(f"  Status:       {result.status.value}")
    print(f"  Tasks:        {len(result.tasks_completed)} completed")
    print(f"  - {', '.join(result.tasks_completed)}")
    print(f"  Time:         {result.execution_time_ms:.0f}ms")
    print(f"  Success:      {'✅' if result.is_success() else '❌'}")
    print()

    if result.result:
        print("  Result Preview:")
        result_str = str(result.result)[:200]
        print(f"  {result_str}...")
    print()


async def demo_multiple_requests():
    """여러 요청 데모"""
    print("=" * 70)
    print("🎯 여러 요청 처리 데모")
    print("=" * 70)
    print()

    class MockLLM:
        async def complete(self, prompt: str, **kwargs) -> str:
            prompt_lower = prompt.lower()
            if "authentication" in prompt_lower or "add" in prompt_lower:
                return '{"intent": "add_feature", "reasoning": "Feature request", "confidence": 0.90}'
            elif "refactor" in prompt_lower:
                return '{"intent": "refactor", "reasoning": "Refactor request", "confidence": 0.88}'
            elif "bug" in prompt_lower or "fix" in prompt_lower:
                return '{"intent": "fix_bug", "reasoning": "Bug fix", "confidence": 0.95}'
            return '{"intent": "unknown", "reasoning": "Unclear", "confidence": 0.3}'

    llm = MockLLM()
    classifier = IntentClassifier(llm)
    router = Router(classifier)
    planner = TaskGraphPlanner()
    workflow = WorkflowStateMachine(max_iterations=1)
    context_adapter = ContextAdapter()

    orchestrator = AgentOrchestrator(
        router=router,
        task_planner=planner,
        workflow=workflow,
        context_adapter=context_adapter,
    )

    requests = [
        "fix bug in payment processing",
        "add new feature for user authentication",
        "refactor database connection code",
    ]

    results = []
    for i, request in enumerate(requests, 1):
        print(f"{i}. Request: {request}")
        result = await orchestrator.execute(request, {"repo_id": f"repo-{i}"})
        results.append(result)
        print(f"   → {result.intent.value} ({result.confidence:.2f}) - {result.status.value}")
        print()

    print("📊 Summary:")
    print(f"  Total requests:  {len(results)}")
    print(f"  Successful:      {sum(1 for r in results if r.is_success())}")
    print(f"  Avg confidence:  {sum(r.confidence for r in results) / len(results):.2f}")
    print(f"  Avg time:        {sum(r.execution_time_ms for r in results) / len(results):.0f}ms")
    print()


async def demo_with_real_llm():
    """실제 LLM 데모 (설정되어 있으면)"""
    print("=" * 70)
    print("🎯 실제 LLM 데모 (Optional)")
    print("=" * 70)
    print()

    try:
        settings = Settings()

        # Check if LLM is configured
        if not settings.llm.local_llm_base_url:
            print("⚠️  Local LLM not configured. Skipping real LLM demo.")
            print("   Set LOCAL_LLM_BASE_URL in .env to enable.")
            print()
            return

        print(f"📡 Connecting to LLM: {settings.llm.local_llm_base_url}")

        # Try to create LiteLLMAdapter
        llm = LiteLLMAdapter(
            model=settings.llm.local_llm_model or "qwen2.5-coder:32b",
            api_base=settings.llm.local_llm_base_url,
        )

        classifier = IntentClassifier(llm)
        router = Router(classifier)
        planner = TaskGraphPlanner()
        workflow = WorkflowStateMachine(max_iterations=1)
        context_adapter = ContextAdapter()

        orchestrator = AgentOrchestrator(
            router=router,
            task_planner=planner,
            workflow=workflow,
            context_adapter=context_adapter,
        )

        print("📥 Request: fix null pointer exception in getUserData")
        print()

        result = await orchestrator.execute(
            user_request="fix null pointer exception in getUserData method", context={"repo_id": "production-app"}
        )

        print("📤 Results (Real LLM):")
        print(f"  Intent:       {result.intent.value}")
        print(f"  Confidence:   {result.confidence:.2f}")
        print(f"  Status:       {result.status.value}")
        print(f"  Time:         {result.execution_time_ms:.0f}ms")
        print()

    except Exception as e:
        print(f"⚠️  Real LLM demo failed: {e}")
        print("   This is OK - using Mock LLM for demos")
        print()


async def main():
    """메인 실행"""
    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║                  Orchestrator 데모 스크립트                       ║")
    print("║                                                                  ║")
    print("║  Phase 0 완료! 실제로 작동하는 Agent를 확인해보세요.              ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print()

    try:
        # Demo 1: 기본
        await demo_basic()

        # Demo 2: 여러 요청
        await demo_multiple_requests()

        # Demo 3: 실제 LLM (optional)
        await demo_with_real_llm()

        print("=" * 70)
        print("✅ 모든 데모 완료!")
        print("=" * 70)
        print()
        print("📝 다음 단계:")
        print("  1. 실제 LLM 연결 (.env 설정)")
        print("  2. 실제 코드베이스로 테스트")
        print("  3. CLI 인터페이스 구축")
        print("  4. API 서버 배포")
        print()

    except KeyboardInterrupt:
        print("\n\n⚠️  중단됨")
    except Exception as e:
        print(f"\n\n❌ 에러 발생: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
