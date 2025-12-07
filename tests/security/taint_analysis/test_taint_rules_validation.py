#!/usr/bin/env python3
"""
Taint Rules 비판적 검증

실제 취약점 코드 샘플로 테스트
"""

import re
import sys
from pathlib import Path

# Import rules directly
sys.path.insert(0, str(Path(__file__).parent / "src/contexts/code_foundation/infrastructure/analyzers/taint_rules"))

from base import RuleSet, Severity, VulnerabilityType
from frameworks.django import DJANGO_SANITIZERS, DJANGO_SINKS, DJANGO_SOURCES
from frameworks.flask import FLASK_SANITIZERS, FLASK_SINKS, FLASK_SOURCES
from sanitizers.python_core import PYTHON_CORE_SANITIZERS
from sinks.python_core import PYTHON_CORE_SINKS
from sources.python_core import PYTHON_CORE_SOURCES

# ============================================================
# 실제 취약점 코드 샘플
# ============================================================

VULNERABLE_SAMPLES = {
    "SQL_INJECTION": [
        # Should detect
        ("cursor.execute(f'SELECT * FROM users WHERE id={user_id}')", True, "Python f-string SQL"),
        ("User.objects.raw(f'SELECT * FROM users WHERE name={name}')", True, "Django raw SQL"),
        ("db.execute('SELECT * FROM users WHERE id=' + str(id))", True, "String concat SQL"),
        # Should NOT detect (safe)
        ("cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))", False, "Parameterized SQL"),
        ("User.objects.filter(name=user_name)", False, "Django ORM safe"),
    ],
    "COMMAND_INJECTION": [
        # Should detect
        ("os.system(f'rm -rf {path}')", True, "f-string command"),
        ("subprocess.call(cmd, shell=True)", True, "subprocess with shell=True"),
        ("os.popen(user_command)", True, "os.popen"),
        # Should NOT detect (safer)
        ("subprocess.run(['ls', '-la'])", False, "subprocess list form"),
        ("subprocess.run(cmd.split())", False, "subprocess split"),
    ],
    "CODE_INJECTION": [
        # Should detect
        ("eval(user_input)", True, "eval user input"),
        ("exec(request.get_json())", True, "exec JSON"),
        ("compile(code, '<string>', 'exec')", True, "compile"),
        # Should NOT detect
        ("eval('2 + 2')", False, "eval literal"),
    ],
    "PATH_TRAVERSAL": [
        # Should detect
        ("open(user_path, 'r')", True, "open user path"),
        ("send_file(request.args.get('file'))", True, "Flask send_file"),
        ("shutil.rmtree(directory)", True, "rmtree"),
        # Should NOT detect (sanitized)
        ("open(os.path.basename(user_path), 'r')", False, "basename sanitized"),
    ],
    "XSS": [
        # Should detect
        ("return HttpResponse(user_content)", True, "Django HttpResponse"),
        ("return make_response(request.args.get('msg'))", True, "Flask make_response"),
        ("mark_safe(user_html)", True, "Django mark_safe"),
        # Should NOT detect (sanitized)
        ("return HttpResponse(escape(user_content))", False, "Escaped content"),
    ],
    "OPEN_REDIRECT": [
        # Should detect
        ("return redirect(request.GET.get('next'))", True, "Django redirect user URL"),
        ("return flask.redirect(request.args.get('url'))", True, "Flask redirect user URL"),
        # Should NOT detect (safe)
        ("return redirect(url_for('home'))", False, "url_for redirect"),
        ("return redirect(reverse('profile'))", False, "reverse redirect"),
    ],
}

SANITIZER_EFFECTIVENESS_TESTS = [
    # (code, vuln_type, expected_min_effectiveness)
    ("html.escape(x)", VulnerabilityType.XSS, 0.9),
    ("html.escape(x)", VulnerabilityType.SQL_INJECTION, 0.0),
    ("shlex.quote(x)", VulnerabilityType.COMMAND_INJECTION, 0.9),
    ("os.path.basename(x)", VulnerabilityType.PATH_TRAVERSAL, 0.8),
    ("secure_filename(x)", VulnerabilityType.PATH_TRAVERSAL, 0.9),
    ("escape(x)", VulnerabilityType.XSS, 0.9),
    ("str.replace(';', '')", VulnerabilityType.SQL_INJECTION, 0.0),  # Too weak!
]


def validate_rules():
    """Rules 검증"""
    print("=" * 80)
    print("Taint Rules 비판적 검증")
    print("=" * 80)

    # Combine all rules
    all_rules = RuleSet(
        name="All Rules",
        description="Combined validation",
        sources=PYTHON_CORE_SOURCES + FLASK_SOURCES + DJANGO_SOURCES,
        sinks=PYTHON_CORE_SINKS + FLASK_SINKS + DJANGO_SINKS,
        sanitizers=PYTHON_CORE_SANITIZERS + FLASK_SANITIZERS + DJANGO_SANITIZERS,
    )

    stats = all_rules.get_stats()
    print("\n[Total Rules]")
    print(f"  Sources: {stats['sources']}")
    print(f"  Sinks: {stats['sinks']}")
    print(f"  Sanitizers: {stats['sanitizers']}")
    print(f"  Total: {stats['total']}")

    # Test 1: Sink Detection
    print(f"\n{'=' * 80}")
    print("Test 1: Sink Detection (실제 취약점 코드)")
    print("=" * 80)

    total_tests = 0
    passed_tests = 0
    failed_tests = []

    for vuln_type, samples in VULNERABLE_SAMPLES.items():
        print(f"\n[{vuln_type}]")
        for code, should_detect, description in samples:
            total_tests += 1

            # Check if any sink matches
            matches = [s for s in all_rules.sinks if s.matches(code)]
            detected = len(matches) > 0

            if detected == should_detect:
                status = "✅"
                passed_tests += 1
            else:
                status = "❌"
                failed_tests.append(
                    {
                        "vuln": vuln_type,
                        "code": code,
                        "expected": should_detect,
                        "got": detected,
                        "desc": description,
                    }
                )

            detect_str = "DETECT" if should_detect else "IGNORE"
            result_str = "detected" if detected else "ignored"
            print(f"  {status} [{detect_str}] {description:30} → {result_str}")
            if matches and detected != should_detect:
                print(f"      Matched: {[m.pattern for m in matches]}")

    # Test 2: Sanitizer Effectiveness
    print(f"\n{'=' * 80}")
    print("Test 2: Sanitizer Effectiveness (효과성 검증)")
    print("=" * 80)

    sanitizer_tests = 0
    sanitizer_passed = 0

    for code, vuln, min_eff in SANITIZER_EFFECTIVENESS_TESTS:
        sanitizer_tests += 1

        matches = [s for s in all_rules.sanitizers if s.matches(code)]
        if matches:
            eff = matches[0].effectiveness(vuln)
            passed = eff >= min_eff

            if passed:
                status = "✅"
                sanitizer_passed += 1
            else:
                status = "❌"
                failed_tests.append(
                    {
                        "type": "sanitizer",
                        "code": code,
                        "vuln": vuln.value,
                        "expected": f">={min_eff * 100}%",
                        "got": f"{eff * 100}%",
                    }
                )

            print(f"  {status} {code:30} → {vuln.value:20} {eff * 100:3.0f}% (expect >={min_eff * 100:.0f}%)")
        else:
            print(f"  ⚠️  {code:30} → No match!")
            sanitizer_tests -= 1

    # Test 3: Regex Pattern Validation
    print(f"\n{'=' * 80}")
    print("Test 3: Regex Pattern Validation (패턴 검증)")
    print("=" * 80)

    regex_errors = []
    for source in all_rules.sources:
        try:
            re.compile(source.pattern)
        except re.error as e:
            regex_errors.append(f"Source: {source.pattern} → {e}")

    for sink in all_rules.sinks:
        try:
            re.compile(sink.pattern)
        except re.error as e:
            regex_errors.append(f"Sink: {sink.pattern} → {e}")

    for sanitizer in all_rules.sanitizers:
        try:
            re.compile(sanitizer.pattern)
        except re.error as e:
            regex_errors.append(f"Sanitizer: {sanitizer.pattern} → {e}")

    if regex_errors:
        print(f"  ❌ {len(regex_errors)} regex errors:")
        for err in regex_errors:
            print(f"    {err}")
    else:
        print(f"  ✅ All {stats['total']} patterns compile successfully")

    # Test 4: False Positives Check
    print(f"\n{'=' * 80}")
    print("Test 4: False Positives (오탐 검사)")
    print("=" * 80)

    safe_code = [
        "user = User.objects.get(id=pk)",
        "data = json.loads(text)",
        "result = int(value)",
        "name = 'constant_string'",
        "print('Hello')",
    ]

    false_positives = 0
    for code in safe_code:
        matches = [s for s in all_rules.sinks if s.matches(code)]
        if matches:
            print(f"  ⚠️  FALSE POSITIVE: '{code}' matched {len(matches)} sinks")
            false_positives += 1
        else:
            print(f"  ✅ Correctly ignored: '{code}'")

    # Final Report
    print(f"\n{'=' * 80}")
    print("최종 평가")
    print("=" * 80)

    detection_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    sanitizer_rate = (sanitizer_passed / sanitizer_tests * 100) if sanitizer_tests > 0 else 0

    print("\n[Sink Detection]")
    print(f"  Passed: {passed_tests}/{total_tests} ({detection_rate:.1f}%)")
    print(f"  Failed: {len([f for f in failed_tests if 'vuln' in f])}")

    print("\n[Sanitizer Effectiveness]")
    print(f"  Passed: {sanitizer_passed}/{sanitizer_tests} ({sanitizer_rate:.1f}%)")

    print("\n[Pattern Quality]")
    print(f"  Regex Errors: {len(regex_errors)}")
    print(f"  False Positives: {false_positives}")

    # Grade
    print("\n[종합 평가]")
    if detection_rate >= 90 and sanitizer_rate >= 80 and len(regex_errors) == 0:
        grade = "A+ (Excellent)"
    elif detection_rate >= 80 and sanitizer_rate >= 70:
        grade = "A (Good)"
    elif detection_rate >= 70 and sanitizer_rate >= 60:
        grade = "B (Acceptable)"
    else:
        grade = "C (Needs Work)"

    print(f"  Grade: {grade}")

    # Show failures
    if failed_tests:
        print(f"\n{'=' * 80}")
        print("실패한 테스트 상세")
        print("=" * 80)
        for i, fail in enumerate(failed_tests, 1):
            print(f"\n{i}. {fail.get('desc', fail.get('type', 'Unknown'))}")
            print(f"   Code: {fail.get('code', 'N/A')}")
            print(f"   Expected: {fail.get('expected', 'N/A')}")
            print(f"   Got: {fail.get('got', 'N/A')}")

    print("\n" + "=" * 80)

    return detection_rate >= 80


if __name__ == "__main__":
    success = validate_rules()
    sys.exit(0 if success else 1)
