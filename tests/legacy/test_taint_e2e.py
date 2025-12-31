"""Test L14 Taint Analysis in E2E Pipeline"""

import codegraph_ir
from pathlib import Path
import tempfile
import os
import shutil

# Create test repository with vulnerable code
test_repo = tempfile.mkdtemp(prefix="taint_test_")

# Write vulnerable Python file
test_file = Path(test_repo) / "vulnerable.py"
test_file.write_text("""
def unsafe_function():
    user_data = input()  # Source: user input
    eval(user_data)      # Sink: code execution
    
def safe_function():
    user_data = input()
    print(user_data)  # Not a sink
""")

print(f"Test repo: {test_repo}")
print(f"Test file: {test_file}")

# Run E2E pipeline with taint analysis enabled
result = codegraph_ir.run_ir_indexing_pipeline(
    repo_root=test_repo,
    repo_name="taint_test",
    file_paths=None,  # Scan all files
    enable_chunking=True,
    enable_cross_file=True,
    enable_symbols=True,
    enable_points_to=False,  # Disable for faster testing
    enable_repomap=False,
    enable_taint=True,  # ✅ Enable taint analysis
    parallel_workers=0,
)

# Extract results
nodes = result.get("nodes", [])
edges = result.get("edges", [])
taint_results = result.get("taint_results", [])
stats = result.get("stats", {})

print(f"\n=== IR Generation ===")
print(f"Nodes: {len(nodes)}")
print(f"Edges: {len(edges)}")

# Show some nodes
print("\nSample nodes:")
for node in nodes[:15]:
    kind = node.get("kind", "Unknown")
    name = node.get("name", "Unknown")
    fqn = node.get("fqn", "")
    print(f"  - {kind}: {name} (FQN: {fqn})")

print(f"\n=== Taint Analysis ===")
print(f"Taint results: {len(taint_results)}")

if taint_results:
    for tr in taint_results:
        print(f"\nFunction: {tr.get('function_id')}")
        print(f"  Sources found: {tr.get('sources_found', 0)}")
        print(f"  Sinks found: {tr.get('sinks_found', 0)}")
        print(f"  Taint flows: {tr.get('taint_flows', 0)}")
else:
    print("⚠️ No taint results found")

print(f"\n=== Stats ===")
print(f"Files processed: {stats.get('files_processed', 0)}")
print(f"Total LOC: {stats.get('total_loc', 0)}")
print(f"Total duration: {stats.get('total_duration_ms', 0)} ms")

# Cleanup
shutil.rmtree(test_repo)

print("\n✅ Test complete")
