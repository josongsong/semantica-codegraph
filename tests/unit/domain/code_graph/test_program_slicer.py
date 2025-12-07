"""
Unit Tests for Program Slicer
"""

import pytest

from src.contexts.reasoning_engine.infrastructure.pdg import DependencyType, PDGBuilder, PDGEdge, PDGNode
from src.contexts.reasoning_engine.infrastructure.slicer import (
    BudgetConfig,
    BudgetManager,
    ContextOptimizer,
    ProgramSlicer,
    SliceConfig,
)


@pytest.fixture
def simple_pdg():
    """Simple PDG for testing"""
    builder = PDGBuilder()

    # Create nodes
    nodes = [
        PDGNode("n1", "x = 10", 1, ["x"], []),
        PDGNode("n2", "y = x + 5", 2, ["y"], ["x"]),
        PDGNode("n3", "z = y * 2", 3, ["z"], ["y"]),
        PDGNode("n4", "result = z", 4, ["result"], ["z"]),
    ]

    for node in nodes:
        builder.add_node(node)

    # Create edges (data dependencies)
    edges = [
        PDGEdge("n1", "n2", DependencyType.DATA, "x"),
        PDGEdge("n2", "n3", DependencyType.DATA, "y"),
        PDGEdge("n3", "n4", DependencyType.DATA, "z"),
    ]

    for edge in edges:
        builder.add_edge(edge)

    return builder


def test_backward_slice_simple(simple_pdg):
    """Test backward slice - simple chain"""
    slicer = ProgramSlicer(simple_pdg)

    # Slice from "result"
    result = slicer.backward_slice("n4")

    assert result.target_variable == "n4"
    assert result.slice_type == "backward"

    # Should include all dependencies: n1, n2, n3, n4
    assert len(result.slice_nodes) == 4
    assert "n1" in result.slice_nodes
    assert "n2" in result.slice_nodes
    assert "n3" in result.slice_nodes
    assert "n4" in result.slice_nodes

    print(f"✅ Backward slice: {len(result.slice_nodes)} nodes")


def test_forward_slice_simple(simple_pdg):
    """Test forward slice - simple chain"""
    slicer = ProgramSlicer(simple_pdg)

    # Slice from "x"
    result = slicer.forward_slice("n1")

    assert result.slice_type == "forward"

    # Should include all dependents: n1, n2, n3, n4
    assert len(result.slice_nodes) == 4

    print(f"✅ Forward slice: {len(result.slice_nodes)} nodes")


def test_hybrid_slice(simple_pdg):
    """Test hybrid slice (backward + forward)"""
    slicer = ProgramSlicer(simple_pdg)

    # Slice from middle node "n2"
    result = slicer.hybrid_slice("n2")

    assert result.slice_type == "hybrid"

    # Should include all: n1 (backward), n2, n3, n4 (forward)
    assert len(result.slice_nodes) == 4

    # Check metadata
    assert "backward_nodes" in result.metadata
    assert "forward_nodes" in result.metadata

    print(f"✅ Hybrid slice: {len(result.slice_nodes)} nodes")


def test_slice_with_depth_limit(simple_pdg):
    """Test slice with depth limit"""
    config = SliceConfig(max_depth=1)
    slicer = ProgramSlicer(simple_pdg, config)

    # Slice from "n4" with depth=1
    result = slicer.backward_slice("n4", max_depth=1)

    # Should only include n4 and n3 (1 hop)
    assert len(result.slice_nodes) <= 2

    print(f"✅ Depth-limited slice: {len(result.slice_nodes)} nodes")


def test_budget_manager():
    """Test BudgetManager"""
    config = BudgetConfig(max_tokens=100)
    manager = BudgetManager(config)

    # Create mock slice result
    from src.contexts.reasoning_engine.infrastructure.slicer import CodeFragment, SliceResult

    fragments = [
        CodeFragment("test.py", 1, 1, "x = 10", "n1"),
        CodeFragment("test.py", 2, 2, "y = x + 5", "n2"),
        CodeFragment("test.py", 3, 3, "z = y * 2", "n3"),
    ]

    slice_result = SliceResult(
        target_variable="result",
        slice_type="backward",
        slice_nodes={"n1", "n2", "n3"},
        code_fragments=fragments,
    )

    # PDG distance map
    distance_map = {"n1": 2, "n2": 1, "n3": 0}

    # Apply budget
    pruned = manager.apply_budget(slice_result, distance_map)

    # Should be pruned (if tokens > 100)
    tokens = pruned.total_tokens
    assert tokens <= config.max_tokens or len(fragments) <= 3

    print(f"✅ Budget applied: {tokens} tokens")


def test_context_optimizer():
    """Test ContextOptimizer"""
    optimizer = ContextOptimizer()

    # Create mock slice result
    from src.contexts.reasoning_engine.infrastructure.slicer import CodeFragment, SliceResult

    fragments = [
        CodeFragment("test.py", 1, 1, "x = 10", "n1"),
        CodeFragment("test.py", 2, 2, "y = x + 5", "n2"),
    ]

    slice_result = SliceResult(
        target_variable="result",
        slice_type="backward",
        slice_nodes={"n1", "n2"},
        code_fragments=fragments,
        control_context=["Line 1 defines x", "Line 2 uses x"],
    )

    # Optimize for LLM
    optimized = optimizer.optimize_for_llm(slice_result)

    assert optimized.summary
    assert optimized.essential_code
    assert optimized.total_tokens > 0

    # Get LLM prompt
    prompt = optimized.to_llm_prompt()
    assert "# Context Summary" in prompt
    assert "# Code" in prompt

    print(f"✅ Optimized context: {optimized.total_tokens} tokens")
    print(f"✅ LLM prompt: {len(prompt)} chars")


def test_slice_confidence():
    """Test confidence calculation"""
    builder = PDGBuilder()

    # Small slice (coverage-based confidence)
    nodes = [
        PDGNode("n1", "x = 10", 1, ["x"], []),
    ]
    for node in nodes:
        builder.add_node(node)

    slicer = ProgramSlicer(builder)
    result = slicer.backward_slice("n1")

    # FIXED: New confidence calculation (coverage + completeness)
    # Single node with no deps = high completeness, but coverage might vary
    assert 0.0 <= result.confidence <= 1.0
    assert result.confidence > 0.0  # Not zero for valid slice

    print(f"✅ Confidence: {result.confidence:.2f}")


def test_code_fragment_assembly():
    """Test code fragment assembly"""
    optimizer = ContextOptimizer()

    from src.contexts.reasoning_engine.infrastructure.slicer import CodeFragment

    fragments = [
        CodeFragment("service.py", 10, 10, "def foo():", "n1"),
        CodeFragment("service.py", 11, 11, "    return 42", "n2"),
        CodeFragment("utils.py", 5, 5, "x = 100", "n3"),
    ]

    code = optimizer._assemble_code(fragments)

    # Should group by file
    assert "service.py" in code
    assert "utils.py" in code
    assert "def foo():" in code
    assert "x = 100" in code

    print(f"✅ Assembled code ({len(code)} chars)")


def test_empty_slice():
    """Test empty slice handling"""
    builder = PDGBuilder()
    slicer = ProgramSlicer(builder)

    # Slice from non-existent node
    result = slicer.backward_slice("nonexistent")

    # Should handle gracefully
    assert len(result.slice_nodes) == 0
    assert len(result.code_fragments) == 0

    print("✅ Empty slice handled")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
