"""
Quick Integration Test - Rust Adapter

Tests Rust adapter without full environment.
"""

import sys
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "codegraph-engine"))

try:
    from codegraph_engine.code_foundation.infrastructure.generators.rust_adapter import RustIRAdapter
    from codegraph_engine.code_foundation.infrastructure.parsing import SourceFile
    from codegraph_engine.code_foundation.domain.models import Language

    print("✅ Imports successful")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Test Rust adapter
print("\n🔍 Testing Rust Adapter")
print("=" * 70)

adapter = RustIRAdapter("test-repo", enable_rust=True)

print(f"Rust available: {adapter.is_rust_available()}")

if not adapter.is_rust_available():
    print("⚠️  Rust module not installed")
    sys.exit(0)

# Test code
code = """
class Calculator:
    '''Calculator class'''
    
    def add(self, x, y):
        '''Add two numbers'''
        return x + y
    
    def subtract(self, x, y):
        return x - y

def helper(x):
    return x * 2
"""

source = SourceFile.from_content(
    file_path="test.py",
    content=code,
    language=Language.PYTHON,
)

# Generate IR
print("\nGenerating IR...")
ir_docs, errors = adapter.generate_ir_batch([source])

print(f"Errors: {len(errors)}")
if errors:
    for path, error in errors.items():
        print(f"  {path}: {error}")

print(f"IR Documents: {len(ir_docs)}")

if ir_docs:
    ir_doc = ir_docs[0]
    print(f"\nIRDocument:")
    print(f"  File: {ir_doc.file_path}")
    print(f"  Language: {ir_doc.language}")
    print(f"  Nodes: {len(ir_doc.nodes)}")
    print(f"  Edges: {len(ir_doc.edges)}")

    print(f"\n  Nodes:")
    for node in ir_doc.nodes:
        print(f"    - {node.kind.value}: {node.name} ({node.fqn})")

    print(f"\n  Edges:")
    for edge in ir_doc.edges:
        print(f"    - {edge.kind.value}: {edge.source_id[:16]}... → {edge.target_id[:16]}...")

    # Validation
    assert len(ir_doc.nodes) == 4, f"Expected 4 nodes, got {len(ir_doc.nodes)}"
    assert len(ir_doc.edges) >= 2, f"Expected >= 2 edges, got {len(ir_doc.edges)}"

    print("\n✅ All validations passed!")
else:
    print("❌ No IR documents generated!")
    sys.exit(1)

print("=" * 70)
print("🎉 Rust integration working correctly!")
