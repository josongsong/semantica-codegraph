"""Context Adapter 간소화 검증

핵심 기능만 테스트:
1. Mock fallback
2. Error handling (graceful degradation)
3. Workflow integration
4. Async concurrency

실제 서비스 연동은 integration test에서 별도 진행
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.adapters.context_adapter import ContextAdapter

print("=" * 70)
print("🔥 Context Adapter 간소화 검증 (핵심 기능)")
print("=" * 70)
print()


async def main():
    passed = 0
    total = 4

    # Test 1: Mock fallback
    print("🔍 Test 1: Mock Fallback...")
    adapter = ContextAdapter()

    code = await adapter.get_relevant_code("fix bug", "repo1")
    assert "Relevant Code" in code

    symbol = await adapter.get_symbol_definition("func", "repo1")
    assert symbol["found"]

    print("  ✅ Mock fallback works\n")
    passed += 1

    # Test 2: Error handling
    print("🔍 Test 2: Error Handling...")

    class FailingService:
        async def retrieve(self, **kwargs):
            raise RuntimeError("Simulated failure")

    class FailingSymbol:
        async def search(self, **kwargs):
            raise RuntimeError("Simulated failure")

    adapter_failing = ContextAdapter(
        retrieval_service=FailingService(),
        symbol_index=FailingSymbol(),
    )

    code = await adapter_failing.get_relevant_code("query", "repo1")
    assert "Relevant Code" in code

    symbol = await adapter_failing.get_symbol_definition("symbol", "repo1")
    assert symbol["found"]

    print("  ✅ Graceful degradation works\n")
    passed += 1

    # Test 3: Workflow integration
    print("🔍 Test 3: Workflow Integration...")
    adapter = ContextAdapter()

    # Simulate workflow steps
    code = await adapter.get_relevant_code("calculate total", "repo1")
    assert len(code) > 0

    symbol = await adapter.get_symbol_definition("calculate_total", "repo1")
    assert symbol["name"] == "calculate_total"

    impact = await adapter.get_impact_scope(symbol["file_path"], "repo1")
    assert len(impact) > 0

    tests = await adapter.get_related_tests(symbol["file_path"], "repo1")
    assert len(tests) > 0

    print("  ✅ Workflow integration works\n")
    passed += 1

    # Test 4: Async concurrency
    print("🔍 Test 4: Async Concurrency...")
    adapter = ContextAdapter()

    tasks = [
        adapter.get_relevant_code("q1", "r1"),
        adapter.get_relevant_code("q2", "r2"),
        adapter.get_symbol_definition("s1", "r1"),
        adapter.get_symbol_definition("s2", "r2"),
        adapter.get_impact_scope("f1.py", "r1"),
    ]

    results = await asyncio.gather(*tasks)
    assert len(results) == 5
    assert all(r is not None for r in results)

    print("  ✅ Async concurrency works\n")
    passed += 1

    print("=" * 70)
    print(f"📊 테스트 결과: {passed}/{total} 통과")
    print("=" * 70)
    print()

    if passed == total:
        print("🎉 Context Adapter 핵심 기능 검증 완료!")
        print()
        print("✅ 검증된 항목:")
        print("  - Mock fallback (실제 서비스 없이도 동작)")
        print("  - Graceful degradation (에러 시 Mock으로 전환)")
        print("  - Workflow integration (Router → Workflow 통합)")
        print("  - Async concurrency (비동기 동시 호출)")
        print()
        print("📌 다음 단계:")
        print("  - Day 14-16: Context Adapter 완료 ✅")
        print("  - Day 17-18: Task Graph Planner")
        print()
    else:
        print("⚠️  일부 테스트 실패")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
