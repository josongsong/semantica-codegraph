"""
Tests for UnifiedGraphIndex
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.dfg.models import DataFlowEdge, DfgSnapshot, VariableEntity
from codegraph_engine.code_foundation.infrastructure.ir.models import Edge, EdgeKind, IRDocument, Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.query.graph_index import UnifiedGraphIndex
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
)


class TestUnifiedGraphIndex:
    """Test UnifiedGraphIndex construction and queries"""

    def test_init_with_empty_ir(self):
        """Test initialization with empty IRDocument"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        graph = UnifiedGraphIndex(ir_doc)

        assert graph is not None
        stats = graph.get_stats()
        assert stats["total_nodes"] == 0
        assert stats["total_edges"] == 0

    def test_init_with_nodes(self):
        """Test initialization with IR nodes"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Add function node
        func_node = Node(
            id="func:test_func",
            kind=NodeKind.FUNCTION,
            fqn="test.test_func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
            name="test_func",
        )
        ir_doc.nodes.append(func_node)

        graph = UnifiedGraphIndex(ir_doc)

        # Verify node indexed
        assert graph.get_node("func:test_func") is not None
        assert graph.get_node("func:test_func").kind == "function"
        assert graph.get_node("func:test_func").name == "test_func"

    def test_init_with_variables(self):
        """Test initialization with DFG variables"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Add variable
        var = VariableEntity(
            id="var:test:test.py:test_func:x@0:1",
            repo_id="test",
            file_path="test.py",
            function_fqn="test_func",
            name="x",
            kind="local",
            decl_span=Span(2, 4, 2, 5),
        )

        dfg = DfgSnapshot(variables=[var])
        ir_doc.dfg_snapshot = dfg

        graph = UnifiedGraphIndex(ir_doc)

        # Verify variable indexed
        vars_x = graph.find_vars_by_name("x")
        assert len(vars_x) == 1
        assert vars_x[0].name == "x"
        assert vars_x[0].kind == "var"

    def test_init_with_blocks(self):
        """Test initialization with CFG blocks"""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import CFGBlockKind

        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Add function node (required for block)
        func_node = Node(
            id="func:test_func",
            kind=NodeKind.FUNCTION,
            fqn="test.test_func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
            name="test_func",
        )
        ir_doc.nodes.append(func_node)

        # Add block
        block = ControlFlowBlock(
            id="cfg:func:test_func:block:0",
            kind=CFGBlockKind.ENTRY,
            function_node_id="func:test_func",
            span=Span(1, 0, 1, 10),
        )
        ir_doc.cfg_blocks.append(block)

        graph = UnifiedGraphIndex(ir_doc)

        # Verify block indexed
        assert graph.get_node("cfg:func:test_func:block:0") is not None
        assert graph.get_node("cfg:func:test_func:block:0").kind == "block"

    def test_dfg_edges(self):
        """Test DFG edge indexing"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Add variables
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var2 = VariableEntity(
            id="var:2", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )

        # Add edge
        edge = DataFlowEdge(
            id="edge:1",
            from_variable_id="var:1",
            to_variable_id="var:2",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )

        dfg = DfgSnapshot(variables=[var1, var2], edges=[edge])
        ir_doc.dfg_snapshot = dfg

        graph = UnifiedGraphIndex(ir_doc)

        # Verify edge indexed
        edges = graph.get_edges_from("var:1")
        assert len(edges) == 1
        assert edges[0].from_node == "var:1"
        assert edges[0].to_node == "var:2"
        assert edges[0].edge_type == "dfg"

        # Verify backward edge
        back_edges = graph.get_edges_to("var:2")
        assert len(back_edges) == 1
        assert back_edges[0].from_node == "var:1"

    def test_cfg_edges(self):
        """Test CFG edge indexing"""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import CFGBlockKind

        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Add function node
        func_node = Node(
            id="func:test",
            kind=NodeKind.FUNCTION,
            fqn="test.test_func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
        )
        ir_doc.nodes.append(func_node)

        # Add blocks
        block1 = ControlFlowBlock(id="blk:1", kind=CFGBlockKind.ENTRY, function_node_id="func:test")
        block2 = ControlFlowBlock(id="blk:2", kind=CFGBlockKind.BLOCK, function_node_id="func:test")
        ir_doc.cfg_blocks.extend([block1, block2])

        # Add edge
        cfg_edge = ControlFlowEdge(source_block_id="blk:1", target_block_id="blk:2", kind=CFGEdgeKind.NORMAL)
        ir_doc.cfg_edges.append(cfg_edge)

        graph = UnifiedGraphIndex(ir_doc)

        # Verify edge indexed
        edges = graph.get_edges_from("blk:1")
        assert len(edges) == 1
        assert edges[0].to_node == "blk:2"
        assert edges[0].edge_type == "cfg"

    def test_call_edges(self):
        """Test call edge indexing"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Add function nodes
        func1 = Node(
            id="func:caller",
            kind=NodeKind.FUNCTION,
            fqn="test.caller",
            file_path="test.py",
            span=Span(1, 0, 3, 0),
            language="python",
        )
        func2 = Node(
            id="func:callee",
            kind=NodeKind.FUNCTION,
            fqn="test.callee",
            file_path="test.py",
            span=Span(5, 0, 7, 0),
            language="python",
        )
        ir_doc.nodes.extend([func1, func2])

        # Add call edge
        call_edge = Edge(id="edge:call:1", source_id="func:caller", target_id="func:callee", kind=EdgeKind.CALLS)
        ir_doc.edges.append(call_edge)

        graph = UnifiedGraphIndex(ir_doc)

        # Verify edge indexed
        edges = graph.get_edges_from("func:caller", edge_type="call")
        assert len(edges) == 1
        assert edges[0].to_node == "func:callee"
        assert edges[0].edge_type == "call"

    def test_find_funcs_by_name(self):
        """Test function lookup by name"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Add functions
        func1 = Node(
            id="func:1",
            kind=NodeKind.FUNCTION,
            fqn="test.process",
            file_path="test.py",
            span=Span(1, 0, 3, 0),
            language="python",
            name="process",
        )
        func2 = Node(
            id="func:2",
            kind=NodeKind.METHOD,
            fqn="test.Calculator.add",
            file_path="test.py",
            span=Span(5, 0, 7, 0),
            language="python",
            name="add",
        )
        ir_doc.nodes.extend([func1, func2])

        graph = UnifiedGraphIndex(ir_doc)

        # Find by name
        process_funcs = graph.find_funcs_by_name("process")
        assert len(process_funcs) == 1
        assert process_funcs[0].name == "process"

        add_funcs = graph.find_funcs_by_name("add")
        assert len(add_funcs) == 1
        assert add_funcs[0].name == "add"

    def test_get_stats(self):
        """Test statistics"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Add some nodes
        func = Node(
            id="func:1",
            kind=NodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 3, 0),
            language="python",
            name="func",
        )
        ir_doc.nodes.append(func)

        var = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var])

        graph = UnifiedGraphIndex(ir_doc)

        stats = graph.get_stats()
        assert stats["total_nodes"] == 2  # 1 func + 1 var
        assert stats["variables"] == 1
        assert stats["functions"] == 1
