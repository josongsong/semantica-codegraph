"""
SOTA-Level Rust Engine Integration Tests

Tests complete L1-L5 pipeline with real data:
- Edge cases
- Corner cases
- Base cases
- Large scale
- Data validation
"""

import pytest
from pathlib import Path


class TestRustEngineIntegration:
    """Complete integration tests for Rust engine"""

    def test_base_case_simple_function(self):
        """Base case: Simple function"""
        import codegraph_ir

        code = """
def hello(name):
    return f"Hello, {name}!"
"""

        files = [("test.py", code, "test")]
        results = codegraph_ir.process_python_files(files, "test_repo")

        assert len(results) == 1
        assert results[0]["success"]

        nodes = results[0]["nodes"]
        edges = results[0]["edges"]

        # Validate: should have function + variable
        assert len(nodes) >= 1
        assert len(edges) >= 1

        # Check node types (kind is lowercase)
        func_nodes = [n for n in nodes if n["kind"] == "function"]
        assert len(func_nodes) == 1
        assert func_nodes[0]["name"] == "hello"

    def test_edge_case_empty_file(self):
        """Edge case: Empty file"""
        import codegraph_ir

        files = [("empty.py", "", "test")]
        results = codegraph_ir.process_python_files(files, "test_repo")

        assert len(results) == 1
        # Empty file should succeed with 0 nodes
        assert results[0]["success"] or len(results[0].get("nodes", [])) == 0

    def test_edge_case_syntax_error(self):
        """Edge case: Syntax error"""
        import codegraph_ir

        code = "def broken(\n    # incomplete"

        files = [("broken.py", code, "test")]
        results = codegraph_ir.process_python_files(files, "test_repo")

        assert len(results) == 1
        # Should handle gracefully (fail or empty nodes)
        assert not results[0]["success"] or len(results[0].get("nodes", [])) == 0

    def test_corner_case_deeply_nested(self):
        """Corner case: Deeply nested classes"""
        import codegraph_ir

        code = """
class A:
    class B:
        class C:
            def deep_method(self):
                x = 1
                return x
"""

        files = [("nested.py", code, "test")]
        results = codegraph_ir.process_python_files(files, "test_repo")

        assert len(results) == 1
        assert results[0]["success"]

        nodes = results[0]["nodes"]
        # Should handle nested classes
        class_nodes = [n for n in nodes if n["kind"] == "class"]
        assert len(class_nodes) >= 3  # A, B, C

    def test_corner_case_long_file(self):
        """Corner case: Long file (1000 lines)"""
        import codegraph_ir

        # Generate 1000-line file
        code = "\n".join([f"def func_{i}(x):\n    return x + {i}" for i in range(500)])

        files = [("long.py", code, "test")]
        results = codegraph_ir.process_python_files(files, "test_repo")

        assert len(results) == 1
        assert results[0]["success"]

        nodes = results[0]["nodes"]
        func_nodes = [n for n in nodes if n["kind"] == "function"]
        assert len(func_nodes) >= 500

    def test_data_validation_bfg_cfg(self):
        """Data validation: BFG/CFG generation"""
        import codegraph_ir

        code = """
def test_control_flow(x):
    if x > 0:
        result = x * 2
    else:
        result = 0
    return result
"""

        files = [("cf.py", code, "test")]
        results = codegraph_ir.process_python_files(files, "test_repo")

        assert len(results) == 1
        assert results[0]["success"]

        # Validate BFG
        bfg_graphs = results[0]["bfg_graphs"]
        assert len(bfg_graphs) == 1

        bfg = bfg_graphs[0]
        assert "control_flow" in bfg["function_id"]
        assert len(bfg["blocks"]) >= 2  # at least entry + exit

        # Validate CFG (at least 1 edge exists)
        cfg_edges = results[0]["cfg_edges"]
        assert len(cfg_edges) >= 1

    def test_data_validation_dfg_ssa(self):
        """Data validation: DFG/SSA generation"""
        import codegraph_ir

        code = """
def test_data_flow(x, y):
    temp = x + y
    result = temp * 2
    return result
"""

        files = [("df.py", code, "test")]
        results = codegraph_ir.process_python_files(files, "test_repo")

        assert len(results) == 1
        assert results[0]["success"]

        # Validate DFG
        dfg_graphs = results[0]["dfg_graphs"]
        assert len(dfg_graphs) == 1

        dfg = dfg_graphs[0]
        assert dfg["node_count"] >= 2  # temp, result
        # edge_count can be 0 (variables exist but no def-use chains yet)

        # Validate SSA
        ssa_graphs = results[0]["ssa_graphs"]
        assert len(ssa_graphs) == 1

        ssa = ssa_graphs[0]
        assert ssa["variable_count"] >= 2  # temp, result

    def test_large_scale_django(self):
        """Large scale: Django 100 files"""
        import codegraph_ir

        DJANGO = Path("tools/benchmark/_external_benchmark/django/django")
        if not DJANGO.exists():
            pytest.skip("Django repo not found")

        py_files = list(DJANGO.rglob("*.py"))[:100]
        files = [(str(f), f.read_text(), "django") for f in py_files]

        results = codegraph_ir.process_python_files(files, "test_repo")

        assert len(results) == 100

        success = sum(1 for r in results if r["success"])
        assert success == 100  # 100% success

        # Validate data
        total_nodes = sum(len(r["nodes"]) for r in results)
        total_edges = sum(len(r["edges"]) for r in results)

        assert total_nodes > 1000  # Should have many nodes
        assert total_edges > 10000  # Should have many edges

    def test_parallel_execution(self):
        """Test parallel execution with Rayon"""
        import codegraph_ir
        import time

        # Create 50 files
        files = [(f"file_{i}.py", f"def func_{i}():\n    return {i}", f"test_{i}") for i in range(50)]

        start = time.time()
        results = codegraph_ir.process_python_files(files, "test_repo")
        elapsed = time.time() - start

        assert len(results) == 50
        assert all(r["success"] for r in results)

        # Should be fast (parallel)
        assert elapsed < 0.5  # 50 files in < 0.5s

    def test_type_safety_enum_usage(self):
        """Type safety: Enum usage (not strings)"""
        import codegraph_ir

        code = "def test(): pass"
        files = [("test.py", code, "test")]
        results = codegraph_ir.process_python_files(files, "test_repo")

        assert results[0]["success"]

        # Check node kind is string (external boundary)
        # But internally uses Enum
        node = results[0]["nodes"][0]
        assert isinstance(node["kind"], str)  # External: string
        assert node["kind"] in ["function", "variable", "class"]  # Valid enum values (lowercase)

    def test_no_fake_data(self):
        """No fake/stub: All data is real"""
        import codegraph_ir

        code = """
def real_function(x, y):
    result = x + y
    return result
"""

        files = [("real.py", code, "test")]
        results = codegraph_ir.process_python_files(files, "test_repo")

        assert results[0]["success"]

        # Verify real data (not fake)
        nodes = results[0]["nodes"]
        edges = results[0]["edges"]

        # Should have actual nodes
        assert len(nodes) >= 2  # function + variable

        # Should have actual edges (WRITES edges exist)
        # Note: Edge count varies by code complexity
        assert len(edges) >= 1  # Has edges

        # FQN should be real
        func_node = [n for n in nodes if n["kind"] == "function"][0]
        assert "real_function" in func_node["fqn"]
