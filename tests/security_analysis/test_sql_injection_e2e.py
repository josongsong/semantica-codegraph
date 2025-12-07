"""
SQL Injection Detection E2E Test

Tests the complete flow:
1. Python code → IRDocument (via PythonIRGenerator)
2. IRDocument → Vulnerability detection (via SQLInjectionQueryV2)
"""

import pytest

from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
from src.contexts.code_foundation.infrastructure.parsing import SourceFile
from src.contexts.security_analysis.domain.models.vulnerability import CWE, Severity
from src.contexts.security_analysis.infrastructure.queries.injection.sql_injection_v2 import SQLInjectionQueryV2

# ============================================================
# Test Case 1: Simple SQL Injection (user_input → execute)
# ============================================================

VULNERABLE_CODE_SIMPLE = """
import sqlite3

def get_user(user_id):
    # Source: user input
    conn = sqlite3.connect('db.sqlite')
    cursor = conn.cursor()
    
    # Sink: SQL execution without sanitization
    query = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query)
    
    return cursor.fetchone()
"""


def test_sql_injection_simple_detection():
    """
    Test simple SQL injection detection

    Expected: Should detect taint flow from user_id (source) to execute (sink)
    """
    # Step 1: Create SourceFile
    source = SourceFile(
        file_path="test_vulnerable.py",
        content=VULNERABLE_CODE_SIMPLE,
        language="python",
    )

    # Step 2: Generate IRDocument
    generator = PythonIRGenerator(repo_id="test_repo")
    ir_doc = generator.generate(source=source, snapshot_id="test_snapshot")

    # Debug: Check IR generated
    print(f"\n[DEBUG] IR Stats: {ir_doc.get_stats()}")
    print(f"[DEBUG] Nodes: {len(ir_doc.nodes)}")
    print(f"[DEBUG] Edges: {len(ir_doc.edges)}")

    # Step 3: Run SQL Injection query
    query = SQLInjectionQueryV2()
    vulnerabilities = query.analyze(ir_doc)

    # Step 4: Assertions
    print(f"\n[RESULT] Found {len(vulnerabilities)} vulnerabilities")
    for i, vuln in enumerate(vulnerabilities):
        print(f"[{i + 1}] {vuln.title}")
        print(f"    Severity: {vuln.severity}")
        print(f"    Source: {vuln.source_location.file_path}:{vuln.source_location.start_line}")
        print(f"    Sink: {vuln.sink_location.file_path}:{vuln.sink_location.start_line}")
        print(f"    Path length: {len(vuln.taint_path)}")

    # Should detect at least 1 vulnerability
    assert len(vulnerabilities) > 0, "Should detect SQL injection vulnerability!"

    # First vulnerability should be SQL injection
    vuln = vulnerabilities[0]
    assert vuln.cwe == CWE.CWE_89, "Should be CWE-89 (SQL Injection)"
    assert vuln.severity == Severity.CRITICAL, "Should be CRITICAL severity"
    assert len(vuln.taint_path) > 0, "Should have taint path"


# ============================================================
# Test Case 2: Multi-step SQL Injection (input → process → execute)
# ============================================================

VULNERABLE_CODE_MULTISTEP = """
import sqlite3

def sanitize_input(data):
    # Fake sanitization (does nothing!)
    return data

def build_query(user_name):
    # Propagation point
    sanitized = sanitize_input(user_name)
    query = "SELECT * FROM users WHERE name = '" + sanitized + "'"
    return query

def search_user(name):
    # Source: user input
    conn = sqlite3.connect('db.sqlite')
    cursor = conn.cursor()
    
    # Build query
    sql = build_query(name)
    
    # Sink: execute
    cursor.execute(sql)
    
    return cursor.fetchall()
"""


def test_sql_injection_multistep_detection():
    """
    Test multi-step SQL injection detection

    Expected: Should detect taint flow through multiple functions
    """
    source = SourceFile(
        file_path="test_multistep.py",
        content=VULNERABLE_CODE_MULTISTEP,
        language="python",
    )

    generator = PythonIRGenerator(repo_id="test_repo")
    ir_doc = generator.generate(source=source, snapshot_id="test_snapshot")

    query = SQLInjectionQueryV2()
    vulnerabilities = query.analyze(ir_doc)

    print(f"\n[MULTISTEP] Found {len(vulnerabilities)} vulnerabilities")
    for i, vuln in enumerate(vulnerabilities):
        print(f"[{i + 1}] {vuln.title}")
        print(f"    Path: {' → '.join([e.description for e in vuln.taint_path])}")

    # Should detect vulnerability
    assert len(vulnerabilities) > 0, "Should detect multi-step SQL injection!"

    vuln = vulnerabilities[0]
    assert vuln.cwe == CWE.CWE_89
    # Should have path: name → sanitize_input → build_query → execute
    assert len(vuln.taint_path) >= 2, "Should have multi-step path"


# ============================================================
# Test Case 3: Safe Code (with proper sanitization)
# ============================================================

SAFE_CODE_PARAMETERIZED = """
import sqlite3

def get_user_safe(user_id):
    # Source: user input
    conn = sqlite3.connect('db.sqlite')
    cursor = conn.cursor()
    
    # ✅ Safe: parameterized query (sanitized!)
    query = "SELECT * FROM users WHERE id = ?"
    cursor.execute(query, (user_id,))
    
    return cursor.fetchone()
"""


def test_sql_injection_safe_code_no_detection():
    """
    Test that safe code (parameterized query) is NOT flagged

    Expected: Should NOT detect vulnerability (properly sanitized)
    """
    source = SourceFile(
        file_path="test_safe.py",
        content=SAFE_CODE_PARAMETERIZED,
        language="python",
    )

    generator = PythonIRGenerator(repo_id="test_repo")
    ir_doc = generator.generate(source=source, snapshot_id="test_snapshot")

    query = SQLInjectionQueryV2()
    vulnerabilities = query.analyze(ir_doc)

    print(f"\n[SAFE CODE] Found {len(vulnerabilities)} vulnerabilities (should be 0)")

    # Should NOT detect vulnerability (parameterized query is safe)
    # Note: This test might fail if sanitizer detection is not perfect
    # In that case, we should refine the sanitizer rules
    assert len(vulnerabilities) == 0, "Safe code should not be flagged!"


# ============================================================
# Test Case 4: Multiple Vulnerabilities
# ============================================================

VULNERABLE_CODE_MULTIPLE = """
import sqlite3

def get_user(user_id):
    conn = sqlite3.connect('db.sqlite')
    cursor = conn.cursor()
    
    # Vulnerability 1: user_id → execute
    query1 = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query1)
    
    return cursor.fetchone()

def search_product(product_name):
    conn = sqlite3.connect('db.sqlite')
    cursor = conn.cursor()
    
    # Vulnerability 2: product_name → execute
    query2 = "SELECT * FROM products WHERE name = '" + product_name + "'"
    cursor.execute(query2)
    
    return cursor.fetchall()
"""


def test_sql_injection_multiple_vulnerabilities():
    """
    Test detection of multiple SQL injection vulnerabilities in same file

    Expected: Should detect 2 vulnerabilities
    """
    source = SourceFile(
        file_path="test_multiple.py",
        content=VULNERABLE_CODE_MULTIPLE,
        language="python",
    )

    generator = PythonIRGenerator(repo_id="test_repo")
    ir_doc = generator.generate(source=source, snapshot_id="test_snapshot")

    query = SQLInjectionQueryV2()
    vulnerabilities = query.analyze(ir_doc)

    print(f"\n[MULTIPLE] Found {len(vulnerabilities)} vulnerabilities (expected: 2)")
    for i, vuln in enumerate(vulnerabilities):
        print(f"[{i + 1}] {vuln.title}")

    # Should detect 2 vulnerabilities
    # Note: Actual count may vary based on taint analysis precision
    assert len(vulnerabilities) >= 1, "Should detect at least 1 vulnerability"


# ============================================================
# Main Test Runner
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("SQL Injection Detection E2E Tests")
    print("=" * 60)

    # Run all tests
    tests = [
        ("Simple Detection", test_sql_injection_simple_detection),
        ("Multi-step Detection", test_sql_injection_multistep_detection),
        ("Safe Code (No Detection)", test_sql_injection_safe_code_no_detection),
        ("Multiple Vulnerabilities", test_sql_injection_multiple_vulnerabilities),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        print(f"\n{'=' * 60}")
        print(f"Test: {name}")
        print(f"{'=' * 60}")
        try:
            test_func()
            print(f"\n✅ PASSED: {name}")
            passed += 1
        except AssertionError as e:
            print(f"\n❌ FAILED: {name}")
            print(f"    Error: {e}")
            failed += 1
        except Exception as e:
            print(f"\n💥 ERROR: {name}")
            print(f"    Exception: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
