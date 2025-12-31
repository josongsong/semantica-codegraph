#!/usr/bin/env python3
"""Test if PTA actually produces results"""
import sys
sys.path.insert(0, "packages/codegraph-ir")

from pathlib import Path
from codegraph_ir import EndToEndOrchestrator, E2EPipelineConfig

# Run on a small test file
config = E2EPipelineConfig(
    root_path="packages/codegraph-ir/tests/fixtures/python_simple",
    parallel_workers=1,
    enable_chunking=True,
    enable_repomap=False,
    enable_pta=True,
    enable_taint=False,
)

print("🔍 Running PTA on test fixtures...")
orchestrator = EndToEndOrchestrator(config)
result = orchestrator.execute()

print(f"\n📊 Pipeline Results:")
print(f"  Files processed: {result.files_processed}")
print(f"  Total LOC: {result.total_loc}")
print(f"  Nodes: {len(result.nodes) if hasattr(result, 'nodes') else 'N/A'}")
print(f"  Edges: {len(result.edges) if hasattr(result, 'edges') else 'N/A'}")

# Check stage durations
print(f"\n⏱️  Stage Durations:")
for stage, duration in result.stage_durations.items():
    print(f"  {stage}: {duration:.2f}ms")

# Check if PTA data exists
if hasattr(result, 'pta_summary') and result.pta_summary:
    pta = result.pta_summary
    print(f"\n✅ PTA Results:")
    print(f"  Points-to facts: {pta.get('points_to_count', 0)}")
    print(f"  Alias pairs: {pta.get('alias_count', 0)}")
    print(f"  Variables analyzed: {pta.get('var_count', 0)}")
else:
    print(f"\n⚠️  No PTA summary found in result")
    print(f"  Available attributes: {dir(result)}")
