"""
SOTA-Level Unit Tests for EdgeIndex

Test Categories:
1. BASE: Standard operations
2. CORNER: Boundary conditions
3. EDGE: Unusual but valid inputs
4. EXTREME: Large-scale stress tests

Coverage Target: 100%
Performance Target: O(1) lookups, O(k) retrieval
Type Safety: All return types validated
"""

import pytest

from codegraph_engine.code_foundation.domain.query.types import EdgeType
from codegraph_engine.code_foundation.infrastructure.dfg.models import DataFlowEdge, DfgSnapshot, VariableEntity
from codegraph_engine.code_foundation.infrastructure.ir.models import Edge, EdgeKind, IRDocument
from codegraph_engine.code_foundation.infrastructure.query.indexes import EdgeIndex
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
    CFGBlockKind,
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
)


class TestEdgeIndexBase:
    """BASE: Standard operations"""

    def test_init_with_empty_ir(self):
        """Empty IR should create empty edge index"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        index = EdgeIndex(ir_doc)

        stats = index.get_stats()
        assert stats["total_edges"] == 0
        assert stats["dfg_edges"] == 0
        assert stats["cfg_edges"] == 0
        assert stats["call_edges"] == 0

    def test_index_single_dfg_edge(self):
        """Single DFG edge should be indexed bidirectionally"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var2 = VariableEntity(
            id="var:2", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )
        edge = DataFlowEdge(
            id="edge:1",
            from_variable_id="var:1",
            to_variable_id="var:2",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2], edges=[edge])

        index = EdgeIndex(ir_doc)

        # Forward lookup
        outgoing = index.get_outgoing("var:1")
        assert len(outgoing) == 1
        assert outgoing[0].from_node == "var:1"
        assert outgoing[0].to_node == "var:2"
        assert outgoing[0].edge_type == EdgeType.DFG

        # Backward lookup
        incoming = index.get_incoming("var:2")
        assert len(incoming) == 1
        assert incoming[0].from_node == "var:1"

    def test_index_single_cfg_edge(self):
        """Single CFG edge should be indexed"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        block1 = ControlFlowBlock(id="block:1", kind=CFGBlockKind.ENTRY, function_node_id="func:1")
        block2 = ControlFlowBlock(id="block:2", kind=CFGBlockKind.BLOCK, function_node_id="func:1")
        cfg_edge = ControlFlowEdge(source_block_id="block:1", target_block_id="block:2", kind=CFGEdgeKind.NORMAL)

        ir_doc.cfg_blocks.extend([block1, block2])
        ir_doc.cfg_edges.append(cfg_edge)

        index = EdgeIndex(ir_doc)

        outgoing = index.get_outgoing("block:1", EdgeType.CFG)
        assert len(outgoing) == 1
        assert outgoing[0].edge_type == EdgeType.CFG

    def test_index_single_call_edge(self):
        """Single call edge should be indexed"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        call_edge = Edge(id="edge:call:1", source_id="func:caller", target_id="func:callee", kind=EdgeKind.CALLS)
        ir_doc.edges.append(call_edge)

        index = EdgeIndex(ir_doc)

        outgoing = index.get_outgoing("func:caller", EdgeType.CALL)
        assert len(outgoing) == 1
        assert outgoing[0].edge_type == EdgeType.CALL

    def test_get_outgoing_with_no_edges(self):
        """get_outgoing() on node with no edges returns empty list"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        index = EdgeIndex(ir_doc)

        outgoing = index.get_outgoing("nonexistent:node")
        assert outgoing == []

    def test_get_incoming_with_no_edges(self):
        """get_incoming() on node with no edges returns empty list"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        index = EdgeIndex(ir_doc)

        incoming = index.get_incoming("nonexistent:node")
        assert incoming == []

    def test_filter_by_edge_type_dfg(self):
        """Filter edges by DFG type"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var2 = VariableEntity(
            id="var:2", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )
        edge = DataFlowEdge(
            id="edge:1",
            from_variable_id="var:1",
            to_variable_id="var:2",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2], edges=[edge])

        index = EdgeIndex(ir_doc)

        # Filter by DFG
        dfg_edges = index.get_outgoing("var:1", EdgeType.DFG)
        assert len(dfg_edges) == 1

        # Filter by CFG (should be empty)
        cfg_edges = index.get_outgoing("var:1", EdgeType.CFG)
        assert len(cfg_edges) == 0


class TestEdgeIndexCorner:
    """CORNER: Boundary conditions"""

    def test_node_with_multiple_outgoing_edges(self):
        """Node with multiple outgoing edges"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var2 = VariableEntity(
            id="var:2", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )
        var3 = VariableEntity(
            id="var:3", repo_id="test", file_path="test.py", function_fqn="func", name="z", kind="local"
        )

        edge1 = DataFlowEdge(
            id="edge:1",
            from_variable_id="var:1",
            to_variable_id="var:2",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )
        edge2 = DataFlowEdge(
            id="edge:2",
            from_variable_id="var:1",
            to_variable_id="var:3",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )

        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2, var3], edges=[edge1, edge2])
        index = EdgeIndex(ir_doc)

        outgoing = index.get_outgoing("var:1")
        assert len(outgoing) == 2

    def test_node_with_multiple_incoming_edges(self):
        """Node with multiple incoming edges"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var2 = VariableEntity(
            id="var:2", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )
        var3 = VariableEntity(
            id="var:3", repo_id="test", file_path="test.py", function_fqn="func", name="z", kind="local"
        )

        edge1 = DataFlowEdge(
            id="edge:1",
            from_variable_id="var:1",
            to_variable_id="var:3",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )
        edge2 = DataFlowEdge(
            id="edge:2",
            from_variable_id="var:2",
            to_variable_id="var:3",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )

        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2, var3], edges=[edge1, edge2])
        index = EdgeIndex(ir_doc)

        incoming = index.get_incoming("var:3")
        assert len(incoming) == 2

    def test_self_loop_edge(self):
        """Edge from node to itself"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        edge = DataFlowEdge(
            id="edge:loop",
            from_variable_id="var:1",
            to_variable_id="var:1",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1], edges=[edge])
        index = EdgeIndex(ir_doc)

        outgoing = index.get_outgoing("var:1")
        incoming = index.get_incoming("var:1")
        assert len(outgoing) == 1
        assert len(incoming) == 1
        assert outgoing[0].from_node == "var:1"
        assert outgoing[0].to_node == "var:1"

    def test_mixed_edge_types_same_node(self):
        """Node with multiple edge types (DFG + CFG)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # DFG edge
        var1 = VariableEntity(
            id="node:1", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var2 = VariableEntity(
            id="node:2", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )
        dfg_edge = DataFlowEdge(
            id="edge:dfg",
            from_variable_id="node:1",
            to_variable_id="node:2",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2], edges=[dfg_edge])

        # CFG edge (same source node ID)
        block1 = ControlFlowBlock(id="node:1", kind=CFGBlockKind.ENTRY, function_node_id="func:1")
        block2 = ControlFlowBlock(id="node:3", kind=CFGBlockKind.BLOCK, function_node_id="func:1")
        cfg_edge = ControlFlowEdge(source_block_id="node:1", target_block_id="node:3", kind=CFGEdgeKind.NORMAL)
        ir_doc.cfg_blocks.extend([block1, block2])
        ir_doc.cfg_edges.append(cfg_edge)

        index = EdgeIndex(ir_doc)

        # All edges
        all_edges = index.get_outgoing("node:1")
        assert len(all_edges) == 2

        # DFG only
        dfg_only = index.get_outgoing("node:1", EdgeType.DFG)
        assert len(dfg_only) == 1

        # CFG only
        cfg_only = index.get_outgoing("node:1", EdgeType.CFG)
        assert len(cfg_only) == 1

    def test_filter_with_string_edge_type(self):
        """Filter using string edge type (not enum)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var2 = VariableEntity(
            id="var:2", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )
        edge = DataFlowEdge(
            id="edge:1",
            from_variable_id="var:1",
            to_variable_id="var:2",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2], edges=[edge])
        index = EdgeIndex(ir_doc)

        # Filter using string
        edges = index.get_outgoing("var:1", "dfg")
        assert len(edges) == 1


class TestEdgeIndexEdge:
    """EDGE: Unusual but valid inputs"""

    def test_edge_with_empty_attrs(self):
        """Edge with empty attrs dict"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var2 = VariableEntity(
            id="var:2", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )
        edge = DataFlowEdge(
            id="edge:1",
            from_variable_id="var:1",
            to_variable_id="var:2",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            attrs={},
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2], edges=[edge])
        index = EdgeIndex(ir_doc)

        edges = index.get_outgoing("var:1")
        assert len(edges) == 1
        assert edges[0].attrs.get("kind") == "assign"

    def test_interprocedural_edge_indexing(self):
        """Interprocedural edges should be indexed as DFG"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Mock interprocedural edge
        from dataclasses import dataclass

        @dataclass
        class MockInterProcEdge:
            id: str
            from_var_id: str
            to_var_id: str
            kind: str
            call_site_id: str
            caller_func_fqn: str
            callee_func_fqn: str
            arg_position: int | None = None
            confidence: float = 1.0

        interproc_edge = MockInterProcEdge(
            id="edge:interproc:1",
            from_var_id="var:caller:x",
            to_var_id="var:callee:param",
            kind="param_pass",
            call_site_id="call:1",
            caller_func_fqn="caller",
            callee_func_fqn="callee",
            arg_position=0,
            confidence=0.95,
        )

        ir_doc.interprocedural_edges = [interproc_edge]
        index = EdgeIndex(ir_doc)

        edges = index.get_outgoing("var:caller:x", EdgeType.DFG)
        assert len(edges) == 1
        assert edges[0].attrs["interproc_kind"] == "param_pass"
        assert edges[0].attrs["confidence"] == 0.95

    def test_get_outgoing_with_edge_type_all(self):
        """EdgeType.ALL should return all edges"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var2 = VariableEntity(
            id="var:2", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )
        edge = DataFlowEdge(
            id="edge:1",
            from_variable_id="var:1",
            to_variable_id="var:2",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2], edges=[edge])
        index = EdgeIndex(ir_doc)

        # EdgeType.ALL
        all_edges = index.get_outgoing("var:1", EdgeType.ALL)
        assert len(all_edges) == 1


class TestEdgeIndexExtreme:
    """EXTREME: Large-scale stress tests"""

    def test_index_1000_dfg_edges(self):
        """Index 1000 DFG edges (linear chain)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        variables = []
        edges = []

        for i in range(1001):
            var = VariableEntity(
                id=f"var:{i}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=f"x{i}",
                kind="local",
            )
            variables.append(var)

        for i in range(1000):
            edge = DataFlowEdge(
                id=f"edge:{i}",
                from_variable_id=f"var:{i}",
                to_variable_id=f"var:{i + 1}",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            )
            edges.append(edge)

        ir_doc.dfg_snapshot = DfgSnapshot(variables=variables, edges=edges)
        index = EdgeIndex(ir_doc)

        stats = index.get_stats()
        assert stats["total_edges"] == 1000

        # Random access should be O(1)
        edges_500 = index.get_outgoing("var:500")
        assert len(edges_500) == 1
        assert edges_500[0].to_node == "var:501"

    def test_fan_out_100_edges(self):
        """Node with 100 outgoing edges"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        variables = [
            VariableEntity(
                id="var:source", repo_id="test", file_path="test.py", function_fqn="func", name="source", kind="local"
            )
        ]
        edges = []

        for i in range(100):
            var = VariableEntity(
                id=f"var:target:{i}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=f"t{i}",
                kind="local",
            )
            variables.append(var)

            edge = DataFlowEdge(
                id=f"edge:{i}",
                from_variable_id="var:source",
                to_variable_id=f"var:target:{i}",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            )
            edges.append(edge)

        ir_doc.dfg_snapshot = DfgSnapshot(variables=variables, edges=edges)
        index = EdgeIndex(ir_doc)

        outgoing = index.get_outgoing("var:source")
        assert len(outgoing) == 100

    def test_fan_in_100_edges(self):
        """Node with 100 incoming edges"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        variables = [
            VariableEntity(
                id="var:sink", repo_id="test", file_path="test.py", function_fqn="func", name="sink", kind="local"
            )
        ]
        edges = []

        for i in range(100):
            var = VariableEntity(
                id=f"var:source:{i}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=f"s{i}",
                kind="local",
            )
            variables.append(var)

            edge = DataFlowEdge(
                id=f"edge:{i}",
                from_variable_id=f"var:source:{i}",
                to_variable_id="var:sink",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            )
            edges.append(edge)

        ir_doc.dfg_snapshot = DfgSnapshot(variables=variables, edges=edges)
        index = EdgeIndex(ir_doc)

        incoming = index.get_incoming("var:sink")
        assert len(incoming) == 100

    def test_mixed_edge_types_1000_total(self):
        """1000 edges mixed (DFG + CFG + Call)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # 400 DFG edges
        variables = []
        dfg_edges = []
        for i in range(401):
            var = VariableEntity(
                id=f"var:{i}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=f"x{i}",
                kind="local",
            )
            variables.append(var)

        for i in range(400):
            edge = DataFlowEdge(
                id=f"edge:dfg:{i}",
                from_variable_id=f"var:{i}",
                to_variable_id=f"var:{i + 1}",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            )
            dfg_edges.append(edge)
        ir_doc.dfg_snapshot = DfgSnapshot(variables=variables, edges=dfg_edges)

        # 400 CFG edges
        for i in range(401):
            block = ControlFlowBlock(id=f"block:{i}", kind=CFGBlockKind.BLOCK, function_node_id="func:1")
            ir_doc.cfg_blocks.append(block)

        for i in range(400):
            cfg_edge = ControlFlowEdge(
                source_block_id=f"block:{i}", target_block_id=f"block:{i + 1}", kind=CFGEdgeKind.NORMAL
            )
            ir_doc.cfg_edges.append(cfg_edge)

        # 200 Call edges
        for i in range(200):
            call_edge = Edge(id=f"edge:call:{i}", source_id=f"func:{i}", target_id=f"func:{i + 1}", kind=EdgeKind.CALLS)
            ir_doc.edges.append(call_edge)

        index = EdgeIndex(ir_doc)

        stats = index.get_stats()
        assert stats["total_edges"] == 1000
        assert stats["dfg_edges"] == 400
        assert stats["cfg_edges"] == 400
        assert stats["call_edges"] == 200


class TestEdgeIndexStats:
    """Verify statistics accuracy"""

    def test_stats_empty_index(self):
        """Stats for empty index"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        index = EdgeIndex(ir_doc)

        stats = index.get_stats()
        assert stats["total_edges"] == 0
        assert stats["dfg_edges"] == 0
        assert stats["cfg_edges"] == 0
        assert stats["call_edges"] == 0

    def test_stats_counts_match_reality(self):
        """Stats counts should match actual edge counts"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # 2 DFG edges
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var2 = VariableEntity(
            id="var:2", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )
        var3 = VariableEntity(
            id="var:3", repo_id="test", file_path="test.py", function_fqn="func", name="z", kind="local"
        )
        dfg_edges = [
            DataFlowEdge(
                id="edge:1",
                from_variable_id="var:1",
                to_variable_id="var:2",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            DataFlowEdge(
                id="edge:2",
                from_variable_id="var:2",
                to_variable_id="var:3",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
        ]
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2, var3], edges=dfg_edges)

        # 1 CFG edge
        block1 = ControlFlowBlock(id="block:1", kind=CFGBlockKind.ENTRY, function_node_id="func:1")
        block2 = ControlFlowBlock(id="block:2", kind=CFGBlockKind.BLOCK, function_node_id="func:1")
        cfg_edge = ControlFlowEdge(source_block_id="block:1", target_block_id="block:2", kind=CFGEdgeKind.NORMAL)
        ir_doc.cfg_blocks.extend([block1, block2])
        ir_doc.cfg_edges.append(cfg_edge)

        # 1 Call edge
        call_edge = Edge(id="edge:call:1", source_id="func:1", target_id="func:2", kind=EdgeKind.CALLS)
        ir_doc.edges.append(call_edge)

        index = EdgeIndex(ir_doc)

        stats = index.get_stats()
        assert stats["total_edges"] == 4
        assert stats["dfg_edges"] == 2
        assert stats["cfg_edges"] == 1
        assert stats["call_edges"] == 1
