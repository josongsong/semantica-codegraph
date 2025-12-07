#!/usr/bin/env python3
"""
Taint Rules v2.0 비판적 검증

새로 추가된 기능들 테스트:
1. Rule ID & Version tracking
2. Config system
3. IR-based matching
4. Metrics
5. CWE matrix auto-fill
6. Profiles
"""

import sys
from pathlib import Path

# Direct path setup
sys.path.insert(0, str(Path(__file__).parent / "src/contexts/code_foundation/infrastructure/analyzers/taint_rules"))

from base import (
    VULN_CWE_MATRIX,
    MatchKind,
    SanitizerRule,
    Severity,
    SinkRule,
    SourceRule,
    TaintKind,
    TaintRule,
    VulnerabilityType,
)
from metrics import MetricsCollector, RuleHit

from config import RuleSetConfig, TaintConfig, load_profile


def test_rule_id_and_version():
    """Test 1: Rule ID & Version Tracking"""
    print("=" * 80)
    print("Test 1: Rule ID & Version Tracking")
    print("=" * 80)

    try:
        rule = SourceRule(
            id="PY_CORE_SOURCE_001",
            pattern=r"\binput\s*\(",
            description="User input",
            severity=Severity.HIGH,
            vuln_type=VulnerabilityType.CODE_INJECTION,
            taint_kind=TaintKind.USER_INPUT,
            version_introduced="v1.1",
            tags=["python", "core", "user_input"],
        )

        print(f"✅ Rule created with ID: {rule.id}")
        print(f"   Version: {rule.version_introduced}")
        print(f"   Tags: {rule.tags}")
        print(f"   CWE (auto): {rule.cwe_id}")

        # Test ID validation warning
        try:
            bad_rule = SourceRule(
                id="bad-id-format",  # Should warn
                pattern=r"test",
                description="Test",
                severity=Severity.LOW,
                vuln_type=VulnerabilityType.XSS,
            )
            print("⚠️  Bad ID format accepted (should warn)")
        except Exception as e:
            print(f"✅ Bad ID rejected: {e}")

        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_cwe_auto_fill():
    """Test 2: CWE Matrix Auto-fill"""
    print("\n" + "=" * 80)
    print("Test 2: CWE Matrix Auto-fill")
    print("=" * 80)

    try:
        # Create rule WITHOUT cwe_id
        rule = SinkRule(
            id="TEST_SINK_001",
            pattern=r"eval",
            description="Code eval",
            severity=Severity.CRITICAL,
            vuln_type=VulnerabilityType.CODE_INJECTION,
            # NO cwe_id provided!
        )

        expected_cwe = VULN_CWE_MATRIX[VulnerabilityType.CODE_INJECTION]["primary_cwe"]

        if rule.cwe_id == expected_cwe:
            print(f"✅ CWE auto-filled: {rule.cwe_id}")
        else:
            print(f"❌ CWE mismatch: got {rule.cwe_id}, expected {expected_cwe}")
            return False

        # Test all vulnerability types
        print("\n[CWE Matrix Coverage]")
        for vuln_type in VulnerabilityType:
            if vuln_type in VULN_CWE_MATRIX:
                cwe = VULN_CWE_MATRIX[vuln_type]["primary_cwe"]
                severity = VULN_CWE_MATRIX[vuln_type]["severity_default"]
                print(f"  ✅ {vuln_type.value:20} → {cwe:10} ({severity.value})")
            else:
                print(f"  ⚠️  {vuln_type.value:20} → NOT IN MATRIX")

        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_enabled_flag():
    """Test 3: Enabled Flag & Hit Count"""
    print("\n" + "=" * 80)
    print("Test 3: Enabled Flag & Hit Count")
    print("=" * 80)

    try:
        rule = SinkRule(
            id="TEST_SINK_002",
            pattern=r"os\.system",
            description="Command injection",
            severity=Severity.CRITICAL,
            vuln_type=VulnerabilityType.COMMAND_INJECTION,
            enabled=True,
        )

        # Test matching when enabled
        code1 = "os.system(cmd)"
        matched = rule.matches(code1)
        print(f"✅ Enabled rule matched: {matched}")
        print(f"   Hit count: {rule.hit_count}")

        if rule.hit_count != 1:
            print(f"❌ Hit count should be 1, got {rule.hit_count}")
            return False

        # Disable and test
        rule.enabled = False
        code2 = "os.system(another_cmd)"
        matched2 = rule.matches(code2)

        if matched2:
            print("❌ Disabled rule still matched!")
            return False
        else:
            print("✅ Disabled rule correctly ignored")
            print(f"   Hit count unchanged: {rule.hit_count}")

        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_config_system():
    """Test 4: Config System"""
    print("\n" + "=" * 80)
    print("Test 4: Config System")
    print("=" * 80)

    try:
        # Create config programmatically
        config = TaintConfig(
            enabled=True,
            max_path_length=50,
            rule_sets=[
                RuleSetConfig(name="python_core", enabled=True),
                RuleSetConfig(name="flask", enabled=False),
            ],
            rule_overrides={
                "PY_CORE_SINK_001": {
                    "enabled": False,
                    "reason": "Too noisy",
                }
            },
        )

        print("✅ Config created")
        print(f"   Enabled: {config.enabled}")
        print(f"   RuleSets: {len(config.rule_sets)}")

        # Test checks
        assert config.is_rule_set_enabled("python_core") == True
        print("✅ python_core enabled: True")

        assert config.is_rule_set_enabled("flask") == False
        print("✅ flask enabled: False")

        # Test to_dict
        data = config.to_dict()
        print(f"✅ Config serializable: {len(data['taint'])} keys")

        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_profiles():
    """Test 5: Pre-defined Profiles"""
    print("\n" + "=" * 80)
    print("Test 5: Pre-defined Profiles")
    print("=" * 80)

    try:
        profiles = ["strict", "performance", "frontend", "backend"]

        for profile_name in profiles:
            config = load_profile(profile_name)
            print(f"✅ {profile_name:15} → {len(config.rule_sets)} rule sets")

        # Test invalid profile
        try:
            bad = load_profile("invalid")
            print("❌ Invalid profile should raise error")
            return False
        except ValueError as e:
            print("✅ Invalid profile correctly rejected")

        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_metrics_collector():
    """Test 6: Metrics Collector"""
    print("\n" + "=" * 80)
    print("Test 6: Metrics Collector")
    print("=" * 80)

    try:
        collector = MetricsCollector()

        # Record some hits
        collector.record_hit("PY_CORE_SINK_001", "app.py", 42, "myapp")
        collector.record_hit("PY_CORE_SINK_001", "app.py", 50, "myapp")
        collector.record_hit("PY_CORE_SINK_002", "util.py", 10, "myapp")

        print("✅ Recorded 3 hits")

        # Get metrics
        metrics = collector.get_metrics("PY_CORE_SINK_001")

        if metrics.total_hits != 2:
            print(f"❌ Expected 2 hits, got {metrics.total_hits}")
            return False

        print(f"✅ Metrics: {metrics.total_hits} hits, {len(metrics.files_affected)} files")

        # Mark false positive
        collector.mark_false_positive("PY_CORE_SINK_001", "app.py", 42, "Not real issue")

        metrics = collector.get_metrics("PY_CORE_SINK_001")
        if metrics.false_positive_count != 1:
            print(f"❌ Expected 1 FP, got {metrics.false_positive_count}")
            return False

        print(f"✅ False positive marked: {metrics.false_positive_count}")

        # Test noisy rules
        # Need 30%+ FP rate
        for i in range(3):
            collector.record_hit("NOISY_RULE", "test.py", i, "test")
            collector.mark_false_positive("NOISY_RULE", "test.py", i)

        noisy = collector.get_noisy_rules(threshold=0.5)
        print(f"✅ Noisy rules detected: {len(noisy)}")

        # Test heatmap
        heatmap = collector.get_coverage_heatmap()
        print(f"✅ Coverage heatmap: {len(heatmap)} projects")

        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_match_kind():
    """Test 7: Match Kind (IR-based matching)"""
    print("\n" + "=" * 80)
    print("Test 7: Match Kind (IR-based matching)")
    print("=" * 80)

    try:
        # Create rule with CALL_NAME matching
        rule = SinkRule(
            id="TEST_SINK_003",
            pattern=r"eval",  # Fallback regex
            description="Eval call",
            severity=Severity.CRITICAL,
            vuln_type=VulnerabilityType.CODE_INJECTION,
            match_kind=MatchKind.CALL_NAME,
            target_name="eval",
        )

        print(f"✅ Rule with match_kind: {rule.match_kind.value}")
        print(f"   Target: {rule.target_name}")

        # Create mock IR node
        class MockNode:
            def __init__(self, call_name=None, name=None):
                self.call_name = call_name
                self.name = name

        # Should match by call_name
        node1 = MockNode(call_name="eval")
        matched = rule.matches_ir_node(node1)

        if not matched:
            print("❌ Should match by call_name")
            return False

        print("✅ IR-based match (CALL_NAME) works")
        print(f"   Hit count: {rule.hit_count}")

        # Should not match
        node2 = MockNode(call_name="print")
        matched2 = rule.matches_ir_node(node2)

        if matched2:
            print("❌ Should not match 'print'")
            return False

        print("✅ IR-based non-match works")

        # Test MatchKind enum
        print("\n[Available Match Kinds]")
        for kind in MatchKind:
            print(f"  - {kind.value}")

        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("Taint Rules v2.0 - 비판적 검증")
    print("=" * 80)

    tests = [
        ("Rule ID & Version", test_rule_id_and_version),
        ("CWE Auto-fill", test_cwe_auto_fill),
        ("Enabled Flag & Hit Count", test_enabled_flag),
        ("Config System", test_config_system),
        ("Profiles", test_profiles),
        ("Metrics Collector", test_metrics_collector),
        ("Match Kind (IR-based)", test_match_kind),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ Test crashed: {name}")
            print(f"   Error: {e}")
            import traceback

            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 80)
    print("종합 평가")
    print("=" * 80)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    print("\n[Results]")
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status:10} {name}")

    print(f"\nTotal: {passed}/{total} ({passed / total * 100:.0f}%)")

    if passed == total:
        print("\n🎉 모든 테스트 통과! v2.0 완벽!")
        return True
    else:
        print(f"\n⚠️  {total - passed}개 테스트 실패")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
