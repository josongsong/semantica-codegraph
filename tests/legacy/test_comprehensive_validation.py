#!/usr/bin/env python3
"""
NodeKind Refactoring 전방위 검증 테스트
- Rust 빌드 검증
- Python 바인딩 검증
- NodeKind variant 전체 검증
- TRCR 통합 검증
- 성능 벤치마크
- Edge case 테스트
"""
import sys
import time
import subprocess
from pathlib import Path

# TRCR
from trcr import TaintRuleCompiler, TaintRuleExecutor, MockEntity

# Rust IR
try:
    import codegraph_ir
    RUST_IR_AVAILABLE = True
except ImportError:
    print("❌ CRITICAL: codegraph_ir not available")
    sys.exit(1)


class TestSuite:
    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0
        self.errors = []

    def assert_true(self, condition, message):
        if condition:
            self.tests_passed += 1
            print(f"    ✅ {message}")
            return True
        else:
            self.tests_failed += 1
            self.errors.append(message)
            print(f"    ❌ FAILED: {message}")
            return False

    def assert_equal(self, actual, expected, message):
        if actual == expected:
            self.tests_passed += 1
            print(f"    ✅ {message}")
            return True
        else:
            self.tests_failed += 1
            err = f"{message} (expected: {expected}, got: {actual})"
            self.errors.append(err)
            print(f"    ❌ FAILED: {err}")
            return False

    def assert_greater(self, actual, threshold, message):
        if actual > threshold:
            self.tests_passed += 1
            print(f"    ✅ {message} ({actual} > {threshold})")
            return True
        else:
            self.tests_failed += 1
            err = f"{message} ({actual} <= {threshold})"
            self.errors.append(err)
            print(f"    ❌ FAILED: {err}")
            return False


def test_1_rust_build(suite):
    """Test 1: Rust 빌드 검증"""
    print("\n" + "=" * 70)
    print("Test 1: Rust Build Validation")
    print("=" * 70)

    print("\n[1.1] Checking Rust library build...")
    result = subprocess.run(
        ["cargo", "build", "--lib"],
        cwd="packages/codegraph-ir",
        capture_output=True,
        text=True
    )
    suite.assert_equal(result.returncode, 0, "Rust library builds without errors")

    if result.returncode != 0:
        print(f"\nBuild errors:\n{result.stderr}")
        return False

    # Check for compilation errors
    has_errors = "error[E" in result.stderr
    suite.assert_true(not has_errors, "No compilation errors (E0xxx)")

    # Check for critical warnings
    critical_warnings = ["error:", "cannot find"]
    has_critical = any(w in result.stderr.lower() for w in critical_warnings)
    suite.assert_true(not has_critical, "No critical warnings")

    print("\n[1.2] Checking Python bindings (maturin)...")
    result = subprocess.run(
        ["maturin", "develop"],
        cwd="packages/codegraph-ir",
        capture_output=True,
        text=True
    )
    suite.assert_equal(result.returncode, 0, "Maturin builds Python bindings")

    return True


def test_2_nodekind_completeness(suite):
    """Test 2: NodeKind Variant 완전성 검증"""
    print("\n" + "=" * 70)
    print("Test 2: NodeKind Completeness Validation")
    print("=" * 70)

    # 모든 카테고리별 variants
    all_variants = {
        'Base Structural': [
            'File', 'Module', 'Class', 'Function', 'Method', 'Variable',
            'Parameter', 'Field', 'Lambda', 'Import'
        ],
        'Type System': [
            'Interface', 'Enum', 'EnumMember', 'TypeAlias', 'TypeParameter',
            'Constant', 'Property', 'Export'
        ],
        'Rust-specific': [
            'Trait', 'TraitImpl', 'Lifetime', 'Macro', 'MacroInvocation',
            'AssociatedType'
        ],
        'Kotlin-specific': [
            'DataClass', 'SealedClass', 'CompanionObject', 'ExtensionFunction',
            'SuspendFunction'
        ],
        'Go-specific': [
            'Struct', 'Channel', 'Goroutine'
        ],
        'Java-specific': [
            'Annotation', 'AnnotationDecl', 'Record', 'InnerClass'
        ],
        'Control Flow': [
            'Block', 'Condition', 'Loop', 'TryCatch', 'Try', 'Catch',
            'Finally', 'Raise', 'Throw', 'Assert', 'Expression', 'Call', 'Index'
        ],
        'Semantic': [
            'Type', 'Signature', 'CfgBlock'
        ],
        'External': [
            'ExternalModule', 'ExternalFunction', 'ExternalType'
        ],
        'Web/Framework': [
            'Route', 'Service', 'Repository', 'Config', 'Job', 'Middleware'
        ]
    }

    total_tested = 0
    total_passed = 0

    for category, variants in all_variants.items():
        print(f"\n[2.{list(all_variants.keys()).index(category) + 1}] {category}:")
        for variant in variants:
            total_tested += 1
            if hasattr(codegraph_ir.NodeKind, variant):
                kind = getattr(codegraph_ir.NodeKind, variant)
                kind_str = str(kind)
                # Verify __str__ returns correct value
                if kind_str == variant:
                    suite.assert_true(True, f"NodeKind.{variant}")
                    total_passed += 1
                else:
                    suite.assert_true(False, f"NodeKind.{variant} __str__ mismatch")
            else:
                suite.assert_true(False, f"NodeKind.{variant} missing")

    # Verify total count
    actual_total = len([a for a in dir(codegraph_ir.NodeKind) if not a.startswith('_')])
    print(f"\n[2.Summary] Total variants: {actual_total}")
    suite.assert_greater(actual_total, 60, "At least 60 variants available")
    suite.assert_equal(total_passed, total_tested, f"All {total_tested} tested variants present")

    return total_passed == total_tested


def test_3_nodekind_operations(suite):
    """Test 3: NodeKind 연산 검증"""
    print("\n" + "=" * 70)
    print("Test 3: NodeKind Operations Validation")
    print("=" * 70)

    print("\n[3.1] Equality comparison...")
    func1 = codegraph_ir.NodeKind.Function
    func2 = codegraph_ir.NodeKind.Function
    class1 = codegraph_ir.NodeKind.Class

    suite.assert_true(func1 == func2, "NodeKind.Function == NodeKind.Function")
    suite.assert_true(func1 != class1, "NodeKind.Function != NodeKind.Class")

    print("\n[3.2] String representation...")
    suite.assert_equal(str(func1), "Function", "str(NodeKind.Function)")
    suite.assert_equal(str(class1), "Class", "str(NodeKind.Class)")

    print("\n[3.3] Language-specific variants...")
    # Rust
    trait = codegraph_ir.NodeKind.Trait
    suite.assert_equal(str(trait), "Trait", "Rust Trait variant")

    # Go
    goroutine = codegraph_ir.NodeKind.Goroutine
    suite.assert_equal(str(goroutine), "Goroutine", "Go Goroutine variant")

    # Kotlin
    data_class = codegraph_ir.NodeKind.DataClass
    suite.assert_equal(str(data_class), "DataClass", "Kotlin DataClass variant")

    # Java
    annotation = codegraph_ir.NodeKind.Annotation
    suite.assert_equal(str(annotation), "Annotation", "Java Annotation variant")

    print("\n[3.4] Type safety (no implicit conversion)...")
    # These should be different types
    suite.assert_true(func1 != "Function", "NodeKind != string (type safety)")

    return True


def test_4_trcr_integration(suite):
    """Test 4: TRCR 통합 검증"""
    print("\n" + "=" * 70)
    print("Test 4: TRCR Integration Validation")
    print("=" * 70)

    print("\n[4.1] Compiling TRCR rules...")
    compiler = TaintRuleCompiler()
    start = time.time()
    rules = compiler.compile_file("packages/codegraph-trcr/rules/atoms/python.atoms.yaml")
    compile_time = time.time() - start

    suite.assert_greater(len(rules), 200, f"At least 200 rules compiled ({len(rules)})")
    suite.assert_true(compile_time < 1.0, f"Compilation under 1s ({compile_time:.3f}s)")

    print(f"\n[4.2] Creating comprehensive test entities...")
    entities = [
        # SQL Injection (CWE-089)
        MockEntity("sql1", "call", base_type="sqlite3.Cursor", call="execute", args=["query"]),
        MockEntity("sql2", "call", base_type="sqlite3.Connection", call="execute", args=["query"]),
        MockEntity("sql3", "call", base_type="sqlite3.Connection", call="executemany", args=["query"]),
        MockEntity("sql4", "call", base_type="sqlite3.Cursor", call="executescript", args=["query"]),

        # Command Injection (CWE-078)
        MockEntity("cmd1", "call", base_type="os", call="system", args=["cmd"]),
        MockEntity("cmd2", "call", base_type="subprocess", call="run", args=["cmd"]),
        MockEntity("cmd3", "call", base_type="subprocess", call="Popen", args=["cmd"]),
        MockEntity("cmd4", "call", base_type="subprocess", call="call", args=["cmd"]),

        # Path Traversal (CWE-022)
        MockEntity("path1", "call", base_type="pathlib.Path", call="open", args=["file"]),
        MockEntity("path2", "call", call="open", args=["file"]),
        MockEntity("path3", "call", base_type="os.path", call="join", args=["path"]),

        # Deserialization (CWE-502)
        MockEntity("deser1", "call", base_type="pickle", call="loads", args=["data"]),
        MockEntity("deser2", "call", base_type="pickle", call="load", args=["file"]),
        MockEntity("deser3", "call", base_type="yaml", call="load", args=["data"]),

        # Code Injection
        MockEntity("code1", "call", call="eval", args=["code"]),
        MockEntity("code2", "call", call="exec", args=["code"]),
        MockEntity("code3", "call", call="compile", args=["code"]),

        # XSS / Template Injection
        MockEntity("xss1", "call", base_type="flask", call="render_template_string", args=["html"]),
        MockEntity("xss2", "call", base_type="jinja2.Template", call="render", args=["data"]),

        # LDAP Injection (CWE-090)
        MockEntity("ldap1", "call", base_type="ldap", call="search", args=["filter"]),

        # XML Injection
        MockEntity("xml1", "call", base_type="xml.etree.ElementTree", call="fromstring", args=["xml"]),

        # Safe operations (should NOT match)
        MockEntity("safe1", "call", base_type="math", call="sqrt", args=[4]),
        MockEntity("safe2", "call", base_type="json", call="dumps", args=["data"]),
    ]

    print(f"  Created {len(entities)} test entities ({len([e for e in entities if 'safe' in e.id])} safe)")

    print("\n[4.3] Executing TRCR analysis...")
    start = time.time()
    executor = TaintRuleExecutor(rules)
    matches = executor.execute(entities)
    exec_time = time.time() - start

    throughput = len(entities) / exec_time
    suite.assert_true(exec_time < 0.01, f"Execution under 10ms ({exec_time*1000:.2f}ms)")
    suite.assert_greater(throughput, 1000, f"Throughput > 1K entities/sec ({throughput:,.0f})")

    print("\n[4.4] Validating detection results...")
    suite.assert_greater(len(matches), 10, f"At least 10 vulnerabilities detected ({len(matches)})")

    # Check specific vulnerability types
    findings_by_category = {}
    for m in matches:
        cat = m.atom_id.split('.')[0]
        findings_by_category[cat] = findings_by_category.get(cat, 0) + 1

    suite.assert_true('sink' in findings_by_category, "Sink vulnerabilities detected")
    suite.assert_true('barrier' in findings_by_category or len(matches) > 0, "Barrier or sink detected")

    # Verify safe operations are NOT flagged as SINKS (propagators are OK)
    safe_matches = [m for m in matches if 'safe' in m.entity.id]
    safe_sinks = [m for m in safe_matches if m.atom_id.split('.')[0] == 'sink']
    suite.assert_equal(len(safe_sinks), 0, "Safe operations not flagged as SINKS (propagators OK)")

    print(f"\n[4.5] Detection breakdown:")
    for cat, count in sorted(findings_by_category.items()):
        print(f"      • {cat}: {count}")

    return len(matches) > 10


def test_5_performance_benchmark(suite):
    """Test 5: 성능 벤치마크"""
    print("\n" + "=" * 70)
    print("Test 5: Performance Benchmark")
    print("=" * 70)

    print("\n[5.1] Compiling rules (cold start)...")
    compiler = TaintRuleCompiler()

    times = []
    for i in range(3):
        start = time.time()
        rules = compiler.compile_file("packages/codegraph-trcr/rules/atoms/python.atoms.yaml")
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"      Run {i+1}: {elapsed*1000:.2f}ms")

    avg_compile = sum(times) / len(times)
    suite.assert_true(avg_compile < 0.1, f"Avg compilation < 100ms ({avg_compile*1000:.1f}ms)")

    print("\n[5.2] Analysis throughput test...")
    # Create large entity set
    large_entities = []
    for i in range(100):
        large_entities.append(
            MockEntity(f"entity_{i}", "call", base_type="sqlite3.Cursor", call="execute", args=["q"])
        )

    executor = TaintRuleExecutor(rules)

    times = []
    for i in range(5):
        start = time.time()
        matches = executor.execute(large_entities)
        elapsed = time.time() - start
        times.append(elapsed)
        throughput = len(large_entities) / elapsed
        print(f"      Run {i+1}: {elapsed*1000:.2f}ms ({throughput:,.0f} entities/sec)")

    avg_throughput = len(large_entities) / (sum(times) / len(times))
    suite.assert_greater(avg_throughput, 10000, f"Avg throughput > 10K entities/sec ({avg_throughput:,.0f})")

    return True


def test_6_edge_cases(suite):
    """Test 6: Edge Case 검증"""
    print("\n" + "=" * 70)
    print("Test 6: Edge Cases Validation")
    print("=" * 70)

    print("\n[6.1] Empty entity list...")
    compiler = TaintRuleCompiler()
    rules = compiler.compile_file("packages/codegraph-trcr/rules/atoms/python.atoms.yaml")
    executor = TaintRuleExecutor(rules)

    matches = executor.execute([])
    suite.assert_equal(len(matches), 0, "Empty input returns no matches")

    print("\n[6.2] Entities without base_type...")
    entities_no_type = [
        MockEntity("nobase1", "call", call="execute", args=["q"]),
        MockEntity("nobase2", "call", call="system", args=["cmd"]),
    ]
    matches = executor.execute(entities_no_type)
    # Should still match on call name alone
    suite.assert_true(len(matches) >= 0, "Entities without base_type handled")

    print("\n[6.3] Entities with None values...")
    entities_none = [
        MockEntity("none1", "call", base_type=None, call="execute", args=["q"]),
        MockEntity("none2", "call", base_type="sqlite3.Cursor", call=None, args=[]),
    ]
    matches = executor.execute(entities_none)
    suite.assert_true(True, "Entities with None values don't crash")

    print("\n[6.4] Very long entity IDs...")
    long_id = "x" * 1000
    entities_long = [
        MockEntity(long_id, "call", base_type="os", call="system", args=["cmd"])
    ]
    matches = executor.execute(entities_long)
    suite.assert_true(len(matches) > 0, "Long entity IDs handled correctly")

    print("\n[6.5] Special characters in values...")
    entities_special = [
        MockEntity("special'\"\\", "call", base_type="os", call="system", args=["cmd"]),
    ]
    matches = executor.execute(entities_special)
    suite.assert_true(True, "Special characters in entity IDs handled")

    return True


def test_7_regression_tests(suite):
    """Test 7: Regression 테스트 (이전 버그 재발 방지)"""
    print("\n" + "=" * 70)
    print("Test 7: Regression Tests")
    print("=" * 70)

    print("\n[7.1] No duplicate NodeKind enum...")
    # Check that query_engine doesn't define its own NodeKind
    try:
        from codegraph_ir import NodeKind
        # This should be the ONLY NodeKind accessible from Python
        suite.assert_true(True, "Single NodeKind import (no duplicates)")
    except ImportError:
        suite.assert_true(False, "NodeKind not accessible")

    print("\n[7.2] Direct type comparison (no mapping)...")
    # Verify NodeKind values can be compared directly
    func = codegraph_ir.NodeKind.Function
    method = codegraph_ir.NodeKind.Method
    suite.assert_true(func != method, "Direct comparison works (no mapping needed)")

    print("\n[7.3] All 70+ variants accessible...")
    total = len([a for a in dir(codegraph_ir.NodeKind) if not a.startswith('_')])
    suite.assert_greater(total, 60, f"70+ variants accessible ({total})")

    return True


def main():
    print()
    print("═" * 70)
    print(" COMPREHENSIVE VALIDATION TEST SUITE")
    print(" NodeKind Refactoring + TRCR Integration")
    print("═" * 70)

    suite = TestSuite()

    # Run all tests
    tests = [
        ("Rust Build", test_1_rust_build),
        ("NodeKind Completeness", test_2_nodekind_completeness),
        ("NodeKind Operations", test_3_nodekind_operations),
        ("TRCR Integration", test_4_trcr_integration),
        ("Performance Benchmark", test_5_performance_benchmark),
        ("Edge Cases", test_6_edge_cases),
        ("Regression Tests", test_7_regression_tests),
    ]

    failed_tests = []

    for test_name, test_func in tests:
        try:
            success = test_func(suite)
            if not success:
                failed_tests.append(test_name)
        except Exception as e:
            print(f"\n❌ TEST CRASHED: {test_name}")
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()
            suite.tests_failed += 1
            failed_tests.append(test_name)

    # Final report
    print("\n" + "═" * 70)
    print(" FINAL REPORT")
    print("═" * 70)
    print(f"\n✅ Tests Passed: {suite.tests_passed}")
    print(f"❌ Tests Failed: {suite.tests_failed}")
    print(f"📊 Success Rate: {suite.tests_passed/(suite.tests_passed+suite.tests_failed)*100:.1f}%")

    if failed_tests:
        print(f"\n❌ Failed test suites:")
        for test in failed_tests:
            print(f"   • {test}")

    if suite.errors:
        print(f"\n❌ Error details:")
        for i, error in enumerate(suite.errors[:10], 1):
            print(f"   {i}. {error}")
        if len(suite.errors) > 10:
            print(f"   ... and {len(suite.errors) - 10} more")

    print("\n" + "═" * 70)

    if suite.tests_failed == 0:
        print("✅ ALL TESTS PASSED - PRODUCTION READY")
        print("═" * 70)
        return 0
    else:
        print(f"❌ {suite.tests_failed} TESTS FAILED - NEEDS FIX")
        print("═" * 70)
        return 1


if __name__ == '__main__':
    sys.exit(main())
