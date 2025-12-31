"""
E2E Test: Rust IR Generator in Real Pipeline

Tests Rust integration in actual usage scenario.
"""

import sys
import time
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "codegraph-engine"))

try:
    from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder, LayeredIRConfig
    from codegraph_engine.code_foundation.infrastructure.generators.rust_adapter import get_rust_adapter
except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

print("=" * 70)
print("🔍 E2E Test: Rust in Real Pipeline")
print("=" * 70)

# Create test project
test_dir = Path(__file__).parent.parent / ".temp" / "test_project"
test_dir.mkdir(parents=True, exist_ok=True)

# Create test files
test_files = {
    "main.py": """
from utils import helper

class Application:
    def __init__(self, name):
        self.name = name
        self.config = {}
    
    def run(self):
        result = helper(self.name)
        print(result)
        return result
""",
    "utils.py": """
def helper(value):
    processed = value.upper()
    return processed

class Config:
    def load(self):
        data = {}
        return data
""",
}

for fname, content in test_files.items():
    (test_dir / fname).write_text(content)

print(f"\n📁 Test project: {test_dir}")
print(f"   Files: {len(test_files)}")
print()

# Test WITHOUT Rust
print("1️⃣  Test WITHOUT Rust:")
config = LayeredIRConfig()
builder = LayeredIRBuilder(
    project_root=test_dir,
    config=config,
)

files = list(test_dir.glob("*.py"))

start = time.perf_counter()
try:
    import asyncio

    ir_doc = asyncio.run(builder.build(files))
    elapsed_python = time.perf_counter() - start

    print(f"   Time: {elapsed_python:.3f}s")
    print(f"   Nodes: {len(ir_doc.nodes)}")
    print(f"   Edges: {len(ir_doc.edges)}")
    print(f"   ✅ Success")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    elapsed_python = None

# Test WITH Rust
print()
print("2️⃣  Test WITH Rust:")

# Create adapter
rust_adapter = get_rust_adapter(str(test_dir), enable_rust=True)

if not rust_adapter.is_rust_available():
    print("   ⚠️  Rust not available")
else:
    builder_rust = LayeredIRBuilder(
        project_root=test_dir,
        config=config,
        parallel_builder=rust_adapter,
    )

    start = time.perf_counter()
    try:
        ir_doc_rust = asyncio.run(builder_rust.build(files))
        elapsed_rust = time.perf_counter() - start

        print(f"   Time: {elapsed_rust:.3f}s")
        print(f"   Nodes: {len(ir_doc_rust.nodes)}")
        print(f"   Edges: {len(ir_doc_rust.edges)}")
        print(f"   ✅ Success")

        if elapsed_python:
            speedup = elapsed_python / elapsed_rust
            print(f"   Speedup: {speedup:.1f}x")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        import traceback

        traceback.print_exc()

print()
print("=" * 70)
print("✅ E2E test completed!")
print("=" * 70)
