#!/usr/bin/env python3
"""
TRCR Rule Validator - 룰 정합성 검증

Usage:
  python scripts/validate_rules.py \\
    packages/codegraph-trcr/rules/atoms/*.yaml
"""

import argparse
import yaml
import time
from pathlib import Path
from typing import List, Dict, Any, Set
from collections import defaultdict


class RuleValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.stats = defaultdict(int)

    def validate_yaml_syntax(self, yaml_path: Path) -> bool:
        """Validate YAML syntax."""
        try:
            with open(yaml_path) as f:
                yaml.safe_load(f)
            return True
        except yaml.YAMLError as e:
            self.errors.append(f"{yaml_path}: YAML syntax error - {e}")
            return False

    def validate_rule_structure(self, rule: Dict[str, Any], file_path: Path) -> bool:
        """Validate individual rule structure."""
        rule_id = rule.get("id", "<missing>")
        valid = True

        # Required fields
        required = ["id", "kind", "match"]
        for field in required:
            if field not in rule:
                self.errors.append(f"{file_path}:{rule_id} - Missing required field: {field}")
                valid = False

        # Kind validation
        if "kind" in rule:
            valid_kinds = ["source", "sink", "sanitizer", "propagator"]
            if rule["kind"] not in valid_kinds:
                self.errors.append(f"{file_path}:{rule_id} - Invalid kind: {rule['kind']}")
                valid = False

        # Severity validation
        if "severity" in rule:
            valid_severities = ["low", "medium", "high", "critical"]
            if rule["severity"] not in valid_severities:
                self.warnings.append(f"{file_path}:{rule_id} - Invalid severity: {rule['severity']}")

        # CWE format validation
        if "cwe" in rule:
            for cwe in rule["cwe"]:
                if not cwe.startswith("CWE-"):
                    self.warnings.append(f"{file_path}:{rule_id} - Invalid CWE format: {cwe}")

        # Match patterns validation
        if "match" in rule:
            if not isinstance(rule["match"], list):
                self.errors.append(f"{file_path}:{rule_id} - 'match' must be a list")
                valid = False
            elif len(rule["match"]) == 0:
                self.warnings.append(f"{file_path}:{rule_id} - Empty match patterns")

        return valid

    def check_duplicate_ids(self, all_rules: List[tuple[Path, Dict[str, Any]]]):
        """Check for duplicate rule IDs."""
        id_to_files = defaultdict(list)

        for file_path, rule in all_rules:
            rule_id = rule.get("id")
            if rule_id:
                id_to_files[rule_id].append(file_path)

        for rule_id, files in id_to_files.items():
            if len(files) > 1:
                self.errors.append(f"Duplicate rule ID '{rule_id}' in files: {files}")

    def analyze_coverage(self, all_rules: List[tuple[Path, Dict[str, Any]]]):
        """Analyze CWE and OWASP coverage."""
        cwes = set()
        owasp_categories = set()

        for _, rule in all_rules:
            if "cwe" in rule:
                for cwe in rule["cwe"]:
                    cwes.add(cwe)

            if "owasp" in rule:
                owasp_categories.add(rule["owasp"])

        self.stats["cwe_coverage"] = len(cwes)
        self.stats["owasp_coverage"] = len(owasp_categories)
        self.stats["cwes"] = sorted(cwes)
        self.stats["owasp"] = sorted(owasp_categories)

    def analyze_patterns(self, all_rules: List[tuple[Path, Dict[str, Any]]]):
        """Analyze match patterns."""
        total_patterns = 0
        pattern_types = defaultdict(int)

        for _, rule in all_rules:
            if "match" not in rule:
                continue

            for pattern in rule["match"]:
                total_patterns += 1

                if "call" in pattern:
                    pattern_types["call"] += 1
                if "read" in pattern:
                    pattern_types["read"] += 1
                if "base_type" in pattern:
                    pattern_types["typed"] += 1
                else:
                    pattern_types["untyped"] += 1

        self.stats["total_patterns"] = total_patterns
        self.stats["pattern_types"] = dict(pattern_types)

    def benchmark_compilation(self, rule_files: List[Path]):
        """Benchmark rule compilation performance."""
        try:
            from trcr import TaintRuleCompiler

            compiler = TaintRuleCompiler()
            start_time = time.time()

            total_compiled = 0
            for rule_file in rule_files:
                rules = compiler.compile_file(str(rule_file))
                total_compiled += len(rules)

            elapsed = (time.time() - start_time) * 1000  # ms

            self.stats["compiled_rules"] = total_compiled
            self.stats["compile_time_ms"] = elapsed
            self.stats["compile_rate"] = total_compiled / (elapsed / 1000)  # rules/sec

        except ImportError:
            self.warnings.append("TRCR not installed - skipping compilation benchmark")

    def validate_files(self, rule_files: List[Path]) -> bool:
        """Validate all rule files."""
        all_rules = []

        print("=" * 70)
        print("🔍 TRCR Rule Validation")
        print("=" * 70)

        # 1. YAML syntax validation
        print("\n[1/6] Validating YAML syntax...")
        for rule_file in rule_files:
            if not rule_file.exists():
                self.errors.append(f"File not found: {rule_file}")
                continue

            if self.validate_yaml_syntax(rule_file):
                print(f"  ✅ {rule_file}")
            else:
                print(f"  ❌ {rule_file}")

        if self.errors:
            return False

        # 2. Parse all rules
        print("\n[2/6] Parsing rule structures...")
        for rule_file in rule_files:
            with open(rule_file) as f:
                data = yaml.safe_load(f)

            if "atoms" not in data:
                self.warnings.append(f"{rule_file}: No 'atoms' key found")
                continue

            for rule in data["atoms"]:
                all_rules.append((rule_file, rule))
                self.validate_rule_structure(rule, rule_file)

        print(f"  ✅ Parsed {len(all_rules)} rules from {len(rule_files)} files")

        # 3. Check duplicates
        print("\n[3/6] Checking for duplicate IDs...")
        self.check_duplicate_ids(all_rules)
        if not any("Duplicate" in e for e in self.errors):
            print(f"  ✅ No duplicates found")

        # 4. Analyze coverage
        print("\n[4/6] Analyzing CWE/OWASP coverage...")
        self.analyze_coverage(all_rules)
        print(f"  ✅ CWE Coverage: {self.stats['cwe_coverage']} CWEs")
        print(f"  ✅ OWASP Coverage: {self.stats['owasp_coverage']} categories")

        # 5. Analyze patterns
        print("\n[5/6] Analyzing match patterns...")
        self.analyze_patterns(all_rules)
        print(f"  ✅ Total Patterns: {self.stats['total_patterns']}")
        print(f"     - Call patterns: {self.stats['pattern_types'].get('call', 0)}")
        print(f"     - Read patterns: {self.stats['pattern_types'].get('read', 0)}")
        print(f"     - Typed patterns: {self.stats['pattern_types'].get('typed', 0)}")
        print(f"     - Untyped patterns: {self.stats['pattern_types'].get('untyped', 0)}")

        # 6. Benchmark compilation
        print("\n[6/6] Benchmarking compilation...")
        self.benchmark_compilation(rule_files)
        if "compiled_rules" in self.stats:
            print(f"  ✅ Compiled Rules: {self.stats['compiled_rules']}")
            print(f"  ✅ Compile Time: {self.stats['compile_time_ms']:.2f}ms")
            print(f"  ✅ Compile Rate: {self.stats['compile_rate']:.0f} rules/sec")

        return True

    def print_report(self):
        """Print validation report."""
        print("\n" + "=" * 70)
        print("📊 Validation Report")
        print("=" * 70)

        # Errors
        if self.errors:
            print(f"\n❌ Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")
        else:
            print("\n✅ No errors found")

        # Warnings
        if self.warnings:
            print(f"\n⚠️  Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")

        # Statistics
        print("\n📈 Statistics:")
        print(f"  - CWE Coverage: {self.stats.get('cwe_coverage', 0)} CWEs")
        print(f"  - OWASP Coverage: {self.stats.get('owasp_coverage', 0)} categories")
        print(f"  - Total Patterns: {self.stats.get('total_patterns', 0)}")
        if "compiled_rules" in self.stats:
            print(f"  - Compiled Rules: {self.stats['compiled_rules']}")
            print(f"  - Compile Time: {self.stats['compile_time_ms']:.2f}ms")

        # Success/Failure
        print("\n" + "=" * 70)
        if self.errors:
            print("❌ VALIDATION FAILED")
            return False
        else:
            print("✅ VALIDATION PASSED")
            return True


def main():
    parser = argparse.ArgumentParser(description="Validate TRCR rule files")
    parser.add_argument("files", nargs="+", help="Rule YAML files to validate")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")

    args = parser.parse_args()

    # Expand glob patterns
    rule_files = []
    for pattern in args.files:
        if "*" in pattern:
            rule_files.extend(Path(".").glob(pattern))
        else:
            rule_files.append(Path(pattern))

    # Validate
    validator = RuleValidator()
    validator.validate_files(rule_files)

    # Print report
    success = validator.print_report()

    # Check strict mode
    if args.strict and validator.warnings:
        print("\n⚠️  Strict mode: Warnings treated as errors")
        success = False

    return 0 if success else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
