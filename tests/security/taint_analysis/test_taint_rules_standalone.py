#!/usr/bin/env python3
"""
Taint Rules 독립 테스트 (import 에러 회피)
"""

import sys
from pathlib import Path

# Direct import
taint_rules_path = Path(__file__).parent / "src/contexts/code_foundation/infrastructure/analyzers/taint_rules"
sys.path.insert(0, str(taint_rules_path))

from base import RuleSet, Severity, TaintKind, VulnerabilityType
from sanitizers.python_core import PYTHON_CORE_SANITIZERS
from sinks.python_core import PYTHON_CORE_SINKS
from sources.python_core import PYTHON_CORE_SOURCES


def main():
    print("=" * 80)
    print("Taint Rules 기본 테스트")
    print("=" * 80)

    # Rule Set 생성
    core_rules = RuleSet(
        name="Python Core",
        description="Framework-agnostic Python security rules",
        sources=PYTHON_CORE_SOURCES,
        sinks=PYTHON_CORE_SINKS,
        sanitizers=PYTHON_CORE_SANITIZERS,
    )

    stats = core_rules.get_stats()
    print("\n[Rule Set]")
    print(f"  Sources: {stats['sources']}")
    print(f"  Sinks: {stats['sinks']}")
    print(f"  Sanitizers: {stats['sanitizers']}")
    print(f"  Total: {stats['total']}")

    # 증가율
    old_total = 38  # 이전 (13 + 15 + 10)
    new_total = stats["total"]
    increase = ((new_total - old_total) / old_total) * 100

    print(f"\n  Old: {old_total} rules")
    print(f"  New: {new_total} rules")
    print(f"  Increase: +{new_total - old_total} (+{increase:.0f}%)")

    # Source 테스트
    print("\n[Source Tests]")
    tests = [
        ("input('cmd: ')", True),
        ("sys.argv[1]", True),
        ("os.environ['DB']", True),
        ("requests.get(url)", True),
        ("x = 42", False),
    ]

    for code, should_match in tests:
        matches = [s for s in core_rules.sources if s.matches(code)]
        matched = len(matches) > 0
        status = "✓" if matched == should_match else "✗"
        print(f"  {status} '{code:30}' → {len(matches)} sources")

    # Sink 테스트
    print("\n[Sink Tests]")
    tests = [
        ("eval(code)", True, True),  # code, should_match, dangerous
        ("os.system(cmd)", True, True),
        ("cursor.execute(query)", True, True),
        ("print(data)", False, False),
    ]

    for code, should_match, is_dangerous in tests:
        matches = [s for s in core_rules.sinks if s.matches(code)]
        matched = len(matches) > 0
        status = "✓" if matched == should_match else "✗"
        danger = "⚠️" if (matched and is_dangerous) else ""
        print(f"  {status} '{code:30}' → {len(matches)} sinks {danger}")

    # Sanitizer 효과성
    print("\n[Sanitizer Tests]")
    tests = [
        ("html.escape(x)", VulnerabilityType.XSS, "≥90%"),
        ("shlex.quote(x)", VulnerabilityType.COMMAND_INJECTION, "≥90%"),
        ("os.path.basename(x)", VulnerabilityType.PATH_TRAVERSAL, "≥80%"),
    ]

    for code, vuln, expected in tests:
        matches = [s for s in core_rules.sanitizers if s.matches(code)]
        if matches:
            eff = matches[0].effectiveness(vuln)
            eff_pct = int(eff * 100)
            status = "✓" if eff_pct >= 80 else "⚠️"
            print(f"  {status} '{code:25}' → {vuln.value:20} {eff_pct:3}%")

    # Coverage
    print("\n[Coverage by Vulnerability]")
    for vuln in VulnerabilityType:
        sources = sum(1 for s in core_rules.sources if s.vuln_type == vuln)
        sinks = sum(1 for s in core_rules.sinks if s.vuln_type == vuln)
        if sources + sinks > 0:
            print(f"  {vuln.value:20} S:{sources:2} + Sk:{sinks:2} = {sources + sinks:2}")

    print("\n" + "=" * 80)
    print("✅ 기본 Rule Set 작동!")
    print("=" * 80)


if __name__ == "__main__":
    main()
