#!/usr/bin/env python3
"""
TRCR 간단 테스트 - 직접 Python API 사용
"""
import sys
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent))

from trcr import TaintRuleCompiler, TaintRuleExecutor


def test_sql_injection():
    """SQL Injection 테스트"""
    print("=" * 70)
    print("🧪 Test 1: SQL Injection (CWE-089)")
    print("=" * 70)
    print()
    
    # Compile SQL injection rules
    compiler = TaintRuleCompiler()
    
    # Python SQL atoms
    atoms_file = "packages/codegraph-trcr/rules/atoms/python.atoms.yaml"
    print(f"📦 Loading rules from: {atoms_file}")
    
    try:
        executables = compiler.compile_file(atoms_file)
        print(f"✅ Compiled {len(executables)} executables")
    except Exception as e:
        print(f"❌ Compilation failed: {e}")
        return
    
    # Create executor
    executor = TaintRuleExecutor(executables, enable_cache=True)
    
    # Test vulnerable code
    test_code = """
import sqlite3

def unsafe_login(username, password):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # VULNERABLE: Direct string formatting
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    cursor.execute(query)
    
    return cursor.fetchone()
"""
    
    print("\n📝 Test code:")
    print(test_code)
    print()
    
    # Match patterns
    print("🔍 Running pattern matching...")
    matches = executor.match_patterns(test_code, "python")
    
    if matches:
        print(f"✅ Found {len(matches)} matches:")
        for match in matches:
            print(f"  - {match.rule_id}: {match.effect_kind}")
    else:
        print("❌ No matches found")
    
    print()


def test_command_injection():
    """Command Injection 테스트"""
    print("=" * 70)
    print("🧪 Test 2: Command Injection (CWE-078)")
    print("=" * 70)
    print()
    
    compiler = TaintRuleCompiler()
    atoms_file = "packages/codegraph-trcr/rules/atoms/python.atoms.yaml"
    
    try:
        executables = compiler.compile_file(atoms_file)
        executor = TaintRuleExecutor(executables)
        
        test_code = """
import os

def unsafe_ping(host):
    # VULNERABLE: os.system with user input
    result = os.system(f"ping -c 1 {host}")
    return result
"""
        
        print("📝 Test code:")
        print(test_code)
        print()
        
        print("🔍 Running pattern matching...")
        matches = executor.match_patterns(test_code, "python")
        
        if matches:
            print(f"✅ Found {len(matches)} matches:")
            for match in matches:
                print(f"  - {match.rule_id}: {match.effect_kind}")
        else:
            print("❌ No matches found")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print()


def test_codeql_rules():
    """CodeQL 룰 테스트"""
    print("=" * 70)
    print("🧪 Test 3: CodeQL Rules")
    print("=" * 70)
    print()
    
    # CodeQL SQL injection rule
    codeql_rule = "packages/codegraph-trcr/rules/atoms/codeql/python-cwe_089.yaml"
    
    if not Path(codeql_rule).exists():
        print(f"⚠️  CodeQL rule not found: {codeql_rule}")
        return
    
    print(f"📦 Loading CodeQL rule: {codeql_rule}")
    
    compiler = TaintRuleCompiler()
    
    try:
        executables = compiler.compile_file(codeql_rule)
        print(f"✅ Compiled {len(executables)} executables")
        
        executor = TaintRuleExecutor(executables)
        
        test_code = """
import sqlite3

def vulnerable_query(user_input):
    conn = sqlite3.connect('db.sqlite')
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM users WHERE id = {user_input}")
    return cursor.fetchall()
"""
        
        print("\n📝 Test code:")
        print(test_code)
        print()
        
        matches = executor.match_patterns(test_code, "python")
        
        if matches:
            print(f"✅ Found {len(matches)} matches:")
            for match in matches:
                print(f"  - {match.rule_id}: {match.effect_kind}")
        else:
            print("❌ No matches found")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print()


def main():
    print("\n")
    print("🚀 TRCR Security Rule Testing")
    print("=" * 70)
    print()
    
    # Run tests
    test_sql_injection()
    test_command_injection()
    test_codeql_rules()
    
    print("=" * 70)
    print("✅ Testing Complete")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
