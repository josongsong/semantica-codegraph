"""
CFG Models Tests

Tests for Control Flow Graph data models.
"""

from src.foundation.ir.models.core import Span
from src.foundation.semantic_ir.cfg.models import (
    CFGBlockKind,
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
    ControlFlowGraph,
)


class TestCFGBlockKind:
    """Test CFGBlockKind enum."""

    def test_block_kind_values(self):
        """Test CFGBlockKind enum values."""
        assert CFGBlockKind.ENTRY == "Entry"
        assert CFGBlockKind.EXIT == "Exit"
        assert CFGBlockKind.BLOCK == "Block"
        assert CFGBlockKind.CONDITION == "Condition"
        assert CFGBlockKind.LOOP_HEADER == "LoopHeader"
        assert CFGBlockKind.TRY == "Try"
        assert CFGBlockKind.CATCH == "Catch"
        assert CFGBlockKind.FINALLY == "Finally"

    def test_block_kind_is_enum(self):
        """Test CFGBlockKind is an enum."""
        assert issubclass(CFGBlockKind, str)
        # Can be used as string
        assert CFGBlockKind.ENTRY.value == "Entry"


class TestCFGEdgeKind:
    """Test CFGEdgeKind enum."""

    def test_edge_kind_values(self):
        """Test CFGEdgeKind enum values."""
        assert CFGEdgeKind.NORMAL == "NORMAL"
        assert CFGEdgeKind.TRUE_BRANCH == "TRUE_BRANCH"
        assert CFGEdgeKind.FALSE_BRANCH == "FALSE_BRANCH"
        assert CFGEdgeKind.EXCEPTION == "EXCEPTION"
        assert CFGEdgeKind.LOOP_BACK == "LOOP_BACK"

    def test_edge_kind_is_enum(self):
        """Test CFGEdgeKind is an enum."""
        assert issubclass(CFGEdgeKind, str)
        # Can be used as string
        assert CFGEdgeKind.NORMAL.value == "NORMAL"


class TestControlFlowBlock:
    """Test ControlFlowBlock dataclass."""

    def test_block_creation_minimal(self):
        """Test creating block with minimal required fields."""
        block = ControlFlowBlock(
            id="cfg:test:block:1",
            kind=CFGBlockKind.ENTRY,
            function_node_id="func_123",
        )

        assert block.id == "cfg:test:block:1"
        assert block.kind == CFGBlockKind.ENTRY
        assert block.function_node_id == "func_123"
        assert block.span is None
        assert block.defined_variable_ids == []
        assert block.used_variable_ids == []

    def test_block_creation_with_span(self):
        """Test creating block with span."""
        span = Span(start_line=1, start_col=0, end_line=1, end_col=10)

        block = ControlFlowBlock(
            id="cfg:test:block:1",
            kind=CFGBlockKind.BLOCK,
            function_node_id="func_123",
            span=span,
        )

        assert block.span is span
        assert block.span.start_line == 1

    def test_block_creation_with_variables(self):
        """Test creating block with variable IDs."""
        block = ControlFlowBlock(
            id="cfg:test:block:1",
            kind=CFGBlockKind.BLOCK,
            function_node_id="func_123",
            defined_variable_ids=["var_1", "var_2"],
            used_variable_ids=["var_3", "var_4"],
        )

        assert len(block.defined_variable_ids) == 2
        assert "var_1" in block.defined_variable_ids
        assert len(block.used_variable_ids) == 2
        assert "var_3" in block.used_variable_ids

    def test_block_kinds(self):
        """Test creating blocks with different kinds."""
        entry = ControlFlowBlock("b1", CFGBlockKind.ENTRY, "f1")
        assert entry.kind == CFGBlockKind.ENTRY

        exit_block = ControlFlowBlock("b2", CFGBlockKind.EXIT, "f1")
        assert exit_block.kind == CFGBlockKind.EXIT

        condition = ControlFlowBlock("b3", CFGBlockKind.CONDITION, "f1")
        assert condition.kind == CFGBlockKind.CONDITION

        loop = ControlFlowBlock("b4", CFGBlockKind.LOOP_HEADER, "f1")
        assert loop.kind == CFGBlockKind.LOOP_HEADER

        try_block = ControlFlowBlock("b5", CFGBlockKind.TRY, "f1")
        assert try_block.kind == CFGBlockKind.TRY

        catch_block = ControlFlowBlock("b6", CFGBlockKind.CATCH, "f1")
        assert catch_block.kind == CFGBlockKind.CATCH

        finally_block = ControlFlowBlock("b7", CFGBlockKind.FINALLY, "f1")
        assert finally_block.kind == CFGBlockKind.FINALLY


class TestControlFlowEdge:
    """Test ControlFlowEdge dataclass."""

    def test_edge_creation(self):
        """Test creating edge."""
        edge = ControlFlowEdge(
            source_block_id="block_1",
            target_block_id="block_2",
            kind=CFGEdgeKind.NORMAL,
        )

        assert edge.source_block_id == "block_1"
        assert edge.target_block_id == "block_2"
        assert edge.kind == CFGEdgeKind.NORMAL

    def test_edge_kinds(self):
        """Test creating edges with different kinds."""
        normal = ControlFlowEdge("b1", "b2", CFGEdgeKind.NORMAL)
        assert normal.kind == CFGEdgeKind.NORMAL

        true_branch = ControlFlowEdge("b1", "b2", CFGEdgeKind.TRUE_BRANCH)
        assert true_branch.kind == CFGEdgeKind.TRUE_BRANCH

        false_branch = ControlFlowEdge("b1", "b3", CFGEdgeKind.FALSE_BRANCH)
        assert false_branch.kind == CFGEdgeKind.FALSE_BRANCH

        exception = ControlFlowEdge("b1", "b4", CFGEdgeKind.EXCEPTION)
        assert exception.kind == CFGEdgeKind.EXCEPTION

        loop_back = ControlFlowEdge("b1", "b0", CFGEdgeKind.LOOP_BACK)
        assert loop_back.kind == CFGEdgeKind.LOOP_BACK


class TestControlFlowGraph:
    """Test ControlFlowGraph dataclass."""

    def test_cfg_creation_minimal(self):
        """Test creating CFG with minimal required fields."""
        cfg = ControlFlowGraph(
            id="cfg:test_func",
            function_node_id="func_123",
            entry_block_id="block_entry",
            exit_block_id="block_exit",
        )

        assert cfg.id == "cfg:test_func"
        assert cfg.function_node_id == "func_123"
        assert cfg.entry_block_id == "block_entry"
        assert cfg.exit_block_id == "block_exit"
        assert cfg.blocks == []
        assert cfg.edges == []

    def test_cfg_creation_with_blocks(self):
        """Test creating CFG with blocks."""
        entry = ControlFlowBlock("b_entry", CFGBlockKind.ENTRY, "func_1")
        exit_block = ControlFlowBlock("b_exit", CFGBlockKind.EXIT, "func_1")

        cfg = ControlFlowGraph(
            id="cfg:test_func",
            function_node_id="func_1",
            entry_block_id="b_entry",
            exit_block_id="b_exit",
            blocks=[entry, exit_block],
        )

        assert len(cfg.blocks) == 2
        assert cfg.blocks[0] is entry
        assert cfg.blocks[1] is exit_block

    def test_cfg_creation_with_edges(self):
        """Test creating CFG with edges."""
        edge = ControlFlowEdge("b1", "b2", CFGEdgeKind.NORMAL)

        cfg = ControlFlowGraph(
            id="cfg:test_func",
            function_node_id="func_1",
            entry_block_id="b1",
            exit_block_id="b2",
            edges=[edge],
        )

        assert len(cfg.edges) == 1
        assert cfg.edges[0] is edge

    def test_cfg_complete_graph(self):
        """Test creating complete CFG with blocks and edges."""
        # Create blocks
        entry = ControlFlowBlock("b_entry", CFGBlockKind.ENTRY, "func_1")
        block1 = ControlFlowBlock("b1", CFGBlockKind.BLOCK, "func_1")
        block2 = ControlFlowBlock("b2", CFGBlockKind.BLOCK, "func_1")
        exit_block = ControlFlowBlock("b_exit", CFGBlockKind.EXIT, "func_1")

        # Create edges
        edge1 = ControlFlowEdge("b_entry", "b1", CFGEdgeKind.NORMAL)
        edge2 = ControlFlowEdge("b1", "b2", CFGEdgeKind.NORMAL)
        edge3 = ControlFlowEdge("b2", "b_exit", CFGEdgeKind.NORMAL)

        # Create CFG
        cfg = ControlFlowGraph(
            id="cfg:test_func",
            function_node_id="func_1",
            entry_block_id="b_entry",
            exit_block_id="b_exit",
            blocks=[entry, block1, block2, exit_block],
            edges=[edge1, edge2, edge3],
        )

        assert len(cfg.blocks) == 4
        assert len(cfg.edges) == 3
        assert cfg.entry_block_id == "b_entry"
        assert cfg.exit_block_id == "b_exit"

    def test_cfg_with_conditional(self):
        """Test CFG with conditional branches."""
        entry = ControlFlowBlock("b_entry", CFGBlockKind.ENTRY, "func_1")
        condition = ControlFlowBlock("b_cond", CFGBlockKind.CONDITION, "func_1")
        then_block = ControlFlowBlock("b_then", CFGBlockKind.BLOCK, "func_1")
        else_block = ControlFlowBlock("b_else", CFGBlockKind.BLOCK, "func_1")
        exit_block = ControlFlowBlock("b_exit", CFGBlockKind.EXIT, "func_1")

        # Edges for if-else
        edge1 = ControlFlowEdge("b_entry", "b_cond", CFGEdgeKind.NORMAL)
        edge2 = ControlFlowEdge("b_cond", "b_then", CFGEdgeKind.TRUE_BRANCH)
        edge3 = ControlFlowEdge("b_cond", "b_else", CFGEdgeKind.FALSE_BRANCH)
        edge4 = ControlFlowEdge("b_then", "b_exit", CFGEdgeKind.NORMAL)
        edge5 = ControlFlowEdge("b_else", "b_exit", CFGEdgeKind.NORMAL)

        cfg = ControlFlowGraph(
            id="cfg:test_conditional",
            function_node_id="func_1",
            entry_block_id="b_entry",
            exit_block_id="b_exit",
            blocks=[entry, condition, then_block, else_block, exit_block],
            edges=[edge1, edge2, edge3, edge4, edge5],
        )

        assert len(cfg.blocks) == 5
        assert len(cfg.edges) == 5

        # Check conditional edges
        true_edges = [e for e in cfg.edges if e.kind == CFGEdgeKind.TRUE_BRANCH]
        false_edges = [e for e in cfg.edges if e.kind == CFGEdgeKind.FALSE_BRANCH]
        assert len(true_edges) == 1
        assert len(false_edges) == 1

    def test_cfg_with_loop(self):
        """Test CFG with loop."""
        entry = ControlFlowBlock("b_entry", CFGBlockKind.ENTRY, "func_1")
        loop_header = ControlFlowBlock("b_loop", CFGBlockKind.LOOP_HEADER, "func_1")
        body = ControlFlowBlock("b_body", CFGBlockKind.BLOCK, "func_1")
        exit_block = ControlFlowBlock("b_exit", CFGBlockKind.EXIT, "func_1")

        # Edges for loop
        edge1 = ControlFlowEdge("b_entry", "b_loop", CFGEdgeKind.NORMAL)
        edge2 = ControlFlowEdge("b_loop", "b_body", CFGEdgeKind.TRUE_BRANCH)
        edge3 = ControlFlowEdge("b_body", "b_loop", CFGEdgeKind.LOOP_BACK)
        edge4 = ControlFlowEdge("b_loop", "b_exit", CFGEdgeKind.FALSE_BRANCH)

        cfg = ControlFlowGraph(
            id="cfg:test_loop",
            function_node_id="func_1",
            entry_block_id="b_entry",
            exit_block_id="b_exit",
            blocks=[entry, loop_header, body, exit_block],
            edges=[edge1, edge2, edge3, edge4],
        )

        assert len(cfg.blocks) == 4
        assert len(cfg.edges) == 4

        # Check loop back edge
        loop_edges = [e for e in cfg.edges if e.kind == CFGEdgeKind.LOOP_BACK]
        assert len(loop_edges) == 1
        assert loop_edges[0].target_block_id == "b_loop"

    def test_cfg_with_exception_handling(self):
        """Test CFG with try/except."""
        entry = ControlFlowBlock("b_entry", CFGBlockKind.ENTRY, "func_1")
        try_block = ControlFlowBlock("b_try", CFGBlockKind.TRY, "func_1")
        catch_block = ControlFlowBlock("b_catch", CFGBlockKind.CATCH, "func_1")
        finally_block = ControlFlowBlock("b_finally", CFGBlockKind.FINALLY, "func_1")
        exit_block = ControlFlowBlock("b_exit", CFGBlockKind.EXIT, "func_1")

        # Edges for exception handling
        edge1 = ControlFlowEdge("b_entry", "b_try", CFGEdgeKind.NORMAL)
        edge2 = ControlFlowEdge("b_try", "b_finally", CFGEdgeKind.NORMAL)
        edge3 = ControlFlowEdge("b_try", "b_catch", CFGEdgeKind.EXCEPTION)
        edge4 = ControlFlowEdge("b_catch", "b_finally", CFGEdgeKind.NORMAL)
        edge5 = ControlFlowEdge("b_finally", "b_exit", CFGEdgeKind.NORMAL)

        cfg = ControlFlowGraph(
            id="cfg:test_exception",
            function_node_id="func_1",
            entry_block_id="b_entry",
            exit_block_id="b_exit",
            blocks=[entry, try_block, catch_block, finally_block, exit_block],
            edges=[edge1, edge2, edge3, edge4, edge5],
        )

        assert len(cfg.blocks) == 5
        assert len(cfg.edges) == 5

        # Check exception edges
        exception_edges = [e for e in cfg.edges if e.kind == CFGEdgeKind.EXCEPTION]
        assert len(exception_edges) == 1
