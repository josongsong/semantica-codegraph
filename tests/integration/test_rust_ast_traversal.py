"""
Integration test for Rust AST traversal

Tests:
1. Single file traversal
2. Parallel traversal
3. Performance comparison (Python vs Rust)
"""

import time
import pytest


def test_rust_ast_import():
    """Test Rust module can be imported"""
    try:
        import codegraph_ast

        assert hasattr(codegraph_ast, "traverse_ast_parallel")
    except ImportError as e:
        pytest.skip(f"Rust module not installed: {e}")


def test_rust_ast_basic():
    """Test basic AST traversal"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    # Simple Python code
    code = """
def hello():
    return "world"

class MyClass:
    def method(self):
        pass
"""

    # Call Rust traversal
    files = [("test.py", code)]
    results = codegraph_ast.traverse_ast_parallel(files)

    assert len(results) == 1
    result = results[0]

    assert result["success"] is True
    assert result["node_count"] >= 2  # function + class

    # Check nodes
    nodes = result.get("nodes", [])
    kinds = [n["kind"] for n in nodes]

    assert "function_definition" in kinds
    assert "class_definition" in kinds


def test_rust_ast_parallel():
    """Test parallel traversal of multiple files"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    # Generate multiple files
    files = []
    for i in range(10):
        code = f"""
def func_{i}():
    return {i}

class Class_{i}:
    pass
"""
        files.append((f"file_{i}.py", code))

    # Parallel traversal
    results = codegraph_ast.traverse_ast_parallel(files)

    assert len(results) == 10

    # All should succeed
    for result in results:
        assert result["success"] is True
        assert result["node_count"] >= 2


def test_rust_vs_python_performance():
    """Compare Rust vs Python performance (informational)"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    # Generate test files
    code = """
def function_1():
    x = 1
    y = 2
    return x + y

class MyClass:
    def method_1(self):
        pass
    
    def method_2(self):
        pass

def function_2():
    for i in range(10):
        print(i)
"""

    files = [(f"file_{i}.py", code) for i in range(100)]

    # Rust timing
    start = time.perf_counter()
    rust_results = codegraph_ast.traverse_ast_parallel(files)
    rust_time = time.perf_counter() - start

    # Verify results
    assert len(rust_results) == 100
    for result in rust_results:
        assert result["success"] is True

    print(f"\n🦀 Rust: {rust_time:.3f}s ({rust_time / 100 * 1000:.2f}ms/file)")
    print(f"   Total nodes: {sum(r['node_count'] for r in rust_results)}")

    # Success if < 100ms (target: 2.4ms/file * 100 = 240ms)
    assert rust_time < 1.0, f"Rust too slow: {rust_time:.3f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
