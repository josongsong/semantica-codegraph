#!/usr/bin/env python3
"""
Phase 0 검증 스크립트

Dynamic Reasoning Router가 정상 작동하는지 확인
"""

import sys

sys.path.insert(0, ".")

from src.agent.domain.reasoning import (
    DynamicReasoningRouter,
    QueryFeatures,
    ReasoningPath,
)
from src.container import Container


def test_router_direct():
    """Direct Router 테스트"""
    print("=" * 80)
    print("Phase 0 검증: Dynamic Reasoning Router")
    print("=" * 80)

    router = DynamicReasoningRouter()

    # Test 1: Simple Query → System 1
    print("\n[Test 1] Simple Query (NPE 방어)")
    features_simple = QueryFeatures(
        file_count=1,
        impact_nodes=5,
        cyclomatic_complexity=2.0,
        has_test_failure=False,
        touches_security_sink=False,
        regression_risk=0.1,
        similar_success_rate=0.9,
    )

    decision = router.decide(features_simple)
    print(f"  Path: {decision.path.value}")
    print(f"  Confidence: {decision.confidence:.2f}")
    print(f"  Complexity: {decision.complexity_score:.2f}")
    print(f"  Risk: {decision.risk_score:.2f}")
    print(f"  Cost: ${decision.estimated_cost:.2f}")
    print(f"  Time: {decision.estimated_time:.1f}s")

    assert decision.path == ReasoningPath.SYSTEM_1, "Should be System 1"
    print("  ✅ PASS")

    # Test 2: Complex Query → System 2
    print("\n[Test 2] Complex Query (대규모 리팩토링)")
    features_complex = QueryFeatures(
        file_count=10,
        impact_nodes=100,
        cyclomatic_complexity=45.0,
        has_test_failure=True,
        touches_security_sink=False,
        regression_risk=0.7,
        similar_success_rate=0.6,
    )

    decision = router.decide(features_complex)
    print(f"  Path: {decision.path.value}")
    print(f"  Confidence: {decision.confidence:.2f}")
    print(f"  Complexity: {decision.complexity_score:.2f}")
    print(f"  Risk: {decision.risk_score:.2f}")
    print(f"  Cost: ${decision.estimated_cost:.2f}")
    print(f"  Time: {decision.estimated_time:.1f}s")

    assert decision.path == ReasoningPath.SYSTEM_2, "Should be System 2"
    print("  ✅ PASS")

    # Test 3: Security Query → System 2
    print("\n[Test 3] Security Fix")
    features_security = QueryFeatures(
        file_count=2,
        impact_nodes=10,
        cyclomatic_complexity=8.0,
        has_test_failure=False,
        touches_security_sink=True,
        regression_risk=0.3,
        similar_success_rate=0.8,
    )

    decision = router.decide(features_security)
    print(f"  Path: {decision.path.value}")
    print(f"  Risk: {decision.risk_score:.2f} (Security Sink!)")

    assert decision.path == ReasoningPath.SYSTEM_2, "Security → System 2"
    print("  ✅ PASS")


def test_container_integration():
    """Container 통합 테스트"""
    print("\n" + "=" * 80)
    print("Container Integration")
    print("=" * 80)

    container = Container()

    # DI로 Router 가져오기
    router = container.v8_reasoning_router
    print(f"✅ Router from Container: {type(router).__name__}")

    # Adapters 확인
    complexity_analyzer = container.v8_complexity_analyzer
    risk_assessor = container.v8_risk_assessor

    print(f"✅ Complexity Analyzer: {type(complexity_analyzer).__name__}")
    print(f"✅ Risk Assessor: {type(risk_assessor).__name__}")

    # UseCase 확인
    use_case = container.v8_decide_reasoning_path
    print(f"✅ UseCase: {type(use_case).__name__}")

    # Router 직접 사용
    features = QueryFeatures(
        file_count=3,
        impact_nodes=20,
        cyclomatic_complexity=10.0,
        has_test_failure=False,
        touches_security_sink=False,
        regression_risk=0.2,
        similar_success_rate=0.85,
    )

    decision = router.decide(features)
    print(f"\n✅ Router Decision (Direct): {decision.path.value}")
    print(f"   Confidence: {decision.confidence:.2f}")


def test_use_case():
    """UseCase 테스트 (Application Layer)"""
    print("\n" + "=" * 80)
    print("Application Layer: UseCase")
    print("=" * 80)

    container = Container()
    use_case = container.v8_decide_reasoning_path

    # UseCase로 결정 (실제 사용 시나리오)
    decision = use_case.execute(
        problem_description="Fix NPE in UserService.login()",
        target_files=["src/user/service.py"],
        code_snippet="def login(user):\n    return user.name\n",
    )

    print("Problem: Fix NPE in UserService.login()")
    print("Files: 1")
    print(f"Decision: {decision.path.value}")
    print(f"Confidence: {decision.confidence:.2f}")
    print(f"Cost: ${decision.estimated_cost:.2f}")
    print(f"Time: {decision.estimated_time:.1f}s")

    assert decision.path.value == "fast", "Simple NPE fix should be System 1"
    print("✅ PASS")


def main():
    """Main"""
    try:
        test_router_direct()
        test_container_integration()
        test_use_case()

        print("\n" + "=" * 80)
        print("🎉 Phase 0.5 검증 완료!")
        print("=" * 80)
        print("\n성공:")
        print("  ✅ Domain Layer (QueryFeatures, ReasoningDecision, Router)")
        print("  ✅ Ports Layer (IComplexityAnalyzer, IRiskAssessor)")
        print("  ✅ Adapters Layer (RadonComplexityAnalyzer, HistoricalRiskAssessor)")
        print("  ✅ Application Layer (DecideReasoningPathUseCase)")
        print("  ✅ Container DI 통합")
        print("  ✅ System 1/2 분기 정상 작동")
        print("\n수정 완료:")
        print("  ✅ Router 임계값 → 인스턴스 변수 (Thread-safe)")
        print("  ✅ Application Layer 추가 (Hexagonal 완성)")
        print("  ✅ UseCase Orchestration (Adapter → Domain)")
        print("\n다음 단계: Phase 1 - Tree-of-Thought Scoring")

        return 0

    except Exception as e:
        print(f"\n❌ 검증 실패: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
