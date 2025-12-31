#!/usr/bin/env python3
"""
TRCR Test Generator - 테스트 케이스 자동 생성

Usage:
  python scripts/generate_test.py \\
    --rules packages/codegraph-trcr/rules/atoms/python.atoms.yaml \\
    --output scripts/test_generated_rules.py
"""

import argparse
import yaml
from pathlib import Path
from typing import List, Dict, Any


TEST_TEMPLATE = '''#!/usr/bin/env python3
"""
Auto-generated TRCR Test Suite

Generated from: {rule_files}
Total rules: {total_rules}
"""

from trcr import TaintRuleCompiler, TaintRuleExecutor
from trcr.types.entity import MockEntity


# Rule files to test
RULE_FILES = {rule_files_list}


def test_all_rules():
    """Test all TRCR rules"""
    print("=" * 70)
    print("🔥 Auto-generated TRCR Test Suite")
    print("=" * 70)

    # Compile rules
    print("\\nCompiling rules...")
    compiler = TaintRuleCompiler()
    all_rules = []
    for rule_file in RULE_FILES:
        rules = compiler.compile_file(rule_file)
        all_rules.extend(rules)
        print(f"  ✅ {{rule_file}}: {{len(rules)}} rules")

    executor = TaintRuleExecutor(all_rules, enable_cache=False)
    print(f"\\n✅ Total compiled rules: {{len(all_rules)}}")

    # Test cases
    test_cases = {test_cases_code}

    # Run tests
    print("\\n" + "=" * 70)
    print("Test Results")
    print("=" * 70)

    passed = 0
    failed = 0

    for i, test in enumerate(test_cases, 1):
        rule_id = test['rule_id']
        entity = test['entity']

        matches = executor.execute([entity])
        matched = any(m.rule_id == rule_id for m in matches)

        if matched:
            print(f"  [{{i:3d}}] ✅ {{test['name']:<50}} → {{rule_id}}")
            passed += 1
        else:
            print(f"  [{{i:3d}}] ❌ {{test['name']:<50}} → {{rule_id}}")
            if matches:
                print(f"        Got: {{[m.rule_id for m in matches]}}")
            failed += 1

    # Summary
    print("\\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"\\nTotal: {{passed}}/{{len(test_cases)}} passed ({{failed}} failed)")

    if failed == 0:
        print("\\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\\n⚠️  {{failed}} test(s) failed")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(test_all_rules())
'''


def parse_yaml_rules(yaml_path: Path) -> List[Dict[str, Any]]:
    """Parse YAML rule file and extract rule definitions."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    if "atoms" not in data:
        return []

    return data["atoms"]


def generate_test_entity(rule: Dict[str, Any]) -> str:
    """Generate MockEntity code from rule definition."""
    rule_id = rule["id"]
    kind = rule.get("kind", "sink")

    # Get first match pattern
    matches = rule.get("match", [])
    if not matches:
        return None

    first_match = matches[0]

    # Extract pattern info
    base_type = first_match.get("base_type")
    call = first_match.get("call")
    read = first_match.get("read")
    args_spec = first_match.get("args", [])

    # Determine entity kind
    if read:
        entity_kind = "read"
        main_field = f"read='{read}'"
    elif call:
        entity_kind = "call"
        main_field = f"call='{call}'"
    else:
        return None

    # Build entity code
    entity_fields = [
        f"entity_id='{rule_id.replace('.', '_')}'",
        f"kind='{entity_kind}'",
    ]

    if base_type:
        entity_fields.append(f"base_type='{base_type}'")

    entity_fields.append(main_field)

    if args_spec and entity_kind == "call":
        entity_fields.append(f"args=['arg_value']")

    entity_code = f"MockEntity(\n            {',\\n            '.join(entity_fields)}\n        )"

    return entity_code


def generate_test_cases(rule_files: List[Path]) -> str:
    """Generate test cases code from rule files."""
    test_cases = []

    for rule_file in rule_files:
        rules = parse_yaml_rules(rule_file)

        for rule in rules:
            rule_id = rule["id"]
            entity_code = generate_test_entity(rule)

            if entity_code is None:
                continue

            # Generate test name
            name_parts = rule_id.split(".")
            test_name = " ".join(name_parts).title()

            test_case = f'''    {{
        "rule_id": "{rule_id}",
        "name": "{test_name}",
        "entity": {entity_code},
    }}'''

            test_cases.append(test_case)

    return "[\n" + ",\n".join(test_cases) + "\n]"


def main():
    parser = argparse.ArgumentParser(description="Generate TRCR test cases")
    parser.add_argument("--rules", required=True, nargs="+", help="Rule YAML files")
    parser.add_argument("--output", required=True, help="Output test file")

    args = parser.parse_args()

    # Parse rule files
    rule_files = [Path(f) for f in args.rules]
    total_rules = 0

    for rule_file in rule_files:
        if not rule_file.exists():
            print(f"❌ Rule file not found: {rule_file}")
            return 1

        rules = parse_yaml_rules(rule_file)
        total_rules += len(rules)
        print(f"✅ Parsed {rule_file}: {len(rules)} rules")

    # Generate test cases
    print("\nGenerating test cases...")
    test_cases_code = generate_test_cases(rule_files)

    # Generate test file
    test_code = TEST_TEMPLATE.format(
        rule_files=", ".join(str(f) for f in rule_files),
        total_rules=total_rules,
        rule_files_list=str([str(f) for f in rule_files]),
        test_cases_code=test_cases_code,
    )

    # Write output
    output_path = Path(args.output)
    output_path.write_text(test_code)
    print(f"\n✅ Generated test file: {output_path}")
    print(f"   Total test cases: {test_cases_code.count('rule_id')}")

    # Make executable
    output_path.chmod(0o755)

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
