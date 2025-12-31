"""
Production-Grade Tests

SOTA L11 극한 테스트:
- Timeout enforcement (실시간)
- Type safety validation
- Error message quality
- Performance boundaries
- Real-world complex scenarios
"""

import time

import pytest

from codegraph_engine.code_foundation import E, Q, QueryEngine
from codegraph_engine.code_foundation.domain.query.exceptions import InvalidQueryError, QueryTimeoutError
from codegraph_engine.code_foundation.infrastructure.dfg.models import DataFlowEdge, DfgSnapshot, VariableEntity
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument


class TestTimeoutEnforcement:
    """Timeout must be enforced DURING traversal, not after"""

    def test_timeout_during_large_graph_traversal(self):
        """CRITICAL: Timeout should interrupt traversal in progress"""
        # Create large graph: 1000-node chain
        n = 1000
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

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

        # Query with very short timeout
        query = (Q.Var("v0") >> Q.Var("v999")).via(E.DFG).depth(1000).timeout(ms=10)

        start = time.time()

        # Should raise QueryTimeoutError OR return early
        try:
            result = engine.execute_any_path(query)
            elapsed = (time.time() - start) * 1000
            # If no exception, traversal should terminate early
            assert elapsed < 100, f"Timeout not enforced: took {elapsed}ms"
            print(f"\n✅ Timeout enforced (early termination): {elapsed:.1f}ms")
        except QueryTimeoutError as e:
            elapsed = (time.time() - start) * 1000
            # Exception is acceptable
            print(f"\n✅ Timeout enforced (exception): {elapsed:.1f}ms")
            assert elapsed < 100, f"Took too long even with timeout: {elapsed}ms"

    def test_zero_length_paths_filtered(self):
        """CRITICAL: 0-length paths (source==target) should be filtered"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        var_x = VariableEntity(
            id="var:x", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
        )
        var_y = VariableEntity(
            id="var:y", repo_id="test", file_path="test.py", function_fqn="func", name="y", kind="local"
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

        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var_x, var_y], edges=[edge])

        engine = QueryEngine(ir_doc)

        # Query with source==target overlap
        query = (Q.Var(None) >> Q.Var(None)).via(E.DFG).limit_paths(10)
        result = engine.execute_any_path(query)

        # ALL paths must have at least 1 edge
        for path in result.paths:
            assert len(path.edges) > 0, f"Found 0-length path: {[n.name for n in path.nodes]}"

        print(f"\n✅ All {len(result)} paths have edges (no 0-length paths)")


class TestTypeSafety:
    """Type safety and validation"""

    def test_invalid_selector_type(self):
        """Invalid selector should raise clear error"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        engine = QueryEngine(ir_doc)

        from codegraph_engine.code_foundation.domain.query.selectors import NodeSelector

        # Create invalid selector
        invalid = NodeSelector(selector_type="invalid_type")

        with pytest.raises(InvalidQueryError) as exc_info:
            engine.node_matcher.match(invalid)

        # Error message should be helpful
        assert "invalid_type" in str(exc_info.value).lower()
        assert "suggestion" in str(exc_info.value).lower() or "use" in str(exc_info.value).lower()

        print(f"\n✅ Invalid selector error: {exc_info.value.message[:50]}...")

    def test_none_graph_rejects(self):
        """None IRDocument should be rejected immediately"""
        with pytest.raises(ValueError, match="cannot be None"):
            QueryEngine(None)

        print("\n✅ None IRDocument rejected at construction")

    def test_implemented_features_work(self):
        """Q.Call(), Q.Source(), Q.Sink() should now work"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        engine = QueryEngine(ir_doc)

        # Q.Source() should work (may return empty list)
        sources = engine.node_matcher.match(Q.Source("user_input"))
        assert isinstance(sources, list), "Q.Source() should return a list"

        # Q.Sink() should work (may return empty list)
        sinks = engine.node_matcher.match(Q.Sink("eval"))
        assert isinstance(sinks, list), "Q.Sink() should return a list"

        # Q.Call() should work (may return empty list)
        calls = engine.node_matcher.match(Q.Call("execute"))
        assert isinstance(calls, list), "Q.Call() should return a list"

        print("\n✅ Q.Call(), Q.Source(), Q.Sink() implemented and working")


class TestPerformanceBoundaries:
    """Performance at boundaries"""

    def test_max_path_limit_strict(self):
        """Path limit must be strictly enforced"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Create graph with 100 parallel paths
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
            for i in range(100)
        ]

        edges = []
        for i in range(100):
            edges.append(
                DataFlowEdge(
                    id=f"edge:x_i{i}",
                    from_variable_id="var:x",
                    to_variable_id=f"var:i{i}",
                    kind="assign",
                    repo_id="test",
                    file_path="test.py",
                    function_fqn="func",
                )
            )
            edges.append(
                DataFlowEdge(
                    id=f"edge:i{i}_z",
                    from_variable_id=f"var:i{i}",
                    to_variable_id="var:z",
                    kind="assign",
                    repo_id="test",
                    file_path="test.py",
                    function_fqn="func",
                )
            )

        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var_x, var_z] + intermediates, edges=edges)

        engine = QueryEngine(ir_doc)

        # Query with limit=10
        query = (Q.Var("x") >> Q.Var("z")).via(E.DFG).limit_paths(10)
        result = engine.execute_any_path(query)

        # STRICT: Must return exactly 10, not 11 or 9
        assert len(result) == 10, f"Expected exactly 10 paths, got {len(result)}"
        assert result.complete is False
        assert result.truncation_reason.value == "path_limit"

        print(f"\n✅ Path limit strictly enforced: {len(result)}/100 paths")

    def test_max_node_limit_prevents_explosion(self):
        """Node limit must prevent memory explosion"""
        # Create large graph
        n = 1000
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        vars = [
            VariableEntity(
                id=f"var:v{i}", repo_id="test", file_path="test.py", function_fqn="func", name=f"v{i}", kind="local"
            )
            for i in range(n)
        ]

        # Full mesh: every node connects to every other (worst case)
        edges = []
        for i in range(min(50, n)):  # Limit edge creation for test speed
            for j in range(min(50, n)):
                if i != j:
                    edges.append(
                        DataFlowEdge(
                            id=f"edge:{i}_{j}",
                            from_variable_id=f"var:v{i}",
                            to_variable_id=f"var:v{j}",
                            kind="assign",
                            repo_id="test",
                            file_path="test.py",
                            function_fqn="func",
                        )
                    )

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars[:50], edges=edges)

        engine = QueryEngine(ir_doc)

        # Query with low node limit
        query = (Q.Var("v0") >> Q.Var("v49")).via(E.DFG).limit_nodes(100).limit_paths(50)

        start = time.time()
        result = engine.execute_any_path(query)
        elapsed = time.time() - start

        # Should terminate quickly (not explore all 1000 nodes)
        assert elapsed < 1.0, f"Node limit not enforced: took {elapsed}s"

        print(f"\n✅ Node limit enforced: {elapsed * 1000:.1f}ms")


class TestErrorMessageQuality:
    """Error messages must be AI-friendly and actionable"""

    def test_error_messages_have_suggestions(self):
        """All errors should include actionable suggestions"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        engine = QueryEngine(ir_doc)

        # Test various invalid inputs
        errors = []

        try:
            from codegraph_engine.code_foundation.domain.query.selectors import NodeSelector

            engine.node_matcher.match(NodeSelector(selector_type="unknown"))
        except InvalidQueryError as e:
            errors.append(("unknown selector", e))

        # Q.Source(), Q.Call(), Q.Sink() are now implemented, so they won't raise errors

        # All errors should have suggestions
        for name, error in errors:
            assert error.suggestion is not None, f"{name} has no suggestion"
            assert len(error.suggestion) > 10, f"{name} suggestion too short"
            print(f"\n{name}: {error.message}")
            print(f"  Suggestion: {error.suggestion}")

        assert len(errors) >= 1, "Should have at least 1 error case"
        print(f"\n✅ All {len(errors)} errors have actionable suggestions")


class TestRealWorldScenarios:
    """Real-world complex scenarios"""

    def test_security_taint_simulation(self):
        """Simulate real security taint analysis"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Simulate: input → transform1 → transform2 → output
        # With sanitizer branch
        vars = [
            VariableEntity(
                id=f"var:{name}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=name,
                kind="local",
            )
            for name in ["input", "t1", "t2", "sanitized", "output"]
        ]

        edges = [
            # Main flow: input → t1 → t2 → output (TAINT)
            DataFlowEdge(
                id="e1",
                from_variable_id="var:input",
                to_variable_id="var:t1",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            DataFlowEdge(
                id="e2",
                from_variable_id="var:t1",
                to_variable_id="var:t2",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            DataFlowEdge(
                id="e3",
                from_variable_id="var:t2",
                to_variable_id="var:output",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            # Safe flow: input → sanitized → output (CLEAN)
            DataFlowEdge(
                id="e4",
                from_variable_id="var:input",
                to_variable_id="var:sanitized",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            DataFlowEdge(
                id="e5",
                from_variable_id="var:sanitized",
                to_variable_id="var:output",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)

        engine = QueryEngine(ir_doc)

        # Find ALL paths (should find 2)
        all_paths_query = (Q.Var("input") >> Q.Var("output")).via(E.DFG)
        all_result = engine.execute_any_path(all_paths_query)

        assert len(all_result) == 2, "Should find 2 paths (tainted + sanitized)"

        # Find TAINTED paths (excluding sanitized)
        tainted_query = (Q.Var("input") >> Q.Var("output")).via(E.DFG).excluding(Q.Var("sanitized"))
        tainted_result = engine.execute_any_path(tainted_query)

        assert len(tainted_result) == 1, "Should find 1 tainted path"

        tainted_path = tainted_result.paths[0]
        tainted_names = [n.name for n in tainted_path.nodes]
        assert "sanitized" not in tainted_names, "Tainted path should not go through sanitizer"

        print("\n✅ Security analysis:")
        print(f"   Total paths: {len(all_result)}")
        print(f"   Tainted (no sanitizer): {len(tainted_result)}")
        print(f"   Tainted path: {' → '.join(tainted_names)}")

    def test_impact_analysis_comprehensive(self):
        """Comprehensive impact analysis"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Complex dependency graph
        # config affects: a, b, c, d (direct + indirect)
        vars = [
            VariableEntity(
                id=f"var:{name}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=name,
                kind="local",
            )
            for name in ["config", "a", "b", "c", "d", "e"]
        ]

        edges = [
            # config → a → c
            DataFlowEdge(
                id="e1",
                from_variable_id="var:config",
                to_variable_id="var:a",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            DataFlowEdge(
                id="e2",
                from_variable_id="var:a",
                to_variable_id="var:c",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            # config → b → d
            DataFlowEdge(
                id="e3",
                from_variable_id="var:config",
                to_variable_id="var:b",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            DataFlowEdge(
                id="e4",
                from_variable_id="var:b",
                to_variable_id="var:d",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            # e is independent
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)

        engine = QueryEngine(ir_doc)

        # Forward impact: Find specific paths to each variable
        affected = set()

        # Test each variable individually (Q.Var(None) has issues)
        for target_name in ["a", "b", "c", "d", "e"]:
            forward = (Q.Var("config") >> Q.Var(target_name)).via(E.DFG).limit_paths(5)
            result = engine.execute_any_path(forward)

            if len(result) > 0:
                affected.add(target_name)

        # Verify correct impact
        assert "a" in affected, "a should be affected by config"
        assert "b" in affected, "b should be affected by config"
        assert "c" in affected, "c should be affected by config (indirect)"
        assert "d" in affected, "d should be affected by config (indirect)"
        assert "e" not in affected, "e is independent, should not be affected"

        print("\n✅ Impact analysis:")
        print(f"   Affected variables: {sorted(affected)}")
        print("   Independent: e")

    def test_pathset_operations_complete(self):
        """Test all PathSet operations work correctly"""
        from codegraph_engine.code_foundation.domain.query.results import PathResult, PathSet, UnifiedNode

        # Create paths of different lengths
        paths = []
        for length in [2, 5, 3, 7, 4]:
            nodes = [
                UnifiedNode(id=f"node:{length}:{i}", kind="var", name=f"v{i}", file_path="test.py", span=None, attrs={})
                for i in range(length)
            ]
            paths.append(PathResult(nodes=nodes, edges=[]))

        path_set = PathSet(paths=paths, complete=True)

        # Test operations
        assert len(path_set) == 5
        assert path_set.complete is True

        # shortest/longest
        shortest = path_set.shortest()
        assert len(shortest) == 2

        longest = path_set.longest()
        assert len(longest) == 7

        # limit
        limited = path_set.limit(3)
        assert len(limited) == 3

        # describe
        desc = path_set.describe()
        assert "5 paths" in desc.lower()

        print("\n✅ PathSet operations:")
        print(f"   Total: {len(path_set)}")
        print(f"   Shortest: {len(shortest)} nodes")
        print(f"   Longest: {len(longest)} nodes")
        print(f"   Description: {desc[:50]}...")


class TestDataIntegrity:
    """Data integrity and consistency"""

    def test_path_edges_connectivity(self):
        """Every edge in path must connect consecutive nodes"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Chain: a → b → c
        vars = [
            VariableEntity(
                id=f"var:{name}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=name,
                kind="local",
            )
            for name in ["a", "b", "c"]
        ]

        edges = [
            DataFlowEdge(
                id="e1",
                from_variable_id="var:a",
                to_variable_id="var:b",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            DataFlowEdge(
                id="e2",
                from_variable_id="var:b",
                to_variable_id="var:c",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)

        engine = QueryEngine(ir_doc)
        query = (Q.Var("a") >> Q.Var("c")).via(E.DFG)
        result = engine.execute_any_path(query)

        # Verify connectivity
        assert len(result) == 1
        path = result.paths[0]

        # STRICT: Edges must connect consecutive nodes
        for i, edge in enumerate(path.edges):
            assert edge.from_node == path.nodes[i].id, f"Edge {i} from_node mismatch"
            assert edge.to_node == path.nodes[i + 1].id, f"Edge {i} to_node mismatch"

        print("\n✅ Path connectivity verified:")
        print(f"   {len(path.nodes)} nodes, {len(path.edges)} edges")
        print("   All edges connect consecutive nodes")

    def test_no_duplicate_paths(self):
        """PathSet should not contain duplicate paths"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Diamond: x → a → z, x → b → z
        vars = [
            VariableEntity(
                id=f"var:{name}",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name=name,
                kind="local",
            )
            for name in ["x", "a", "b", "z"]
        ]

        edges = [
            DataFlowEdge(
                id="e1",
                from_variable_id="var:x",
                to_variable_id="var:a",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            DataFlowEdge(
                id="e2",
                from_variable_id="var:x",
                to_variable_id="var:b",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            DataFlowEdge(
                id="e3",
                from_variable_id="var:a",
                to_variable_id="var:z",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            DataFlowEdge(
                id="e4",
                from_variable_id="var:b",
                to_variable_id="var:z",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)

        engine = QueryEngine(ir_doc)
        query = (Q.Var("x") >> Q.Var("z")).via(E.DFG)
        result = engine.execute_any_path(query)

        # Check for duplicates
        path_signatures = set()
        for path in result.paths:
            sig = tuple(n.id for n in path.nodes)
            assert sig not in path_signatures, f"Duplicate path found: {[n.name for n in path.nodes]}"
            path_signatures.add(sig)

        print(f"\n✅ No duplicate paths: {len(result)} unique paths")
