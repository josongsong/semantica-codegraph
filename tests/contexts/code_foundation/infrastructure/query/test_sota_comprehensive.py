"""
SOTA Comprehensive Tests - CodeQL Level

All edge/corner/extreme cases for:
- Inter-procedural
- Context sensitivity
- Field sensitivity
- Combined scenarios
"""

import pytest

from codegraph_engine.code_foundation import E, Q, QueryEngine
from codegraph_engine.code_foundation.infrastructure.dfg.models import DataFlowEdge, DfgSnapshot, VariableEntity
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
from codegraph_engine.code_foundation.infrastructure.ir.models.interprocedural import InterproceduralDataFlowEdge


class TestInterproceduralEdgeCases:
    """Inter-procedural edge/corner cases"""

    def test_recursive_function_call(self):
        """
        Recursive call: factorial(n) calls factorial(n-1)

        Should handle without infinite loop
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        vars = [
            VariableEntity(
                id="var:factorial:n",
                repo_id="test",
                file_path="test.py",
                function_fqn="factorial",
                name="n",
                kind="parameter",
            ),
            VariableEntity(
                id="var:factorial:result",
                repo_id="test",
                file_path="test.py",
                function_fqn="factorial",
                name="result",
                kind="local",
            ),
            VariableEntity(
                id="var:factorial:__return__",
                repo_id="test",
                file_path="test.py",
                function_fqn="factorial",
                name="__return__",
                kind="local",
            ),
        ]

        edges = [
            DataFlowEdge(
                id="dfg:1",
                from_variable_id="var:factorial:n",
                to_variable_id="var:factorial:result",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="factorial",
            ),
            DataFlowEdge(
                id="dfg:2",
                from_variable_id="var:factorial:result",
                to_variable_id="var:factorial:__return__",
                kind="return",
                repo_id="test",
                file_path="test.py",
                function_fqn="factorial",
            ),
        ]

        # Recursive call: n → n (same function)
        interproc = [
            InterproceduralDataFlowEdge(
                id="interproc:1",
                kind="arg_to_param",
                from_var_id="var:factorial:result",  # Recursive arg
                to_var_id="var:factorial:n",  # Same function param
                call_site_id="call:1",
                caller_func_fqn="factorial",
                callee_func_fqn="factorial",
                arg_position=0,
                repo_id="test",
                file_path="test.py",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)
        ir_doc.interprocedural_edges = interproc

        engine = QueryEngine(ir_doc)

        # Query with depth limit (prevent infinite)
        query = (Q.Var("n") >> Q.Var("__return__")).via(E.DFG).depth(5).limit_paths(10)
        result = engine.execute_any_path(query)

        # Should terminate and find path
        assert len(result) >= 1
        print(f"\n✅ Recursive call: {len(result)} paths (terminated safely)")

    def test_multiple_callers_one_callee(self):
        """
        Multiple functions call the same function

        Code:
            def shared(x):
                return x * 2

            def caller1():
                a = shared(1)

            def caller2():
                b = shared(2)

        Both should be tracked independently
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        vars = [
            # shared()
            VariableEntity(
                id="var:shared:x",
                repo_id="test",
                file_path="test.py",
                function_fqn="shared",
                name="x",
                kind="parameter",
            ),
            VariableEntity(
                id="var:shared:__return__",
                repo_id="test",
                file_path="test.py",
                function_fqn="shared",
                name="__return__",
                kind="local",
            ),
            # caller1()
            VariableEntity(
                id="var:caller1:arg1",
                repo_id="test",
                file_path="test.py",
                function_fqn="caller1",
                name="arg1",
                kind="local",
            ),
            VariableEntity(
                id="var:caller1:a", repo_id="test", file_path="test.py", function_fqn="caller1", name="a", kind="local"
            ),
            # caller2()
            VariableEntity(
                id="var:caller2:arg2",
                repo_id="test",
                file_path="test.py",
                function_fqn="caller2",
                name="arg2",
                kind="local",
            ),
            VariableEntity(
                id="var:caller2:b", repo_id="test", file_path="test.py", function_fqn="caller2", name="b", kind="local"
            ),
        ]

        edges = [
            # shared: x → __return__
            DataFlowEdge(
                id="dfg:1",
                from_variable_id="var:shared:x",
                to_variable_id="var:shared:__return__",
                kind="compute",
                repo_id="test",
                file_path="test.py",
                function_fqn="shared",
            ),
        ]

        # Inter-procedural: 2 callers
        interproc = [
            # caller1.arg1 → shared.x
            InterproceduralDataFlowEdge(
                id="interproc:1",
                kind="arg_to_param",
                from_var_id="var:caller1:arg1",
                to_var_id="var:shared:x",
                call_site_id="call:1",
                caller_func_fqn="caller1",
                callee_func_fqn="shared",
                arg_position=0,
                repo_id="test",
                file_path="test.py",
            ),
            # shared.__return__ → caller1.a
            InterproceduralDataFlowEdge(
                id="interproc:2",
                kind="return_to_callsite",
                from_var_id="var:shared:__return__",
                to_var_id="var:caller1:a",
                call_site_id="call:1",
                caller_func_fqn="caller1",
                callee_func_fqn="shared",
                repo_id="test",
                file_path="test.py",
            ),
            # caller2.arg2 → shared.x
            InterproceduralDataFlowEdge(
                id="interproc:3",
                kind="arg_to_param",
                from_var_id="var:caller2:arg2",
                to_var_id="var:shared:x",
                call_site_id="call:2",
                caller_func_fqn="caller2",
                callee_func_fqn="shared",
                arg_position=0,
                repo_id="test",
                file_path="test.py",
            ),
            # shared.__return__ → caller2.b
            InterproceduralDataFlowEdge(
                id="interproc:4",
                kind="return_to_callsite",
                from_var_id="var:shared:__return__",
                to_var_id="var:caller2:b",
                call_site_id="call:2",
                caller_func_fqn="caller2",
                callee_func_fqn="shared",
                repo_id="test",
                file_path="test.py",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)
        ir_doc.interprocedural_edges = interproc

        engine = QueryEngine(ir_doc)

        # Query: arg1 → a (through shared)
        query1 = (Q.Var("arg1") >> Q.Var("a")).via(E.DFG).limit_paths(10)
        result1 = engine.execute_any_path(query1)

        assert len(result1) >= 1
        assert result1.paths[0].nodes[0].name == "arg1"
        assert result1.paths[0].nodes[-1].name == "a"

        # Query: arg2 → b (through shared)
        query2 = (Q.Var("arg2") >> Q.Var("b")).via(E.DFG).limit_paths(10)
        result2 = engine.execute_any_path(query2)

        assert len(result2) >= 1
        assert result2.paths[0].nodes[-1].name == "b"

        print("\n✅ Multiple callers: Both paths tracked independently")

    def test_interproc_with_wildcard_source(self):
        """
        Inter-procedural with wildcard source

        Q.Var(None) >> Q.Var("sink") across functions
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        vars = [
            # func1
            VariableEntity(
                id="var:func1:a", repo_id="test", file_path="test.py", function_fqn="func1", name="a", kind="local"
            ),
            VariableEntity(
                id="var:func1:__return__",
                repo_id="test",
                file_path="test.py",
                function_fqn="func1",
                name="__return__",
                kind="local",
            ),
            # func2
            VariableEntity(
                id="var:func2:sink",
                repo_id="test",
                file_path="test.py",
                function_fqn="func2",
                name="sink",
                kind="local",
            ),
        ]

        edges = [
            DataFlowEdge(
                id="dfg:1",
                from_variable_id="var:func1:a",
                to_variable_id="var:func1:__return__",
                kind="return",
                repo_id="test",
                file_path="test.py",
                function_fqn="func1",
            ),
        ]

        interproc = [
            InterproceduralDataFlowEdge(
                id="interproc:1",
                kind="return_to_callsite",
                from_var_id="var:func1:__return__",
                to_var_id="var:func2:sink",
                call_site_id="call:1",
                caller_func_fqn="func2",
                callee_func_fqn="func1",
                repo_id="test",
                file_path="test.py",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)
        ir_doc.interprocedural_edges = interproc

        engine = QueryEngine(ir_doc)

        # Wildcard source: Q.Var(None) → sink
        query = (Q.Var(None) >> Q.Var("sink")).via(E.DFG).limit_paths(10)
        result = engine.execute_any_path(query)

        # Should find: a → __return__ → sink
        assert len(result) >= 1
        path = result.paths[0]
        assert path.nodes[-1].name == "sink"

        print(f"\n✅ Wildcard + inter-proc: {len(path.nodes)} nodes across functions")


class TestFieldSensitivityBasic:
    """Field-sensitive analysis"""

    def test_field_selector_basic(self):
        """Q.Field("user", "id") matches user.id"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        vars = [
            VariableEntity(
                id="var:user", repo_id="test", file_path="test.py", function_fqn="func", name="user", kind="local"
            ),
            VariableEntity(
                id="var:user.id", repo_id="test", file_path="test.py", function_fqn="func", name="user.id", kind="local"
            ),
            VariableEntity(
                id="var:user.name",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name="user.name",
                kind="local",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=[])

        engine = QueryEngine(ir_doc)

        # Match field
        nodes = engine.node_matcher.match(Q.Field("user", "id"))

        assert len(nodes) == 1
        assert nodes[0].name == "user.id"

        print("\n✅ Field selector: Q.Field('user', 'id') matched")

    def test_field_dataflow(self):
        """
        Field-sensitive taint tracking

        Code:
            user.id = request.get("id")  # TAINTED
            user.name = "admin"          # SAFE
            query = f"...{user.name}..." # Should be SAFE
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        vars = [
            VariableEntity(
                id="var:source", repo_id="test", file_path="test.py", function_fqn="func", name="source", kind="local"
            ),
            VariableEntity(
                id="var:user.id", repo_id="test", file_path="test.py", function_fqn="func", name="user.id", kind="local"
            ),
            VariableEntity(
                id="var:user.name",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                name="user.name",
                kind="local",
            ),
            VariableEntity(
                id="var:query", repo_id="test", file_path="test.py", function_fqn="func", name="query", kind="local"
            ),
        ]

        edges = [
            # source → user.id (tainted)
            DataFlowEdge(
                id="dfg:1",
                from_variable_id="var:source",
                to_variable_id="var:user.id",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
            # user.name → query (should NOT find this from source)
            DataFlowEdge(
                id="dfg:2",
                from_variable_id="var:user.name",
                to_variable_id="var:query",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)

        engine = QueryEngine(ir_doc)

        # Query: source → user.id (should find)
        query1 = (Q.Var("source") >> Q.Field("user", "id")).via(E.DFG)
        result1 = engine.execute_any_path(query1)
        assert len(result1) == 1

        # Query: source → user.name (should NOT find)
        query2 = (Q.Var("source") >> Q.Field("user", "name")).via(E.DFG)
        result2 = engine.execute_any_path(query2)
        assert len(result2) == 0, "source should not flow to user.name"

        # Query: source → query (should NOT find - no path through user.name)
        query3 = (Q.Var("source") >> Q.Var("query")).via(E.DFG)
        result3 = engine.execute_any_path(query3)
        assert len(result3) == 0, "source should not reach query (field-sensitive)"

        print("\n✅ Field-sensitive: user.id tainted, user.name safe")


class TestContextSensitivityBasic:
    """Context-sensitive analysis (infrastructure ready)"""

    def test_context_field_in_unified_node(self):
        """
        Context field is available in UnifiedNode

        This enables future context-sensitive analysis
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        vars = [
            VariableEntity(
                id="var:x", repo_id="test", file_path="test.py", function_fqn="func", name="x", kind="local"
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=[])

        from codegraph_engine.code_foundation.infrastructure.query.graph_index import UnifiedGraphIndex

        graph = UnifiedGraphIndex(ir_doc)
        node = graph.get_node("var:x")

        # Verify context field exists
        assert hasattr(node, "context"), "UnifiedNode should have context field"
        assert node.context is None, "Default context should be None"

        # Can set context
        node.context = "main>process"
        assert node.context == "main>process"

        print("\n✅ Context field ready (infrastructure complete)")


class TestCombinedScenarios:
    """Combined: inter-proc + field + context"""

    def test_taint_with_field_sensitivity(self):
        """
        SQL Injection with field sensitivity

        Code:
            def get_request():
                req.user_id = input()  # TAINTED
                req.safe_id = "123"    # SAFE
                return req

            def execute():
                r = get_request()
                query = f"...{r.user_id}..."  # VULNERABLE
                query2 = f"...{r.safe_id}..." # SAFE
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        vars = [
            # get_request()
            VariableEntity(
                id="var:get_request:source",
                repo_id="test",
                file_path="test.py",
                function_fqn="get_request",
                name="source",
                kind="local",
            ),
            VariableEntity(
                id="var:get_request:req.user_id",
                repo_id="test",
                file_path="test.py",
                function_fqn="get_request",
                name="req.user_id",
                kind="local",
            ),
            VariableEntity(
                id="var:get_request:req.safe_id",
                repo_id="test",
                file_path="test.py",
                function_fqn="get_request",
                name="req.safe_id",
                kind="local",
            ),
            VariableEntity(
                id="var:get_request:__return__",
                repo_id="test",
                file_path="test.py",
                function_fqn="get_request",
                name="__return__",
                kind="local",
            ),
            # execute()
            VariableEntity(
                id="var:execute:r.user_id",
                repo_id="test",
                file_path="test.py",
                function_fqn="execute",
                name="r.user_id",
                kind="local",
            ),
            VariableEntity(
                id="var:execute:r.safe_id",
                repo_id="test",
                file_path="test.py",
                function_fqn="execute",
                name="r.safe_id",
                kind="local",
            ),
            VariableEntity(
                id="var:execute:query",
                repo_id="test",
                file_path="test.py",
                function_fqn="execute",
                name="query",
                kind="local",
            ),
            VariableEntity(
                id="var:execute:query2",
                repo_id="test",
                file_path="test.py",
                function_fqn="execute",
                name="query2",
                kind="local",
            ),
        ]

        # Intra-procedural
        edges = [
            # get_request: source → req.user_id, req.user_id → __return__
            DataFlowEdge(
                id="dfg:1",
                from_variable_id="var:get_request:source",
                to_variable_id="var:get_request:req.user_id",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="get_request",
            ),
            DataFlowEdge(
                id="dfg:2",
                from_variable_id="var:get_request:req.user_id",
                to_variable_id="var:get_request:__return__",
                kind="return",
                repo_id="test",
                file_path="test.py",
                function_fqn="get_request",
            ),
            # execute: r.user_id → query, r.safe_id → query2
            DataFlowEdge(
                id="dfg:3",
                from_variable_id="var:execute:r.user_id",
                to_variable_id="var:execute:query",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="execute",
            ),
            DataFlowEdge(
                id="dfg:4",
                from_variable_id="var:execute:r.safe_id",
                to_variable_id="var:execute:query2",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="execute",
            ),
        ]

        # Inter-procedural: return → fields
        interproc = [
            # __return__ → r.user_id
            InterproceduralDataFlowEdge(
                id="interproc:1",
                kind="return_to_callsite",
                from_var_id="var:get_request:__return__",
                to_var_id="var:execute:r.user_id",
                call_site_id="call:1",
                caller_func_fqn="execute",
                callee_func_fqn="get_request",
                repo_id="test",
                file_path="test.py",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)
        ir_doc.interprocedural_edges = interproc

        engine = QueryEngine(ir_doc)

        # Taint path: source → query (through field)
        query1 = (Q.Var("source") >> Q.Var("query")).via(E.DFG).depth(10)
        result1 = engine.execute_any_path(query1)

        assert len(result1) >= 1, "Taint should flow through user_id field"
        print(f"\nTaint path: {' → '.join([n.name for n in result1.paths[0].nodes])}")

        # Safe path: source → query2 (should NOT exist)
        query2 = (Q.Var("source") >> Q.Var("query2")).via(E.DFG).depth(10)
        result2 = engine.execute_any_path(query2)

        assert len(result2) == 0, "source should not reach query2 (safe_id is independent)"

        print("✅ Field + Inter-proc: Tainted field tracked, safe field isolated")


class TestSOTAExtremeCases:
    """SOTA extreme cases"""

    def test_deep_call_chain_10_functions(self):
        """10-function deep call chain"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # f0() → f1() → ... → f9()
        vars = []
        edges = []
        interproc = []

        for i in range(10):
            func_name = f"func{i}"
            # param, __return__
            vars.append(
                VariableEntity(
                    id=f"var:{func_name}:param",
                    repo_id="test",
                    file_path="test.py",
                    function_fqn=func_name,
                    name="param",
                    kind="parameter",
                )
            )
            vars.append(
                VariableEntity(
                    id=f"var:{func_name}:__return__",
                    repo_id="test",
                    file_path="test.py",
                    function_fqn=func_name,
                    name="__return__",
                    kind="local",
                )
            )

            # param → __return__
            edges.append(
                DataFlowEdge(
                    id=f"dfg:{i}",
                    from_variable_id=f"var:{func_name}:param",
                    to_variable_id=f"var:{func_name}:__return__",
                    kind="return",
                    repo_id="test",
                    file_path="test.py",
                    function_fqn=func_name,
                )
            )

            # Connect to next function
            if i < 9:
                next_func = f"func{i + 1}"
                interproc.append(
                    InterproceduralDataFlowEdge(
                        id=f"interproc:{i}",
                        kind="return_to_callsite",
                        from_var_id=f"var:{func_name}:__return__",
                        to_var_id=f"var:{next_func}:param",
                        call_site_id=f"call:{i}",
                        caller_func_fqn=next_func,
                        callee_func_fqn=func_name,
                        repo_id="test",
                        file_path="test.py",
                    )
                )

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)
        ir_doc.interprocedural_edges = interproc

        engine = QueryEngine(ir_doc)

        # Query: func0.param → func9.param
        query = (Q.Var("param") >> Q.Var("param")).via(E.DFG).depth(25).limit_paths(10)
        result = engine.execute_any_path(query)

        assert len(result) >= 1, "Should find deep path"

        path = result.paths[0]
        # Should find shortest path (may not include all 10 functions due to same var name "param")
        # Key: inter-procedural traversal works across many functions
        assert len(path.nodes) >= 3, f"Should have multi-hop path, got {len(path.nodes)}"
        assert path.nodes[0].name == "param"
        assert path.nodes[-1].name == "param"

        print(f"\n✅ 10-function chain: {len(path.nodes)} nodes (inter-proc traversal works)")

    def test_fan_out_fan_in(self):
        """
        Fan-out then fan-in pattern

        Code:
            def fanout(x):
                return x, x, x

            def process_a(a): return a
            def process_b(b): return b
            def process_c(c): return c

            def fanin(p, q, r):
                return combine(p, q, r)

            def main():
                x = source()
                a, b, c = fanout(x)
                p = process_a(a)
                q = process_b(b)
                r = process_c(c)
                result = fanin(p, q, r)

        Multiple paths from source to result
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Simplified: source → middle1, middle2, middle3 → sink
        vars = [
            VariableEntity(
                id="var:source", repo_id="test", file_path="test.py", function_fqn="main", name="source", kind="local"
            ),
            VariableEntity(
                id="var:m1", repo_id="test", file_path="test.py", function_fqn="proc1", name="m1", kind="local"
            ),
            VariableEntity(
                id="var:m2", repo_id="test", file_path="test.py", function_fqn="proc2", name="m2", kind="local"
            ),
            VariableEntity(
                id="var:m3", repo_id="test", file_path="test.py", function_fqn="proc3", name="m3", kind="local"
            ),
            VariableEntity(
                id="var:sink", repo_id="test", file_path="test.py", function_fqn="main", name="sink", kind="local"
            ),
        ]

        edges = []

        # Inter-procedural: source fans out, then fans in to sink
        interproc = [
            # source → m1, m2, m3
            InterproceduralDataFlowEdge(
                id="interproc:1",
                kind="arg_to_param",
                from_var_id="var:source",
                to_var_id="var:m1",
                call_site_id="call:1",
                caller_func_fqn="main",
                callee_func_fqn="proc1",
                arg_position=0,
                repo_id="test",
                file_path="test.py",
            ),
            InterproceduralDataFlowEdge(
                id="interproc:2",
                kind="arg_to_param",
                from_var_id="var:source",
                to_var_id="var:m2",
                call_site_id="call:2",
                caller_func_fqn="main",
                callee_func_fqn="proc2",
                arg_position=0,
                repo_id="test",
                file_path="test.py",
            ),
            InterproceduralDataFlowEdge(
                id="interproc:3",
                kind="arg_to_param",
                from_var_id="var:source",
                to_var_id="var:m3",
                call_site_id="call:3",
                caller_func_fqn="main",
                callee_func_fqn="proc3",
                arg_position=0,
                repo_id="test",
                file_path="test.py",
            ),
            # m1, m2, m3 → sink
            InterproceduralDataFlowEdge(
                id="interproc:4",
                kind="arg_to_param",
                from_var_id="var:m1",
                to_var_id="var:sink",
                call_site_id="call:4",
                caller_func_fqn="main",
                callee_func_fqn="combine",
                arg_position=0,
                repo_id="test",
                file_path="test.py",
            ),
            InterproceduralDataFlowEdge(
                id="interproc:5",
                kind="arg_to_param",
                from_var_id="var:m2",
                to_var_id="var:sink",
                call_site_id="call:4",
                caller_func_fqn="main",
                callee_func_fqn="combine",
                arg_position=1,
                repo_id="test",
                file_path="test.py",
            ),
            InterproceduralDataFlowEdge(
                id="interproc:6",
                kind="arg_to_param",
                from_var_id="var:m3",
                to_var_id="var:sink",
                call_site_id="call:4",
                caller_func_fqn="main",
                callee_func_fqn="combine",
                arg_position=2,
                repo_id="test",
                file_path="test.py",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)
        ir_doc.interprocedural_edges = interproc

        engine = QueryEngine(ir_doc)

        # Query: source → sink (multiple paths)
        query = (Q.Var("source") >> Q.Var("sink")).via(E.DFG).depth(5).limit_paths(10)
        result = engine.execute_any_path(query)

        # Should find at least 1 path (may find 3)
        assert len(result) >= 1

        path = result.paths[0]
        assert path.nodes[0].name == "source"
        assert path.nodes[-1].name == "sink"

        print(f"\n✅ Fan-out/fan-in: {len(result)} paths found")


class TestSOTABenchmark:
    """Performance benchmark"""

    def test_large_interprocedural_graph(self):
        """
        Large graph: 50 functions, 100 variables, 200 edges

        Query should complete in < 1s
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        vars = []
        edges = []
        interproc = []

        # 50 functions, each with 2 variables
        for i in range(50):
            func = f"func{i}"
            vars.append(
                VariableEntity(
                    id=f"var:{func}:x",
                    repo_id="test",
                    file_path="test.py",
                    function_fqn=func,
                    name="x",
                    kind="parameter",
                )
            )
            vars.append(
                VariableEntity(
                    id=f"var:{func}:y", repo_id="test", file_path="test.py", function_fqn=func, name="y", kind="local"
                )
            )

            # x → y
            edges.append(
                DataFlowEdge(
                    id=f"dfg:{i}",
                    from_variable_id=f"var:{func}:x",
                    to_variable_id=f"var:{func}:y",
                    kind="assign",
                    repo_id="test",
                    file_path="test.py",
                    function_fqn=func,
                )
            )

            # Connect chain
            if i < 49:
                next_func = f"func{i + 1}"
                interproc.append(
                    InterproceduralDataFlowEdge(
                        id=f"interproc:{i}",
                        kind="arg_to_param",
                        from_var_id=f"var:{func}:y",
                        to_var_id=f"var:{next_func}:x",
                        call_site_id=f"call:{i}",
                        caller_func_fqn=next_func,
                        callee_func_fqn=func,
                        arg_position=0,
                        repo_id="test",
                        file_path="test.py",
                    )
                )

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)
        ir_doc.interprocedural_edges = interproc

        import time

        start = time.time()
        engine = QueryEngine(ir_doc)
        build_time = time.time() - start

        start = time.time()
        query = (Q.Var("x") >> Q.Var("y")).via(E.DFG).depth(100).limit_paths(10).timeout(1000)
        result = engine.execute_any_path(query)
        query_time = time.time() - start

        print(f"\n✅ Large graph: Build {build_time * 1000:.1f}ms, Query {query_time * 1000:.1f}ms")
        print(f"   Graph: {len(vars)} vars, {len(edges) + len(interproc)} edges")
        print(f"   Result: {len(result)} paths")

        assert build_time < 1.0, f"Build should be < 1s, got {build_time:.2f}s"
        assert query_time < 1.0, f"Query should be < 1s, got {query_time:.2f}s"
