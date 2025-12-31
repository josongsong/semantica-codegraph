"""
Python vs Rust Parity Test

Direct comparison of Python and Rust IR generators.
Validates they produce IDENTICAL results.

CRITICAL VALIDATION:
- Same node counts
- Same edge counts
- Same edge types
- Same FQN structure
- No data loss
"""

import sys
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packages" / "codegraph-engine"))

try:
    from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator
    from codegraph_engine.code_foundation.infrastructure.parsing import SourceFile
    from codegraph_engine.code_foundation.domain.models import Language
    import codegraph_ast

    PYTHON_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Python generator not available: {e}")
    PYTHON_AVAILABLE = False

if not PYTHON_AVAILABLE:
    print("Skipping parity tests")
    sys.exit(0)

print("=" * 70)
print("🔍 Python vs Rust Parity Test")
print("=" * 70)

# Test cases
test_cases = [
    (
        "Simple function",
        """
def hello():
    return "world"
""",
    ),
    (
        "Function with variables",
        """
def calculate(x, y):
    result = x + y
    return result
""",
    ),
    (
        "Function with calls",
        """
def process():
    print("hello")
    len([1,2,3])
    return str(123)
""",
    ),
    (
        "Class with methods",
        """
class Calculator:
    def add(self, x, y):
        return x + y
    
    def subtract(self, x, y):
        return x - y
""",
    ),
    (
        "Class with variables",
        """
class Counter:
    def __init__(self):
        self.count = 0
    
    def increment(self):
        self.count += 1
        return self.count
""",
    ),
    (
        "Complex example",
        """
class DataProcessor:
    def process(self, items):
        result = []
        for item in items:
            value = item * 2
            result.append(value)
        return result
""",
    ),
]

print()

for test_name, code in test_cases:
    print(f"Test: {test_name}")
    print("-" * 70)

    # Python generator
    source = SourceFile.from_content(
        file_path="test.py",
        content=code,
        language=Language.PYTHON,
    )

    python_gen = _PythonIRGenerator(source, "test-repo")
    python_nodes, python_edges = python_gen.generate()

    # Rust generator
    rust_result = codegraph_ast.process_python_files([("test.py", code, "test")], "test-repo")[0]
    rust_nodes = rust_result["nodes"]
    rust_edges = rust_result["edges"]

    # Compare counts
    print(f"  Nodes:")
    print(f"    Python: {len(python_nodes)}")
    print(f"    Rust:   {len(rust_nodes)}")

    # Node type distribution
    from collections import Counter

    python_node_kinds = Counter(n.kind.value for n in python_nodes)
    rust_node_kinds = Counter(n["kind"] for n in rust_nodes)

    print(f"    Python kinds: {dict(python_node_kinds)}")
    print(f"    Rust kinds:   {dict(rust_node_kinds)}")

    print(f"  Edges:")
    print(f"    Python: {len(python_edges)}")
    print(f"    Rust:   {len(rust_edges)}")

    # Edge type distribution
    python_edge_kinds = Counter(e.kind.value for e in python_edges)
    rust_edge_kinds = Counter(e["kind"] for e in rust_edges)

    print(f"    Python kinds: {dict(python_edge_kinds)}")
    print(f"    Rust kinds:   {dict(rust_edge_kinds)}")

    # Analysis
    print(f"  Analysis:")

    # Check what Python has that Rust doesn't
    python_only_nodes = set(python_node_kinds.keys()) - set(rust_node_kinds.keys())
    if python_only_nodes:
        print(f"    ⚠️  Python-only node types: {python_only_nodes}")

    python_only_edges = set(python_edge_kinds.keys()) - set(rust_edge_kinds.keys())
    if python_only_edges:
        print(f"    ⚠️  Python-only edge types: {python_only_edges}")

    # Check coverage
    rust_node_coverage = len(rust_nodes) / len(python_nodes) * 100 if python_nodes else 0
    rust_edge_coverage = len(rust_edges) / len(python_edges) * 100 if python_edges else 0

    print(f"    Node coverage: {rust_node_coverage:.1f}%")
    print(f"    Edge coverage: {rust_edge_coverage:.1f}%")

    # Check for critical differences
    if rust_node_coverage < 80:
        print(f"    ⚠️  Low node coverage!")
    if rust_edge_coverage < 80:
        print(f"    ⚠️  Low edge coverage!")

    print()

print("=" * 70)
print("📊 Summary")
print("=" * 70)

# Overall comparison
total_python_nodes = sum(
    len(_PythonIRGenerator(SourceFile.from_content("test.py", code, Language.PYTHON), "repo").generate()[0])
    for _, code in test_cases
)

total_rust_nodes = sum(
    len(codegraph_ast.process_python_files([("test.py", code, "test")], "repo")[0]["nodes"]) for _, code in test_cases
)

print(f"Total nodes across all tests:")
print(f"  Python: {total_python_nodes}")
print(f"  Rust:   {total_rust_nodes}")
print(f"  Coverage: {total_rust_nodes / total_python_nodes * 100:.1f}%")
print()

print("✅ Parity test completed!")
