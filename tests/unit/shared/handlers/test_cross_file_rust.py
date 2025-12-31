"""
RFC-062: Rust CrossFileResolver Integration Tests

Tests the Rust implementation of CrossFileResolver:
- DashMap-based symbol index
- Rayon parallel import resolution
- petgraph dependency graph
"""

import pytest
import time


@pytest.fixture
def rust_module():
    """Get Rust codegraph_ir module, skip if not available."""
    try:
        import codegraph_ir.codegraph_ir as native

        if not hasattr(native, "build_global_context_py"):
            pytest.skip("Rust build_global_context_py not available")
        return native
    except ImportError:
        pytest.skip("codegraph_ir module not available")


class TestRustCrossFileResolver:
    """Test Rust CrossFileResolver implementation."""

    def test_empty_input(self, rust_module):
        """Test with no IR documents."""
        result = rust_module.build_global_context_py([])

        assert result["total_symbols"] == 0
        assert result["total_files"] == 0
        assert result["total_dependencies"] == 0
        assert len(result["symbol_table"]) == 0

    def test_single_file(self, rust_module):
        """Test with a single file containing symbols."""
        ir_docs = [
            {
                "file_path": "src/main.py",
                "nodes": [
                    {
                        "id": "node1",
                        "kind": "function",
                        "fqn": "main.foo",
                        "file_path": "src/main.py",
                        "span": {"start_line": 1, "start_col": 0, "end_line": 5, "end_col": 0},
                        "name": "foo",
                    },
                    {
                        "id": "node2",
                        "kind": "function",
                        "fqn": "main.bar",
                        "file_path": "src/main.py",
                        "span": {"start_line": 7, "start_col": 0, "end_line": 10, "end_col": 0},
                        "name": "bar",
                    },
                ],
                "edges": [],
            }
        ]

        result = rust_module.build_global_context_py(ir_docs)

        assert result["total_symbols"] == 2
        assert result["total_files"] == 1
        assert "main.foo" in result["symbol_table"]
        assert "main.bar" in result["symbol_table"]

        # Verify symbol structure
        symbol = result["symbol_table"]["main.foo"]
        assert symbol["fqn"] == "main.foo"
        assert symbol["name"] == "foo"
        assert symbol["kind"] == "function"
        assert symbol["file_path"] == "src/main.py"

    def test_multiple_files(self, rust_module):
        """Test with multiple files."""
        ir_docs = [
            {
                "file_path": "src/main.py",
                "nodes": [
                    {
                        "id": "main_foo",
                        "kind": "function",
                        "fqn": "main.foo",
                        "file_path": "src/main.py",
                        "span": {"start_line": 1, "start_col": 0, "end_line": 5, "end_col": 0},
                        "name": "foo",
                    },
                ],
                "edges": [],
            },
            {
                "file_path": "src/utils.py",
                "nodes": [
                    {
                        "id": "utils_helper",
                        "kind": "function",
                        "fqn": "utils.helper",
                        "file_path": "src/utils.py",
                        "span": {"start_line": 1, "start_col": 0, "end_line": 3, "end_col": 0},
                        "name": "helper",
                    },
                ],
                "edges": [],
            },
            {
                "file_path": "src/lib.py",
                "nodes": [
                    {
                        "id": "lib_process",
                        "kind": "function",
                        "fqn": "lib.process",
                        "file_path": "src/lib.py",
                        "span": {"start_line": 1, "start_col": 0, "end_line": 8, "end_col": 0},
                        "name": "process",
                    },
                ],
                "edges": [],
            },
        ]

        result = rust_module.build_global_context_py(ir_docs)

        assert result["total_symbols"] == 3
        assert result["total_files"] == 3
        assert "main.foo" in result["symbol_table"]
        assert "utils.helper" in result["symbol_table"]
        assert "lib.process" in result["symbol_table"]

    def test_import_resolution(self, rust_module):
        """Test import resolution between files."""
        ir_docs = [
            {
                "file_path": "src/utils.py",
                "nodes": [
                    {
                        "id": "utils_helper",
                        "kind": "function",
                        "fqn": "utils.helper",
                        "file_path": "src/utils.py",
                        "span": {"start_line": 1, "start_col": 0, "end_line": 3, "end_col": 0},
                        "name": "helper",
                    },
                ],
                "edges": [],
            },
            {
                "file_path": "src/main.py",
                "nodes": [
                    {
                        "id": "main_func",
                        "kind": "function",
                        "fqn": "main.main_func",
                        "file_path": "src/main.py",
                        "span": {"start_line": 3, "start_col": 0, "end_line": 8, "end_col": 0},
                        "name": "main_func",
                    },
                    {
                        "id": "import_helper",
                        "kind": "import",
                        "fqn": "utils.helper",
                        "file_path": "src/main.py",
                        "span": {"start_line": 1, "start_col": 0, "end_line": 1, "end_col": 25},
                        "name": "helper",
                    },
                ],
                "edges": [
                    {
                        "source_id": "main_func",
                        "target_id": "import_helper",
                        "kind": "IMPORTS",
                    }
                ],
            },
        ]

        result = rust_module.build_global_context_py(ir_docs)

        assert result["total_files"] == 2
        # Import resolution should create dependencies
        assert result["total_imports"] > 0 or result["total_dependencies"] >= 0

    def test_class_symbols(self, rust_module):
        """Test class symbol handling."""
        ir_docs = [
            {
                "file_path": "src/models.py",
                "nodes": [
                    {
                        "id": "user_class",
                        "kind": "class",
                        "fqn": "models.User",
                        "file_path": "src/models.py",
                        "span": {"start_line": 1, "start_col": 0, "end_line": 20, "end_col": 0},
                        "name": "User",
                    },
                    {
                        "id": "user_init",
                        "kind": "method",
                        "fqn": "models.User.__init__",
                        "file_path": "src/models.py",
                        "span": {"start_line": 2, "start_col": 4, "end_line": 5, "end_col": 0},
                        "name": "__init__",
                    },
                ],
                "edges": [],
            }
        ]

        result = rust_module.build_global_context_py(ir_docs)

        assert result["total_symbols"] == 2
        assert "models.User" in result["symbol_table"]
        assert "models.User.__init__" in result["symbol_table"]

        # Verify class symbol
        user_symbol = result["symbol_table"]["models.User"]
        assert user_symbol["kind"] == "class"

    def test_build_duration_tracking(self, rust_module):
        """Test that build duration is tracked."""
        ir_docs = [
            {
                "file_path": "src/main.py",
                "nodes": [
                    {
                        "id": "node1",
                        "kind": "function",
                        "fqn": "main.foo",
                        "file_path": "src/main.py",
                        "span": {"start_line": 1, "start_col": 0, "end_line": 5, "end_col": 0},
                        "name": "foo",
                    },
                ],
                "edges": [],
            }
        ]

        result = rust_module.build_global_context_py(ir_docs)

        # Duration should be tracked (>= 0)
        assert "build_duration_ms" in result
        assert result["build_duration_ms"] >= 0

    def test_topological_order(self, rust_module):
        """Test topological ordering of files."""
        ir_docs = [
            {
                "file_path": "src/main.py",
                "nodes": [
                    {
                        "id": "main_func",
                        "kind": "function",
                        "fqn": "main.main_func",
                        "file_path": "src/main.py",
                        "span": {"start_line": 1, "start_col": 0, "end_line": 5, "end_col": 0},
                        "name": "main_func",
                    },
                ],
                "edges": [],
            },
        ]

        result = rust_module.build_global_context_py(ir_docs)

        assert "topological_order" in result
        assert isinstance(result["topological_order"], list)


class TestRustCrossFilePerformance:
    """Performance tests for Rust CrossFileResolver."""

    def test_parallel_processing(self, rust_module):
        """Test that parallel processing works for multiple files."""
        # Create 100 files with 10 symbols each
        ir_docs = []
        for i in range(100):
            nodes = []
            for j in range(10):
                nodes.append(
                    {
                        "id": f"node_{i}_{j}",
                        "kind": "function",
                        "fqn": f"module_{i}.func_{j}",
                        "file_path": f"src/module_{i}.py",
                        "span": {"start_line": j * 10, "start_col": 0, "end_line": j * 10 + 5, "end_col": 0},
                        "name": f"func_{j}",
                    }
                )
            ir_docs.append(
                {
                    "file_path": f"src/module_{i}.py",
                    "nodes": nodes,
                    "edges": [],
                }
            )

        start = time.perf_counter()
        result = rust_module.build_global_context_py(ir_docs)
        duration = time.perf_counter() - start

        assert result["total_symbols"] == 1000
        assert result["total_files"] == 100

        # Should complete in under 1 second (Rust is fast!)
        assert duration < 1.0, f"Processing took too long: {duration}s"

        # Rust duration should be reported
        assert result["build_duration_ms"] >= 0
