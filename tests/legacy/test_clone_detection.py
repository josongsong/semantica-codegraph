#!/usr/bin/env python3
"""
Quick test for clone detection without maturin install
"""

import sys
import subprocess

# Try to import, if fails, show how to install
try:
    # Add build path for testing
    sys.path.insert(0, "packages/codegraph-rust/target/release")
    import codegraph_ir
    print("✅ codegraph_ir imported successfully!")
except ImportError as e:
    print(f"❌ Failed to import codegraph_ir: {e}")
    print("\n📝 To install, run:")
    print("  cd packages/codegraph-rust/codegraph-ir")
    print("  maturin develop --release")
    sys.exit(1)

# Test data
fragments = [
    {
        "file_path": "test1.py",
        "start_line": 1,
        "end_line": 5,
        "content": "def calculate_sum(numbers):\n    total = 0\n    for num in numbers:\n        total += num\n    return total",
        "token_count": 25,
        "loc": 5,
    },
    {
        "file_path": "test2.py",
        "start_line": 10,
        "end_line": 14,
        "content": "def calculate_sum(numbers):\n    total = 0\n    for num in numbers:\n        total += num\n    return total",
        "token_count": 25,
        "loc": 5,
    },
]

print("\n🧪 Testing Clone Detection API...")

try:
    # Test detect_clones_all
    print("\n1. Testing detect_clones_all()...")
    result = codegraph_ir.detect_clones_all(fragments)
    print(f"   ✅ Found {len(result)} clone(s)")

    if result:
        for i, clone in enumerate(result, 1):
            print(f"\n   Clone {i}:")
            print(f"     Type: {clone['clone_type']}")
            print(f"     Source: {clone['source_file']}:{clone['source_start_line']}")
            print(f"     Target: {clone['target_file']}:{clone['target_start_line']}")
            print(f"     Similarity: {clone['similarity']:.2%}")

    # Test Type-1
    print("\n2. Testing detect_clones_type1()...")
    type1 = codegraph_ir.detect_clones_type1(fragments, 10, 3)
    print(f"   ✅ Found {len(type1)} Type-1 clone(s)")

    # Test Type-2
    print("\n3. Testing detect_clones_type2()...")
    type2 = codegraph_ir.detect_clones_type2(fragments, 10, 3, 0.8)
    print(f"   ✅ Found {len(type2)} Type-2 clone(s)")

    # Test Type-3
    print("\n4. Testing detect_clones_type3()...")
    type3 = codegraph_ir.detect_clones_type3(fragments, 10, 3, 0.7, 0.3)
    print(f"   ✅ Found {len(type3)} Type-3 clone(s)")

    # Test Type-4
    print("\n5. Testing detect_clones_type4()...")
    type4 = codegraph_ir.detect_clones_type4(fragments, 5, 2, 0.5, 0.4, 0.3, 0.3)
    print(f"   ✅ Found {len(type4)} Type-4 clone(s)")

    # Test file-specific
    print("\n6. Testing detect_clones_in_file()...")
    file_clones = codegraph_ir.detect_clones_in_file(fragments, "test1.py", "all")
    print(f"   ✅ Found {len(file_clones)} clone(s) in test1.py")

    print("\n" + "="*60)
    print("🎉 All tests passed!")
    print("="*60)

except Exception as e:
    print(f"\n❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
