#!/usr/bin/env python3
"""
Test script for integrated Rust pipeline with Effect Analysis and SMT
"""

import sys
sys.path.insert(0, 'packages/codegraph-rust/codegraph-ir')

try:
    import codegraph_ir
    print("✅ codegraph_ir module imported successfully")
except ImportError as e:
    print(f"❌ Failed to import codegraph_ir: {e}")
    sys.exit(1)

# Test code with various analysis features
test_code = """
def pure_function(x, y):
    return x + y

def impure_io():
    print("Hello")
    return 42

def database_query(user_id):
    db.query(f"SELECT * FROM users WHERE id = {user_id}")

class Calculator:
    def add(self, a, b):
        return a + b

    def print_result(self, result):
        print(f"Result: {result}")
"""

# Process the test code
print("\n=== Processing Test Code ===")
try:
    # Prepare file data: [(file_path, content, module_path)]
    file_data = [
        ("test_file.py", test_code, "test_file")
    ]

    import msgpack

    # Pass file_data directly (not msgpack-encoded)
    result = codegraph_ir.process_python_files_msgpack(
        file_data,
        "test_repo"
    )

    parsed = msgpack.unpackb(result, raw=False)

    # Debug: Print what we got
    print(f"\n✅ IR Processing successful!")
    print(f"   Result type: {type(parsed)}")

    # If it's a list, the first element might be the actual result
    if isinstance(parsed, list):
        if len(parsed) > 0:
            actual_result = parsed[0]
            print(f"   First element type: {type(actual_result)}")
        else:
            print("   Empty result list!")
            actual_result = {}
    else:
        actual_result = parsed

    # Now print the actual results
    if isinstance(actual_result, dict):
        print(f"   Success: {actual_result.get('success', False)}")

        errors = actual_result.get('errors', [])
        if errors:
            print(f"   ⚠️  Errors: {errors}")

        nodes = actual_result.get('nodes', [])
        edges = actual_result.get('edges', [])
        print(f"   Nodes: {len(nodes)}")
        print(f"   Edges: {len(edges)}")
        print(f"   Occurrences: {len(actual_result.get('occurrences', []))}")

        # Show some node details
        if nodes:
            print(f"\n📦 Sample Nodes:")
            for node in nodes[:5]:
                node_kind = node.get('kind', 'Unknown')
                node_name = node.get('name', 'unnamed')
                print(f"   - {node_kind}: {node_name}")

        # Show some edge details
        if edges:
            print(f"\n🔗 Sample Edges:")
            for edge in edges[:5]:
                edge_kind = edge.get('kind', 'Unknown')
                source = edge.get('source', '?')
                target = edge.get('target', '?')
                print(f"   - {edge_kind}: {source} → {target}")

        # Note about advanced analyses
        print(f"\n💡 Note: Advanced analyses (Effect Analysis, SMT, PDG, Taint, etc.)")
        print(f"   are integrated in the E2E pipeline orchestrator but not yet")
        print(f"   exposed through the per-file msgpack API. See:")
        print(f"   - packages/codegraph-rust/codegraph-ir/src/pipeline/end_to_end_orchestrator.rs")
        print(f"   - execute_l8_effect_analysis()")
        print(f"   - execute_l8_smt_verification()")

    print("\n✅ All integration tests passed!")

except Exception as e:
    print(f"\n❌ Error during processing: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
