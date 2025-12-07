"""
DeltaGraph Unit Tests

Phase 2 교훈: 테스트 먼저, 모든 edge case 커버
"""

import pytest

from src.contexts.reasoning_engine.domain.speculative_models import Delta, DeltaOperation
from src.contexts.reasoning_engine.infrastructure.speculative.delta_graph import DeltaGraph
from src.contexts.reasoning_engine.infrastructure.speculative.exceptions import SimulationError


# Mock base graph
def create_base_graph():
    """Create a simple base graph for testing"""
    return {
        "nodes": {
            "n1": {"id": "n1", "name": "func1", "type": "function"},
            "n2": {"id": "n2", "name": "func2", "type": "function"},
            "n3": {"id": "n3", "name": "var1", "type": "variable"},
        },
        "edges": {
            "n1": [{"source": "n1", "target": "n2", "kind": "CALLS"}],
            "n2": [],
            "n3": [],
        },
    }


class TestDeltaGraphInit:
    """Test DeltaGraph initialization"""

    def test_init_with_base(self):
        """Initialize with base graph"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        assert delta_graph.base == base
        assert delta_graph.delta_count() == 0
        assert len(delta_graph._node_index) == 0

    def test_init_with_deltas(self):
        """Initialize with pre-existing deltas"""
        base = create_base_graph()
        deltas = [
            Delta(operation=DeltaOperation.UPDATE_NODE, node_id="n1", new_data={"name": "new_func1"}),
        ]

        delta_graph = DeltaGraph(base, deltas)

        assert delta_graph.delta_count() == 1
        assert len(delta_graph._node_index) == 1

    def test_init_with_none_base_raises(self):
        """Initialize with None base should raise"""
        with pytest.raises(SimulationError, match="Base graph cannot be None"):
            DeltaGraph(None)


class TestDeltaGraphGetNode:
    """Test node retrieval (Copy-on-Write)"""

    def test_get_base_node(self):
        """Get node from base graph"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        node = delta_graph.get_node("n1")

        assert node is not None
        assert node["name"] == "func1"

    def test_get_updated_node(self):
        """Get updated node from delta"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        # Update node
        delta_graph.apply_delta(
            Delta(
                operation=DeltaOperation.UPDATE_NODE,
                node_id="n1",
                new_data={"id": "n1", "name": "new_func1", "type": "function"},
            )
        )

        node = delta_graph.get_node("n1")

        assert node["name"] == "new_func1"

        # Base should be unchanged
        assert base["nodes"]["n1"]["name"] == "func1"

    def test_get_added_node(self):
        """Get newly added node"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(
            Delta(
                operation=DeltaOperation.ADD_NODE,
                node_id="n4",
                new_data={"id": "n4", "name": "new_func", "type": "function"},
            )
        )

        node = delta_graph.get_node("n4")

        assert node is not None
        assert node["name"] == "new_func"

    def test_get_deleted_node_returns_none(self):
        """Get deleted node should return None"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(Delta(operation=DeltaOperation.DELETE_NODE, node_id="n1"))

        node = delta_graph.get_node("n1")

        assert node is None

    def test_get_nonexistent_node_returns_none(self):
        """Get non-existent node should return None"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        node = delta_graph.get_node("nonexistent")

        assert node is None


class TestDeltaGraphGetAllNodes:
    """Test get_all_nodes (Base + Delta merge)"""

    def test_get_all_base_nodes(self):
        """Get all nodes from base"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        nodes = delta_graph.get_all_nodes()

        assert len(nodes) == 3
        assert "n1" in nodes
        assert "n2" in nodes
        assert "n3" in nodes

    def test_get_all_with_updates(self):
        """Get all nodes with updates"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(
            Delta(operation=DeltaOperation.UPDATE_NODE, node_id="n1", new_data={"name": "updated_func1"})
        )

        nodes = delta_graph.get_all_nodes()

        assert len(nodes) == 3
        assert nodes["n1"]["name"] == "updated_func1"

    def test_get_all_with_additions(self):
        """Get all nodes with additions"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(Delta(operation=DeltaOperation.ADD_NODE, node_id="n4", new_data={"name": "new_node"}))

        nodes = delta_graph.get_all_nodes()

        assert len(nodes) == 4
        assert "n4" in nodes

    def test_get_all_with_deletions(self):
        """Get all nodes with deletions"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(Delta(operation=DeltaOperation.DELETE_NODE, node_id="n1"))

        nodes = delta_graph.get_all_nodes()

        assert len(nodes) == 2
        assert "n1" not in nodes


class TestDeltaGraphApplyDelta:
    """Test delta application"""

    def test_apply_update_delta(self):
        """Apply UPDATE_NODE delta"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(Delta(operation=DeltaOperation.UPDATE_NODE, node_id="n1", new_data={"name": "updated"}))

        assert delta_graph.delta_count() == 1
        assert "n1" in delta_graph._node_index

    def test_apply_add_delta(self):
        """Apply ADD_NODE delta"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(Delta(operation=DeltaOperation.ADD_NODE, node_id="n4", new_data={"name": "new_node"}))

        assert delta_graph.delta_count() == 1
        assert "n4" in delta_graph._node_index

    def test_apply_delete_delta(self):
        """Apply DELETE_NODE delta"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(Delta(operation=DeltaOperation.DELETE_NODE, node_id="n1"))

        assert delta_graph.delta_count() == 1
        assert "n1" in delta_graph._deleted_nodes
        assert "n1" not in delta_graph._node_index

    def test_apply_invalid_delta_type_raises(self):
        """Apply invalid delta type should raise"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        with pytest.raises(SimulationError, match="Invalid delta type"):
            delta_graph.apply_delta("not a delta")

    def test_apply_multiple_deltas(self):
        """Apply multiple deltas"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(Delta(operation=DeltaOperation.UPDATE_NODE, node_id="n1", new_data={"v": 1}))
        delta_graph.apply_delta(Delta(operation=DeltaOperation.ADD_NODE, node_id="n4", new_data={"v": 2}))
        delta_graph.apply_delta(Delta(operation=DeltaOperation.DELETE_NODE, node_id="n2"))

        assert delta_graph.delta_count() == 3


class TestDeltaGraphRollback:
    """Test delta rollback"""

    def test_rollback_single_delta(self):
        """Rollback 1 delta"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(Delta(operation=DeltaOperation.UPDATE_NODE, node_id="n1", new_data={"name": "v1"}))
        delta_graph.apply_delta(Delta(operation=DeltaOperation.UPDATE_NODE, node_id="n1", new_data={"name": "v2"}))

        assert delta_graph.get_node("n1")["name"] == "v2"

        delta_graph.rollback(1)

        assert delta_graph.delta_count() == 1
        assert delta_graph.get_node("n1")["name"] == "v1"

    def test_rollback_multiple_deltas(self):
        """Rollback multiple deltas"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(Delta(operation=DeltaOperation.UPDATE_NODE, node_id="n1", new_data={"v": 1}))
        delta_graph.apply_delta(Delta(operation=DeltaOperation.UPDATE_NODE, node_id="n2", new_data={"v": 2}))
        delta_graph.apply_delta(Delta(operation=DeltaOperation.UPDATE_NODE, node_id="n3", new_data={"v": 3}))

        delta_graph.rollback(2)

        assert delta_graph.delta_count() == 1

    def test_rollback_all_deltas(self):
        """Rollback all deltas"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(Delta(operation=DeltaOperation.UPDATE_NODE, node_id="n1", new_data={"v": 1}))
        delta_graph.rollback(1)

        assert delta_graph.delta_count() == 0
        assert delta_graph.get_node("n1")["name"] == "func1"  # Back to base

    def test_rollback_zero_does_nothing(self):
        """Rollback 0 should do nothing"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(Delta(operation=DeltaOperation.UPDATE_NODE, node_id="n1", new_data={"v": 1}))

        rolled_back = delta_graph.rollback(0)

        assert len(rolled_back) == 0
        assert delta_graph.delta_count() == 1

    def test_rollback_more_than_available_raises(self):
        """Rollback more than available should raise"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(Delta(operation=DeltaOperation.UPDATE_NODE, node_id="n1", new_data={"v": 1}))

        with pytest.raises(SimulationError, match="Cannot rollback"):
            delta_graph.rollback(10)


class TestDeltaGraphMemory:
    """Test memory overhead calculation"""

    def test_memory_overhead_empty(self):
        """Memory overhead with no deltas"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        overhead = delta_graph.memory_overhead()

        assert overhead > 0  # Has indices
        assert overhead < 1000  # Should be small

    def test_memory_overhead_with_deltas(self):
        """Memory overhead with deltas"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        # Update existing nodes
        for i in range(1, 4):  # n1, n2, n3 exist in base
            delta_graph.apply_delta(
                Delta(
                    DeltaOperation.UPDATE_NODE,
                    f"n{i}",
                    {"data": "x" * 100},  # Some data
                )
            )

        overhead = delta_graph.memory_overhead()

        assert overhead > 300  # Should have grown


class TestDeltaGraphHelpers:
    """Test helper methods"""

    def test_is_modified_true(self):
        """is_modified returns True for modified node"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        delta_graph.apply_delta(Delta(operation=DeltaOperation.UPDATE_NODE, node_id="n1", new_data={}))

        assert delta_graph.is_modified("n1") is True

    def test_is_modified_false(self):
        """is_modified returns False for unmodified node"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        assert delta_graph.is_modified("n1") is False

    def test_repr(self):
        """__repr__ returns meaningful string"""
        base = create_base_graph()
        delta_graph = DeltaGraph(base)

        repr_str = repr(delta_graph)

        assert "DeltaGraph" in repr_str
        assert "deltas=0" in repr_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
