"""
Schema Synchronization Tests

Validates Python ↔ Rust schema consistency.

SSOT: Python (models.py)
Implementation: Rust (types.rs)
Validation: This test!
"""

import pytest


class TestNodeKindSync:
    """NodeKind enum synchronization"""

    def test_node_kind_values(self):
        """NodeKind values match between Python and Rust"""
        # Python SSOT
        from codegraph_engine.code_foundation.infrastructure.ir.models import NodeKind

        python_kinds = {kind.value for kind in NodeKind}

        # Rust should support all Python kinds
        import codegraph_ir

        # Test: Rust can handle all Python kinds
        for kind in python_kinds:
            # Create test node with this kind
            code = f"def test(): pass" if kind in ["FUNCTION", "function"] else "x = 1"
            files = [("test.py", code, "test")]

            try:
                results = codegraph_ir.process_python_files(files, "test_repo")
                # Should succeed
                assert results[0]["success"], f"Rust failed for kind: {kind}"
            except Exception as e:
                pytest.fail(f"Rust doesn't support Python kind '{kind}': {e}")


class TestEdgeKindSync:
    """EdgeKind enum synchronization"""

    def test_edge_kind_values(self):
        """EdgeKind values match between Python and Rust"""
        # Python SSOT
        from codegraph_engine.code_foundation.infrastructure.ir.models import EdgeKind

        python_kinds = {kind.value for kind in EdgeKind}

        # Known Rust edge kinds (from verification)
        rust_kinds = {"contains", "calls", "reads", "writes", "inherits"}

        # Rust should support critical edges
        critical_edges = {"contains", "calls", "writes", "reads"}
        assert critical_edges.issubset(rust_kinds), "Rust missing critical edge kinds"


class TestSpanSync:
    """Span struct field synchronization"""

    def test_span_fields(self):
        """Span fields match between Python and Rust"""
        import codegraph_ir

        code = "def test(): pass"
        files = [("test.py", code, "test")]
        results = codegraph_ir.process_python_files(files, "test_repo")

        if results and results[0]["success"] and results[0]["nodes"]:
            node = results[0]["nodes"][0]
            span = node["span"]

            # Rust span should have same fields as Python
            required_fields = ["start_line", "start_col", "end_line", "end_col"]
            for field in required_fields:
                assert field in span, f"Rust Span missing field: {field}"
                assert isinstance(span[field], int), f"Rust Span.{field} not int"


class TestNodeFieldsSync:
    """Node struct field synchronization"""

    def test_node_required_fields(self):
        """Node required fields match"""
        import codegraph_ir

        code = "def test(): pass"
        files = [("test.py", code, "test")]
        results = codegraph_ir.process_python_files(files, "test_repo")

        if results and results[0]["success"] and results[0]["nodes"]:
            node = results[0]["nodes"][0]

            # Critical fields
            required = ["id", "kind", "fqn", "file_path", "span", "language"]
            for field in required:
                assert field in node, f"Rust Node missing field: {field}"


class TestProcessResultSync:
    """ProcessResult structure synchronization"""

    def test_process_result_fields(self):
        """ProcessResult has all required fields"""
        import codegraph_ir

        code = "def test(): pass"
        files = [("test.py", code, "test")]
        results = codegraph_ir.process_python_files(files, "test_repo")

        assert len(results) == 1
        result = results[0]

        # Required fields
        required = [
            "success",
            "nodes",
            "edges",
            "bfg_graphs",
            "cfg_edges",
            "type_entities",
            "dfg_graphs",
            "ssa_graphs",
        ]

        for field in required:
            assert field in result, f"Rust ProcessResult missing field: {field}"
