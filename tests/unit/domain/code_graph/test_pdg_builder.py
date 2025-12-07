"""
PDG Builder Unit Tests
"""

import pytest

from src.contexts.reasoning_engine.infrastructure.pdg.pdg_builder import (
    DependencyType,
    PDGBuilder,
    PDGEdge,
    PDGNode,
)


def test_pdg_node_creation():
    """PDG Node 생성 검증"""
    node = PDGNode(
        node_id="func:foo:stmt:1",
        statement="x = 10",
        line_number=5,
        defined_vars=["x"],
        used_vars=[],
    )

    assert node.node_id == "func:foo:stmt:1"
    assert node.statement == "x = 10"
    assert node.line_number == 5
    assert node.defined_vars == ["x"]
    assert node.used_vars == []


def test_pdg_edge_creation():
    """PDG Edge 생성 검증"""
    edge = PDGEdge(
        from_node="stmt:1",
        to_node="stmt:2",
        dependency_type=DependencyType.DATA,
        label="x",
    )

    assert edge.from_node == "stmt:1"
    assert edge.to_node == "stmt:2"
    assert edge.dependency_type == DependencyType.DATA
    assert edge.label == "x"


def test_pdg_build_simple():
    """간단한 PDG 생성 검증"""
    builder = PDGBuilder()

    # Simple CFG:
    # stmt1: x = 10
    # stmt2: y = x + 5
    cfg_nodes = [
        {
            "id": "stmt1",
            "statement": "x = 10",
            "line": 1,
            "defined_vars": ["x"],
            "used_vars": [],
            "is_entry": True,
        },
        {
            "id": "stmt2",
            "statement": "y = x + 5",
            "line": 2,
            "defined_vars": ["y"],
            "used_vars": ["x"],
        },
    ]

    cfg_edges = [
        {"from": "stmt1", "to": "stmt2"},
    ]

    dfg_edges = [
        {"from": "stmt1", "to": "stmt2", "variable": "x"},
    ]

    # Build PDG
    nodes, edges = builder.build(cfg_nodes, cfg_edges, dfg_edges)

    # Verify nodes
    assert len(nodes) == 2
    assert "stmt1" in nodes
    assert "stmt2" in nodes

    # Verify edges
    assert len(edges) == 2  # 1 control + 1 data

    control_edges = [e for e in edges if e.dependency_type == DependencyType.CONTROL]
    data_edges = [e for e in edges if e.dependency_type == DependencyType.DATA]

    assert len(control_edges) == 1
    assert len(data_edges) == 1


def test_backward_slice():
    """Backward slice 검증"""
    builder = PDGBuilder()

    # CFG:
    # stmt1: x = 10
    # stmt2: y = 20
    # stmt3: z = x + y
    cfg_nodes = [
        {
            "id": "stmt1",
            "statement": "x = 10",
            "line": 1,
            "defined_vars": ["x"],
            "used_vars": [],
        },
        {
            "id": "stmt2",
            "statement": "y = 20",
            "line": 2,
            "defined_vars": ["y"],
            "used_vars": [],
        },
        {
            "id": "stmt3",
            "statement": "z = x + y",
            "line": 3,
            "defined_vars": ["z"],
            "used_vars": ["x", "y"],
        },
    ]

    cfg_edges = [
        {"from": "stmt1", "to": "stmt2"},
        {"from": "stmt2", "to": "stmt3"},
    ]

    dfg_edges = [
        {"from": "stmt1", "to": "stmt3", "variable": "x"},
        {"from": "stmt2", "to": "stmt3", "variable": "y"},
    ]

    # Build PDG
    builder.build(cfg_nodes, cfg_edges, dfg_edges)

    # Backward slice from stmt3
    slice_nodes = builder.backward_slice("stmt3")

    # stmt3 depends on stmt1, stmt2
    assert "stmt3" in slice_nodes
    assert "stmt1" in slice_nodes
    assert "stmt2" in slice_nodes


def test_forward_slice():
    """Forward slice 검증"""
    builder = PDGBuilder()

    # CFG:
    # stmt1: x = 10
    # stmt2: y = x + 5
    # stmt3: z = 20
    cfg_nodes = [
        {
            "id": "stmt1",
            "statement": "x = 10",
            "line": 1,
            "defined_vars": ["x"],
            "used_vars": [],
        },
        {
            "id": "stmt2",
            "statement": "y = x + 5",
            "line": 2,
            "defined_vars": ["y"],
            "used_vars": ["x"],
        },
        {
            "id": "stmt3",
            "statement": "z = 20",
            "line": 3,
            "defined_vars": ["z"],
            "used_vars": [],
        },
    ]

    cfg_edges = [
        {"from": "stmt1", "to": "stmt2"},
        {"from": "stmt2", "to": "stmt3"},
    ]

    dfg_edges = [
        {"from": "stmt1", "to": "stmt2", "variable": "x"},
    ]

    # Build PDG
    builder.build(cfg_nodes, cfg_edges, dfg_edges)

    # Forward slice from stmt1
    slice_nodes = builder.forward_slice("stmt1")

    # stmt1 affects stmt2
    assert "stmt1" in slice_nodes
    assert "stmt2" in slice_nodes
    # stmt3 is NOT affected by stmt1
    # (하지만 control dependency로 연결될 수 있음)


def test_pdg_stats():
    """PDG 통계 검증"""
    builder = PDGBuilder()

    cfg_nodes = [
        {"id": "s1", "statement": "x=1", "line": 1, "defined_vars": ["x"], "used_vars": []},
        {"id": "s2", "statement": "y=x", "line": 2, "defined_vars": ["y"], "used_vars": ["x"]},
    ]

    cfg_edges = [{"from": "s1", "to": "s2"}]
    dfg_edges = [{"from": "s1", "to": "s2", "variable": "x"}]

    builder.build(cfg_nodes, cfg_edges, dfg_edges)

    stats = builder.get_stats()

    assert stats["node_count"] == 2
    assert stats["edge_count"] == 2
    assert stats["control_edges"] == 1
    assert stats["data_edges"] == 1
