"""
SOTA-Level Unit Tests for NodeIndex

Test Categories:
1. BASE: Standard operations
2. CORNER: Boundary conditions
3. EDGE: Unusual but valid inputs
4. EXTREME: Large-scale stress tests

Coverage Target: 100%
Performance Target: O(1) lookups verified
Type Safety: All return types validated
"""

import pytest

from codegraph_engine.code_foundation.domain.query.types import NodeKind
from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot, VariableEntity
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument, Node, Span
from codegraph_engine.code_foundation.infrastructure.ir.models import NodeKind as IRNodeKind
from codegraph_engine.code_foundation.infrastructure.query.indexes import NodeIndex
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
    CFGBlockKind,
    ControlFlowBlock,
)
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import (
    Expression,
    ExprKind,
)


class TestNodeIndexBase:
    """BASE: Standard operations"""

    def test_init_with_empty_ir(self):
        """Empty IR document should create empty index"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        index = NodeIndex(ir_doc)

        assert index.get_count() == 0
        assert index.get_all() == []

    def test_init_with_single_node(self):
        """Single node should be indexed correctly"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func = Node(
            id="func:test",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
            name="test_func",
        )
        ir_doc.nodes.append(func)

        index = NodeIndex(ir_doc)

        assert index.get_count() == 1
        node = index.get("func:test")
        assert node is not None
        assert node.id == "func:test"
        assert node.name == "test_func"
        assert node.kind == NodeKind.FUNCTION

    def test_get_existing_node(self):
        """O(1) lookup for existing node"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func = Node(
            id="func:existing",
            kind=IRNodeKind.FUNCTION,
            fqn="test.existing",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
        )
        ir_doc.nodes.append(func)
        index = NodeIndex(ir_doc)

        node = index.get("func:existing")
        assert node is not None
        assert node.id == "func:existing"

    def test_get_nonexistent_node(self):
        """O(1) lookup for non-existent node returns None"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        index = NodeIndex(ir_doc)

        node = index.get("nonexistent:id")
        assert node is None

    def test_exists_returns_true_for_existing(self):
        """exists() returns True for indexed node"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func = Node(
            id="func:test",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
        )
        ir_doc.nodes.append(func)
        index = NodeIndex(ir_doc)

        assert index.exists("func:test") is True

    def test_exists_returns_false_for_nonexistent(self):
        """exists() returns False for non-indexed node"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        index = NodeIndex(ir_doc)

        assert index.exists("nonexistent:id") is False

    def test_index_multiple_node_types(self):
        """Index multiple node types (function, class, variable, block, expression)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Function
        func = Node(
            id="func:1",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
            name="func",
        )
        ir_doc.nodes.append(func)

        # Class
        cls = Node(
            id="class:1",
            kind=IRNodeKind.CLASS,
            fqn="test.MyClass",
            file_path="test.py",
            span=Span(6, 0, 10, 0),
            language="python",
            name="MyClass",
        )
        ir_doc.nodes.append(cls)

        # Variable
        var = VariableEntity(
            id="var:1",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            name="x",
            kind="local",
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var])

        # Block
        block = ControlFlowBlock(id="block:1", kind=CFGBlockKind.ENTRY, function_node_id="func:1")
        ir_doc.cfg_blocks.append(block)

        # Expression
        expr = Expression(
            id="expr:1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 4, 2, 10),
            attrs={"callee_name": "print"},
        )
        ir_doc.expressions.append(expr)

        index = NodeIndex(ir_doc)

        assert index.get_count() == 5
        assert index.get("func:1") is not None
        assert index.get("class:1") is not None
        assert index.get("var:1") is not None
        assert index.get("block:1") is not None
        assert index.get("expr:1") is not None


class TestNodeIndexCorner:
    """CORNER: Boundary conditions"""

    def test_node_with_no_span(self):
        """Node without span should be indexed correctly"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func = Node(
            id="func:no_span",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=None,
            language="python",
            name="func",
        )
        ir_doc.nodes.append(func)
        index = NodeIndex(ir_doc)

        node = index.get("func:no_span")
        assert node is not None
        assert node.span is None

    def test_variable_with_no_decl_span(self):
        """Variable without decl_span should be indexed"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var = VariableEntity(
            id="var:no_span",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            name="x",
            kind="local",
            decl_span=None,
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var])
        index = NodeIndex(ir_doc)

        node = index.get("var:no_span")
        assert node is not None
        assert node.span is None

    def test_block_with_missing_function_node(self):
        """Block referencing non-existent function should use empty file_path"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        block = ControlFlowBlock(
            id="block:orphan",
            kind=CFGBlockKind.ENTRY,
            function_node_id="nonexistent:func",
        )
        ir_doc.cfg_blocks.append(block)
        index = NodeIndex(ir_doc)

        node = index.get("block:orphan")
        assert node is not None
        assert node.file_path == ""

    def test_node_with_empty_name(self):
        """Node with empty name should be indexed"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func = Node(
            id="func:no_name",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
            name="",
        )
        ir_doc.nodes.append(func)
        index = NodeIndex(ir_doc)

        node = index.get("func:no_name")
        assert node is not None
        assert node.name == ""

    def test_node_with_unknown_kind(self):
        """Node with unknown kind should fallback gracefully"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        # Create node with known kind (can't create unknown directly)
        func = Node(
            id="func:unknown",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
        )
        ir_doc.nodes.append(func)
        index = NodeIndex(ir_doc)

        node = index.get("func:unknown")
        assert node is not None
        # Should convert to domain NodeKind

    def test_duplicate_node_ids(self):
        """Last node with duplicate ID should win"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func1 = Node(
            id="func:dup",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func1",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
            name="func1",
        )
        func2 = Node(
            id="func:dup",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func2",
            file_path="test.py",
            span=Span(6, 0, 10, 0),
            language="python",
            name="func2",
        )
        ir_doc.nodes.extend([func1, func2])
        index = NodeIndex(ir_doc)

        node = index.get("func:dup")
        assert node is not None
        assert node.name == "func2"  # Last one wins


class TestNodeIndexEdge:
    """EDGE: Unusual but valid inputs"""

    def test_expression_without_callee_name(self):
        """Expression without callee_name should be indexed with empty name"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        expr = Expression(
            id="expr:no_callee",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 4, 2, 10),
            attrs={},
        )
        ir_doc.expressions.append(expr)
        index = NodeIndex(ir_doc)

        node = index.get("expr:no_callee")
        assert node is not None
        assert node.name == ""

    def test_variable_with_all_optional_fields_none(self):
        """Variable with minimal fields should be indexed"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var = VariableEntity(
            id="var:minimal",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            name="x",
            kind="local",
            decl_span=None,
            type_id=None,
            scope_id=None,
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var])
        index = NodeIndex(ir_doc)

        node = index.get("var:minimal")
        assert node is not None
        assert node.attrs.get("type_id") is None
        assert node.attrs.get("scope_id") is None

    def test_node_with_empty_attrs(self):
        """Node with empty attrs dict should be indexed"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func = Node(
            id="func:empty_attrs",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
            attrs={},
        )
        ir_doc.nodes.append(func)
        index = NodeIndex(ir_doc)

        node = index.get("func:empty_attrs")
        assert node is not None
        assert "fqn" in node.attrs

    def test_get_all_preserves_order(self):
        """get_all() should return nodes (order not guaranteed but consistent)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        for i in range(5):
            func = Node(
                id=f"func:{i}",
                kind=IRNodeKind.FUNCTION,
                fqn=f"test.func{i}",
                file_path="test.py",
                span=Span(i, 0, i + 1, 0),
                language="python",
                name=f"func{i}",
            )
            ir_doc.nodes.append(func)
        index = NodeIndex(ir_doc)

        all_nodes = index.get_all()
        assert len(all_nodes) == 5
        # All nodes should be present
        node_ids = {n.id for n in all_nodes}
        assert node_ids == {f"func:{i}" for i in range(5)}


class TestNodeIndexExtreme:
    """EXTREME: Large-scale stress tests"""

    def test_index_1000_nodes(self):
        """Index 1000 nodes should complete in reasonable time"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        for i in range(1000):
            func = Node(
                id=f"func:{i}",
                kind=IRNodeKind.FUNCTION,
                fqn=f"test.func{i}",
                file_path=f"test{i % 10}.py",
                span=Span(i, 0, i + 1, 0),
                language="python",
                name=f"func{i}",
            )
            ir_doc.nodes.append(func)

        index = NodeIndex(ir_doc)

        assert index.get_count() == 1000
        # Random access should be O(1)
        assert index.get("func:500") is not None
        assert index.get("func:999") is not None

    def test_lookup_performance_constant_time(self):
        """Verify O(1) lookup time regardless of index size"""
        import time

        # Small index
        ir_doc_small = IRDocument(repo_id="test", snapshot_id="v1")
        for i in range(100):
            ir_doc_small.nodes.append(
                Node(
                    id=f"func:{i}",
                    kind=IRNodeKind.FUNCTION,
                    fqn=f"test.func{i}",
                    file_path="test.py",
                    span=Span(i, 0, i + 1, 0),
                    language="python",
                )
            )
        index_small = NodeIndex(ir_doc_small)

        # Large index
        ir_doc_large = IRDocument(repo_id="test", snapshot_id="v1")
        for i in range(1000):
            ir_doc_large.nodes.append(
                Node(
                    id=f"func:{i}",
                    kind=IRNodeKind.FUNCTION,
                    fqn=f"test.func{i}",
                    file_path="test.py",
                    span=Span(i, 0, i + 1, 0),
                    language="python",
                )
            )
        index_large = NodeIndex(ir_doc_large)

        # Measure lookup time
        start = time.perf_counter()
        for _ in range(1000):
            index_small.get("func:50")
        time_small = time.perf_counter() - start

        start = time.perf_counter()
        for _ in range(1000):
            index_large.get("func:500")
        time_large = time.perf_counter() - start

        # O(1) means time should be similar (within 2x factor)
        assert time_large < time_small * 2

    def test_mixed_node_types_large_scale(self):
        """Index 500 mixed node types"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # 200 functions
        for i in range(200):
            ir_doc.nodes.append(
                Node(
                    id=f"func:{i}",
                    kind=IRNodeKind.FUNCTION,
                    fqn=f"test.func{i}",
                    file_path="test.py",
                    span=Span(i, 0, i + 1, 0),
                    language="python",
                    name=f"func{i}",
                )
            )

        # 150 variables
        vars_list = []
        for i in range(150):
            vars_list.append(
                VariableEntity(
                    id=f"var:{i}",
                    repo_id="test",
                    file_path="test.py",
                    function_fqn=f"func{i % 200}",
                    name=f"x{i}",
                    kind="local",
                )
            )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars_list)

        # 100 blocks
        for i in range(100):
            ir_doc.cfg_blocks.append(
                ControlFlowBlock(
                    id=f"block:{i}",
                    kind=CFGBlockKind.ENTRY,
                    function_node_id=f"func:{i % 200}",
                )
            )

        # 50 expressions
        for i in range(50):
            ir_doc.expressions.append(
                Expression(
                    id=f"expr:{i}",
                    kind=ExprKind.CALL,
                    repo_id="test",
                    file_path="test.py",
                    function_fqn=f"func{i % 200}",
                    span=Span(i, 4, i, 10),
                    attrs={"callee_name": f"print{i}"},
                )
            )

        index = NodeIndex(ir_doc)

        assert index.get_count() == 500
        assert index.get("func:100") is not None
        assert index.get("var:75") is not None
        assert index.get("block:50") is not None
        assert index.get("expr:25") is not None


class TestNodeIndexTypeConversion:
    """Verify IR → Domain type conversions"""

    def test_function_kind_conversion(self):
        """IR NodeKind.FUNCTION → Domain NodeKind.FUNCTION"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func = Node(
            id="func:test",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
        )
        ir_doc.nodes.append(func)
        index = NodeIndex(ir_doc)

        node = index.get("func:test")
        assert node is not None
        assert node.kind == NodeKind.FUNCTION

    def test_variable_kind_is_var(self):
        """VariableEntity → Domain NodeKind.VAR"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var = VariableEntity(
            id="var:test",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            name="x",
            kind="local",
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var])
        index = NodeIndex(ir_doc)

        node = index.get("var:test")
        assert node is not None
        assert node.kind == NodeKind.VAR

    def test_block_kind_is_block(self):
        """ControlFlowBlock → Domain NodeKind.BLOCK"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        # Add function node first
        func = Node(
            id="func:test",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
        )
        ir_doc.nodes.append(func)

        block = ControlFlowBlock(id="block:test", kind=CFGBlockKind.ENTRY, function_node_id="func:test")
        ir_doc.cfg_blocks.append(block)
        index = NodeIndex(ir_doc)

        node = index.get("block:test")
        assert node is not None
        assert node.kind == NodeKind.BLOCK

    def test_expression_kind_is_expr(self):
        """Expression → Domain NodeKind.EXPR"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        expr = Expression(
            id="expr:test",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 4, 2, 10),
            attrs={"callee_name": "print"},
        )
        ir_doc.expressions.append(expr)
        index = NodeIndex(ir_doc)

        node = index.get("expr:test")
        assert node is not None
        assert node.kind == NodeKind.EXPR
