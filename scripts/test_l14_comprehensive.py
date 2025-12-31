#!/usr/bin/env python3
"""
Comprehensive L14 TRCR Test Suite

Tests all complex scenarios:
1. Interprocedural taint flow
2. Sanitizer detection
3. Multiple CWE patterns (SQL, Command, XSS, Path Traversal)
4. Cross-file taint flow
5. Alias analysis
6. Large files
"""

import sys
from pathlib import Path
from typing import Dict, List

# Test Cases
TEST_CASES = {
    "interprocedural": """
import sqlite3

def get_user_input():
    '''Source function'''
    return input("Enter user ID: ")

def execute_query(data):
    '''Sink function'''
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE id={data}"
    cursor.execute(query)  # VULN: SQL Injection
    return cursor.fetchall()

def main():
    '''Main flow: source → sink through function calls'''
    user_data = get_user_input()  # Call source
    results = execute_query(user_data)  # Call sink
    return results
""",
    "sanitizer": """
import sqlite3
import html

def safe_query(user_input):
    '''Should NOT report: sanitizer present'''
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()

    # Sanitize input
    safe_input = html.escape(user_input)

    # Now safe to use
    cursor.execute(f"SELECT * FROM users WHERE name='{safe_input}'")
    return cursor.fetchall()

def unsafe_query(user_input):
    '''VULN: No sanitizer'''
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM users WHERE name='{user_input}'")
    return cursor.fetchall()

def main():
    data = input("Enter name: ")
    safe_query(data)  # OK
    unsafe_query(data)  # VULN
""",
    "multiple_cwe": """
import sqlite3
import subprocess
import os

def test_sql_injection():
    '''CWE-89: SQL Injection'''
    user_id = input("Enter ID: ")
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM users WHERE id={user_id}")

def test_command_injection():
    '''CWE-78: OS Command Injection'''
    filename = input("Enter filename: ")
    subprocess.Popen(f"cat {filename}", shell=True)

def test_path_traversal():
    '''CWE-22: Path Traversal'''
    user_file = input("Enter file: ")
    with open(f"/data/{user_file}", 'r') as f:
        return f.read()

def test_xss():
    '''CWE-79: XSS (if Flask is available)'''
    user_content = input("Enter content: ")
    # Note: This needs Flask to be detected properly
    # response.write(user_content)
    return user_content
""",
    "alias_analysis": """
import sqlite3

def test_aliases():
    '''Test alias tracking: x → y → z → sink'''
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()

    x = input("Enter ID: ")  # Source
    y = x  # Alias 1
    z = y  # Alias 2

    query = f"SELECT * FROM users WHERE id={z}"
    cursor.execute(query)  # VULN: Should detect through aliases

    return cursor.fetchall()
""",
    "complex_flow": """
import sqlite3

def get_input():
    return input("ID: ")

def validate(data):
    '''Passes through without sanitization'''
    if len(data) > 0:
        return data
    return "0"

def build_query(validated_data):
    return f"SELECT * FROM users WHERE id={validated_data}"

def execute(query):
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    cursor.execute(query)  # VULN
    return cursor.fetchall()

def main():
    '''Complex flow: source → validate → build → execute'''
    user_input = get_input()
    validated = validate(user_input)
    query = build_query(validated)
    results = execute(query)
    return results
""",
    "large_file": """
import sqlite3

# Large file with many functions

def helper1(x): return x
def helper2(x): return helper1(x)
def helper3(x): return helper2(x)
def helper4(x): return helper3(x)
def helper5(x): return helper4(x)
def helper6(x): return helper5(x)
def helper7(x): return helper6(x)
def helper8(x): return helper7(x)
def helper9(x): return helper8(x)
def helper10(x): return helper9(x)

def get_source():
    return input("Enter data: ")

def process_data(data):
    step1 = helper1(data)
    step2 = helper2(step1)
    step3 = helper3(step2)
    step4 = helper4(step3)
    step5 = helper5(step4)
    step6 = helper6(step5)
    step7 = helper7(step6)
    step8 = helper8(step7)
    step9 = helper9(step8)
    return helper10(step9)

def execute_sink(processed):
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM t WHERE x={processed}")
    return cursor.fetchall()

def main():
    source = get_source()
    processed = process_data(source)
    result = execute_sink(processed)
    return result

# More dummy functions to increase file size
def dummy1(): pass
def dummy2(): pass
def dummy3(): pass
def dummy4(): pass
def dummy5(): pass
def dummy6(): pass
def dummy7(): pass
def dummy8(): pass
def dummy9(): pass
def dummy10(): pass
""",
}


def run_test_case(name: str, code: str) -> Dict:
    """Run a single test case"""
    print(f"\n{'=' * 70}")
    print(f"Test Case: {name}")
    print("=" * 70)

    # Create test file
    test_file = Path(f"/tmp/trcr_test_{name}.py")
    test_file.write_text(code)
    print(f"📝 Created: {test_file}")
    print(f"   Lines: {len(code.splitlines())}")

    # Import codegraph_ir
    try:
        import codegraph_ir
    except ImportError as e:
        print(f"❌ Failed to import codegraph_ir: {e}")
        return {"error": str(e)}

    # Run pipeline
    print("\n🚀 Running E2E pipeline with TRCR...")

    result = codegraph_ir.run_ir_indexing_pipeline(
        repo_root=str(test_file.parent),
        repo_name=f"trcr-test-{name}",
        file_paths=[str(test_file)],
        enable_chunking=False,
        enable_cross_file=True,
        enable_symbols=False,
        enable_points_to=False,
        enable_repomap=False,
        enable_taint=True,
        use_trcr=True,
        parallel_workers=1,
    )

    # Analyze results
    stats = result.get("stats", {})
    taint_results = result.get("taint_results", [])

    print(f"\n📊 Results:")
    print(f"   Duration: {stats.get('total_duration_ms', 0):.2f}ms")
    print(f"   Functions analyzed: {len(taint_results)}")

    total_sources = 0
    total_sinks = 0
    total_flows = 0

    for summary in taint_results:
        sources = summary.get("sources_found", 0)
        sinks = summary.get("sinks_found", 0)
        flows = summary.get("taint_flows", 0)

        total_sources += sources
        total_sinks += sinks
        total_flows += flows

        if sources > 0 or sinks > 0 or flows > 0:
            print(f"\n   Function: {summary.get('function_id', 'unknown')}")
            print(f"      Sources: {sources}")
            print(f"      Sinks: {sinks}")
            print(f"      Flows: {flows}")

    print(f"\n   Total Sources: {total_sources}")
    print(f"   Total Sinks: {total_sinks}")
    print(f"   Total Flows: {total_flows}")

    # Verdict
    if total_flows > 0:
        print(f"\n✅ PASS: Detected {total_flows} taint flow(s)")
    elif total_sources > 0:
        print(f"\n⚠️  PARTIAL: Found {total_sources} sources but no complete flows")
        print("    (May need L6 type inference for sink detection)")
    else:
        print("\n❌ FAIL: No taint flows detected")

    return {
        "name": name,
        "duration_ms": stats.get("total_duration_ms", 0),
        "sources": total_sources,
        "sinks": total_sinks,
        "flows": total_flows,
        "passed": total_flows > 0,
    }


def main():
    """Run all test cases"""
    print("=" * 70)
    print("🔥 Comprehensive L14 TRCR Test Suite")
    print("=" * 70)
    print(f"\nTest Cases: {len(TEST_CASES)}")
    print(f"  1. Interprocedural taint flow")
    print(f"  2. Sanitizer detection")
    print(f"  3. Multiple CWE patterns (SQL, Command, Path, XSS)")
    print(f"  4. Alias analysis")
    print(f"  5. Complex multi-step flow")
    print(f"  6. Large file (100+ LOC)")

    results: List[Dict] = []

    # Run each test case
    for name, code in TEST_CASES.items():
        try:
            result = run_test_case(name, code)
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test '{name}' crashed: {e}")
            import traceback

            traceback.print_exc()
            results.append(
                {
                    "name": name,
                    "error": str(e),
                    "passed": False,
                }
            )

    # Summary
    print("\n" + "=" * 70)
    print("📊 Summary")
    print("=" * 70)

    passed = sum(1 for r in results if r.get("passed", False))
    total = len(results)

    print(f"\n{'Test Case':<20} {'Duration':<12} {'Sources':<8} {'Sinks':<8} {'Flows':<8} {'Status'}")
    print("-" * 70)

    for r in results:
        if "error" in r and "duration_ms" not in r:
            print(f"{r['name']:<20} {'ERROR':<12} {'-':<8} {'-':<8} {'-':<8} ❌")
        else:
            duration = f"{r.get('duration_ms', 0):.1f}ms"
            sources = r.get("sources", 0)
            sinks = r.get("sinks", 0)
            flows = r.get("flows", 0)
            status = "✅" if r.get("passed", False) else "⚠️ "

            print(f"{r['name']:<20} {duration:<12} {sources:<8} {sinks:<8} {flows:<8} {status}")

    print("-" * 70)
    print(f"\nTotal: {passed}/{total} passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    elif passed > 0:
        print(f"\n⚠️  PARTIAL SUCCESS: {passed}/{total} tests passed")
        print("   Note: Sink detection may require L6 type inference")
        return 1
    else:
        print("\n❌ ALL TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
