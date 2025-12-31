"""
Impact Models Tests

Test Coverage:
- ImpactLevel enum
- ImpactNode, ImpactPath
- Propagation types
"""

import pytest

from codegraph_engine.reasoning_engine.domain.impact_models import (
    ImpactLevel,
    ImpactNode,
    ImpactPath,
    PropagationType,
)


class TestImpactLevel:
    """ImpactLevel enum tests"""

    def test_all_levels_defined(self):
        """All impact levels exist"""
        assert ImpactLevel.NONE.value == "none"
        assert ImpactLevel.LOW.value == "low"
        assert ImpactLevel.MEDIUM.value == "medium"
        assert ImpactLevel.HIGH.value == "high"
        assert ImpactLevel.CRITICAL.value == "critical"

    def test_level_ordering(self):
        """Levels have logical ordering"""
        levels = list(ImpactLevel)
        assert levels.index(ImpactLevel.NONE) < levels.index(ImpactLevel.CRITICAL)


class TestPropagationType:
    """PropagationType enum tests"""

    def test_propagation_types_defined(self):
        """Propagation types exist"""
        assert PropagationType.DIRECT_CALL.value == "direct_call"
        assert PropagationType.INDIRECT_CALL.value == "indirect_call"
        assert PropagationType.DATA_FLOW.value == "data_flow"

    def test_all_propagation_types(self):
        """All propagation types"""
        assert PropagationType.TYPE_DEPENDENCY.value == "type_dependency"
        assert PropagationType.INHERITANCE.value == "inheritance"
        assert PropagationType.IMPORT.value == "import"


class TestImpactNode:
    """ImpactNode model tests"""

    def test_create_impact_node(self):
        """Create impact node"""
        node = ImpactNode(
            symbol_id="module.func",
            name="func",
            kind="function",
            file_path="module.py",
            impact_level=ImpactLevel.HIGH,
        )
        assert node.symbol_id == "module.func"
        assert node.impact_level == ImpactLevel.HIGH

    def test_impact_node_with_distance(self):
        """Impact node with distance"""
        node = ImpactNode(
            symbol_id="module.Class.method",
            name="method",
            kind="method",
            file_path="module.py",
            impact_level=ImpactLevel.MEDIUM,
            distance=2,
        )
        assert node.distance == 2

    def test_impact_node_defaults(self):
        """Impact node default values"""
        node = ImpactNode(
            symbol_id="test",
            name="test",
            kind="function",
            file_path="test.py",
        )
        assert node.impact_level == ImpactLevel.NONE
        assert node.distance == 0
        assert node.confidence == 1.0


class TestImpactPath:
    """ImpactPath model tests"""

    def test_create_impact_path(self):
        """Create impact path"""
        path = ImpactPath(
            source="module.changed_func",
            target="module.affected_func",
            nodes=["module.changed_func", "module.helper", "module.affected_func"],
        )
        assert len(path.nodes) == 3
        assert path.source == "module.changed_func"
        assert path.target == "module.affected_func"

    def test_path_length(self):
        """Path length calculation"""
        path = ImpactPath(
            source="a",
            target="d",
            nodes=["a", "b", "c", "d"],
        )
        assert len(path.nodes) == 4


class TestEdgeCases:
    """Edge cases"""

    def test_self_impact(self):
        """Symbol impacts itself"""
        node = ImpactNode(
            symbol_id="module.self_referencing",
            name="self_referencing",
            kind="function",
            file_path="module.py",
            impact_level=ImpactLevel.LOW,
        )
        assert node.symbol_id == "module.self_referencing"

    def test_circular_path(self):
        """Circular impact path"""
        path = ImpactPath(
            source="a",
            target="a",
            nodes=["a", "b", "c", "a"],
        )
        assert path.source == path.target

    def test_long_path(self):
        """Long impact path"""
        nodes = [f"node_{i}" for i in range(100)]
        path = ImpactPath(
            source=nodes[0],
            target=nodes[-1],
            nodes=nodes,
        )
        assert len(path.nodes) == 100

    def test_node_hashable(self):
        """ImpactNode is hashable"""
        node1 = ImpactNode("id1", "n", "f", "p.py")
        node2 = ImpactNode("id1", "n", "f", "p.py")
        assert hash(node1) == hash(node2)
        assert len({node1, node2}) == 1
