#!/usr/bin/env python3
"""
Test L14 E2E Orchestrator with TRCR Integration

This test validates the full pipeline:
1. E2E Orchestrator reads test file
2. Builds IR (L1-L6)
3. Runs L14 taint analysis with TRCR enabled
4. Detects SQL injection vulnerability
"""

import sys
from pathlib import Path

# Add packages to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "packages" / "codegraph-ir"))


def test_l14_trcr_integration():
    """Test E2E orchestrator with TRCR detects SQL injection"""
    print("=" * 60)
    print("L14 E2E TRCR Test: SQL Injection Detection")
    print("=" * 60)

    try:
        import codegraph_ir
    except ImportError as e:
        print(f"❌ Failed to import codegraph_ir: {e}")
        print("   Run: cd packages/codegraph-ir && maturin develop --features python")
        return False

    # Test file path
    test_file = Path("/tmp/test_sql_injection.py")
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        print("   Run: python scripts/test_l14_trcr.py")
        return False

    print(f"\n📝 Test file: {test_file}")

    # Run E2E pipeline with TRCR enabled
    print("\n🚀 Running E2E pipeline with TRCR enabled...")

    result = codegraph_ir.run_ir_indexing_pipeline(
        repo_root=str(test_file.parent),
        repo_name="test-trcr",
        file_paths=[str(test_file)],
        enable_chunking=False,
        enable_cross_file=True,  # Needed for call graph
        enable_symbols=False,
        enable_points_to=False,
        enable_repomap=False,
        enable_taint=True,  # 🔥 Enable taint analysis
        use_trcr=True,  # 🔥 Enable TRCR mode (488 atoms + 30 CWE rules)
        parallel_workers=1,
    )

    # Check stats
    stats = result.get("stats", {})
    print(f"\n📊 Pipeline Stats:")
    print(f"   Files processed: {stats.get('files_processed', 0)}")
    print(f"   Total duration: {stats.get('total_duration_ms', 0):.2f}ms")

    # Check taint results
    taint_results = result.get("taint_results", [])
    print(f"\n🔍 Taint Analysis Results:")
    print(f"   Total taint summaries: {len(taint_results)}")

    if not taint_results:
        print("   ⚠️  No taint flows detected (TRCR may not be enabled)")
        print("   Expected: SQL injection (input() → cursor.execute())")
        return False

    # Display results
    for i, summary in enumerate(taint_results):
        function_id = summary.get("function_id", "unknown")
        sources = summary.get("sources_found", 0)
        sinks = summary.get("sinks_found", 0)
        flows = summary.get("taint_flows", 0)

        print(f"\n   [{i + 1}/{len(taint_results)}] Function: {function_id}")
        print(f"       Sources: {sources}")
        print(f"       Sinks: {sinks}")
        print(f"       Flows: {flows}")

    # Validate results
    total_flows = sum(s.get("taint_flows", 0) for s in taint_results)

    if total_flows == 0:
        print("\n❌ FAILED: Expected at least one taint flow (input→execute)")
        return False

    print(f"\n✅ SUCCESS: TRCR detected {total_flows} taint flow(s)")
    print("   Expected: SQL injection (input() → cursor.execute())")
    return True


if __name__ == "__main__":
    success = test_l14_trcr_integration()
    sys.exit(0 if success else 1)
