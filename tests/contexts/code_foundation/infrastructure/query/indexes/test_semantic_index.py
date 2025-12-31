"""
SOTA-Level Unit Tests for SemanticIndex

Test Categories:
1. BASE: Standard operations
2. CORNER: Boundary conditions
3. EDGE: Unusual but valid inputs
4. EXTREME: Large-scale stress tests

Coverage Target: 100%
Performance Target: O(1) name lookup, O(k) retrieval
Type Safety: All return types validated (no None in results)
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot, VariableEntity
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument, Node, Span
from codegraph_engine.code_foundation.infrastructure.ir.models import NodeKind as IRNodeKind
from codegraph_engine.code_foundation.infrastructure.query.indexes import NodeIndex, SemanticIndex
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
    CFGBlockKind,
    ControlFlowBlock,
)
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import (
    Expression,
    ExprKind,
)


class TestSemanticIndexBase:
    """BASE: Standard operations"""

    def test_init_with_empty_ir(self):
        """Empty IR should create empty semantic index"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        stats = index.get_stats()
        assert stats["unique_var_names"] == 0
        assert stats["unique_func_names"] == 0
        assert stats["unique_class_names"] == 0

    def test_find_vars_by_name_single_match(self):
        """Find variable by name"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="my_var", kind="local"
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var])
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        vars_found = index.find_vars_by_name("my_var")
        assert len(vars_found) == 1
        assert vars_found[0].name == "my_var"
        assert vars_found[0].id == "var:1"

    def test_find_vars_by_name_no_match(self):
        """Find variable that doesn't exist returns empty list"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        vars_found = index.find_vars_by_name("nonexistent")
        assert vars_found == []

    def test_find_funcs_by_name_single_match(self):
        """Find function by name"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func = Node(
            id="func:1",
            kind=IRNodeKind.FUNCTION,
            fqn="test.process_data",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
            name="process_data",
        )
        ir_doc.nodes.append(func)
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        funcs_found = index.find_funcs_by_name("process_data")
        assert len(funcs_found) == 1
        assert funcs_found[0].name == "process_data"

    def test_find_funcs_by_name_no_match(self):
        """Find function that doesn't exist returns empty list"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        funcs_found = index.find_funcs_by_name("nonexistent")
        assert funcs_found == []

    def test_find_classes_by_name_single_match(self):
        """Find class by name"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        cls = Node(
            id="class:1",
            kind=IRNodeKind.CLASS,
            fqn="test.Calculator",
            file_path="test.py",
            span=Span(1, 0, 10, 0),
            language="python",
            name="Calculator",
        )
        ir_doc.nodes.append(cls)
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        classes_found = index.find_classes_by_name("Calculator")
        assert len(classes_found) == 1
        assert classes_found[0].name == "Calculator"

    def test_find_call_sites_by_name_single_match(self):
        """Find call sites by callee name"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
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
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        call_sites = index.find_call_sites_by_name("print")
        assert len(call_sites) == 1
        assert call_sites[0].id == "expr:1"

    def test_find_blocks_by_function_single_match(self):
        """Find CFG blocks by function ID"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func = Node(
            id="func:1",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
        )
        ir_doc.nodes.append(func)

        block = ControlFlowBlock(id="block:1", kind=CFGBlockKind.ENTRY, function_node_id="func:1")
        ir_doc.cfg_blocks.append(block)

        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        blocks = index.find_blocks_by_function("func:1")
        assert len(blocks) == 1
        assert blocks[0].id == "block:1"


class TestSemanticIndexCorner:
    """CORNER: Boundary conditions"""

    def test_multiple_vars_same_name(self):
        """Multiple variables with same name (different scopes)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func1", name="x", kind="local"
        )
        var2 = VariableEntity(
            id="var:2", repo_id="test", file_path="test.py", function_fqn="func2", name="x", kind="local"
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2])
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        vars_found = index.find_vars_by_name("x")
        assert len(vars_found) == 2

    def test_multiple_funcs_same_name(self):
        """Multiple functions with same name (different modules)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func1 = Node(
            id="func:1",
            kind=IRNodeKind.FUNCTION,
            fqn="module1.process",
            file_path="test1.py",
            span=Span(1, 0, 5, 0),
            language="python",
            name="process",
        )
        func2 = Node(
            id="func:2",
            kind=IRNodeKind.FUNCTION,
            fqn="module2.process",
            file_path="test2.py",
            span=Span(1, 0, 5, 0),
            language="python",
            name="process",
        )
        ir_doc.nodes.extend([func1, func2])
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        funcs_found = index.find_funcs_by_name("process")
        assert len(funcs_found) == 2

    def test_function_without_name(self):
        """Function with empty name should NOT be indexed by name (filtered)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func = Node(
            id="func:1",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
            name="",
        )
        ir_doc.nodes.append(func)
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        funcs_found = index.find_funcs_by_name("")
        # Empty names are intentionally NOT indexed (semantic search requires meaningful names)
        assert len(funcs_found) == 0

    def test_variable_without_name(self):
        """Variable with empty name should NOT be indexed (filtered)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="", kind="local"
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var])
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        vars_found = index.find_vars_by_name("")
        # Empty names are intentionally NOT indexed (semantic search requires meaningful names)
        assert len(vars_found) == 0

    def test_multiple_blocks_same_function(self):
        """Multiple CFG blocks for same function"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func = Node(
            id="func:1",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
        )
        ir_doc.nodes.append(func)

        block1 = ControlFlowBlock(id="block:1", kind=CFGBlockKind.ENTRY, function_node_id="func:1")
        block2 = ControlFlowBlock(id="block:2", kind=CFGBlockKind.BLOCK, function_node_id="func:1")
        block3 = ControlFlowBlock(id="block:3", kind=CFGBlockKind.EXIT, function_node_id="func:1")
        ir_doc.cfg_blocks.extend([block1, block2, block3])

        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        blocks = index.find_blocks_by_function("func:1")
        assert len(blocks) == 3

    def test_call_site_without_callee_name(self):
        """Call expression without callee_name shouldn't be indexed by name"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        expr = Expression(
            id="expr:1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 4, 2, 10),
            attrs={},
        )
        ir_doc.expressions.append(expr)
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        # No callee_name, so shouldn't find anything
        call_sites = index.find_call_sites_by_name("anything")
        assert call_sites == []


class TestSemanticIndexEdge:
    """EDGE: Unusual but valid inputs"""

    def test_find_vars_by_pattern_wildcard_prefix(self):
        """Find variables by pattern: user_*"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="user_id", kind="local"
        )
        var2 = VariableEntity(
            id="var:2", repo_id="test", file_path="test.py", function_fqn="func", name="user_name", kind="local"
        )
        var3 = VariableEntity(
            id="var:3", repo_id="test", file_path="test.py", function_fqn="func", name="admin_id", kind="local"
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2, var3])
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        vars_found = index.find_vars_by_pattern("user_*")
        assert len(vars_found) == 2
        names = {v.name for v in vars_found}
        assert names == {"user_id", "user_name"}

    def test_find_vars_by_pattern_wildcard_suffix(self):
        """Find variables by pattern: *_input"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="user_input", kind="local"
        )
        var2 = VariableEntity(
            id="var:2", repo_id="test", file_path="test.py", function_fqn="func", name="file_input", kind="local"
        )
        var3 = VariableEntity(
            id="var:3", repo_id="test", file_path="test.py", function_fqn="func", name="output", kind="local"
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2, var3])
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        vars_found = index.find_vars_by_pattern("*_input")
        assert len(vars_found) == 2

    def test_find_funcs_by_pattern_wildcard_prefix(self):
        """Find functions by pattern: get_*"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func1 = Node(
            id="func:1",
            kind=IRNodeKind.FUNCTION,
            fqn="test.get_user",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
            name="get_user",
        )
        func2 = Node(
            id="func:2",
            kind=IRNodeKind.FUNCTION,
            fqn="test.get_data",
            file_path="test.py",
            span=Span(6, 0, 10, 0),
            language="python",
            name="get_data",
        )
        func3 = Node(
            id="func:3",
            kind=IRNodeKind.FUNCTION,
            fqn="test.set_user",
            file_path="test.py",
            span=Span(11, 0, 15, 0),
            language="python",
            name="set_user",
        )
        ir_doc.nodes.extend([func1, func2, func3])
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        funcs_found = index.find_funcs_by_pattern("get_*")
        assert len(funcs_found) == 2

    def test_find_vars_by_name_and_type(self):
        """Find variables by name AND type (composite query)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var1 = VariableEntity(
            id="var:1",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            name="x",
            kind="local",
            type_id="type:int",
        )
        var2 = VariableEntity(
            id="var:2",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            name="x",
            kind="local",
            type_id="type:str",
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2])
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        vars_int = index.find_vars_by_name_and_type("x", "type:int")
        assert len(vars_int) == 1
        assert vars_int[0].id == "var:1"

    def test_find_vars_by_name_and_scope(self):
        """Find variables by name AND scope (composite query)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var1 = VariableEntity(
            id="var:1",
            repo_id="test",
            file_path="test.py",
            function_fqn="func1",
            name="x",
            kind="local",
            scope_id="scope:func1",
        )
        var2 = VariableEntity(
            id="var:2",
            repo_id="test",
            file_path="test.py",
            function_fqn="func2",
            name="x",
            kind="local",
            scope_id="scope:func2",
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2])
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        vars_func1 = index.find_vars_by_name_and_scope("x", "scope:func1")
        assert len(vars_func1) == 1
        assert vars_func1[0].id == "var:1"

    def test_find_funcs_in_class(self):
        """Find functions in specific class"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func1 = Node(
            id="func:1",
            kind=IRNodeKind.METHOD,
            fqn="test.Calculator.add",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
            name="Calculator.add",
        )
        func2 = Node(
            id="func:2",
            kind=IRNodeKind.METHOD,
            fqn="test.Parser.add",
            file_path="test.py",
            span=Span(6, 0, 10, 0),
            language="python",
            name="add",
        )
        ir_doc.nodes.extend([func1, func2])
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        funcs_in_calc = index.find_funcs_in_class("add", "Calculator")
        assert len(funcs_in_calc) == 1
        assert "Calculator" in funcs_in_calc[0].attrs.get("fqn", "")


class TestSemanticIndexExtreme:
    """EXTREME: Large-scale stress tests"""

    def test_index_1000_variables(self):
        """Index 1000 variables"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        variables = []
        for i in range(1000):
            var = VariableEntity(
                id=f"var:{i}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=f"x{i}",
                kind="local",
            )
            variables.append(var)
        ir_doc.dfg_snapshot = DfgSnapshot(variables=variables)
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        stats = index.get_stats()
        assert stats["total_vars"] == 1000

        # Random access should be O(1)
        vars_500 = index.find_vars_by_name("x500")
        assert len(vars_500) == 1

    def test_index_1000_functions(self):
        """Index 1000 functions"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        for i in range(1000):
            func = Node(
                id=f"func:{i}",
                kind=IRNodeKind.FUNCTION,
                fqn=f"test.func{i}",
                file_path="test.py",
                span=Span(i * 10, 0, i * 10 + 5, 0),
                language="python",
                name=f"func{i}",
            )
            ir_doc.nodes.append(func)
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        stats = index.get_stats()
        assert stats["total_funcs"] == 1000

    def test_100_vars_same_name(self):
        """100 variables with same name (different scopes)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        variables = []
        for i in range(100):
            var = VariableEntity(
                id=f"var:{i}",
                repo_id="test",
                file_path="test.py",
                function_fqn=f"func{i}",
                name="x",
                kind="local",
            )
            variables.append(var)
        ir_doc.dfg_snapshot = DfgSnapshot(variables=variables)
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        vars_found = index.find_vars_by_name("x")
        assert len(vars_found) == 100

    def test_pattern_matching_performance(self):
        """Pattern matching should be O(M) where M = candidate count"""
        import time

        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        variables = []
        for i in range(1000):
            name = f"user_{i}" if i < 500 else f"admin_{i}"
            var = VariableEntity(
                id=f"var:{i}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=name,
                kind="local",
            )
            variables.append(var)
        ir_doc.dfg_snapshot = DfgSnapshot(variables=variables)
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        # Pattern matching should complete quickly
        start = time.perf_counter()
        vars_found = index.find_vars_by_pattern("user_*")
        elapsed = time.perf_counter() - start

        assert len(vars_found) == 500
        assert elapsed < 0.1  # Should complete in < 100ms

    def test_mixed_entities_large_scale(self):
        """Mix of 2000 entities (vars, funcs, classes, call sites, blocks)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # 500 variables
        variables = []
        for i in range(500):
            var = VariableEntity(
                id=f"var:{i}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=f"x{i}",
                kind="local",
            )
            variables.append(var)
        ir_doc.dfg_snapshot = DfgSnapshot(variables=variables)

        # 500 functions
        for i in range(500):
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

        # 500 classes
        for i in range(500):
            cls = Node(
                id=f"class:{i}",
                kind=IRNodeKind.CLASS,
                fqn=f"test.Class{i}",
                file_path="test.py",
                span=Span(i + 1000, 0, i + 1010, 0),
                language="python",
                name=f"Class{i}",
            )
            ir_doc.nodes.append(cls)

        # 250 call sites
        for i in range(250):
            expr = Expression(
                id=f"expr:{i}",
                kind=ExprKind.CALL,
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                span=Span(i + 2000, 4, i + 2000, 10),
                attrs={"callee_name": f"call{i}"},
            )
            ir_doc.expressions.append(expr)

        # 250 blocks
        for i in range(250):
            block = ControlFlowBlock(id=f"block:{i}", kind=CFGBlockKind.BLOCK, function_node_id=f"func:{i % 500}")
            ir_doc.cfg_blocks.append(block)

        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        stats = index.get_stats()
        assert stats["total_vars"] == 500
        assert stats["total_funcs"] == 500
        assert stats["total_classes"] == 500
        assert stats["total_call_sites"] == 250


class TestSemanticIndexTypeSafety:
    """Verify type safety: No None in results"""

    def test_find_vars_never_returns_none(self):
        """find_vars_by_name() never returns None in list"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        var = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var])
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        vars_found = index.find_vars_by_name("x")
        # Type check: No None values
        assert all(v is not None for v in vars_found)

    def test_find_funcs_never_returns_none(self):
        """find_funcs_by_name() never returns None in list"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
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
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        funcs_found = index.find_funcs_by_name("func")
        assert all(f is not None for f in funcs_found)

    def test_find_blocks_never_returns_none(self):
        """find_blocks_by_function() never returns None in list"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        func = Node(
            id="func:1",
            kind=IRNodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
        )
        ir_doc.nodes.append(func)

        block = ControlFlowBlock(id="block:1", kind=CFGBlockKind.ENTRY, function_node_id="func:1")
        ir_doc.cfg_blocks.append(block)

        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        blocks = index.find_blocks_by_function("func:1")
        assert all(b is not None for b in blocks)


class TestSemanticIndexStats:
    """Verify statistics accuracy"""

    def test_stats_counts_unique_names(self):
        """Stats should count unique names, not total entities"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # 3 variables, 2 unique names
        var1 = VariableEntity(
            id="var:1", repo_id="test", file_path="test.py", function_fqn="func1", name="x", kind="local"
        )
        var2 = VariableEntity(
            id="var:2", repo_id="test", file_path="test.py", function_fqn="func2", name="x", kind="local"
        )
        var3 = VariableEntity(
            id="var:3", repo_id="test", file_path="test.py", function_fqn="func3", name="y", kind="local"
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2, var3])

        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        stats = index.get_stats()
        assert stats["unique_var_names"] == 2  # "x" and "y"
        assert stats["total_vars"] == 3  # 3 variables total

    def test_stats_empty_index(self):
        """Stats for empty index should be all zeros"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        node_index = NodeIndex(ir_doc)
        index = SemanticIndex(ir_doc, node_index)

        stats = index.get_stats()
        assert stats["unique_var_names"] == 0
        assert stats["unique_func_names"] == 0
        assert stats["unique_class_names"] == 0
        assert stats["unique_call_names"] == 0
        assert stats["total_vars"] == 0
        assert stats["total_funcs"] == 0
        assert stats["total_classes"] == 0
        assert stats["total_call_sites"] == 0
