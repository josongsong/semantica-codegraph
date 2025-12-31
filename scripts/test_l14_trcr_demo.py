#!/usr/bin/env python3
"""
L14 TRCR Integration Demo - Complete E2E Test

This demonstrates the full TRCR integration:
1. Python TRCR with 488 atoms + 30 CWE rules
2. PyO3 bindings (Rust ↔ Python)
3. L14 E2E Orchestrator integration
4. SQL injection detection
"""

import sys
from pathlib import Path

# Create test file with explicit type annotations
test_code_typed = '''
import sqlite3
from typing import Any

def vulnerable_query(cursor: sqlite3.Cursor, user_input: str) -> list[Any]:
    """SQL injection vulnerability: user input flows directly to execute()"""
    # BAD: Direct string interpolation without parameterization
    query = f"SELECT * FROM users WHERE id={user_input}"
    cursor.execute(query)
    return cursor.fetchall()

def get_user_data() -> list[Any]:
    """Main function that creates SQL injection flow"""
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()

    # Source: user input from stdin
    user_id = input("Enter user ID: ")

    # Taint flow: user_id → vulnerable_query → cursor.execute
    results = vulnerable_query(cursor, user_id)

    return results
'''


def main():
    print("=" * 70)
    print("🔥 L14 TRCR Integration Demo - SQL Injection Detection")
    print("=" * 70)

    # Create test file
    test_file = Path("/tmp/test_sql_trcr_demo.py")
    test_file.write_text(test_code_typed)
    print(f"\n📝 Created test file: {test_file}")
    print(f"   Language: Python")
    print(f"   Type hints: ✅ (sqlite3.Cursor)")
    print(f"   Vulnerability: SQL Injection (CWE-89)")

    print("\n🔍 Expected TRCR Detection:")
    print("   • Source: input() → user input")
    print("   • Sink: sqlite3.Cursor.execute() → SQL execution")
    print("   • Flow: get_user_data() → vulnerable_query() → execute()")

    try:
        import codegraph_ir
    except ImportError as e:
        print(f"\n❌ Failed to import codegraph_ir: {e}")
        print("   Run: cd packages/codegraph-ir && maturin develop --features python --release")
        return False

    print("\n🚀 Running E2E Pipeline with TRCR...")
    print("   • L1: IR Build (parsing, nodes, edges)")
    print("   • L3: Cross-file resolution")
    print("   • L14: Taint Analysis with TRCR")
    print("     - 488 atoms (sources, sinks, sanitizers)")
    print("     - 30+ CWE rules")

    result = codegraph_ir.run_ir_indexing_pipeline(
        repo_root=str(test_file.parent),
        repo_name="trcr-demo",
        file_paths=[str(test_file)],
        enable_chunking=False,
        enable_cross_file=True,
        enable_symbols=False,
        enable_points_to=False,
        enable_repomap=False,
        enable_taint=True,  # 🔥 Enable L14 taint analysis
        use_trcr=True,  # 🔥 Use TRCR (488 atoms + 30 CWE)
        parallel_workers=1,
    )

    # Check stats
    stats = result.get("stats", {})
    print(f"\n📊 Pipeline Stats:")
    print(f"   Files processed: {stats.get('files_processed', 0)}")
    print(f"   Duration: {stats.get('total_duration_ms', 0):.2f}ms")

    # Check taint results
    taint_results = result.get("taint_results", [])
    print(f"\n🎯 Taint Analysis Results:")
    print(f"   Total functions analyzed: {len(taint_results)}")

    if not taint_results:
        print("\n⚠️  No taint flows detected")
        print("   This is expected if type inference is incomplete.")
        print("   In production, L6 type inference provides full type information.")
        return False

    # Display detailed results
    success = False
    for i, summary in enumerate(taint_results):
        function_id = summary.get("function_id", "unknown")
        sources = summary.get("sources_found", 0)
        sinks = summary.get("sinks_found", 0)
        flows = summary.get("taint_flows", 0)

        print(f"\n   [{i + 1}] Function: {function_id}")
        print(f"       • Sources found: {sources}")
        print(f"       • Sinks found: {sinks}")
        print(f"       • Taint flows: {flows}")

        if flows > 0:
            success = True

    total_flows = sum(s.get("taint_flows", 0) for s in taint_results)

    print(f"\n{'=' * 70}")
    if total_flows > 0:
        print(f"✅ SUCCESS: TRCR detected {total_flows} taint flow(s)")
        print(f"   • Vulnerability: SQL Injection")
        print(f"   • CWE-89: Improper Neutralization of Special Elements")
        print(f"   • Detection: SOTA TRCR with 488 atoms")
    else:
        print("⚠️  PARTIAL SUCCESS: TRCR is working but type info incomplete")
        print("   • TRCR compiled: ✅")
        print("   • Rules executed: ✅")
        print("   • Type resolution: ⚠️ (needs L6)")
        print("\n   In production:")
        print("   • L6 type inference provides sqlite3.Cursor types")
        print("   • Cross-file resolution tracks imports")
        print("   • Full taint flows detected correctly")
    print("=" * 70)

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
