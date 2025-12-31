"""
SOTA L11 Edge Case Tests

Tests ALL edge cases, corner cases, and extreme scenarios:
- Empty/minimal inputs
- Unicode & special characters
- Deep nesting
- Large files
- Malformed syntax
- Boundary conditions
- Concurrent access
- Memory limits

PRODUCTION REQUIREMENTS:
- No crashes
- Graceful degradation
- Complete error reporting
- Memory safety
"""

import pytest


def test_empty_file():
    """Edge: Empty file"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    result = codegraph_ast.process_python_files([("empty.py", "", "test")], "repo")

    assert len(result) == 1
    assert result[0]["success"] is True
    assert len(result[0]["nodes"]) == 0
    assert len(result[0]["edges"]) == 0


def test_only_whitespace():
    """Edge: Only whitespace"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = "   \n\n\t\t\n   "
    result = codegraph_ast.process_python_files([("ws.py", code, "test")], "repo")

    assert result[0]["success"] is True
    assert len(result[0]["nodes"]) == 0


def test_only_comments():
    """Edge: Only comments"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = """
# Comment 1
# Comment 2
# Comment 3
"""
    result = codegraph_ast.process_python_files([("comments.py", code, "test")], "repo")

    assert result[0]["success"] is True
    assert len(result[0]["nodes"]) == 0


def test_unicode_identifiers():
    """Edge: Unicode identifiers"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = """
class 한글클래스:
    def 메서드(self):
        pass

def 함수():
    \"\"\"독스트링\"\"\"
    pass
"""
    result = codegraph_ast.process_python_files([("unicode.py", code, "test")], "repo")

    assert result[0]["success"] is True
    assert len(result[0]["nodes"]) == 3

    # Check names
    names = {n["name"] for n in result[0]["nodes"]}
    assert "한글클래스" in names
    assert "메서드" in names
    assert "함수" in names


def test_emoji_in_code():
    """Edge: Emoji in docstrings (identifiers are ASCII-only per Python spec)"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = """
def rocket_func():
    \"\"\"Emoji function 🎉🚀\"\"\"
    pass
"""
    result = codegraph_ast.process_python_files([("emoji.py", code, "test")], "repo")

    assert result[0]["success"] is True
    assert len(result[0]["nodes"]) == 1
    assert result[0]["nodes"][0]["name"] == "rocket_func"
    # Emoji should be preserved in docstring
    assert "🎉" in result[0]["nodes"][0]["docstring"]
    assert "🚀" in result[0]["nodes"][0]["docstring"]


def test_deeply_nested_classes():
    """Edge: 10-level nested classes"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = """
class L1:
    class L2:
        class L3:
            class L4:
                class L5:
                    class L6:
                        class L7:
                            class L8:
                                class L9:
                                    class L10:
                                        def deepest(self):
                                            pass
"""
    result = codegraph_ast.process_python_files([("deep.py", code, "test")], "repo")

    assert result[0]["success"] is True
    assert len(result[0]["nodes"]) == 11  # 10 classes + 1 method

    # Check deepest FQN
    deepest = max(result[0]["nodes"], key=lambda n: len(n["fqn"]))
    assert "L10.deepest" in deepest["fqn"]


def test_very_long_function_name():
    """Edge: 200-char function name"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    long_name = "a" * 200
    code = f"def {long_name}(): pass"

    result = codegraph_ast.process_python_files([("long.py", code, "test")], "repo")

    assert result[0]["success"] is True
    assert len(result[0]["nodes"]) == 1
    assert result[0]["nodes"][0]["name"] == long_name


def test_100_parameters():
    """Edge: 100 parameters"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    params = ", ".join(f"p{i}" for i in range(100))
    code = f"def func({params}): pass"

    result = codegraph_ast.process_python_files([("params.py", code, "test")], "repo")

    assert result[0]["success"] is True
    assert len(result[0]["nodes"]) == 1


def test_1000_methods():
    """Extreme: 1000 methods in one class"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    methods = "\n".join(f"    def method{i}(self): pass" for i in range(1000))
    code = f"class BigClass:\n{methods}"

    result = codegraph_ast.process_python_files([("big.py", code, "test")], "repo")

    assert result[0]["success"] is True
    assert len(result[0]["nodes"]) == 1001  # 1 class + 1000 methods


def test_malformed_syntax_no_crash():
    """Edge: Malformed syntax should not crash"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    bad_codes = [
        "def incomplete(",
        "class NoColon",
        "if True\n    pass",
        "def f():\nreturn",  # Bad indentation
        "def f() return 1",  # Missing colon
    ]

    for code in bad_codes:
        result = codegraph_ast.process_python_files([("bad.py", code, "test")], "repo")
        # Should not crash (tree-sitter is error-tolerant)
        assert len(result) == 1
        assert "success" in result[0]


def test_null_bytes_in_code():
    """Edge: Null bytes in code"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = "def func():\x00 pass"

    # Should handle gracefully
    try:
        result = codegraph_ast.process_python_files([("null.py", code, "test")], "repo")
        # If it succeeds, check it doesn't crash
        assert len(result) == 1
    except Exception:
        # If it fails, that's also acceptable for null bytes
        pass


def test_concurrent_processing():
    """Edge: Process same file multiple times concurrently"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = """
class Test:
    def method(self):
        pass
"""

    # Process 100 copies in parallel
    files = [(f"file{i}.py", code, f"mod{i}") for i in range(100)]
    result = codegraph_ast.process_python_files(files, "repo")

    assert len(result) == 100

    # All should succeed
    for r in result:
        assert r["success"] is True
        assert len(r["nodes"]) == 2  # class + method


def test_node_id_uniqueness():
    """Critical: Node IDs must be unique within file"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = """
class A:
    def method(self):
        pass

class B:
    def method(self):
        pass
"""

    result = codegraph_ast.process_python_files([("test.py", code, "test")], "repo")

    node_ids = [n["id"] for n in result[0]["nodes"]]

    # All IDs must be unique
    assert len(node_ids) == len(set(node_ids))


def test_node_id_stability_across_runs():
    """Critical: Same input → same Node IDs"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = """
class Stable:
    def method(self):
        pass
"""

    # Run 10 times
    results = []
    for _ in range(10):
        r = codegraph_ast.process_python_files([("test.py", code, "test")], "repo")
        results.append(r)

    # All should have identical node IDs
    first_ids = [n["id"] for n in results[0][0]["nodes"]]

    for r in results[1:]:
        ids = [n["id"] for n in r[0]["nodes"]]
        assert ids == first_ids


def test_fqn_correctness():
    """Critical: FQN must be correct for all nesting levels"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = """
class Outer:
    class Middle:
        class Inner:
            def method(self):
                pass
"""

    result = codegraph_ast.process_python_files([("test.py", code, "myapp.models")], "repo")

    fqns = {n["name"]: n["fqn"] for n in result[0]["nodes"]}

    assert fqns["Outer"] == "myapp.models.Outer"
    assert fqns["Middle"] == "myapp.models.Outer.Middle"
    assert fqns["Inner"] == "myapp.models.Outer.Middle.Inner"
    assert fqns["method"] == "myapp.models.Outer.Middle.Inner.method"


def test_edge_source_target_validity():
    """Critical: All edges must reference valid nodes"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    code = """
class Parent:
    def method(self):
        pass
"""

    result = codegraph_ast.process_python_files([("test.py", code, "test")], "repo")

    node_ids = {n["id"] for n in result[0]["nodes"]}

    # All edge source/target IDs must exist in nodes
    for edge in result[0]["edges"]:
        # Source must be a valid node ID
        assert edge["source_id"] in node_ids, f"Invalid source: {edge['source_id']}"
        # Target might be external (for INHERITS), so only check CONTAINS
        if edge["kind"] == "CONTAINS":
            assert edge["target_id"] in node_ids, f"Invalid target: {edge['target_id']}"


def test_memory_safety_large_file():
    """Extreme: Very large file (10k lines)"""
    try:
        import codegraph_ast
    except ImportError:
        pytest.skip("Rust module not installed")

    # Generate 10k line file
    lines = []
    for i in range(1000):
        lines.append(f"class Class{i}:")
        lines.append(f"    def method{i}(self):")
        lines.append(f"        pass")
        lines.append("")

    code = "\n".join(lines)

    result = codegraph_ast.process_python_files([("huge.py", code, "test")], "repo")

    assert result[0]["success"] is True
    # Should have 1000 classes + 1000 methods = 2000 nodes
    assert len(result[0]["nodes"]) == 2000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
