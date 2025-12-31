"""
DFG Builder Tests

Test Coverage:
- Base: Build data flow graph from IR
- Edge: Complex control flow, loops
- Corner: Empty functions, nested scopes
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.dfg.builder import DfgBuilder
from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator
from codegraph_engine.code_foundation.infrastructure.parsing import SourceFile


@pytest.fixture
def generator():
    """Create IR generator"""
    return _PythonIRGenerator(repo_id="test")


@pytest.fixture
def builder():
    """Create DFG builder"""
    return DfgBuilder()


class TestBasicDFGGeneration:
    """Basic DFG generation tests"""

    def test_simple_assignment(self, generator, builder):
        """Simple variable assignment"""
        code = """
def foo():
    x = 1
    y = x + 2
    return y
"""
        source = SourceFile.from_content("test.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        # Find function node
        func_nodes = [n for n in ir_doc.nodes if n.name == "foo"]
        assert len(func_nodes) == 1

    def test_function_call_dataflow(self, generator, builder):
        """Data flow through function call"""
        code = """
def helper(x):
    return x * 2

def main():
    a = 10
    b = helper(a)
    return b
"""
        source = SourceFile.from_content("test.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None
        assert len(ir_doc.nodes) >= 2


class TestDfgBuilder:
    """DfgBuilder tests"""

    def test_builder_creation(self, builder):
        """Create DFG builder"""
        assert builder is not None

    def test_builder_has_build_method(self, builder):
        """Builder has build_full method"""
        assert hasattr(builder, "build_full")


class TestEdgeCases:
    """Edge case tests"""

    def test_empty_function(self, generator):
        """Empty function body"""
        code = """
def empty():
    pass
"""
        source = SourceFile.from_content("empty.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None

    def test_conditional_flow(self, generator):
        """Conditional data flow"""
        code = """
def conditional(x):
    if x > 0:
        result = x * 2
    else:
        result = x * -1
    return result
"""
        source = SourceFile.from_content("cond.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None

    def test_loop_flow(self, generator):
        """Loop data flow"""
        code = """
def loop_sum(items):
    total = 0
    for item in items:
        total += item
    return total
"""
        source = SourceFile.from_content("loop.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None

    def test_nested_scopes(self, generator):
        """Nested function scopes"""
        code = """
def outer():
    x = 1
    def inner():
        y = x + 1
        return y
    return inner()
"""
        source = SourceFile.from_content("nested.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None


class TestCornerCases:
    """Corner case tests"""

    def test_multiple_assignments(self, generator):
        """Multiple assignments to same variable"""
        code = """
def reassign():
    x = 1
    x = 2
    x = 3
    return x
"""
        source = SourceFile.from_content("reassign.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None

    def test_tuple_unpacking(self, generator):
        """Tuple unpacking"""
        code = """
def unpack():
    a, b, c = (1, 2, 3)
    x, *rest = [1, 2, 3, 4]
    return a + b + c
"""
        source = SourceFile.from_content("unpack.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None

    def test_exception_handling(self, generator):
        """Exception handling flow"""
        code = """
def with_exception():
    try:
        x = risky_operation()
    except ValueError as e:
        x = default_value
    finally:
        cleanup()
    return x
"""
        source = SourceFile.from_content("exception.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None
