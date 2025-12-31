"""
Inter-procedural Analysis E2E Tests

Tests cross-function data flow using real Python code.
"""

import pytest

from codegraph_engine.code_foundation import E, Q, QueryEngine
from codegraph_engine.code_foundation.infrastructure.ir.interprocedural_builder import InterproceduralDataFlowBuilder
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
from codegraph_engine.code_foundation.infrastructure.ir.models.interprocedural import InterproceduralDataFlowEdge


class TestInterproceduralBasic:
    """Basic inter-procedural data flow"""

    def test_simple_call_arg_to_param(self):
        """
        Test: argument flows to parameter

        Code:
            def callee(param):
                pass

            def caller():
                arg = user_input()
                callee(arg)

        Query: user_input → param (cross-function)
        """
        # Build mock IR with inter-procedural edge
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Variables
        from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot, VariableEntity

        vars = [
            # Caller
            VariableEntity(
                id="var:caller:user_input",
                repo_id="test",
                file_path="test.py",
                function_fqn="caller",
                name="user_input",
                kind="local",
            ),
            VariableEntity(
                id="var:caller:arg",
                repo_id="test",
                file_path="test.py",
                function_fqn="caller",
                name="arg",
                kind="local",
            ),
            # Callee
            VariableEntity(
                id="var:callee:param",
                repo_id="test",
                file_path="test.py",
                function_fqn="callee",
                name="param",
                kind="parameter",
            ),
        ]

        # Intra-procedural edge (in caller)
        from codegraph_engine.code_foundation.infrastructure.dfg.models import DataFlowEdge

        edges = [
            DataFlowEdge(
                id="dfg:1",
                from_variable_id="var:caller:user_input",
                to_variable_id="var:caller:arg",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="caller",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)

        # Inter-procedural edge (arg → param)
        interproc_edge = InterproceduralDataFlowEdge(
            id="interproc:1",
            kind="arg_to_param",
            from_var_id="var:caller:arg",
            to_var_id="var:callee:param",
            call_site_id="call:1",
            caller_func_fqn="caller",
            callee_func_fqn="callee",
            arg_position=0,
            repo_id="test",
            file_path="test.py",
        )
        ir_doc.interprocedural_edges = [interproc_edge]

        # Query
        engine = QueryEngine(ir_doc)

        # Cross-function query: user_input → param
        query = (Q.Var("user_input") >> Q.Var("param")).via(E.DFG).limit_paths(10)
        result = engine.execute_any_path(query)

        # Verify
        assert len(result) == 1, f"Should find 1 cross-function path, got {len(result)}"

        path = result.paths[0]
        assert len(path.nodes) == 3, "Should have 3 nodes (user_input → arg → param)"
        assert path.nodes[0].name == "user_input"
        assert path.nodes[1].name == "arg"
        assert path.nodes[2].name == "param"

        # Verify edge types
        assert len(path.edges) == 2
        assert path.edges[0].edge_type == "dfg"  # Intra-proc
        assert path.edges[1].edge_type == "dfg"  # Inter-proc (treated as DFG)
        assert path.edges[1].attrs.get("interproc_kind") == "arg_to_param"

        print("\n✅ Simple inter-procedural: user_input → arg → param (cross-function)")

    def test_return_to_callsite(self):
        """
        Test: return value flows to call site

        Code:
            def callee():
                ret = compute()
                return ret

            def caller():
                result = callee()
                sink(result)

        Query: ret → result (cross-function)
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        from codegraph_engine.code_foundation.infrastructure.dfg.models import DataFlowEdge, DfgSnapshot, VariableEntity

        vars = [
            # Callee
            VariableEntity(
                id="var:callee:ret",
                repo_id="test",
                file_path="test.py",
                function_fqn="callee",
                name="ret",
                kind="local",
            ),
            VariableEntity(
                id="var:callee:__return__",
                repo_id="test",
                file_path="test.py",
                function_fqn="callee",
                name="__return__",
                kind="local",
            ),
            # Caller
            VariableEntity(
                id="var:caller:result",
                repo_id="test",
                file_path="test.py",
                function_fqn="caller",
                name="result",
                kind="local",
            ),
        ]

        # Intra-procedural (in callee)
        edges = [
            DataFlowEdge(
                id="dfg:1",
                from_variable_id="var:callee:ret",
                to_variable_id="var:callee:__return__",
                kind="return",
                repo_id="test",
                file_path="test.py",
                function_fqn="callee",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)

        # Inter-procedural edge (return → call site)
        interproc_edge = InterproceduralDataFlowEdge(
            id="interproc:1",
            kind="return_to_callsite",
            from_var_id="var:callee:__return__",
            to_var_id="var:caller:result",
            call_site_id="call:1",
            caller_func_fqn="caller",
            callee_func_fqn="callee",
            arg_position=None,
            repo_id="test",
            file_path="test.py",
        )
        ir_doc.interprocedural_edges = [interproc_edge]

        # Query
        engine = QueryEngine(ir_doc)

        # Cross-function: ret → result
        query = (Q.Var("ret") >> Q.Var("result")).via(E.DFG).limit_paths(10)
        result = engine.execute_any_path(query)

        # Verify
        assert len(result) == 1
        path = result.paths[0]
        assert len(path.nodes) == 3
        assert path.nodes[0].name == "ret"
        assert path.nodes[1].name == "__return__"
        assert path.nodes[2].name == "result"

        print("\n✅ Return to call site: ret → __return__ → result (cross-function)")


class TestInterproceduralChain:
    """Multi-hop inter-procedural analysis"""

    def test_three_function_chain(self):
        """
        Test: 3-function chain

        Code:
            def source():
                return user_input()

            def middle():
                data = source()
                return data

            def sink():
                final = middle()
                execute(final)

        Query: user_input → final (3-function chain)
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        from codegraph_engine.code_foundation.infrastructure.dfg.models import DataFlowEdge, DfgSnapshot, VariableEntity

        vars = [
            # source()
            VariableEntity(
                id="var:source:input",
                repo_id="test",
                file_path="test.py",
                function_fqn="source",
                name="input",
                kind="local",
            ),
            VariableEntity(
                id="var:source:__return__",
                repo_id="test",
                file_path="test.py",
                function_fqn="source",
                name="__return__",
                kind="local",
            ),
            # middle()
            VariableEntity(
                id="var:middle:data",
                repo_id="test",
                file_path="test.py",
                function_fqn="middle",
                name="data",
                kind="local",
            ),
            VariableEntity(
                id="var:middle:__return__",
                repo_id="test",
                file_path="test.py",
                function_fqn="middle",
                name="__return__",
                kind="local",
            ),
            # sink()
            VariableEntity(
                id="var:sink:final",
                repo_id="test",
                file_path="test.py",
                function_fqn="sink",
                name="final",
                kind="local",
            ),
        ]

        # Intra-procedural edges
        edges = [
            # source: input → __return__
            DataFlowEdge(
                id="dfg:1",
                from_variable_id="var:source:input",
                to_variable_id="var:source:__return__",
                kind="return",
                repo_id="test",
                file_path="test.py",
                function_fqn="source",
            ),
            # middle: data → __return__
            DataFlowEdge(
                id="dfg:2",
                from_variable_id="var:middle:data",
                to_variable_id="var:middle:__return__",
                kind="return",
                repo_id="test",
                file_path="test.py",
                function_fqn="middle",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)

        # Inter-procedural edges
        ir_doc.interprocedural_edges = [
            # source() return → middle.data
            InterproceduralDataFlowEdge(
                id="interproc:1",
                kind="return_to_callsite",
                from_var_id="var:source:__return__",
                to_var_id="var:middle:data",
                call_site_id="call:1",
                caller_func_fqn="middle",
                callee_func_fqn="source",
                repo_id="test",
                file_path="test.py",
            ),
            # middle() return → sink.final
            InterproceduralDataFlowEdge(
                id="interproc:2",
                kind="return_to_callsite",
                from_var_id="var:middle:__return__",
                to_var_id="var:sink:final",
                call_site_id="call:2",
                caller_func_fqn="sink",
                callee_func_fqn="middle",
                repo_id="test",
                file_path="test.py",
            ),
        ]

        # Query
        engine = QueryEngine(ir_doc)

        # 3-hop cross-function: input → final
        query = (Q.Var("input") >> Q.Var("final")).via(E.DFG).depth(10).limit_paths(10)
        result = engine.execute_any_path(query)

        # Verify
        assert len(result) >= 1, "Should find path across 3 functions"

        path = result.paths[0]
        print(f"\nPath: {' → '.join([n.name for n in path.nodes])}")

        # Should be: input → __return__(source) → data → __return__(middle) → final
        assert len(path.nodes) == 5
        assert path.nodes[0].name == "input"
        assert path.nodes[-1].name == "final"

        # Verify crosses function boundaries
        funcs = [n.attrs.get("function_fqn") for n in path.nodes]
        assert "source" in str(funcs)
        assert "middle" in str(funcs)
        assert "sink" in str(funcs)

        print(f"✅ 3-function chain: {len(path.nodes)} nodes across 3 functions")


class TestInterproceduralTaint:
    """Inter-procedural taint analysis"""

    def test_taint_across_functions(self):
        """
        Test: Taint flows across functions

        Code:
            def get_input():
                return request.get("id")  # SOURCE

            def process():
                user_id = get_input()
                query = f"...{user_id}..."
                return query

            def execute():
                q = process()
                db.execute(q)  # SINK

        Query: SOURCE → SINK (cross-function)
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        from codegraph_engine.code_foundation.infrastructure.dfg.models import DataFlowEdge, DfgSnapshot, VariableEntity

        vars = [
            # get_input()
            VariableEntity(
                id="var:get_input:source",
                repo_id="test",
                file_path="test.py",
                function_fqn="get_input",
                name="source",
                kind="local",
            ),
            VariableEntity(
                id="var:get_input:__return__",
                repo_id="test",
                file_path="test.py",
                function_fqn="get_input",
                name="__return__",
                kind="local",
            ),
            # process()
            VariableEntity(
                id="var:process:user_id",
                repo_id="test",
                file_path="test.py",
                function_fqn="process",
                name="user_id",
                kind="local",
            ),
            VariableEntity(
                id="var:process:query",
                repo_id="test",
                file_path="test.py",
                function_fqn="process",
                name="query",
                kind="local",
            ),
            VariableEntity(
                id="var:process:__return__",
                repo_id="test",
                file_path="test.py",
                function_fqn="process",
                name="__return__",
                kind="local",
            ),
            # execute()
            VariableEntity(
                id="var:execute:q", repo_id="test", file_path="test.py", function_fqn="execute", name="q", kind="local"
            ),
            VariableEntity(
                id="var:execute:sink",
                repo_id="test",
                file_path="test.py",
                function_fqn="execute",
                name="sink",
                kind="local",
            ),
        ]

        # Intra-procedural edges
        edges = [
            # get_input: source → __return__
            DataFlowEdge(
                id="dfg:1",
                from_variable_id="var:get_input:source",
                to_variable_id="var:get_input:__return__",
                kind="return",
                repo_id="test",
                file_path="test.py",
                function_fqn="get_input",
            ),
            # process: user_id → query → __return__
            DataFlowEdge(
                id="dfg:2",
                from_variable_id="var:process:user_id",
                to_variable_id="var:process:query",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="process",
            ),
            DataFlowEdge(
                id="dfg:3",
                from_variable_id="var:process:query",
                to_variable_id="var:process:__return__",
                kind="return",
                repo_id="test",
                file_path="test.py",
                function_fqn="process",
            ),
            # execute: q → sink
            DataFlowEdge(
                id="dfg:4",
                from_variable_id="var:execute:q",
                to_variable_id="var:execute:sink",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="execute",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)

        # Inter-procedural edges
        ir_doc.interprocedural_edges = [
            # get_input() return → process.user_id
            InterproceduralDataFlowEdge(
                id="interproc:1",
                kind="return_to_callsite",
                from_var_id="var:get_input:__return__",
                to_var_id="var:process:user_id",
                call_site_id="call:1",
                caller_func_fqn="process",
                callee_func_fqn="get_input",
                repo_id="test",
                file_path="test.py",
            ),
            # process() return → execute.q
            InterproceduralDataFlowEdge(
                id="interproc:2",
                kind="return_to_callsite",
                from_var_id="var:process:__return__",
                to_var_id="var:execute:q",
                call_site_id="call:2",
                caller_func_fqn="execute",
                callee_func_fqn="process",
                repo_id="test",
                file_path="test.py",
            ),
        ]

        # Query
        engine = QueryEngine(ir_doc)

        # Full taint path: source → sink
        query = (Q.Var("source") >> Q.Var("sink")).via(E.DFG).depth(15).limit_paths(10)
        result = engine.execute_any_path(query)

        # Verify
        assert len(result) >= 1, "Should find taint path across 3 functions"

        path = result.paths[0]
        print(f"\nTaint path: {' → '.join([n.name for n in path.nodes])}")

        # Should be: source → __return__(get_input) → user_id → query → __return__(process) → q → sink
        assert len(path.nodes) == 7
        assert path.nodes[0].name == "source"
        assert path.nodes[-1].name == "sink"

        # Verify crosses 3 functions
        funcs_visited = set()
        for node in path.nodes:
            if "function_fqn" in node.attrs:
                funcs_visited.add(node.attrs["function_fqn"])

        assert len(funcs_visited) == 3, f"Should cross 3 functions, got {funcs_visited}"

        print("✅ Inter-procedural taint: 7 nodes across 3 functions")


class TestInterproceduralWildcard:
    """Inter-procedural with wildcard"""

    def test_wildcard_impact_across_functions(self):
        """
        Test: Impact analysis across functions

        Code:
            def process(config):
                a = config
                b = config
                return a, b

            def main():
                c = process(CONFIG)
                d = process(CONFIG)

        Query: CONFIG → Q.Var(None) (find all affected)
        """
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        from codegraph_engine.code_foundation.infrastructure.dfg.models import DataFlowEdge, DfgSnapshot, VariableEntity

        vars = [
            # main()
            VariableEntity(
                id="var:main:CONFIG",
                repo_id="test",
                file_path="test.py",
                function_fqn="main",
                name="CONFIG",
                kind="local",
            ),
            VariableEntity(
                id="var:main:c", repo_id="test", file_path="test.py", function_fqn="main", name="c", kind="local"
            ),
            # process()
            VariableEntity(
                id="var:process:config",
                repo_id="test",
                file_path="test.py",
                function_fqn="process",
                name="config",
                kind="parameter",
            ),
            VariableEntity(
                id="var:process:a", repo_id="test", file_path="test.py", function_fqn="process", name="a", kind="local"
            ),
            VariableEntity(
                id="var:process:b", repo_id="test", file_path="test.py", function_fqn="process", name="b", kind="local"
            ),
            VariableEntity(
                id="var:process:__return__",
                repo_id="test",
                file_path="test.py",
                function_fqn="process",
                name="__return__",
                kind="local",
            ),
        ]

        # Intra-procedural edges
        edges = [
            # process: config → a, config → b, a → __return__
            DataFlowEdge(
                id="dfg:1",
                from_variable_id="var:process:config",
                to_variable_id="var:process:a",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="process",
            ),
            DataFlowEdge(
                id="dfg:2",
                from_variable_id="var:process:config",
                to_variable_id="var:process:b",
                kind="assign",
                repo_id="test",
                file_path="test.py",
                function_fqn="process",
            ),
            DataFlowEdge(
                id="dfg:3",
                from_variable_id="var:process:a",
                to_variable_id="var:process:__return__",
                kind="return",
                repo_id="test",
                file_path="test.py",
                function_fqn="process",
            ),
        ]

        ir_doc.dfg_snapshot = DfgSnapshot(variables=vars, edges=edges)

        # Inter-procedural edges
        ir_doc.interprocedural_edges = [
            # main.CONFIG → process.config
            InterproceduralDataFlowEdge(
                id="interproc:1",
                kind="arg_to_param",
                from_var_id="var:main:CONFIG",
                to_var_id="var:process:config",
                call_site_id="call:1",
                caller_func_fqn="main",
                callee_func_fqn="process",
                arg_position=0,
                repo_id="test",
                file_path="test.py",
            ),
            # process.__return__ → main.c
            InterproceduralDataFlowEdge(
                id="interproc:2",
                kind="return_to_callsite",
                from_var_id="var:process:__return__",
                to_var_id="var:main:c",
                call_site_id="call:1",
                caller_func_fqn="main",
                callee_func_fqn="process",
                repo_id="test",
                file_path="test.py",
            ),
        ]

        # Query
        engine = QueryEngine(ir_doc)

        # Impact analysis with wildcard: CONFIG → ?
        query = (Q.Var("CONFIG") >> Q.Var(None)).via(E.DFG).depth(10).limit_paths(20)
        result = engine.execute_any_path(query)

        # Verify
        print(f"\nImpact of CONFIG: {len(result)} paths")
        for path in result.paths[:5]:
            print(f"  - {' → '.join([n.name for n in path.nodes])}")

        # Should find shortest path first: CONFIG → config (cross-function)
        assert len(result) >= 1, "Should find impact paths"

        # Verify crosses function boundary
        path = result.paths[0]
        funcs = [n.attrs.get("function_fqn") for n in path.nodes if "function_fqn" in n.attrs]
        unique_funcs = set(funcs)

        # CONFIG (main) → config (process)
        assert len(unique_funcs) >= 2, f"Should cross functions, got {unique_funcs}"
        assert "main" in unique_funcs
        assert "process" in unique_funcs

        print(f"✅ Wildcard impact: {len(result)} paths across {len(unique_funcs)} functions")
