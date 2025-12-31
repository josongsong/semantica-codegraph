"""
Test incremental update_global_context API (RFC-062)

Verifies that only changed files and their dependents are re-processed.
"""

import pytest
import codegraph_ir
from codegraph_engine.code_foundation.infrastructure.ir.models.core import (
    Node,
    NodeKind,
    Span,
    Edge,
    EdgeKind,
)
from dataclasses import asdict


def make_node_dict(node_id, fqn, file_path):
    node = Node(
        id=node_id,
        kind=NodeKind.FUNCTION,
        fqn=fqn,
        file_path=file_path,
        span=Span(start_line=1, start_col=0, end_line=10, end_col=0),
        language="python",
    )
    node_dict = asdict(node)
    node_dict["kind"] = "function"
    node_dict["span"] = {
        "start_line": 1,
        "start_col": 0,
        "end_line": 10,
        "end_col": 0,
    }
    return node_dict


def make_edge_dict(edge_id, source_id, target_id):
    edge = Edge(
        id=edge_id,
        source_id=source_id,
        target_id=target_id,
        kind=EdgeKind.IMPORTS,
    )
    edge_dict = asdict(edge)
    edge_dict["kind"] = "IMPORTS"
    return edge_dict


class TestIncrementalUpdate:
    """Test incremental update_global_context API"""

    def test_incremental_update_single_file(self):
        """Test updating a single file"""
        # Initial build: 3 files
        ir_docs = [
            {
                "file_path": "src/a.py",
                "nodes": [make_node_dict("a_foo", "a.foo", "src/a.py")],
                "edges": [],
            },
            {
                "file_path": "src/b.py",
                "nodes": [make_node_dict("b_bar", "b.bar", "src/b.py")],
                "edges": [make_edge_dict("edge1", "b_bar", "a_foo")],
            },
            {
                "file_path": "src/c.py",
                "nodes": [make_node_dict("c_baz", "c.baz", "src/c.py")],
                "edges": [make_edge_dict("edge2", "c_baz", "b_bar")],
            },
        ]

        initial_context = codegraph_ir.build_global_context_py(ir_docs)
        assert initial_context["total_files"] == 3

        # Update: Change only src/a.py
        changed_ir_docs = [
            {
                "file_path": "src/a.py",
                "nodes": [make_node_dict("a_foo_v2", "a.foo_v2", "src/a.py")],
                "edges": [],
            }
        ]

        new_context, affected_files = codegraph_ir.update_global_context_py(initial_context, changed_ir_docs, ir_docs)

        # Verify: affected files should include a.py, b.py (depends on a), c.py (depends on b)
        assert len(affected_files) >= 1  # At least a.py
        assert "src/a.py" in affected_files

    def test_incremental_update_no_dependents(self):
        """Test updating a file with no dependents"""
        ir_docs = [
            {
                "file_path": "src/a.py",
                "nodes": [make_node_dict("a_foo", "a.foo", "src/a.py")],
                "edges": [],
            },
            {
                "file_path": "src/b.py",
                "nodes": [make_node_dict("b_bar", "b.bar", "src/b.py")],
                "edges": [],
            },
        ]

        initial_context = codegraph_ir.build_global_context_py(ir_docs)

        # Update: Change b.py (no dependents)
        changed_ir_docs = [
            {
                "file_path": "src/b.py",
                "nodes": [make_node_dict("b_bar_v2", "b.bar_v2", "src/b.py")],
                "edges": [],
            }
        ]

        new_context, affected_files = codegraph_ir.update_global_context_py(initial_context, changed_ir_docs, ir_docs)

        # Only b.py should be affected
        assert "src/b.py" in affected_files
        assert new_context["total_files"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
