"""
Context Builder Tests

Tests for call-string context generation (k=1).
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.dfg.models import VariableEntity
from codegraph_engine.code_foundation.infrastructure.ir.models import Span
from codegraph_engine.code_foundation.infrastructure.semantic_ir.context_builder import ContextBuilder
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind


def test_context_builder_basic():
    """Test basic context generation"""
    # Setup: Variables
    variables = [
        VariableEntity(
            id="var_x",
            repo_id="test",
            file_path="test.py",
            function_fqn="test.inc",
            name="x",
            kind="param",
            scope_id="test.inc",
            decl_span=Span(0, 0, 0, 0),
        )
    ]

    # Setup: Expressions (CALL)
    expressions = [
        Expression(
            id="call_1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="test.main",
            span=Span(0, 0, 0, 0),
            reads_vars=[],
            defines_var=None,
            attrs={"callee_name": "inc"},
        )
    ]

    # Execute
    builder = ContextBuilder()
    context_map = builder.build(variables, expressions)

    # Verify
    assert "test.inc" in context_map or "inc" in context_map
    context_value = context_map.get("test.inc") or context_map.get("inc")
    assert context_value == "call_1"

    # Apply
    builder.apply_contexts(variables, context_map)
    assert variables[0].context == "call_1"


def test_context_builder_multiple_calls():
    """Test multiple call sites create different contexts"""
    # Setup: Variables in called function
    variables = [
        VariableEntity(
            id="var_x1",
            repo_id="test",
            file_path="test.py",
            function_fqn="test.process",
            name="x",
            kind="param",
            scope_id="test.process",
            decl_span=Span(0, 0, 0, 0),
        )
    ]

    # Setup: Multiple calls to same function
    expressions = [
        Expression(
            id="call_site_1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="test.main",
            span=Span(5, 0, 5, 10),
            reads_vars=[],
            defines_var=None,
            attrs={"callee_name": "process"},
        ),
        Expression(
            id="call_site_2",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="test.main",
            span=Span(10, 0, 10, 10),
            reads_vars=[],
            defines_var=None,
            attrs={"callee_name": "process"},
        ),
    ]

    # Execute
    builder = ContextBuilder()
    context_map = builder.build(variables, expressions)

    # Verify: Last call wins (for k=1 simple)
    assert "test.process" in context_map or "process" in context_map
    context_value = context_map.get("test.process") or context_map.get("process")
    assert context_value in ["call_site_1", "call_site_2"]


def test_context_builder_no_calls():
    """Test top-level functions have no context"""
    # Setup: Top-level function (no calls)
    variables = [
        VariableEntity(
            id="var_x",
            repo_id="test",
            file_path="test.py",
            function_fqn="test.main",
            name="x",
            kind="local",
            scope_id="test.main",
            decl_span=Span(0, 0, 0, 0),
        )
    ]

    expressions = []  # No calls

    # Execute
    builder = ContextBuilder()
    context_map = builder.build(variables, expressions)

    # Verify
    assert len(context_map) == 0

    # Apply (should be no-op)
    builder.apply_contexts(variables, context_map)
    assert variables[0].context is None  # No context
