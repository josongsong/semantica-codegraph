#!/usr/bin/env python3
"""
Test script for E2E Pipeline with Advanced Analysis
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
print("\n=== Executing E2E Pipeline ===")
try:
    # Prepare file data: [(file_path, content, module_path)]
    file_data = [
        ("test_file.py", test_code, "test_file")
    ]

    import msgpack

    # Execute E2E pipeline
    result = codegraph_ir.execute_e2e_pipeline_msgpack(
        file_data,
        "test_repo",
        None  # repo_root (optional)
    )

    parsed = msgpack.unpackb(result, raw=False)

    print(f"\n✅ E2E Pipeline Execution successful!")
    print(f"   Result keys: {list(parsed.keys())}")

    # Print basic IR results
    print(f"\n📊 IR Results:")
    print(f"   Nodes: {len(parsed.get('nodes', []))}")
    print(f"   Edges: {len(parsed.get('edges', []))}")
    print(f"   Occurrences: {len(parsed.get('occurrences', []))}")

    # Print advanced analysis results
    if 'effect_results' in parsed and parsed['effect_results']:
        print(f"\n🎯 Effect Analysis:")
        for effect in parsed['effect_results'][:5]:
            print(f"   - {effect.get('function_id')}: {effect.get('effects')} (Pure: {effect.get('is_pure')})")
    else:
        print(f"\n🎯 Effect Analysis: No results")

    if 'smt_results' in parsed and parsed['smt_results']:
        print(f"\n🔍 SMT Verification:")
        print(f"   - {len(parsed['smt_results'])} functions verified")
        for smt in parsed['smt_results'][:3]:
            print(f"   - {smt.get('function_id')}: {smt.get('result')}")
    else:
        print(f"\n🔍 SMT Verification: No results")

    if 'dfg_graphs' in parsed and parsed['dfg_graphs']:
        print(f"\n📊 DFG Graphs: {len(parsed.get('dfg_graphs', []))}")
        for dfg in parsed['dfg_graphs'][:3]:
            print(f"   - {dfg.get('function_id')}: {dfg.get('def_count')} defs, {dfg.get('use_count')} uses")
    else:
        print(f"\n📊 DFG Graphs: No results")

    if 'ssa_graphs' in parsed and parsed['ssa_graphs']:
        print(f"\n🔄 SSA Graphs: {len(parsed.get('ssa_graphs', []))}")
        for ssa in parsed['ssa_graphs'][:3]:
            print(f"   - {ssa.get('function_id')}: {ssa.get('version_count')} versions, {ssa.get('phi_node_count')} phi nodes")
    else:
        print(f"\n🔄 SSA Graphs: No results")

    if 'pdg_graphs' in parsed and parsed['pdg_graphs']:
        print(f"\n🕸️  PDG Graphs: {len(parsed.get('pdg_graphs', []))}")
        for pdg in parsed['pdg_graphs'][:3]:
            print(f"   - {pdg.get('function_id')}: {pdg.get('node_count')} nodes, {pdg.get('control_edges')} control edges")
    else:
        print(f"\n🕸️  PDG Graphs: No results")

    if 'taint_results' in parsed and parsed['taint_results']:
        print(f"\n🔒 Taint Analysis: {len(parsed.get('taint_results', []))}")
        for taint in parsed['taint_results'][:3]:
            print(f"   - {taint.get('function_id')}: {taint.get('taint_flows')} flows")
    else:
        print(f"\n🔒 Taint Analysis: No results")

    if 'memory_safety_issues' in parsed and parsed['memory_safety_issues']:
        print(f"\n💾 Memory Safety Issues: {len(parsed.get('memory_safety_issues', []))}")
        for issue in parsed['memory_safety_issues'][:3]:
            print(f"   - {issue.get('issue_type')}: {issue.get('description')}")
    else:
        print(f"\n💾 Memory Safety Issues: None found")

    # Print stats
    if 'stats' in parsed:
        stats = parsed['stats']
        print(f"\n📈 Pipeline Statistics:")
        print(f"   Files processed: {stats.get('files_processed', 0)}")
        print(f"   Total duration: {stats.get('total_duration', 0):.3f}s")
        print(f"   LOC/s: {stats.get('loc_per_second', 0):.0f}")

    print("\n✅ All E2E pipeline tests passed!")

except Exception as e:
    print(f"\n❌ Error during processing: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
