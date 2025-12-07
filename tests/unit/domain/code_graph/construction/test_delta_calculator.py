"""
Tests for Graph Delta Calculator

Tests delta calculation between old and new graph states.
"""

import pytest
from src.graph_construction.domain import (
    EdgeType,
    GraphDeltaOp,
    GraphEdgeRecord,
    GraphNodeRecord,
    NodeKind,
)
from src.infra.graph_construction import GraphDeltaCalculator


class TestGraphDeltaCalculatorNodes:
    """Test node delta calculation"""

    @pytest.fixture
    def calculator(self):
        return GraphDeltaCalculator()

    def test_insert_node(self, calculator):
        """Test: 새 노드 삽입 감지"""
        old_nodes = []
        new_nodes = [
            GraphNodeRecord(
                id="py://pkg.module.Foo",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.CLASS,
                attrs={"name": "Foo"},
            )
        ]

        deltas = calculator.calculate_deltas(old_nodes, [], new_nodes, [])

        node_deltas = [d for d in deltas if d.kind == "node"]
        assert len(node_deltas) == 1
        assert node_deltas[0].op == GraphDeltaOp.INSERT
        assert node_deltas[0].record.id == "py://pkg.module.Foo"

    def test_delete_node(self, calculator):
        """Test: 노드 삭제 감지"""
        old_nodes = [
            GraphNodeRecord(
                id="py://pkg.module.Bar",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.FUNCTION,
                attrs={"name": "Bar"},
            )
        ]
        new_nodes = []

        deltas = calculator.calculate_deltas(old_nodes, [], new_nodes, [])

        node_deltas = [d for d in deltas if d.kind == "node"]
        assert len(node_deltas) == 1
        assert node_deltas[0].op == GraphDeltaOp.DELETE
        assert node_deltas[0].record.id == "py://pkg.module.Bar"

    def test_update_node_attrs(self, calculator):
        """Test: 노드 attrs 변경 감지"""
        old_nodes = [
            GraphNodeRecord(
                id="py://pkg.module.Baz",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.FUNCTION,
                attrs={"name": "Baz", "param_count": 1},
            )
        ]
        new_nodes = [
            GraphNodeRecord(
                id="py://pkg.module.Baz",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.FUNCTION,
                attrs={"name": "Baz", "param_count": 2},  # changed
            )
        ]

        deltas = calculator.calculate_deltas(old_nodes, [], new_nodes, [])

        node_deltas = [d for d in deltas if d.kind == "node"]
        assert len(node_deltas) == 1
        assert node_deltas[0].op == GraphDeltaOp.UPDATE
        assert node_deltas[0].record.id == "py://pkg.module.Baz"

    def test_no_change_node(self, calculator):
        """Test: 변경 없는 노드는 delta 없음"""
        node = GraphNodeRecord(
            id="py://pkg.module.Qux",
            repo_id="test_repo",
            namespace="main",
            kind=NodeKind.CLASS,
            attrs={"name": "Qux"},
        )
        old_nodes = [node]
        new_nodes = [node]

        deltas = calculator.calculate_deltas(old_nodes, [], new_nodes, [])

        node_deltas = [d for d in deltas if d.kind == "node"]
        assert len(node_deltas) == 0


class TestGraphDeltaCalculatorEdges:
    """Test edge delta calculation"""

    @pytest.fixture
    def calculator(self):
        return GraphDeltaCalculator()

    def test_insert_edge(self, calculator):
        """Test: 새 엣지 삽입 감지"""
        old_edges = []
        new_edges = [
            GraphEdgeRecord(
                id="edge:1",
                repo_id="test_repo",
                namespace="main",
                src_id="py://pkg.A",
                dst_id="py://pkg.B",
                edge_type=EdgeType.CALLS,
                attrs={},
            )
        ]

        deltas = calculator.calculate_deltas([], old_edges, [], new_edges)

        edge_deltas = [d for d in deltas if d.kind == "edge"]
        assert len(edge_deltas) == 1
        assert edge_deltas[0].op == GraphDeltaOp.INSERT
        assert edge_deltas[0].record.id == "edge:1"

    def test_delete_edge(self, calculator):
        """Test: 엣지 삭제 감지"""
        old_edges = [
            GraphEdgeRecord(
                id="edge:2",
                repo_id="test_repo",
                namespace="main",
                src_id="py://pkg.C",
                dst_id="py://pkg.D",
                edge_type=EdgeType.DEFINES,
                attrs={},
            )
        ]
        new_edges = []

        deltas = calculator.calculate_deltas([], old_edges, [], new_edges)

        edge_deltas = [d for d in deltas if d.kind == "edge"]
        assert len(edge_deltas) == 1
        assert edge_deltas[0].op == GraphDeltaOp.DELETE
        assert edge_deltas[0].record.id == "edge:2"

    def test_update_edge_attrs(self, calculator):
        """Test: 엣지 attrs 변경 감지"""
        old_edges = [
            GraphEdgeRecord(
                id="edge:3",
                repo_id="test_repo",
                namespace="main",
                src_id="py://pkg.E",
                dst_id="py://pkg.F",
                edge_type=EdgeType.IMPORTS,
                attrs={"import_kind": "module"},
            )
        ]
        new_edges = [
            GraphEdgeRecord(
                id="edge:3",
                repo_id="test_repo",
                namespace="main",
                src_id="py://pkg.E",
                dst_id="py://pkg.F",
                edge_type=EdgeType.IMPORTS,
                attrs={"import_kind": "symbol"},  # changed
            )
        ]

        deltas = calculator.calculate_deltas([], old_edges, [], new_edges)

        edge_deltas = [d for d in deltas if d.kind == "edge"]
        assert len(edge_deltas) == 1
        assert edge_deltas[0].op == GraphDeltaOp.UPDATE
        assert edge_deltas[0].record.id == "edge:3"

    def test_no_change_edge(self, calculator):
        """Test: 변경 없는 엣지는 delta 없음"""
        edge = GraphEdgeRecord(
            id="edge:4",
            repo_id="test_repo",
            namespace="main",
            src_id="py://pkg.G",
            dst_id="py://pkg.H",
            edge_type=EdgeType.CONTAINS,
            attrs={},
        )
        old_edges = [edge]
        new_edges = [edge]

        deltas = calculator.calculate_deltas([], old_edges, [], new_edges)

        edge_deltas = [d for d in deltas if d.kind == "edge"]
        assert len(edge_deltas) == 0


class TestGraphDeltaCalculatorComplex:
    """Test complex delta scenarios"""

    @pytest.fixture
    def calculator(self):
        return GraphDeltaCalculator()

    def test_mixed_operations(self, calculator):
        """Test: INSERT/UPDATE/DELETE 혼합 시나리오"""
        # Old state
        old_nodes = [
            GraphNodeRecord(
                id="py://pkg.A",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.CLASS,
                attrs={"name": "A", "version": 1},
            ),
            GraphNodeRecord(
                id="py://pkg.B",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.FUNCTION,
                attrs={"name": "B"},
            ),
            GraphNodeRecord(
                id="py://pkg.C",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.FUNCTION,
                attrs={"name": "C"},
            ),
        ]

        # New state
        new_nodes = [
            GraphNodeRecord(
                id="py://pkg.A",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.CLASS,
                attrs={"name": "A", "version": 2},  # UPDATED
            ),
            GraphNodeRecord(
                id="py://pkg.B",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.FUNCTION,
                attrs={"name": "B"},  # NO CHANGE
            ),
            # C is DELETED
            GraphNodeRecord(
                id="py://pkg.D",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.METHOD,
                attrs={"name": "D"},  # INSERTED
            ),
        ]

        deltas = calculator.calculate_deltas(old_nodes, [], new_nodes, [])

        node_deltas = [d for d in deltas if d.kind == "node"]

        # Check operations
        insert_deltas = [d for d in node_deltas if d.op == GraphDeltaOp.INSERT]
        update_deltas = [d for d in node_deltas if d.op == GraphDeltaOp.UPDATE]
        delete_deltas = [d for d in node_deltas if d.op == GraphDeltaOp.DELETE]

        assert len(insert_deltas) == 1  # D inserted
        assert len(update_deltas) == 1  # A updated
        assert len(delete_deltas) == 1  # C deleted

        assert insert_deltas[0].record.id == "py://pkg.D"
        assert update_deltas[0].record.id == "py://pkg.A"
        assert delete_deltas[0].record.id == "py://pkg.C"

    def test_attrs_hash_deterministic(self, calculator):
        """Test: attrs 해시는 결정론적"""
        attrs1 = {"key1": "value1", "key2": "value2"}
        attrs2 = {"key2": "value2", "key1": "value1"}  # 순서 다름

        hash1 = calculator.calculate_attrs_hash(attrs1)
        hash2 = calculator.calculate_attrs_hash(attrs2)

        assert hash1 == hash2  # 순서와 상관없이 같은 해시

    def test_empty_graphs(self, calculator):
        """Test: 빈 그래프 간 delta는 빈 리스트"""
        deltas = calculator.calculate_deltas([], [], [], [])
        assert len(deltas) == 0

    def test_file_refactor_scenario(self, calculator):
        """Test: 파일 리팩토링 시나리오 (함수 추가, 클래스 수정)"""
        # Old: file with 1 class
        old_nodes = [
            GraphNodeRecord(
                id="py://pkg.module",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.FILE,
                attrs={"file_path": "/pkg/module.py"},
            ),
            GraphNodeRecord(
                id="py://pkg.module.OldClass",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.CLASS,
                attrs={"name": "OldClass", "methods": 2},
            ),
        ]

        old_edges = [
            GraphEdgeRecord(
                id="edge:defines_1",
                repo_id="test_repo",
                namespace="main",
                src_id="py://pkg.module",
                dst_id="py://pkg.module.OldClass",
                edge_type=EdgeType.DEFINES,
                attrs={},
            )
        ]

        # New: file with updated class + new function
        new_nodes = [
            GraphNodeRecord(
                id="py://pkg.module",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.FILE,
                attrs={"file_path": "/pkg/module.py"},  # no change
            ),
            GraphNodeRecord(
                id="py://pkg.module.OldClass",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.CLASS,
                attrs={"name": "OldClass", "methods": 3},  # updated
            ),
            GraphNodeRecord(
                id="py://pkg.module.new_helper",
                repo_id="test_repo",
                namespace="main",
                kind=NodeKind.FUNCTION,
                attrs={"name": "new_helper"},  # inserted
            ),
        ]

        new_edges = [
            GraphEdgeRecord(
                id="edge:defines_1",
                repo_id="test_repo",
                namespace="main",
                src_id="py://pkg.module",
                dst_id="py://pkg.module.OldClass",
                edge_type=EdgeType.DEFINES,
                attrs={},  # no change
            ),
            GraphEdgeRecord(
                id="edge:defines_2",
                repo_id="test_repo",
                namespace="main",
                src_id="py://pkg.module",
                dst_id="py://pkg.module.new_helper",
                edge_type=EdgeType.DEFINES,
                attrs={},  # inserted
            ),
        ]

        deltas = calculator.calculate_deltas(old_nodes, old_edges, new_nodes, new_edges)

        # Expectations:
        # - 1 node UPDATE (OldClass)
        # - 1 node INSERT (new_helper)
        # - 1 edge INSERT (defines new_helper)

        node_deltas = [d for d in deltas if d.kind == "node"]
        edge_deltas = [d for d in deltas if d.kind == "edge"]

        assert len(node_deltas) == 2  # 1 update + 1 insert
        assert len(edge_deltas) == 1  # 1 insert

        node_updates = [d for d in node_deltas if d.op == GraphDeltaOp.UPDATE]
        node_inserts = [d for d in node_deltas if d.op == GraphDeltaOp.INSERT]

        assert len(node_updates) == 1
        assert len(node_inserts) == 1
        assert node_updates[0].record.id == "py://pkg.module.OldClass"
        assert node_inserts[0].record.id == "py://pkg.module.new_helper"
