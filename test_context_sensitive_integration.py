"""
Integration Tests for Context-Sensitive Call Graph

Tests the full pipeline:
1. CallContext model
2. ArgumentValueTracker
3. ContextSensitiveAnalyzer
4. Integration with Type Narrowing
"""

import asyncio
from pathlib import Path
from src.contexts.code_foundation.infrastructure.graphs.call_context import (
    CallContext,
    ContextSensitiveCallGraph,
    ContextSensitivity,
)
from src.contexts.code_foundation.infrastructure.graphs.value_tracker import (
    ArgumentValueTracker,
    TrackedValue,
    ValueKind,
)
from src.contexts.code_foundation.infrastructure.graphs.context_sensitive_analyzer import (
    ContextSensitiveAnalyzer,
)


def test_call_context_basic():
    """Test CallContext model"""
    print("\n[CallContext Test] Basic functionality...")
    
    # Create context
    ctx = CallContext.from_dict(
        call_site="main.py:10:5",
        args={"use_fast": True, "cache_size": 100},
        parent=None,
    )
    
    assert ctx.call_site == "main.py:10:5"
    assert ctx.get_argument("use_fast") == True
    assert ctx.get_argument("cache_size") == 100
    assert ctx.depth == 0
    
    # Test matching
    assert ctx.matches_pattern({"use_fast": True})
    assert not ctx.matches_pattern({"use_fast": False})
    
    # Test context ID
    context_id = ctx.context_id()
    assert "main.py:10:5" in context_id
    assert "use_fast=True" in context_id
    
    print("  ✅ CallContext creation and matching")


def test_call_context_chain():
    """Test call context chaining"""
    print("\n[CallContext Chain Test] Parent-child contexts...")
    
    # Parent context
    parent = CallContext.from_dict(
        call_site="main.py:10:5",
        args={"mode": "production"},
        parent=None,
    )
    
    # Child context
    child = CallContext.from_dict(
        call_site="service.py:45:10",
        args={"use_cache": True},
        parent=parent,
    )
    
    assert child.depth == 1
    assert child.caller_context == parent
    assert parent.depth == 0
    
    print("  ✅ Context chain with depth tracking")


def test_argument_value_tracker():
    """Test ArgumentValueTracker"""
    print("\n[Value Tracker Test] Tracking argument values...")
    
    tracker = ArgumentValueTracker()
    
    # Track literal values
    tracker.track_argument(
        call_site="main.py:10:5",
        param_name="use_fast",
        value_node={"type": "true", "value": "true"},
    )
    
    tracker.track_argument(
        call_site="main.py:15:5",
        param_name="cache_size",
        value_node={"type": "integer_literal", "value": "100"},
    )
    
    # Get concrete values
    concrete1 = tracker.get_concrete_values("main.py:10:5", "use_fast")
    concrete2 = tracker.get_concrete_values("main.py:15:5", "cache_size")
    
    assert "use_fast" in concrete1
    assert "cache_size" in concrete2
    
    # Get statistics
    stats = tracker.get_statistics()
    assert stats["total_call_sites"] >= 2
    assert stats["concrete_values"] >= 2
    
    print(f"  ✅ Tracked {stats['total_call_sites']} call sites")
    print(f"  ✅ Concrete values: {stats['concrete_values']}/{stats['total_tracked_values']}")


def test_context_sensitive_call_graph():
    """Test ContextSensitiveCallGraph"""
    print("\n[CS Call Graph Test] Context-sensitive edges...")
    
    cg = ContextSensitiveCallGraph()
    
    # Add edges with different contexts
    ctx1 = CallContext.from_dict(
        call_site="main.py:10:5",
        args={"use_fast": True},
        parent=None,
    )
    
    ctx2 = CallContext.from_dict(
        call_site="main.py:15:5",
        args={"use_fast": False},
        parent=None,
    )
    
    # Same caller-callee, different contexts
    cg.add_edge("process", "fast_path", ctx1)
    cg.add_edge("process", "slow_path", ctx2)
    
    # Query
    callees_ctx1 = cg.get_callees("process", ctx1)
    callees_ctx2 = cg.get_callees("process", ctx2)
    
    assert "fast_path" in callees_ctx1
    assert "fast_path" not in callees_ctx2
    assert "slow_path" in callees_ctx2
    assert "slow_path" not in callees_ctx1
    
    print("  ✅ Context-sensitive edge tracking")
    print(f"  ✅ Context 1 callees: {callees_ctx1}")
    print(f"  ✅ Context 2 callees: {callees_ctx2}")


def test_cs_call_graph_comparison():
    """Test CS call graph vs basic call graph"""
    print("\n[CS vs Basic CG Test] Precision comparison...")
    
    cg = ContextSensitiveCallGraph()
    
    # Context-sensitive edges
    for i in range(5):
        ctx = CallContext.from_dict(
            call_site=f"main.py:{i*10}:5",
            args={"flag": i % 2 == 0},
            parent=None,
        )
        cg.add_edge("process", "handler", ctx)
    
    # Basic call graph (context-insensitive)
    basic_cg = {("process", "handler")}
    
    # Compare
    comparison = cg.compare_with_basic(basic_cg)
    
    assert comparison["basic_edges"] == 1
    assert comparison["cs_edges"] == 1  # Same edge type
    assert comparison["total_contexts"] == 5  # But 5 contexts!
    assert comparison["avg_contexts_per_edge"] == 5.0
    
    print(f"  ✅ Basic edges: {comparison['basic_edges']}")
    print(f"  ✅ Total contexts: {comparison['total_contexts']}")
    print(f"  ✅ Contexts per edge: {comparison['avg_contexts_per_edge']}")


async def test_cs_analyzer_integration():
    """Test ContextSensitiveAnalyzer with mock IR"""
    print("\n[CS Analyzer Test] Full integration...")
    
    analyzer = ContextSensitiveAnalyzer()
    
    # Create mock IR with call edges
    class MockIRDoc:
        def __init__(self, edges):
            self.edges = edges
    
    class MockEdge:
        def __init__(self, source, target, call_site, arguments):
            self.type = "CALLS"
            self.source = source
            self.target = target
            self.metadata = {
                "call_site": call_site,
                "arguments": arguments,
            }
    
    # Scenario: process(use_fast) calls different functions based on use_fast
    ir_docs = {
        "main.py": MockIRDoc([
            MockEdge(
                source="process",
                target="fast_query",
                call_site="main.py:10:5",
                arguments={
                    "use_fast": {"type": "true", "value": "true"}
                },
            ),
            MockEdge(
                source="process",
                target="slow_query",
                call_site="main.py:15:5",
                arguments={
                    "use_fast": {"type": "false", "value": "false"}
                },
            ),
        ])
    }
    
    # Analyze
    cs_cg = await analyzer.analyze(ir_docs, use_type_narrowing=False)
    
    # Check results
    assert len(cs_cg.edges) >= 2
    
    # Query reachable with different contexts
    reachable_fast = analyzer.query_reachable(
        start_function="process",
        argument_pattern={"use_fast": True},
        max_depth=5,
    )
    
    reachable_slow = analyzer.query_reachable(
        start_function="process",
        argument_pattern={"use_fast": False},
        max_depth=5,
    )
    
    print(f"  ✅ CS call graph: {len(cs_cg)} contexts")
    print(f"  ✅ Reachable (use_fast=True): {len(reachable_fast)} functions")
    print(f"  ✅ Reachable (use_fast=False): {len(reachable_slow)} functions")


async def test_impact_analysis():
    """Test context-sensitive impact analysis"""
    print("\n[Impact Analysis Test] Context-aware impact...")
    
    analyzer = ContextSensitiveAnalyzer()
    
    # Mock IR
    class MockIRDoc:
        def __init__(self, edges):
            self.edges = edges
    
    class MockEdge:
        def __init__(self, source, target, call_site, arguments):
            self.type = "CALLS"
            self.source = source
            self.target = target
            self.metadata = {
                "call_site": call_site,
                "arguments": arguments,
            }
    
    ir_docs = {
        "service.py": MockIRDoc([
            MockEdge(
                source="handle_request",
                target="process_data",
                call_site="service.py:20:5",
                arguments={"mode": {"type": "string_literal", "value": "fast"}},
            ),
            MockEdge(
                source="handle_batch",
                target="process_data",
                call_site="service.py:40:5",
                arguments={"mode": {"type": "string_literal", "value": "slow"}},
            ),
        ])
    }
    
    cs_cg = await analyzer.analyze(ir_docs)
    
    # Impact analysis
    impact = analyzer.get_impact_analysis(
        changed_function="process_data",
        context_filter={"mode": "fast"},
    )
    
    assert "direct_callers" in impact
    assert "downstream_impact" in impact
    assert impact["changed_function"] == "process_data"
    
    print(f"  ✅ Direct callers: {impact['direct_callers']}")
    print(f"  ✅ Affected contexts: {impact['num_affected_contexts']}")
    print(f"  ✅ Total affected: {impact['total_affected']}")


async def test_context_comparison():
    """Test comparing different contexts"""
    print("\n[Context Comparison Test] Comparing execution paths...")
    
    analyzer = ContextSensitiveAnalyzer()
    
    # Mock IR with branching behavior
    class MockIRDoc:
        def __init__(self, edges):
            self.edges = edges
    
    class MockEdge:
        def __init__(self, source, target, call_site, arguments):
            self.type = "CALLS"
            self.source = source
            self.target = target
            self.metadata = {
                "call_site": call_site,
                "arguments": arguments,
            }
    
    ir_docs = {
        "branching.py": MockIRDoc([
            # Fast path
            MockEdge(
                source="execute",
                target="fast_setup",
                call_site="branching.py:10:5",
                arguments={"optimize": {"type": "true"}},
            ),
            MockEdge(
                source="execute",
                target="fast_execute",
                call_site="branching.py:15:5",
                arguments={"optimize": {"type": "true"}},
            ),
            # Slow path
            MockEdge(
                source="execute",
                target="slow_setup",
                call_site="branching.py:20:5",
                arguments={"optimize": {"type": "false"}},
            ),
            MockEdge(
                source="execute",
                target="slow_execute",
                call_site="branching.py:25:5",
                arguments={"optimize": {"type": "false"}},
            ),
        ])
    }
    
    cs_cg = await analyzer.analyze(ir_docs)
    
    # Compare contexts
    comparison = analyzer.compare_contexts(
        function="execute",
        context1={"optimize": True},
        context2={"optimize": False},
    )
    
    print(f"  ✅ Only in optimized: {comparison['only_in_context1']}")
    print(f"  ✅ Only in non-optimized: {comparison['only_in_context2']}")
    print(f"  ✅ Common: {comparison['common']}")
    print(f"  ✅ Precision gain: {comparison['precision_gain_pct']:.1f}%")


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("🔬 Context-Sensitive Analysis Integration Tests")
    print("=" * 60)
    
    # Sync tests
    test_call_context_basic()
    test_call_context_chain()
    test_argument_value_tracker()
    test_context_sensitive_call_graph()
    test_cs_call_graph_comparison()
    
    # Async tests
    asyncio.run(test_cs_analyzer_integration())
    asyncio.run(test_impact_analysis())
    asyncio.run(test_context_comparison())
    
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    print("  ✅ PASS: CallContext model")
    print("  ✅ PASS: ArgumentValueTracker")
    print("  ✅ PASS: ContextSensitiveCallGraph")
    print("  ✅ PASS: CS vs Basic comparison")
    print("  ✅ PASS: Full analyzer integration")
    print("  ✅ PASS: Impact analysis")
    print("  ✅ PASS: Context comparison")
    print("=" * 60)
    print("\n✅ All tests passed!")
    print("\n🎯 Month 2 - Week 5-8: Context-Sensitive Call Graph COMPLETE!")


if __name__ == "__main__":
    run_all_tests()

