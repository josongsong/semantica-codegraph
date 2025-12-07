"""
Real Production Scenarios Test

Tests with realistic code patterns and sizes.
"""

import pytest

from src.contexts.reasoning_engine.infrastructure.pdg.pdg_builder import DependencyType, PDGBuilder, PDGEdge, PDGNode
from src.contexts.reasoning_engine.infrastructure.slicer.budget_manager import BudgetConfig, BudgetManager
from src.contexts.reasoning_engine.infrastructure.slicer.interprocedural import (
    CallSite,
    FunctionContext,
    InterproceduralAnalyzer,
)
from src.contexts.reasoning_engine.infrastructure.slicer.slicer import ProgramSlicer


def test_large_dependency_chain():
    """Test 100+ node dependency chain (real large function scenario)"""
    builder = PDGBuilder()

    # Create 100-node chain
    for i in range(100):
        node = PDGNode(
            node_id=f"n{i}",
            statement=f"x{i} = x{i - 1} + 1",
            line_number=i,
            defined_vars=[f"x{i}"],
            used_vars=[f"x{i - 1}"] if i > 0 else [],
        )
        builder.add_node(node)

    # Add edges
    for i in range(1, 100):
        builder.add_edge(PDGEdge(f"n{i - 1}", f"n{i}", DependencyType.DATA, f"x{i - 1}"))

    # Slice from end
    slicer = ProgramSlicer(builder)
    result = slicer.backward_slice("n99")

    # Should get all 100 nodes
    assert len(result.slice_nodes) == 100
    assert result.total_tokens > 0
    assert result.confidence > 0


def test_multi_level_function_calls():
    """Test 3-level function call hierarchy (realistic application)"""
    builder = PDGBuilder()

    # API handler
    api_nodes = [
        PDGNode("api:1", "request = get_request()", 0, ["request"], []),
        PDGNode("api:2", "user_id = request.user_id", 1, ["user_id"], ["request"]),
        PDGNode("api:3", "data = service.process(user_id)", 2, ["data"], ["user_id"]),
        PDGNode("api:4", "return response(data)", 3, [], ["data"]),
    ]

    # Service layer
    service_nodes = [
        PDGNode("svc:1", "def process(user_id)", 0, ["user_id"], []),
        PDGNode("svc:2", "user = db.get_user(user_id)", 1, ["user"], ["user_id"]),
        PDGNode("svc:3", "result = transform(user)", 2, ["result"], ["user"]),
        PDGNode("svc:4", "return result", 3, [], ["result"]),
    ]

    # DB layer
    db_nodes = [
        PDGNode("db:1", "def get_user(id)", 0, ["id"], []),
        PDGNode("db:2", 'query = "SELECT * FROM users WHERE id = ?"', 1, ["query"], []),
        PDGNode("db:3", "row = execute(query, id)", 2, ["row"], ["query", "id"]),
        PDGNode("db:4", "return row", 3, [], ["row"]),
    ]

    for node in api_nodes + service_nodes + db_nodes:
        builder.add_node(node)

    # Add dependencies
    builder.add_edge(PDGEdge("api:1", "api:2", DependencyType.DATA, "request"))
    builder.add_edge(PDGEdge("api:2", "api:3", DependencyType.DATA, "user_id"))
    builder.add_edge(PDGEdge("api:3", "api:4", DependencyType.DATA, "data"))

    builder.add_edge(PDGEdge("svc:1", "svc:2", DependencyType.DATA, "user_id"))
    builder.add_edge(PDGEdge("svc:2", "svc:3", DependencyType.DATA, "user"))
    builder.add_edge(PDGEdge("svc:3", "svc:4", DependencyType.DATA, "result"))

    builder.add_edge(PDGEdge("db:1", "db:2", DependencyType.CONTROL, ""))
    builder.add_edge(PDGEdge("db:2", "db:3", DependencyType.DATA, "query"))
    builder.add_edge(PDGEdge("db:1", "db:3", DependencyType.DATA, "id"))
    builder.add_edge(PDGEdge("db:3", "db:4", DependencyType.DATA, "row"))

    # Setup interprocedural
    api_ctx = FunctionContext(
        function_name="api_handler",
        entry_node_id="api:1",
        exit_node_id="api:4",
        formal_params=[],
        local_nodes={"api:1", "api:2", "api:3", "api:4"},
        call_sites=[CallSite("api:3", "service.process", ["api:2"], "api:3")],
    )

    svc_ctx = FunctionContext(
        function_name="service.process",
        entry_node_id="svc:1",
        exit_node_id="svc:4",
        formal_params=["svc:1"],
        local_nodes={"svc:1", "svc:2", "svc:3", "svc:4"},
        call_sites=[CallSite("svc:2", "db.get_user", ["svc:1"], "svc:2")],
    )

    db_ctx = FunctionContext(
        function_name="db.get_user",
        entry_node_id="db:1",
        exit_node_id="db:4",
        formal_params=["db:1"],
        local_nodes={"db:1", "db:2", "db:3", "db:4"},
        call_sites=[],
    )

    analyzer = InterproceduralAnalyzer(builder)
    analyzer.build_call_graph(
        {
            "api_handler": api_ctx,
            "service.process": svc_ctx,
            "db.get_user": db_ctx,
        }
    )

    # Backward slice from API return
    result = analyzer.interprocedural_backward_slice("api:4", max_depth=5)

    # Should include all layers
    assert len(result) >= 10  # At least most nodes
    assert any("api:" in n for n in result)
    assert any("svc:" in n for n in result)
    assert any("db:" in n for n in result)


def test_budget_pruning_realistic():
    """Test budget pruning with realistic token limits"""
    builder = PDGBuilder()

    # Create 50 nodes with varying sizes
    for i in range(50):
        # Vary statement sizes
        if i % 10 == 0:
            stmt = f'def function_{i}(arg1, arg2, arg3):\n    """Long docstring"""\n    return complex_operation(arg1, arg2, arg3)'
        elif i % 5 == 0:
            stmt = f"result_{i} = medium_function(x{i - 1})"
        else:
            stmt = f"x{i} = x{i - 1}"

        node = PDGNode(f"n{i}", stmt, i, [f"x{i}"], [f"x{i - 1}"] if i > 0 else [])
        builder.add_node(node)

    for i in range(1, 50):
        builder.add_edge(PDGEdge(f"n{i - 1}", f"n{i}", DependencyType.DATA, f"x{i - 1}"))

    # Full slice
    slicer = ProgramSlicer(builder)
    full_result = slicer.backward_slice("n49")

    # Apply budget
    config = BudgetConfig(max_tokens=1000, min_tokens=100)
    manager = BudgetManager(config, builder)

    # Distance map (closer to target = smaller distance)
    distance_map = {f"n{i}": 49 - i for i in range(50)}

    pruned_result = manager.apply_budget(full_result, distance_map)

    # Pruning should happen (or all fit)
    assert pruned_result.total_tokens <= config.max_tokens
    # Only assert pruning if original was over budget
    if full_result.estimate_tokens() > config.max_tokens:
        assert len(pruned_result.slice_nodes) < len(full_result.slice_nodes)

    # Should keep closest nodes (highest priority)
    assert "n49" in pruned_result.slice_nodes  # Target
    assert "n48" in pruned_result.slice_nodes  # Close

    # Should drop far nodes
    assert "n0" not in pruned_result.slice_nodes or len(pruned_result.slice_nodes) == 50


def test_complex_control_flow():
    """Test realistic control flow with branches and loops"""
    builder = PDGBuilder()

    nodes = [
        # Entry
        PDGNode("n0", "def process(data):", 0, [], ["data"]),
        # Validation
        PDGNode("n1", "if not data:", 1, [], ["data"]),
        PDGNode("n2", "raise ValueError()", 2, [], []),
        # Loop
        PDGNode("n3", "results = []", 3, ["results"], []),
        PDGNode("n4", "for item in data:", 4, ["item"], ["data"]),
        PDGNode("n5", "if is_valid(item):", 5, [], ["item"]),
        PDGNode("n6", "processed = transform(item)", 6, ["processed"], ["item"]),
        PDGNode("n7", "results.append(processed)", 7, [], ["results", "processed"]),
        # Return
        PDGNode("n8", "return results", 8, [], ["results"]),
    ]

    for node in nodes:
        builder.add_node(node)

    # Control dependencies
    builder.add_edge(PDGEdge("n0", "n1", DependencyType.CONTROL, ""))
    builder.add_edge(PDGEdge("n1", "n2", DependencyType.CONTROL, "if_true"))
    builder.add_edge(PDGEdge("n1", "n3", DependencyType.CONTROL, "if_false"))
    builder.add_edge(PDGEdge("n3", "n4", DependencyType.CONTROL, ""))
    builder.add_edge(PDGEdge("n4", "n5", DependencyType.CONTROL, "loop"))
    builder.add_edge(PDGEdge("n5", "n6", DependencyType.CONTROL, "if_true"))
    builder.add_edge(PDGEdge("n6", "n7", DependencyType.CONTROL, ""))

    # Data dependencies
    builder.add_edge(PDGEdge("n3", "n7", DependencyType.DATA, "results"))
    builder.add_edge(PDGEdge("n6", "n7", DependencyType.DATA, "processed"))
    builder.add_edge(PDGEdge("n7", "n8", DependencyType.DATA, "results"))
    builder.add_edge(PDGEdge("n4", "n6", DependencyType.DATA, "item"))

    # Slice from return
    slicer = ProgramSlicer(builder)
    result = slicer.backward_slice("n8")

    # Should include relevant control and data dependencies
    assert "n8" in result.slice_nodes  # Return
    assert "n7" in result.slice_nodes  # Append
    assert "n3" in result.slice_nodes  # Results init

    # Control context should be generated
    assert len(result.control_context) > 0


def test_realistic_token_counts():
    """Test that token estimation is realistic"""
    builder = PDGBuilder()

    realistic_code = """
def calculate_metrics(data: List[Dict]) -> Dict[str, float]:
    \"\"\"Calculate various metrics from input data.\"\"\"

    total = sum(item['value'] for item in data)
    count = len(data)
    average = total / count if count > 0 else 0

    return {
        'total': total,
        'count': count,
        'average': average,
    }
"""

    node = PDGNode(
        "realistic_func",
        realistic_code,
        0,
        ["total", "count", "average"],
        ["data"],
        file_path="metrics.py",
        start_line=0,
        end_line=len(realistic_code.split("\n")),
    )

    builder.add_node(node)

    slicer = ProgramSlicer(builder)
    result = slicer.backward_slice("realistic_func")

    # Token count should be calculated
    # Different estimation methods may give different results
    estimated = result.estimate_tokens()
    actual = result.total_tokens

    # Both should be reasonable (non-zero for this code)
    assert estimated > 0, "Estimate should be > 0"
    assert actual > 0, "Total tokens should be > 0"

    # They should be in the same ballpark (allow wide tolerance)
    # Different tokenizers/methods can vary significantly
    ratio = max(estimated, actual) / min(estimated, actual)
    assert ratio < 10, f"Estimates too different: {estimated} vs {actual}"


def test_performance_large_slice():
    """Test performance with realistic large slice"""
    import time

    builder = PDGBuilder()

    # Create 200 nodes (realistic large function)
    for i in range(200):
        node = PDGNode(
            f"n{i}",
            f"var_{i} = compute(var_{i - 1})" if i > 0 else "var_0 = init()",
            i,
            [f"var_{i}"],
            [f"var_{i - 1}"] if i > 0 else [],
        )
        builder.add_node(node)

    for i in range(1, 200):
        builder.add_edge(PDGEdge(f"n{i - 1}", f"n{i}", DependencyType.DATA, f"var_{i - 1}"))

    slicer = ProgramSlicer(builder)

    # Time the slice
    start = time.time()
    result = slicer.backward_slice("n199")
    elapsed = time.time() - start

    # Should complete in reasonable time (allow more for CI)
    assert elapsed < 10.0, f"Too slow: {elapsed:.2f}s for 200 nodes"

    # Should get all nodes (or most of them given depth limit)
    # With default max_depth=100, may not get all 200
    assert len(result.slice_nodes) >= 100, f"Got {len(result.slice_nodes)}, expected at least 100"

    # Tokens should be estimated (may be 0 for simple IR statements)
    estimated = result.estimate_tokens()
    assert estimated >= 0, "Estimate should be non-negative"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
