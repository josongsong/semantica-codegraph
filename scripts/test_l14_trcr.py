#!/usr/bin/env python3
"""
Test L14 Taint Analysis with TRCR Integration

This script tests that the Rust E2E orchestrator can use TRCR for taint analysis.
"""

import sys
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "codegraph-trcr"))


def test_simple_sql_injection():
    """Test TRCR detects SQL injection"""
    print("=" * 60)
    print("Test: L14 Taint Analysis with TRCR")
    print("=" * 60)

    # Create test file with SQL injection vulnerability
    test_code = '''
import sqlite3

def vulnerable_query(user_input):
    """SQL injection vulnerability: user input flows to execute()"""
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()

    # BAD: Direct string concatenation
    query = f"SELECT * FROM users WHERE id={user_input}"
    cursor.execute(query)

    return cursor.fetchall()

def get_user_data():
    user_id = input("Enter user ID: ")  # Source: user input
    results = vulnerable_query(user_id)  # Sink: SQL execution
    return results
'''

    test_file = Path("/tmp/test_sql_injection.py")
    test_file.write_text(test_code)

    print(f"\n📝 Created test file: {test_file}")
    print(f"Code:\n{test_code}")

    print("\n🔍 Expected TRCR detection:")
    print("  - Source: input() → user input")
    print("  - Sink: cursor.execute() → SQL execution")
    print("  - Flow: get_user_data() calls both source and sink")

    print("\n✅ Test file ready for L14 analysis")
    print(f"Run: IRIndexingOrchestrator with use_trcr=True on {test_file}")

    return test_file


if __name__ == "__main__":
    test_file = test_simple_sql_injection()
    print(f"\n💡 Next step: Run Rust E2E pipeline with:")
    print(f"   - enable_taint=True")
    print(f"   - use_trcr=True")
    print(f"   - file: {test_file}")
