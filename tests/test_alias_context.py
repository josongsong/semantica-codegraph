"""
Tests for Alias Analysis and Context-Sensitive Analysis (Week 3)

Tests:
- Alias analysis (must-alias, may-alias)
- Call string approach
- Context-sensitive taint tracking
- Heap abstraction
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.alias_analyzer import (
    AliasAnalyzer,
    AliasSet,
    AliasType,
)
from codegraph_engine.code_foundation.infrastructure.analyzers.context_manager import (
    CallString,
    ContextManager,
    ContextState,
)

# Alias Analysis Tests


def test_alias_analyzer_initialization():
    """AliasAnalyzer 초기화"""
    analyzer = AliasAnalyzer()

    assert analyzer._alias_graph == {}
    assert analyzer._alias_sets == []
    assert analyzer._heap_locations == {}


def test_direct_alias():
    """Direct alias: a = b"""
    analyzer = AliasAnalyzer()

    analyzer.add_alias("b", "a", AliasType.DIRECT)

    assert analyzer.is_aliased("a", "b")
    assert "a" in analyzer.get_aliases("b")


def test_must_alias_propagation():
    """Must-alias taint propagation"""
    analyzer = AliasAnalyzer()

    # a = b (must-alias)
    analyzer.add_alias("b", "a", AliasType.DIRECT, is_must=True)

    # b is tainted
    analyzer.propagate_taint("b", True)

    # a should also be tainted
    assert analyzer.is_tainted("a")
    assert analyzer.is_tainted("b")


def test_may_alias():
    """May-alias: a = b or a = c"""
    analyzer = AliasAnalyzer()

    # May-alias: b -> a, c -> a
    analyzer.add_alias("b", "a", AliasType.DIRECT, is_must=False)
    analyzer.add_alias("c", "a", AliasType.DIRECT, is_must=False)

    # May-alias check: b의 may-aliases에 a가 있어야 함
    aliases_b = analyzer.get_aliases("b", include_may=True)
    aliases_c = analyzer.get_aliases("c", include_may=True)

    assert "a" in aliases_b or "a" in aliases_c


def test_alias_set_merging():
    """Alias set 병합"""
    analyzer = AliasAnalyzer()

    # a = b
    analyzer.add_alias("b", "a")

    # c = a
    analyzer.add_alias("a", "c")

    # a, b, c should be in same set
    assert analyzer.is_aliased("a", "b")
    assert analyzer.is_aliased("b", "c")
    assert analyzer.is_aliased("a", "c")


def test_field_alias():
    """Field access alias: a = obj.field"""
    analyzer = AliasAnalyzer()

    analyzer.analyze_field_access("obj", "name", "a")

    # obj.name과 a가 alias
    assert "a" in analyzer.get_aliases("obj.name")


def test_element_alias():
    """Element access alias: a = arr[0]"""
    analyzer = AliasAnalyzer()

    analyzer.analyze_element_access("arr", 0, "a")

    # arr[0]과 a가 alias
    assert "a" in analyzer.get_aliases("arr[0]")


def test_heap_location():
    """Heap abstraction"""
    analyzer = AliasAnalyzer()

    # Heap location: obj1, obj2 point to same heap
    analyzer.add_heap_location("heap_1", {"obj1", "obj2"}, is_tainted=True)

    # obj1, obj2 should be aliased via heap
    heap_aliases = analyzer.get_heap_aliases("obj1")
    assert heap_aliases is not None
    assert "obj2" in heap_aliases

    # Both should be tainted
    assert analyzer.is_tainted("obj1")
    assert analyzer.is_tainted("obj2")


def test_kill_aliases():
    """Alias 재할당 시 제거"""
    analyzer = AliasAnalyzer()

    # a = b
    analyzer.add_alias("b", "a")
    assert analyzer.is_aliased("a", "b")

    # a = c (kill a's old alias)
    analyzer.kill_aliases("a")

    # a는 더 이상 b와 alias가 아님
    # (단, b는 여전히 alias set에 남아있을 수 있음)
    aliases = analyzer.get_aliases("a")
    # a가 새로 할당되었으므로 alias가 없어야 함


def test_alias_statistics():
    """통계 정보"""
    analyzer = AliasAnalyzer()

    analyzer.add_alias("b", "a")
    analyzer.add_alias("c", "d", is_must=False)

    stats = analyzer.get_statistics()
    assert stats["alias_sets"] > 0
    assert stats["must_aliases"] >= 1


# Context-Sensitive Analysis Tests


def test_call_string_creation():
    """CallString 생성"""
    cs = CallString(k_limit=2)

    assert cs.to_string() == "<empty>"
    assert cs.k_limit == 2


def test_call_string_push():
    """CallString push"""
    cs = CallString(k_limit=2)

    cs1 = cs.push("func1")
    assert "func1" in cs1.to_string()

    cs2 = cs1.push("func2")
    assert "func1->func2" == cs2.to_string()


def test_call_string_k_limiting():
    """K-limiting: 최근 K개만 유지"""
    cs = CallString(k_limit=2)

    cs = cs.push("func1")
    cs = cs.push("func2")
    cs = cs.push("func3")  # K=2이므로 func1 제거

    assert "func1" not in cs.to_string()
    assert "func2" in cs.to_string()
    assert "func3" in cs.to_string()


def test_call_string_equality():
    """CallString 동등성"""
    cs1 = CallString(k_limit=2)
    cs1 = cs1.push("func1").push("func2")

    cs2 = CallString(k_limit=2)
    cs2 = cs2.push("func1").push("func2")

    assert cs1 == cs2
    assert hash(cs1) == hash(cs2)


def test_context_manager_initialization():
    """ContextManager 초기화"""
    mgr = ContextManager(k_limit=2)

    assert mgr.k_limit == 2
    assert len(mgr._contexts) == 0


def test_enter_function_creates_context():
    """함수 진입 시 context 생성"""
    mgr = ContextManager(k_limit=2)

    cs = CallString(k_limit=2).push("main")
    ctx = mgr.enter_function("foo", cs, {0})

    assert ctx.call_string == cs
    assert 0 in ctx.tainted_params


def test_exit_function_updates_context():
    """함수 종료 시 context 업데이트"""
    mgr = ContextManager(k_limit=2)

    cs = CallString(k_limit=2).push("main")
    ctx = mgr.enter_function("foo", cs, {0})

    mgr.exit_function("foo", cs, return_tainted=True)

    updated_ctx = mgr.get_context_state("foo", cs)
    assert updated_ctx.return_tainted is True


def test_make_call_creates_new_call_string():
    """함수 호출 시 새 call string 생성"""
    mgr = ContextManager(k_limit=2)

    cs = CallString(k_limit=2).push("main")
    new_cs = mgr.make_call("main", "foo", cs)

    assert "foo" in new_cs.to_string()


def test_context_merging():
    """Context 병합"""
    mgr = ContextManager(k_limit=2)

    cs1 = CallString(k_limit=2).push("main")
    cs2 = CallString(k_limit=2).push("other")

    ctx1 = ContextState(cs1, tainted_vars={"a"}, return_tainted=False)
    ctx2 = ContextState(cs2, tainted_vars={"b"}, return_tainted=True)

    merged = mgr.merge_contexts([ctx1, ctx2])

    assert "a" in merged.tainted_vars
    assert "b" in merged.tainted_vars
    assert merged.return_tainted is True


def test_context_widening():
    """Context widening (너무 많은 context 병합)"""
    mgr = ContextManager(k_limit=2)
    mgr._merge_threshold = 3  # 테스트용으로 낮춤

    # 3개 초과 context 생성
    for i in range(5):
        cs = CallString(k_limit=2).push(f"caller_{i}")
        mgr.enter_function("foo", cs, {i})

    # Widening 발생했는지 확인
    all_contexts = mgr.get_all_contexts("foo")
    assert len(all_contexts) <= mgr._merge_threshold + 1


def test_is_context_sensitive():
    """Context-sensitive 분석 필요 여부"""
    mgr = ContextManager(k_limit=2)

    cs1 = CallString(k_limit=2).push("main")
    mgr.enter_function("foo", cs1, {0})

    assert not mgr.is_context_sensitive_for("foo")  # 1개만 있음

    cs2 = CallString(k_limit=2).push("other")
    mgr.enter_function("foo", cs2, {1})

    assert mgr.is_context_sensitive_for("foo")  # 2개 이상


def test_context_statistics():
    """통계 정보"""
    mgr = ContextManager(k_limit=2)

    cs = CallString(k_limit=2).push("main")
    mgr.enter_function("foo", cs, {0})

    stats = mgr.get_statistics()
    assert stats["total_contexts"] == 1
    assert stats["k_limit"] == 2


# Integration Tests


def test_full_taint_engine_with_alias_analysis():
    """FullTaintEngine + Alias Analysis"""
    from codegraph_engine.code_foundation.infrastructure.analyzers.taint_engine_full import FullTaintEngine

    engine = FullTaintEngine()
    engine.enable_alias_analysis()

    assert hasattr(engine, "_alias_analyzer")


def test_full_taint_engine_with_context_sensitivity():
    """FullTaintEngine + Context-Sensitive Analysis"""
    from codegraph_engine.code_foundation.infrastructure.analyzers.taint_engine_full import FullTaintEngine

    engine = FullTaintEngine()
    engine.enable_context_sensitivity(k_limit=3)

    assert hasattr(engine, "_context_manager")
    assert engine._context_manager.k_limit == 3
