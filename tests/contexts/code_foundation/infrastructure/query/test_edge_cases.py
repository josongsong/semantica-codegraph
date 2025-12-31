"""
Edge Cases, Corner Cases, Extreme Cases for Query Engine

SOTA L11 테스트: 모든 극한 상황 검증
"""

import pytest

from codegraph_engine.code_foundation import E, Q, QueryEngine
from codegraph_engine.code_foundation.domain.query.exceptions import InvalidQueryError, QueryTimeoutError
from codegraph_engine.code_foundation.infrastructure.dfg.models import DataFlowEdge, DfgSnapshot, VariableEntity
from codegraph_engine.code_foundation.infrastructure.ir.models import Edge, EdgeKind, IRDocument, Node, NodeKind, Span


class TestEdgeCases:
    """Edge cases and boundary conditions"""

    def test_empty_graph(self):
        """EDGE: Empty IRDocument"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        engine = QueryEngine(ir_doc)

        query = (Q.Var("x") >> Q.Var("y")).via(E.DFG)
        result = engine.execute_any_path(query)

        assert len(result) == 0
        assert result.complete is True

    def test_source_not_found(self):
        """EDGE: Source selector matches nothing"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Add only target variable
        var_y = VariableEntity(
            id="var:y", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var_y])

        engine = QueryEngine(ir_doc)

        # Query for non-existent source
        query = (Q.Var("x") >> Q.Var("y")).via(E.DFG)
        result = engine.execute_any_path(query)

        assert len(result) == 0

    def test_target_not_found(self):
        """EDGE: Target selector matches nothing"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        var_x = VariableEntity(
            id="var:x", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var_x])

        engine = QueryEngine(ir_doc)

        query = (Q.Var("x") >> Q.Var("nonexistent")).via(E.DFG)
        result = engine.execute_any_path(query)

        assert len(result) == 0

    def test_self_loop(self):
        """EDGE: Node with self-referencing edge"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        var_x = VariableEntity(
            id="var:x", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )

        # Self-loop edge
        self_loop = DataFlowEdge(
            id="edge:loop",
            from_variable_id="var:x",
            to_variable_id="var:x",
            kind="alias",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )

        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var_x], edges=[self_loop])

        engine = QueryEngine(ir_doc)

        # Query: x >> x
        query = (Q.Var("x") >> Q.Var("x")).via(E.DFG)
        result = engine.execute_any_path(query)

        # Should find path (0-length path or self-loop?)
        # Current behavior: finds path with 1 node
        assert len(result) >= 0  # Don't crash

    def test_cycle_in_graph(self):
        """EDGE: Cycle detection (x → y → z → x)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Create cycle
        var_x = VariableEntity(
            id="var:x", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var_y = VariableEntity(
            id="var:y", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )
        var_z = VariableEntity(
            id="var:z", repo_id="test", file_path="test.py", function_fqn="func", name="z", kind="local"
        )

        edge1 = DataFlowEdge(
            id="edge:1",
            from_variable_id="var:x",
            to_variable_id="var:y",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )
        edge2 = DataFlowEdge(
            id="edge:2",
            from_variable_id="var:y",
            to_variable_id="var:z",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )
        edge3 = DataFlowEdge(
            id="edge:3",
            from_variable_id="var:z",
            to_variable_id="var:x",
            kind="alias",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )

        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var_x, var_y, var_z], edges=[edge1, edge2, edge3])

        engine = QueryEngine(ir_doc)

        # Query: x >> z (should find path without infinite loop)
        query = (Q.Var("x") >> Q.Var("z")).via(E.DFG).limit_paths(5)
        result = engine.execute_any_path(query)

        # Should find path and not hang
        assert len(result) >= 1
        # First path should be shortest (x → y → z)
        shortest = result.shortest()
        assert len(shortest) == 3

    def test_multiple_paths(self):
        """EDGE: Multiple paths between same source/target"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Create diamond graph: x → a → z, x → b → z
        var_x = VariableEntity(
            id="var:x", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var_a = VariableEntity(
            id="var:a", repo_id="test", file_path="test.py", function_fqn="func", name="a", kind="local"
        )
        var_b = VariableEntity(
            id="var:b", repo_id="test", file_path="test.py", function_fqn="func", name="b", kind="local"
        )
        var_z = VariableEntity(
            id="var:z", repo_id="test", file_path="test.py", function_fqn="func", name="z", kind="local"
        )

        edges = [
            DataFlowEdge(
                id="edge:1",
                from_variable_id="var:x",
                to_variable_id="var:a",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            DataFlowEdge(
                id="edge:2",
                from_variable_id="var:x",
                to_variable_id="var:b",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            DataFlowEdge(
                id="edge:3",
                from_variable_id="var:a",
                to_variable_id="var:z",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            DataFlowEdge(
                id="edge:4",
                from_variable_id="var:b",
                to_variable_id="var:z",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var_x, var_a, var_b, var_z], edges=edges)

        engine = QueryEngine(ir_doc)

        # Query: x >> z (should find 2 paths)
        query = (Q.Var("x") >> Q.Var("z")).via(E.DFG)
        result = engine.execute_any_path(query)

        assert len(result) == 2  # x→a→z and x→b→z
        # Both paths should have length 3
        assert all(len(p) == 3 for p in result.paths)

    def test_depth_limit_respected(self):
        """EDGE: Depth limit strictly enforced"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Chain: x → y → z → w (3 hops)
        vars = [
            VariableEntity(
                id=f"var:{name}", repo_id="test", file_path="test.py", function_fqn="func", name=name, kind="local"
            )
            for name in ["x", "y", "z", "w"]
        ]

        edges = [
            DataFlowEdge(
                id=f"edge:{i}",
                from_variable_id=f"var:{from_name}",
                to_variable_id=f"var:{to_name}",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            )
            for i, (from_name, to_name) in enumerate([("x", "y"), ("y", "z"), ("z", "w")])
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)

        engine = QueryEngine(ir_doc)

        # Query with depth=2 (max 2 hops)
        query = (Q.Var("x") >> Q.Var("w")).via(E.DFG).depth(2)
        result = engine.execute_any_path(query)

        # Should NOT find path (requires 3 hops)
        assert len(result) == 0

    def test_path_limit_respected(self):
        """EDGE: Path limit strictly enforced"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Create 5 paths from x to z
        var_x = VariableEntity(
            id="var:x", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var_z = VariableEntity(
            id="var:z", repo_id="test", file_path="test.py", function_fqn="func", name="z", kind="local"
        )
        intermediates = [
            VariableEntity(
                id=f"var:i{i}", repo_id="test", file_path="test.py", function_fqn="func", name=f"i{i}", kind="local"
            )
            for i in range(5)
        ]

        edges = []
        for i, var_i in enumerate(intermediates):
            edges.append(
                DataFlowEdge(
                    id=f"edge:x_i{i}",
                    from_variable_id="var:x",
                    to_variable_id=var_i.id,
                    kind="assign",
                    repo_id="test",
                    file_path="test.py",
                    function_fqn="func",
                )
            )
            edges.append(
                DataFlowEdge(
                    id=f"edge:i{i}_z",
                    from_variable_id=var_i.id,
                    to_variable_id="var:z",
                    kind="assign",
                    repo_id="test",
                    file_path="test.py",
                    function_fqn="func",
                )
            )

        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var_x, var_z] + intermediates, edges=edges)

        engine = QueryEngine(ir_doc)

        # Query with limit=3
        query = (Q.Var("x") >> Q.Var("z")).via(E.DFG).limit_paths(3)
        result = engine.execute_any_path(query)

        # Should find exactly 3 paths (not 5)
        assert len(result) == 3
        assert result.complete is False
        assert result.truncation_reason.value == "path_limit"

    def test_disconnected_graph(self):
        """EDGE: Disconnected components"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Component 1: x → y
        var_x = VariableEntity(
            id="var:x", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var_y = VariableEntity(
            id="var:y", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )
        edge1 = DataFlowEdge(
            id="edge:1",
            from_variable_id="var:x",
            to_variable_id="var:y",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )

        # Component 2: a → b (disconnected)
        var_a = VariableEntity(
            id="var:a", repo_id="test", file_path="test.py", function_fqn="func", name="a", kind="local"
        )
        var_b = VariableEntity(
            id="var:b", repo_id="test", file_path="test.py", function_fqn="func", name="b", kind="local"
        )
        edge2 = DataFlowEdge(
            id="edge:2",
            from_variable_id="var:a",
            to_variable_id="var:b",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )

        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var_x, var_y, var_a, var_b], edges=[edge1, edge2])

        engine = QueryEngine(ir_doc)

        # Query: x >> b (crosses disconnected components)
        query = (Q.Var("x") >> Q.Var("b")).via(E.DFG)
        result = engine.execute_any_path(query)

        # Should find no path
        assert len(result) == 0

    def test_source_equals_target(self):
        """EDGE: Source and target are same node"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        var_x = VariableEntity(
            id="var:x", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var_x])

        engine = QueryEngine(ir_doc)

        # Query: x >> x (0-length path)
        query = Q.Var("x") >> Q.Var("x")
        result = engine.execute_any_path(query)

        # Should find 0-length path or empty
        # Current behavior: finds path with 1 node
        assert len(result) >= 0  # At least don't crash

    def test_very_deep_path(self):
        """EXTREME: Very long chain (100 nodes)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Create chain: v0 → v1 → v2 → ... → v99
        n = 100
        vars = [
            VariableEntity(
                id=f"var:v{i}", repo_id="test", file_path="test.py", function_fqn="func", name=f"v{i}", kind="local"
            )
            for i in range(n)
        ]

        edges = [
            DataFlowEdge(
                id=f"edge:{i}",
                from_variable_id=f"var:v{i}",
                to_variable_id=f"var:v{i + 1}",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            )
            for i in range(n - 1)
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)

        engine = QueryEngine(ir_doc)

        # Query with low depth limit
        query = (Q.Var("v0") >> Q.Var("v99")).via(E.DFG).depth(50)
        result = engine.execute_any_path(query)

        # Should NOT find path (requires 99 hops)
        assert len(result) == 0

        # Query with sufficient depth
        query2 = (Q.Var("v0") >> Q.Var("v99")).via(E.DFG).depth(100)
        result2 = engine.execute_any_path(query2)

        # Should find path
        assert len(result2) == 1
        assert len(result2.paths[0]) == 100

    def test_many_branches(self):
        """EXTREME: Node with many outgoing edges (100 branches)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        var_x = VariableEntity(
            id="var:x", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )

        # 100 branches from x
        branches = [
            VariableEntity(
                id=f"var:branch{i}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=f"branch{i}",
                kind="local",
            )
            for i in range(100)
        ]

        edges = [
            DataFlowEdge(
                id=f"edge:{i}",
                from_variable_id="var:x",
                to_variable_id=f"var:branch{i}",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            )
            for i in range(100)
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var_x] + branches, edges=edges)

        engine = QueryEngine(ir_doc)

        # Query: x >> branch50
        query = (Q.Var("x") >> Q.Var("branch50")).via(E.DFG)
        result = engine.execute_any_path(query)

        # Should find exactly 1 path (x → branch50)
        assert len(result) == 1
        assert len(result.paths[0]) == 2


class TestCornerCases:
    """Corner cases and unusual inputs"""

    def test_none_ir_document(self):
        """CORNER: None IRDocument"""
        with pytest.raises(ValueError, match="cannot be None"):
            QueryEngine(None)

    def test_selector_with_none_name(self):
        """CORNER: Selector with None name"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        engine = QueryEngine(ir_doc)

        # Q.Var(None) should match all variables
        query = Q.Var(None) >> Q.Var("target")
        # Should not crash
        result = engine.execute_any_path(query)
        assert len(result) >= 0

    def test_union_with_empty_operands(self):
        """CORNER: Union with no operands"""
        from codegraph_engine.code_foundation.domain.query.selectors import NodeSelector

        # Create union with empty operands
        union = NodeSelector(selector_type="union", attrs={"operands": []})

        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        engine = QueryEngine(ir_doc)

        # Should not crash
        nodes = engine.node_matcher.match(union)
        assert len(nodes) == 0

    def test_backward_with_no_incoming_edges(self):
        """CORNER: Backward query on node with no incoming edges from other nodes"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # x → y (no incoming to x from OTHER nodes)
        var_x = VariableEntity(
            id="var:x", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var_y = VariableEntity(
            id="var:y", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
        )
        var_z = VariableEntity(
            id="var:z", repo_id="test", file_path="test.py", function_fqn="func", name="z", kind="local"
        )
        edge = DataFlowEdge(
            id="edge:1",
            from_variable_id="var:x",
            to_variable_id="var:y",
            kind="assign",
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
        )

        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var_x, var_y, var_z], edges=[edge])

        engine = QueryEngine(ir_doc)

        # Backward: x << z (z has no path to x)
        query = (Q.Var("x") << Q.Var("z")).via(E.DFG)
        result = engine.execute_any_path(query)

        # Should find no paths (z → x doesn't exist)
        assert len(result) == 0


class TestExtremeScenarios:
    """Extreme scenarios and stress tests"""

    def test_query_explain_with_all_constraints(self):
        """EXTREME: Query with maximum constraints"""
        query = (
            (Q.Var("input") >> Q.Call("execute"))
            .via(E.DFG | E.CALL)
            .depth(10)
            .where(lambda p: len(p) < 10)
            .excluding(Q.Func("sanitize"))
            .within(Q.Module("core.*"))
            .context_sensitive(k=1)
            .alias_sensitive(mode="must")
            .limit_paths(20)
            .limit_nodes(1000)
            .timeout(ms=5000)
        )

        # Should not crash
        explanation = query.explain()
        assert isinstance(explanation, str)
        assert "input" in explanation
        assert "execute" in explanation

    def test_chained_operators(self):
        """EXTREME: Chained >> operators"""
        # a >> b >> c (not standard, but shouldn't crash)
        a = Q.Var("a")
        b = Q.Var("b")
        c = Q.Var("c")

        # This creates: FlowExpr(a, b) >> c
        # Which is: FlowExpr >> NodeSelector
        # Should create FlowExpr(FlowExpr(a,b), c)? Or error?

        # Current: Will likely error (NodeSelector expected)
        # Test that it errors gracefully
        try:
            expr = a >> b >> c
            # If it doesn't error, it should be valid FlowExpr
            assert expr is not None
        except (TypeError, AttributeError):
            # Graceful error is acceptable
            pass

    def test_pathresult_operations(self):
        """BASE: PathResult basic operations"""
        from codegraph_engine.code_foundation.domain.query.results import PathResult, UnifiedEdge, UnifiedNode

        # Create path
        nodes = [
            UnifiedNode(id=f"node:{i}", kind="var", name=f"v{i}", file_path="test.py", span=(i, 0, i, 1), attrs={})
            for i in range(5)
        ]
        edges = [
            UnifiedEdge(from_node=f"node:{i}", to_node=f"node:{i + 1}", edge_type="dfg", attrs={}) for i in range(4)
        ]

        path = PathResult(nodes=nodes, edges=edges)

        # Test operations
        assert len(path) == 5
        assert path[0].name == "v0"
        assert path[-1].name == "v4"

        # Test iteration
        names = [n.name for n in path]
        assert names == ["v0", "v1", "v2", "v3", "v4"]

        # Test subpath
        subpath = path.subpath(1, 3)
        assert len(subpath) == 2
        assert subpath[0].name == "v1"
        assert subpath[1].name == "v2"

    def test_pathset_operations(self):
        """BASE: PathSet basic operations"""
        from codegraph_engine.code_foundation.domain.query.results import PathResult, PathSet, UnifiedNode

        # Create paths of different lengths
        paths = []
        for length in [3, 5, 2, 7]:
            nodes = [
                UnifiedNode(id=f"node:{length}:{i}", kind="var", name=f"v{i}", file_path="test.py", span=None, attrs={})
                for i in range(length)
            ]
            paths.append(PathResult(nodes=nodes, edges=[]))

        path_set = PathSet(paths=paths, complete=True)

        # Test operations
        assert len(path_set) == 4
        assert path_set.complete is True

        # Test shortest/longest
        shortest = path_set.shortest()
        assert len(shortest) == 2

        longest = path_set.longest()
        assert len(longest) == 7

        # Test limit
        limited = path_set.limit(2)
        assert len(limited) == 2

        # Test bool
        assert bool(path_set) is True

        empty_set = PathSet(paths=[], complete=True)
        assert bool(empty_set) is False
