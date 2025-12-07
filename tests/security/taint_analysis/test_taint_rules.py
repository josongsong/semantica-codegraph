#!/usr/bin/env python3
"""
Taint Rules 기본 테스트
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.contexts.code_foundation.infrastructure.analyzers.taint_rules import (
    VulnerabilityType,
    Severity,
    TaintKind,
    RuleSet,
)
from src.contexts.code_foundation.infrastructure.analyzers.taint_rules.sources import PYTHON_CORE_SOURCES
from src.contexts.code_foundation.infrastructure.analyzers.taint_rules.sinks import PYTHON_CORE_SINKS
from src.contexts.code_foundation.infrastructure.analyzers.taint_rules.sanitizers import PYTHON_CORE_SANITIZERS


def test_basic_rules():
    """기본 Rule 로딩 테스트"""
    print("=" * 80)
    print("Taint Rules 기본 테스트")
    print("=" * 80)

    # 1. Rule Set 생성
    core_rules = RuleSet(
        name="Python Core",
        description="Framework-agnostic Python security rules",
        sources=PYTHON_CORE_SOURCES,
        sinks=PYTHON_CORE_SINKS,
        sanitizers=PYTHON_CORE_SANITIZERS,
    )

    stats = core_rules.get_stats()
    print(f"\n[Rule Set Stats]")
    print(f"  Name: {stats['name']}")
    print(f"  Sources: {stats['sources']}")
    print(f"  Sinks: {stats['sinks']}")
    print(f"  Sanitizers: {stats['sanitizers']}")
    print(f"  Total: {stats['total']}")

    # 2. Source 매칭 테스트
    print(f"\n[Source Matching]")
    test_sources = [
        "user_input = input('Enter command: ')",
        "db_host = os.environ['DB_HOST']",
        "data = requests.get(url).json()",
        "normal_var = 42",  # Should not match
    ]

    for code in test_sources:
        matches = [s for s in core_rules.sources if s.matches(code)]
        if matches:
            print(f"  ✓ '{code[:50]}...'")
            for m in matches:
                print(f"    → {m.description} ({m.severity.value})")
        else:
            print(f"  ✗ '{code[:50]}...' (no match)")

    # 3. Sink 매칭 테스트
    print(f"\n[Sink Matching]")
    test_sinks = [
        "os.system(f'rm -rf {path}')",
        "eval(user_code)",
        "cursor.execute(f'SELECT * FROM users WHERE id={id}')",
        "cursor.execute('SELECT * FROM users WHERE id=?', (id,))",  # Safe
    ]

    for code in test_sinks:
        matches = [s for s in core_rules.sinks if s.matches(code)]
        if matches:
            print(f"  ✓ '{code[:50]}...'")
            for m in matches:
                safe = m.is_safe_usage(code)
                safety = " [SAFE USAGE]" if safe else " [DANGEROUS!]"
                print(f"    → {m.description} ({m.severity.value}){safety}")
        else:
            print(f"  ✗ '{code[:50]}...' (no match)")

    # 4. Sanitizer 효과성 테스트
    print(f"\n[Sanitizer Effectiveness]")
    test_sanitizers = [
        ("html.escape(user_input)", VulnerabilityType.XSS),
        ("html.escape(user_input)", VulnerabilityType.SQL_INJECTION),
        ("shlex.quote(cmd)", VulnerabilityType.COMMAND_INJECTION),
        ("os.path.basename(path)", VulnerabilityType.PATH_TRAVERSAL),
    ]

    for code, vuln in test_sanitizers:
        matches = [s for s in core_rules.sanitizers if s.matches(code)]
        if matches:
            for m in matches:
                eff = m.effectiveness(vuln)
                eff_pct = int(eff * 100)
                if eff >= 0.9:
                    level = "✅ Excellent"
                elif eff >= 0.7:
                    level = "✓ Good"
                elif eff >= 0.5:
                    level = "⚠️ Partial"
                else:
                    level = "❌ Weak"
                print(f"  {code[:40]:40} → {vuln.value:20} {eff_pct:3}% {level}")

    # 5. 취약점 타입별 통계
    print(f"\n[Coverage by Vulnerability Type]")
    vuln_coverage = {}
    for vuln in VulnerabilityType:
        sources = [s for s in core_rules.sources if s.vuln_type == vuln]
        sinks = [s for s in core_rules.sinks if s.vuln_type == vuln]
        if sources or sinks:
            vuln_coverage[vuln.value] = {
                "sources": len(sources),
                "sinks": len(sinks),
            }

    for vuln, counts in sorted(vuln_coverage.items()):
        print(f"  {vuln:20} Sources: {counts['sources']:2}  Sinks: {counts['sinks']:2}")

    print("\n" + "=" * 80)
    print("✅ 테스트 완료")
    print("=" * 80)


if __name__ == "__main__":
    test_basic_rules()
