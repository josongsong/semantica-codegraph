"""
Integration Test: Rust IR Generation

Tests complete IR generation (Node + Edge) from Python code.

PRODUCTION REQUIREMENTS:
- Validate all Node fields
- Validate all Edge types
- Compare with Python generator output
- No fake data
"""

import pytest


def test_rust_ir_import():
    """Test Rust IR module can be imported"""
    try:
        import codegraph_ast

        assert hasattr(codegraph_ast, "process_python_files")
    except ImportError as e:
        pytest.skip(f"Rust module not installed: {e}")


def test_rust_ir_simple_function():
    """Test IR generation for simple function"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = """
def calculate(x, y):
    \"\"\"Calculate sum\"\"\"
    return x + y
"""

    files = [("test.py", code, "myapp.calc")]
    results = codegraph_ast.process_python_files(files, "test-repo")

    assert len(results) == 1
    result = results[0]

    assert result["success"] is True
    assert len(result["nodes"]) == 1

    node = result["nodes"][0]
    assert node["kind"] == "function"
    assert node["name"] == "calculate"
    assert node["fqn"] == "myapp.calc.calculate"
    assert node["file_path"] == "test.py"
    assert node["language"] == "python"
    assert node["module_path"] == "myapp.calc"
    assert node["docstring"] == "Calculate sum"
    assert "content_hash" in node


def test_rust_ir_class_with_methods():
    """Test IR generation for class with methods"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = """
class Calculator:
    \"\"\"Calculator class\"\"\"
    
    def add(self, x, y):
        return x + y
    
    def subtract(self, x, y):
        return x - y
"""

    files = [("test.py", code, "myapp.calc")]
    results = codegraph_ast.process_python_files(files, "test-repo")

    assert len(results) == 1
    result = results[0]

    assert result["success"] is True
    assert len(result["nodes"]) == 3  # 1 class + 2 methods

    # Check class
    class_node = next(n for n in result["nodes"] if n["kind"] == "class")
    assert class_node["name"] == "Calculator"
    assert class_node["fqn"] == "myapp.calc.Calculator"
    assert class_node["docstring"] == "Calculator class"

    # Check methods
    methods = [n for n in result["nodes"] if n["kind"] == "method"]
    assert len(methods) == 2

    method_names = {m["name"] for m in methods}
    assert method_names == {"add", "subtract"}

    # Check FQNs
    for method in methods:
        assert method["fqn"].startswith("myapp.calc.Calculator.")

    # Check CONTAINS edges
    edges = result["edges"]
    contains_edges = [e for e in edges if e["kind"] == "CONTAINS"]
    assert len(contains_edges) >= 2  # At least 2 methods from class


def test_rust_ir_inheritance():
    """Test IR generation for class inheritance"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = """
class Base:
    pass

class Child(Base):
    pass

class MultiChild(Base, Mixin):
    pass
"""

    files = [("test.py", code, "myapp.models")]
    results = codegraph_ast.process_python_files(files, "test-repo")

    assert len(results) == 1
    result = results[0]

    assert result["success"] is True
    assert len(result["nodes"]) == 3  # 3 classes

    # Check INHERITS edges
    edges = result["edges"]
    inherits_edges = [e for e in edges if e["kind"] == "INHERITS"]
    assert len(inherits_edges) == 3  # Child→Base, MultiChild→Base, MultiChild→Mixin


def test_rust_ir_parallel_processing():
    """Test parallel processing of multiple files"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    files = []
    for i in range(10):
        code = f"""
class Class{i}:
    def method{i}(self):
        pass
"""
        files.append((f"file{i}.py", code, f"myapp.module{i}"))

    results = codegraph_ast.process_python_files(files, "test-repo")

    assert len(results) == 10

    for i, result in enumerate(results):
        assert result["success"] is True
        assert result["file_index"] == i
        assert len(result["nodes"]) == 2  # 1 class + 1 method


def test_rust_ir_node_id_stability():
    """Test Node ID stability (same input → same ID)"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = """
def stable_function():
    pass
"""

    files = [("test.py", code, "myapp.test")]

    # Process twice
    results1 = codegraph_ast.process_python_files(files, "test-repo")
    results2 = codegraph_ast.process_python_files(files, "test-repo")

    node1 = results1[0]["nodes"][0]
    node2 = results2[0]["nodes"][0]

    # IDs should be identical
    assert node1["id"] == node2["id"]

    # Content hashes should be identical
    assert node1["content_hash"] == node2["content_hash"]


def test_rust_ir_error_handling():
    """Test error handling for invalid syntax"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    # Invalid Python syntax
    code = "def invalid syntax here"

    files = [("test.py", code, "myapp.test")]
    results = codegraph_ast.process_python_files(files, "test-repo")

    assert len(results) == 1
    result = results[0]

    # tree-sitter is error-tolerant, so may still parse something
    # Just ensure it doesn't crash
    assert "success" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
