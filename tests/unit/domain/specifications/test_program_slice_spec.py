"""
RFC-06-TEST-SPEC: Program Slice Engine Tests

Based on Section 8 of RFC-06-TEST-SPEC.
"""

import time

import pytest

from src.contexts.reasoning_engine.infrastructure.pdg.pdg_builder import DependencyType, PDGBuilder, PDGEdge, PDGNode
from src.contexts.reasoning_engine.infrastructure.slicer.slicer import ProgramSlicer


def test_sl_01_backward_slice():
    """
    SL-01: Backward Slice

    Given: r = w + 1; w = y + 1; y = a(z); z = x + 1
    Target: r
    Expected: z→a(z)→y→w→r (full chain)
    """
    builder = PDGBuilder()

    nodes = [
        PDGNode("n1", "z = x + 1", 0, ["z"], ["x"]),
        PDGNode("n2", "y = a(z)", 1, ["y"], ["z"]),
        PDGNode("n3", "w = y + 1", 2, ["w"], ["y"]),
        PDGNode("n4", "r = w + 1", 3, ["r"], ["w"]),
    ]

    for node in nodes:
        builder.add_node(node)

    # Build dependency chain
    builder.add_edge(PDGEdge("n1", "n2", DependencyType.DATA, "z"))
    builder.add_edge(PDGEdge("n2", "n3", DependencyType.DATA, "y"))
    builder.add_edge(PDGEdge("n3", "n4", DependencyType.DATA, "w"))

    # Backward slice from r
    slicer = ProgramSlicer(builder)
    result = slicer.backward_slice("n4")

    # Verification
    assert result.slice_nodes == {"n1", "n2", "n3", "n4"}, f"Expected full chain, got {result.slice_nodes}"

    assert result.slice_type == "backward"
    assert result.confidence > 0


def test_sl_02_forward_slice():
    """
    SL-02: Forward Slice

    Given: y = x + 1; z = x * 2; log(x)
    Target: x
    Expected: y, z, log all included
    """
    builder = PDGBuilder()

    nodes = [
        PDGNode("x", "x = 10", 0, ["x"], []),
        PDGNode("y", "y = x + 1", 1, ["y"], ["x"]),
        PDGNode("z", "z = x * 2", 2, ["z"], ["x"]),
        PDGNode("log", "log(x)", 3, [], ["x"]),
    ]

    for node in nodes:
        builder.add_node(node)

    # Forward dependencies
    builder.add_edge(PDGEdge("x", "y", DependencyType.DATA, "x"))
    builder.add_edge(PDGEdge("x", "z", DependencyType.DATA, "x"))
    builder.add_edge(PDGEdge("x", "log", DependencyType.DATA, "x"))

    # Forward slice from x
    slicer = ProgramSlicer(builder)
    result = slicer.forward_slice("x")

    # Verification
    assert "y" in result.slice_nodes, "y should be affected by x"
    assert "z" in result.slice_nodes, "z should be affected by x"
    assert "log" in result.slice_nodes, "log should be affected by x"

    assert result.slice_type == "forward"


def test_minimum_slice():
    """
    Verification: Minimum slice maintained

    Slice should not include unnecessary nodes.
    """
    builder = PDGBuilder()

    # x affects y, y affects z
    # unrelated: a, b
    nodes = [
        PDGNode("x", "x = 1", 0, ["x"], []),
        PDGNode("y", "y = x + 1", 1, ["y"], ["x"]),
        PDGNode("z", "z = y + 1", 2, ["z"], ["y"]),
        PDGNode("a", "a = 100", 3, ["a"], []),  # Unrelated
        PDGNode("b", "b = a + 1", 4, ["b"], ["a"]),  # Unrelated
    ]

    for node in nodes:
        builder.add_node(node)

    builder.add_edge(PDGEdge("x", "y", DependencyType.DATA, "x"))
    builder.add_edge(PDGEdge("y", "z", DependencyType.DATA, "y"))
    builder.add_edge(PDGEdge("a", "b", DependencyType.DATA, "a"))

    slicer = ProgramSlicer(builder)
    result = slicer.backward_slice("z")

    # Should only include x, y, z (not a, b)
    assert result.slice_nodes == {"x", "y", "z"}, f"Slice should be minimal, got {result.slice_nodes}"


def test_control_dependency_included():
    """
    Verification: Control dependency included in slice
    """
    builder = PDGBuilder()

    nodes = [
        PDGNode("cond", "if x > 0:", 0, [], ["x"]),
        PDGNode("then", "y = x + 1", 1, ["y"], ["x"]),
        PDGNode("use", "print(y)", 2, [], ["y"]),
    ]

    for node in nodes:
        builder.add_node(node)

    # Control + Data dependencies
    builder.add_edge(PDGEdge("cond", "then", DependencyType.CONTROL, "if"))
    builder.add_edge(PDGEdge("then", "use", DependencyType.DATA, "y"))

    slicer = ProgramSlicer(builder)
    result = slicer.backward_slice("use")

    # Should include control dependency
    assert "cond" in result.slice_nodes, "Control dependency should be included"
    assert len(result.control_context) > 0, "Control context should be generated"


def test_parseable_code():
    """
    Verification: Sliced code is parseable
    """
    builder = PDGBuilder()

    # Real Python code
    nodes = [
        PDGNode("n1", "def foo():\n    x = 1\n    return x", 0, ["x"], []),
    ]

    for node in nodes:
        builder.add_node(node)

    slicer = ProgramSlicer(builder)
    result = slicer.backward_slice("n1")

    # Code should be valid
    for fragment in result.code_fragments:
        assert len(fragment.code) > 0
        # Should not have syntax errors (basic check)
        assert fragment.code.count("(") == fragment.code.count(")")


def test_determinism():
    """
    Verification: Same input → Same output

    Run slice 3 times, should get identical results.
    """
    builder = PDGBuilder()

    for i in range(5):
        node = PDGNode(
            f"n{i}", f"x{i} = x{i - 1} + 1" if i > 0 else "x0 = 0", i, [f"x{i}"], [f"x{i - 1}"] if i > 0 else []
        )
        builder.add_node(node)

    for i in range(1, 5):
        builder.add_edge(PDGEdge(f"n{i - 1}", f"n{i}", DependencyType.DATA, f"x{i - 1}"))

    slicer = ProgramSlicer(builder)

    # Run 3 times
    results = []
    for _ in range(3):
        result = slicer.backward_slice("n4")
        results.append(result)

    # All should be identical
    for i in range(1, 3):
        assert results[i].slice_nodes == results[0].slice_nodes, f"Non-deterministic: run {i} differs from run 0"
        assert results[i].total_tokens == results[0].total_tokens


def test_performance_baseline():
    """
    Performance: Slice extraction < 20ms

    Test with realistic 50-node graph.
    """
    builder = PDGBuilder()

    # 50 nodes
    for i in range(50):
        node = PDGNode(f"n{i}", f"x{i} = compute()", i, [f"x{i}"], [f"x{i - 1}"] if i > 0 else [])
        builder.add_node(node)

    for i in range(1, 50):
        builder.add_edge(PDGEdge(f"n{i - 1}", f"n{i}", DependencyType.DATA, f"x{i - 1}"))

    slicer = ProgramSlicer(builder)

    # Measure time
    start = time.time()
    result = slicer.backward_slice("n49")
    elapsed = (time.time() - start) * 1000  # ms

    # Should be < 20ms
    assert elapsed < 20, f"Too slow: {elapsed:.2f}ms > 20ms"
    assert len(result.slice_nodes) == 50


def test_regression_safety():
    """
    Regression: Hash comparison

    If implementation changes, result hash should be same.
    """
    builder = PDGBuilder()

    nodes = [
        PDGNode("a", "a = 1", 0, ["a"], []),
        PDGNode("b", "b = a + 1", 1, ["b"], ["a"]),
        PDGNode("c", "c = b + 1", 2, ["c"], ["b"]),
    ]

    for node in nodes:
        builder.add_node(node)

    builder.add_edge(PDGEdge("a", "b", DependencyType.DATA, "a"))
    builder.add_edge(PDGEdge("b", "c", DependencyType.DATA, "b"))

    slicer = ProgramSlicer(builder)
    result = slicer.backward_slice("c")

    # Create hash of result
    result_hash = hash(frozenset(result.slice_nodes))

    # Expected hash (record this)
    expected_hash = hash(frozenset({"a", "b", "c"}))

    assert result_hash == expected_hash, f"Regression detected: hash changed from {expected_hash} to {result_hash}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
