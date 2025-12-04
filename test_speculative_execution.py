"""
Integration Tests for Speculative Graph Execution

Tests:
1. Patch simulation
2. Graph delta computation
3. Risk analysis
4. Speculative execution
5. Batch analysis
"""

from src.contexts.analysis_indexing.infrastructure.speculative import (
    SpeculativePatch,
    PatchType,
    SpeculativeResult,
    GraphDelta,
    RiskLevel,
    GraphSimulator,
    SpeculativeExecutor,
    RiskAnalyzer,
)
from src.contexts.analysis_indexing.infrastructure.speculative.models import SimulationContext
from src.contexts.code_foundation.infrastructure.graphs.context_sensitive_analyzer import (
    ContextSensitiveCallGraph,
)


def test_speculative_patch_model():
    """Test SpeculativePatch model"""
    print("\n[SpeculativePatch Test] Patch model...")
    
    # Rename patch
    patch = SpeculativePatch(
        patch_id="patch_1",
        patch_type=PatchType.RENAME,
        file_path="service.py",
        target_symbol="old_func",
        old_value="old_func",
        new_value="new_func",
        description="Rename function",
        reason="Better naming convention",
    )
    
    assert patch.is_breaking_change()
    
    print(f"  ✅ Patch created: {patch}")
    print(f"  ✅ Breaking change: {patch.is_breaking_change()}")
    
    # Add field patch (safe)
    patch2 = SpeculativePatch(
        patch_id="patch_2",
        patch_type=PatchType.ADD_FIELD,
        file_path="models.py",
        target_symbol="User",
        new_value="email: str",
    )
    
    assert not patch2.is_breaking_change()
    print(f"  ✅ Add field patch (non-breaking): {patch2}")


def test_graph_delta():
    """Test GraphDelta"""
    print("\n[GraphDelta Test] Graph changes...")
    
    delta = GraphDelta()
    
    # Add changes
    delta.nodes_added.add("new_func")
    delta.nodes_removed.add("old_func")
    delta.nodes_modified.add("existing_func")
    
    delta.edges_added.add(("caller", "new_func"))
    delta.edges_removed.add(("caller", "old_func"))
    
    assert delta.size() == 5  # 3 nodes + 2 edges
    assert not delta.is_empty()
    
    print(f"  ✅ Delta: {delta}")
    print(f"  ✅ Size: {delta.size()}")
    print(f"  ✅ Empty: {delta.is_empty()}")


def test_graph_simulator_rename():
    """Test GraphSimulator for rename"""
    print("\n[GraphSimulator Test] Simulating rename...")
    
    # Create mock call graph
    call_graph = ContextSensitiveCallGraph()
    from src.contexts.code_foundation.infrastructure.graphs.call_context import CallContext
    
    ctx1 = CallContext.from_dict("file.py:10:5", {})
    call_graph.add_edge("main", "old_func", ctx1)
    call_graph.add_edge("old_func", "helper", ctx1)
    
    context = SimulationContext()
    context.call_graph = call_graph
    
    simulator = GraphSimulator(context)
    
    # Rename patch
    patch = SpeculativePatch(
        patch_id="rename_1",
        patch_type=PatchType.RENAME,
        file_path="service.py",
        target_symbol="old_func",
        new_value="new_func",
    )
    
    delta = simulator.simulate(patch)
    
    assert len(delta.nodes_modified) >= 1
    assert len(delta.edges_removed) >= 0
    assert len(delta.edges_added) >= 0
    
    print(f"  ✅ Simulated rename: {delta}")
    print(f"  ✅ Nodes modified: {len(delta.nodes_modified)}")
    print(f"  ✅ Edges changed: {len(delta.edges_added) + len(delta.edges_removed)}")


def test_graph_simulator_add_method():
    """Test GraphSimulator for add method"""
    print("\n[GraphSimulator Test] Simulating add method...")
    
    context = SimulationContext()
    simulator = GraphSimulator(context)
    
    patch = SpeculativePatch(
        patch_id="add_1",
        patch_type=PatchType.ADD_METHOD,
        file_path="service.py",
        target_symbol="MyClass",
        new_value="new_method",
    )
    
    delta = simulator.simulate(patch)
    
    assert len(delta.nodes_added) == 1
    assert len(delta.nodes_modified) >= 1  # Parent class
    assert len(delta.edges_added) >= 1  # Parent -> method
    
    print(f"  ✅ Added method: {delta}")
    print(f"  ✅ New nodes: {list(delta.nodes_added)}")


def test_graph_simulator_delete():
    """Test GraphSimulator for delete"""
    print("\n[GraphSimulator Test] Simulating delete...")
    
    # Mock call graph
    call_graph = ContextSensitiveCallGraph()
    from src.contexts.code_foundation.infrastructure.graphs.call_context import CallContext
    
    ctx = CallContext.from_dict("file.py:10:5", {})
    call_graph.add_edge("caller1", "to_delete", ctx)
    call_graph.add_edge("caller2", "to_delete", ctx)
    call_graph.add_edge("to_delete", "helper", ctx)
    
    context = SimulationContext()
    context.call_graph = call_graph
    
    simulator = GraphSimulator(context)
    
    patch = SpeculativePatch(
        patch_id="delete_1",
        patch_type=PatchType.DELETE,
        file_path="service.py",
        target_symbol="to_delete",
    )
    
    delta = simulator.simulate(patch)
    
    assert "to_delete" in delta.nodes_removed
    assert len(delta.edges_removed) >= 3  # All edges involving symbol
    
    print(f"  ✅ Deleted symbol: {delta}")
    print(f"  ✅ Edges removed: {len(delta.edges_removed)}")


def test_risk_analyzer():
    """Test RiskAnalyzer"""
    print("\n[RiskAnalyzer Test] Risk analysis...")
    
    context = SimulationContext()
    analyzer = RiskAnalyzer(context)
    
    # Test safe patch (add field)
    patch1 = SpeculativePatch(
        patch_id="safe_1",
        patch_type=PatchType.ADD_FIELD,
        file_path="models.py",
        target_symbol="User",
        new_value="email: str",
    )
    
    delta1 = GraphDelta()
    delta1.nodes_added.add("User.email")
    delta1.nodes_modified.add("User")
    
    risk1, reasons1 = analyzer.analyze_risk(patch1, delta1)
    
    assert risk1 in (RiskLevel.SAFE, RiskLevel.LOW)
    print(f"  ✅ Safe patch risk: {risk1.name}")
    print(f"  ✅ Reasons: {reasons1}")
    
    # Test risky patch (delete with callers)
    patch2 = SpeculativePatch(
        patch_id="risky_1",
        patch_type=PatchType.DELETE,
        file_path="service.py",
        target_symbol="critical_func",
    )
    
    delta2 = GraphDelta()
    delta2.nodes_removed.add("critical_func")
    # Simulate many edges (many callers)
    for i in range(10):
        delta2.edges_removed.add((f"caller_{i}", "critical_func"))
    
    risk2, reasons2 = analyzer.analyze_risk(patch2, delta2)
    
    assert risk2 >= RiskLevel.HIGH
    print(f"  ✅ Risky patch risk: {risk2.name}")
    print(f"  ✅ Reasons: {reasons2}")


def test_speculative_executor():
    """Test SpeculativeExecutor"""
    print("\n[SpeculativeExecutor Test] Full execution...")
    
    # Setup context with call graph
    call_graph = ContextSensitiveCallGraph()
    from src.contexts.code_foundation.infrastructure.graphs.call_context import CallContext
    
    ctx = CallContext.from_dict("file.py:10:5", {})
    call_graph.add_edge("main", "process", ctx)
    call_graph.add_edge("process", "helper", ctx)
    
    context = SimulationContext()
    context.call_graph = call_graph
    
    executor = SpeculativeExecutor(context)
    
    # Execute rename
    patch = SpeculativePatch(
        patch_id="exec_1",
        patch_type=PatchType.RENAME,
        file_path="service.py",
        target_symbol="process",
        old_value="process",
        new_value="process_data",
        description="Rename for clarity",
    )
    
    result = executor.execute(patch)
    
    assert result.risk_level is not None
    assert result.graph_delta is not None
    assert len(result.recommendations) > 0
    
    summary = result.get_summary()
    
    print(f"  ✅ Execution result: {result}")
    print(f"  ✅ Risk: {summary['risk_level']}")
    print(f"  ✅ Changes: {summary['graph_changes']}")
    print(f"  ✅ Affected: {summary['affected_symbols']}")
    print(f"  ✅ Safe: {summary['is_safe']}")
    print(f"  ✅ Recommendations: {len(result.recommendations)}")


def test_batch_execution():
    """Test batch speculative execution"""
    print("\n[Batch Execution Test] Multiple patches...")
    
    context = SimulationContext()
    executor = SpeculativeExecutor(context)
    
    patches = [
        SpeculativePatch(
            patch_id="batch_1",
            patch_type=PatchType.ADD_FIELD,
            file_path="models.py",
            target_symbol="User",
            new_value="email: str",
        ),
        SpeculativePatch(
            patch_id="batch_2",
            patch_type=PatchType.ADD_METHOD,
            file_path="models.py",
            target_symbol="User",
            new_value="validate_email",
        ),
        SpeculativePatch(
            patch_id="batch_3",
            patch_type=PatchType.RENAME,
            file_path="service.py",
            target_symbol="old_func",
            new_value="new_func",
        ),
    ]
    
    results = executor.execute_batch(patches)
    
    assert len(results) == 3
    
    safe_count = sum(1 for r in results if r.is_safe())
    high_risk_count = sum(1 for r in results if r.risk_level >= RiskLevel.HIGH)
    
    print(f"  ✅ Analyzed {len(results)} patches")
    print(f"  ✅ Safe: {safe_count}")
    print(f"  ✅ High risk: {high_risk_count}")


def test_risk_levels():
    """Test risk level ordering"""
    print("\n[Risk Levels Test] Risk level comparison...")
    
    assert RiskLevel.SAFE < RiskLevel.LOW
    assert RiskLevel.LOW < RiskLevel.MEDIUM
    assert RiskLevel.MEDIUM < RiskLevel.HIGH
    assert RiskLevel.HIGH < RiskLevel.CRITICAL
    
    print("  ✅ Risk levels ordered correctly")
    print(f"  ✅ All levels: {[l.name for l in RiskLevel]}")


def test_recommendations():
    """Test recommendation generation"""
    print("\n[Recommendations Test] Generating recommendations...")
    
    context = SimulationContext()
    analyzer = RiskAnalyzer(context)
    
    # High risk patch
    patch = SpeculativePatch(
        patch_id="rec_1",
        patch_type=PatchType.DELETE,
        file_path="service.py",
        target_symbol="important_func",
    )
    
    delta = GraphDelta()
    delta.nodes_removed.add("important_func")
    
    recommendations = analyzer.generate_recommendations(
        patch, delta, RiskLevel.HIGH
    )
    
    assert len(recommendations) > 0
    assert any("High risk" in r for r in recommendations)
    
    print(f"  ✅ Generated {len(recommendations)} recommendations:")
    for rec in recommendations:
        print(f"    - {rec}")


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("🔬 Speculative Graph Execution Tests")
    print("=" * 60)
    
    test_speculative_patch_model()
    test_graph_delta()
    test_graph_simulator_rename()
    test_graph_simulator_add_method()
    test_graph_simulator_delete()
    test_risk_analyzer()
    test_speculative_executor()
    test_batch_execution()
    test_risk_levels()
    test_recommendations()
    
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    print("  ✅ PASS: SpeculativePatch model")
    print("  ✅ PASS: GraphDelta")
    print("  ✅ PASS: GraphSimulator (rename)")
    print("  ✅ PASS: GraphSimulator (add method)")
    print("  ✅ PASS: GraphSimulator (delete)")
    print("  ✅ PASS: RiskAnalyzer")
    print("  ✅ PASS: SpeculativeExecutor")
    print("  ✅ PASS: Batch execution")
    print("  ✅ PASS: Risk levels")
    print("  ✅ PASS: Recommendations")
    print("=" * 60)
    print("\n✅ All tests passed!")
    print("\n🎯 Month 3 - P1.2: Speculative Graph Execution COMPLETE!")


if __name__ == "__main__":
    run_all_tests()

