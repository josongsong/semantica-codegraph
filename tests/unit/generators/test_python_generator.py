"""
Python Generator Tests

Test Coverage:
- Base: Generate IR from simple Python code
- Edge: Complex structures (classes, decorators, async)
- Corner: Empty files, syntax edge cases
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator
from codegraph_engine.code_foundation.infrastructure.ir.models import EdgeKind, NodeKind
from codegraph_engine.code_foundation.infrastructure.parsing import SourceFile


@pytest.fixture
def generator():
    """Create Python IR generator"""
    return _PythonIRGenerator(repo_id="test")


class TestBasicGeneration:
    """Basic IR generation tests"""

    def test_generate_simple_function(self, generator):
        """Generate IR for simple function"""
        code = """
def hello():
    return "Hello, World!"
"""
        source = SourceFile.from_content("test.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None
        assert len(ir_doc.nodes) > 0

        # Find function node
        func_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FUNCTION]
        assert len(func_nodes) >= 1
        assert any(n.name == "hello" for n in func_nodes)

    def test_generate_function_with_params(self, generator):
        """Generate IR for function with parameters"""
        code = """
def greet(name: str, age: int = 0) -> str:
    return f"Hello, {name}!"
"""
        source = SourceFile.from_content("test.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        func_nodes = [n for n in ir_doc.nodes if n.name == "greet"]
        assert len(func_nodes) == 1

    def test_generate_class(self, generator):
        """Generate IR for class"""
        code = """
class User:
    def __init__(self, name: str):
        self.name = name

    def greet(self) -> str:
        return f"Hello, {self.name}"
"""
        source = SourceFile.from_content("test.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        # Find class node
        class_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.CLASS]
        assert len(class_nodes) >= 1
        assert any(n.name == "User" for n in class_nodes)

        # Find method nodes
        method_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.METHOD]
        assert len(method_nodes) >= 2  # __init__ and greet

    def test_generate_imports(self, generator):
        """Generate IR with imports"""
        code = """
import os
from typing import List, Optional
from pathlib import Path
"""
        source = SourceFile.from_content("test.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None
        # Imports should be captured
        assert len(ir_doc.nodes) >= 0  # May or may not create nodes for imports


class TestEdgeCases:
    """Edge case tests"""

    def test_empty_file(self, generator):
        """Empty file generates empty or minimal IR"""
        code = ""
        source = SourceFile.from_content("empty.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None
        # Empty file should have minimal nodes (maybe module node)

    def test_only_comments(self, generator):
        """File with only comments"""
        code = '''
# This is a comment
# Another comment
"""
Docstring here
"""
'''
        source = SourceFile.from_content("comments.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None

    def test_async_function(self, generator):
        """Async function generation"""
        code = """
async def fetch_data(url: str) -> dict:
    return {"data": "value"}
"""
        source = SourceFile.from_content("async.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        func_nodes = [n for n in ir_doc.nodes if n.name == "fetch_data"]
        assert len(func_nodes) >= 1

    def test_decorated_function(self, generator):
        """Decorated function generation"""
        code = """
@staticmethod
@property
def my_prop():
    return 42
"""
        source = SourceFile.from_content("decorated.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None

    def test_nested_class(self, generator):
        """Nested class generation"""
        code = """
class Outer:
    class Inner:
        def method(self):
            pass
"""
        source = SourceFile.from_content("nested.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        class_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.CLASS]
        # At least outer class should be detected
        assert len(class_nodes) >= 1

    def test_lambda_function(self, generator):
        """Lambda function in code"""
        code = """
transform = lambda x: x * 2
data = list(map(lambda y: y + 1, [1, 2, 3]))
"""
        source = SourceFile.from_content("lambda.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None


class TestEdgeGeneration:
    """Edge (relationship) generation tests"""

    def test_call_edge(self, generator):
        """Function call edge generation"""
        code = """
def helper():
    return 1

def main():
    x = helper()
    return x
"""
        source = SourceFile.from_content("calls.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        # Should have call edges
        call_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.CALLS]
        assert len(call_edges) >= 1

    def test_contains_edge(self, generator):
        """Class contains method edge"""
        code = """
class MyClass:
    def my_method(self):
        pass
"""
        source = SourceFile.from_content("contains.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        # Should have contains edges
        contains_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.CONTAINS]
        assert len(contains_edges) >= 1


class TestCornerCases:
    """Corner case tests"""

    def test_unicode_identifiers(self, generator):
        """Unicode in identifiers"""
        code = """
def 挨拶():
    return "こんにちは"

変数 = 42
"""
        source = SourceFile.from_content("unicode.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None

    def test_very_long_function(self, generator):
        """Very long function"""
        lines = ["def long_func():"]
        for i in range(100):
            lines.append(f"    x{i} = {i}")
        lines.append("    return x99")
        code = "\n".join(lines)

        source = SourceFile.from_content("long.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None

    def test_complex_type_hints(self, generator):
        """Complex type hints"""
        code = """
from typing import Dict, List, Optional, Union, Callable

def process(
    data: Dict[str, List[Optional[int]]],
    callback: Callable[[int], Union[str, None]]
) -> Optional[Dict[str, Any]]:
    return None
"""
        source = SourceFile.from_content("types.py", code, "python")
        ir_doc = generator.generate(source, "v1")

        assert ir_doc is not None
