#!/usr/bin/env python3
"""
CSV 데이터베이스에서 TRCR 룰 자동 생성

Usage:
  python scripts/generate_from_csv.py \\
    --csv data/trcr_rules_database.csv \\
    --output packages/codegraph-trcr/rules/atoms/extended/
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


def generate_from_csv(csv_file: Path, output_dir: Path):
    """CSV 파일에서 룰을 읽어 자동 생성"""

    # CSV 읽기
    with open(csv_file, "r") as f:
        reader = csv.DictReader(f)
        rules = list(reader)

    print(f"📊 Loaded {len(rules)} rules from {csv_file}")
    print("")

    # 카테고리별로 그룹화
    by_category: Dict[str, List[Dict[str, str]]] = {}
    for rule in rules:
        category = rule["name"].split(".")[0]  # info_leak, resource, crypto 등
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(rule)

    # 각 카테고리별로 파일 생성
    for category, category_rules in by_category.items():
        output_file = output_dir / f"python-{category}.yaml"

        print(f"📦 Generating {category} ({len(category_rules)} rules)")

        for i, rule in enumerate(category_rules, 1):
            # generate_rule.py 호출
            cmd = [
                sys.executable,
                "tools/trcr/generate_rule.py",
                "--category",
                rule["category"],
                "--name",
                rule["name"],
                "--patterns",
                rule["patterns"],
                "--severity",
                rule["severity"],
                "--output",
                str(output_file),
            ]

            # CWE 추가 (있으면)
            if rule.get("cwe"):
                cmd.extend(["--cwe", rule["cwe"]])

            # OWASP 추가 (있으면)
            if rule.get("owasp"):
                cmd.extend(["--owasp", rule["owasp"]])

            # Description 추가 (있으면)
            if rule.get("description"):
                cmd.extend(["--description", rule["description"]])

            # 실행
            result = subprocess.run(cmd, capture_output=True, text=True, env={"PYTHONPATH": "."})

            if result.returncode != 0:
                print(f"  ❌ [{i}/{len(category_rules)}] {rule['name']}")
                print(f"      Error: {result.stderr}")
            else:
                print(f"  ✅ [{i}/{len(category_rules)}] {rule['name']}")

        print(f"  → Saved to {output_file}")
        print("")

    print(f"✅ Generated {len(rules)} rules in {len(by_category)} files")


def main():
    parser = argparse.ArgumentParser(description="Generate TRCR rules from CSV")
    parser.add_argument("--csv", required=True, help="CSV file with rule definitions")
    parser.add_argument("--output", required=True, help="Output directory for YAML files")

    args = parser.parse_args()

    csv_file = Path(args.csv)
    output_dir = Path(args.output)

    if not csv_file.exists():
        print(f"❌ CSV file not found: {csv_file}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    generate_from_csv(csv_file, output_dir)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
