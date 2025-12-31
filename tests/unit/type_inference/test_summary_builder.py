"""
RFC-032: ReturnTypeSummaryBuilder Tests
"""

import pytest

from codegraph_engine.code_foundation.domain.type_inference.models import (
    InferSource,
    ReturnTypeSummary,
)
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.type_inference.summary_builder import (
    ReturnTypeSummaryBuilder,
    SummaryBuilderConfig,
)


def create_test_node(
    node_id: str,
    name: str | None = None,
    return_type: str | None = None,
    body_statements: list | None = None,
) -> Node:
    """Helper to create test node."""
    attrs = {}
    if return_type:
        attrs["type_info"] = {"return_type": return_type}
    if body_statements:
        attrs["body_statements"] = body_statements

    return Node(
        id=node_id,
        kind=NodeKind.FUNCTION,
        name=name or node_id,
        fqn=f"test.{name or node_id}",
        language="python",
        file_path="test.py",
        span=Span(0, 0, 0, 0),
        attrs=attrs,
    )


class TestReturnTypeSummary:
    """Test ReturnTypeSummary model."""

    def test_from_annotation(self):
        """Test creating summary from annotation."""
        summary = ReturnTypeSummary.from_annotation("test_func", "int")

        assert summary.function_id == "test_func"
        assert summary.return_type == "int"
        assert summary.confidence == 1.0
        assert summary.source == InferSource.ANNOTATION
        assert summary.is_resolved()

    def test_from_literal(self):
        """Test creating summary from literal."""
        summary = ReturnTypeSummary.from_literal("test_func", "str")

        assert summary.return_type == "str"
        assert summary.confidence == 0.9
        assert summary.source == InferSource.LITERAL

    def test_unknown(self):
        """Test unknown summary."""
        summary = ReturnTypeSummary.unknown("test_func")

        assert summary.return_type is None
        assert summary.confidence == 0.0
        assert not summary.is_resolved()


class TestSummaryBuilder:
    """Test ReturnTypeSummaryBuilder."""

    def test_annotation_priority(self):
        """Annotation should have highest priority."""
        node = create_test_node("func1", "test_func", return_type="int")

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"func1": []})

        assert summaries["func1"].return_type == "int"
        assert summaries["func1"].source == InferSource.ANNOTATION

    def test_dunder_method(self):
        """Dunder methods should have known return types."""
        node = create_test_node("func1", "__init__")

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"func1": []})

        assert summaries["func1"].return_type == "None"
        assert summaries["func1"].source == InferSource.BUILTIN_METHOD

    def test_test_function(self):
        """test_* functions should return None."""
        node = create_test_node("func1", "test_example")

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"func1": []})

        assert summaries["func1"].return_type == "None"

    def test_literal_inference(self):
        """Literal from return statement."""
        node = create_test_node("func1", "get_number", body_statements=[{"type": "return", "value": "42"}])

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"func1": []})

        assert summaries["func1"].return_type == "int"
        assert summaries["func1"].source == InferSource.LITERAL

    def test_no_return_is_none(self):
        """Function with no return should be None."""
        node = create_test_node(
            "func1", "do_something", body_statements=[{"type": "method_call", "object": "x", "method": "print"}]
        )

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"func1": []})

        assert summaries["func1"].return_type == "None"

    def test_union_from_multiple_returns(self):
        """Multiple return types should create Union."""
        node = create_test_node(
            "func1",
            "get_value",
            body_statements=[
                {"type": "return", "value": "42"},
                {"type": "return", "value": '"hello"'},
            ],
        )

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"func1": []})

        assert "int" in summaries["func1"].return_type
        assert "str" in summaries["func1"].return_type
        assert "|" in summaries["func1"].return_type

    def test_widening_large_union(self):
        """Union > max_union_size should become Any."""
        # 9개 서로 다른 타입 → max_union_size=8 초과
        # int, str, bool, list, dict, float, None, set, tuple
        returns = [
            {"type": "return", "value": "1"},  # int
            {"type": "return", "value": '"a"'},  # str
            {"type": "return", "value": "True"},  # bool
            {"type": "return", "value": "[]"},  # list
            {"type": "return", "value": '{"a": 1}'},  # dict (명확한 dict)
            {"type": "return", "value": "1.5"},  # float
            {"type": "return", "value": "None"},  # None
            {"type": "return", "value": "{1}"},  # set
            {"type": "return", "value": "(1, 2)"},  # tuple
        ]
        node = create_test_node("func1", "get_many", body_statements=returns)

        config = SummaryBuilderConfig(max_union_size=8)
        builder = ReturnTypeSummaryBuilder(config)
        summaries = builder.build([node], {"func1": []})

        assert summaries["func1"].return_type == "Any"

    def test_single_node_scc(self):
        """Single node SCC (no recursion)."""
        func1 = create_test_node("func1", body_statements=[{"type": "return", "value": "1"}])
        func2 = create_test_node("func2", body_statements=[{"type": "return", "value": "func1()"}])

        call_graph = {
            "func1": [],
            "func2": ["func1"],
        }

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([func1, func2], call_graph)

        # func1 should be resolved locally
        assert summaries["func1"].return_type == "int"
        # func2 should propagate from func1
        assert summaries["func2"].return_type == "int"
        assert summaries["func2"].source == InferSource.SUMMARY


class TestFixtureInference:
    """Test pytest fixture type inference."""

    def test_fixture_with_yield(self):
        """Fixture with yield should return Generator."""
        node = create_test_node("fixture1", "client", body_statements=[{"type": "yield", "value": "TestClient()"}])
        node.attrs["decorators"] = ["pytest.fixture"]

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"fixture1": []})

        return_type = summaries["fixture1"].return_type
        assert return_type.startswith("Generator[")
        assert "TestClient" in return_type

    def test_fixture_with_return(self):
        """Fixture with return should return that type."""
        node = create_test_node("fixture1", "value", body_statements=[{"type": "return", "value": "42"}])
        node.attrs["decorators"] = ["fixture"]

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"fixture1": []})

        assert summaries["fixture1"].return_type == "int"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
