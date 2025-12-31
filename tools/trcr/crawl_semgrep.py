#!/usr/bin/env python3
"""
Semgrep Security Rules Crawler - High Quality Subset Parser

Parses Semgrep YAML files to extract security patterns and convert to TRCR format.

Usage:
  python tools/trcr/crawl_semgrep.py \
    --output data/semgrep_rules.csv \
    --quality high
"""

import argparse
import re
import subprocess
import tempfile
import yaml
from pathlib import Path
from typing import Dict, List, Optional
import csv


class SemgrepParser:
    """Parser for Semgrep YAML rule files"""

    # CWE pattern extraction
    CWE_PATTERN = re.compile(r"CWE[- ](\d+)", re.IGNORECASE)

    # OWASP pattern extraction
    OWASP_PATTERN = re.compile(r"A\d{2}:\d{4}")

    # Quality thresholds
    QUALITY_FILTERS = {
        "high": lambda rule: (
            rule.get("metadata", {}).get("confidence", "").lower() in ["high", "medium"]
            and rule.get("severity", "").upper() in ["ERROR", "WARNING"]
        ),
        "medium": lambda rule: rule.get("severity", "").upper() in ["ERROR", "WARNING"],
        "all": lambda rule: True,
    }

    def __init__(self, quality: str = "high"):
        self.quality_filter = self.QUALITY_FILTERS.get(quality, self.QUALITY_FILTERS["high"])
        self.stats = {
            "total_files": 0,
            "parsed_files": 0,
            "extracted_rules": 0,
            "skipped_files": 0,
            "skipped_low_quality": 0,
        }

    def extract_cwe(self, metadata: Dict) -> Optional[str]:
        """Extract CWE from metadata"""
        # Try cwe field
        if "cwe" in metadata:
            cwe_list = metadata["cwe"]
            if isinstance(cwe_list, list) and cwe_list:
                cwe_str = cwe_list[0]
                if isinstance(cwe_str, str):
                    match = self.CWE_PATTERN.search(cwe_str)
                    if match:
                        return f"CWE-{match.group(1)}"

        # Try references
        if "references" in metadata:
            for ref in metadata["references"]:
                if isinstance(ref, str):
                    match = self.CWE_PATTERN.search(ref)
                    if match:
                        return f"CWE-{match.group(1)}"

        # Try category or tags
        for field in ["category", "tags"]:
            if field in metadata:
                value = metadata[field]
                if isinstance(value, str):
                    match = self.CWE_PATTERN.search(value)
                    if match:
                        return f"CWE-{match.group(1)}"

        return None

    def extract_owasp(self, metadata: Dict) -> Optional[str]:
        """Extract OWASP category"""
        for field in ["owasp", "category", "references"]:
            if field in metadata:
                value = metadata[field]
                if isinstance(value, str):
                    match = self.OWASP_PATTERN.search(value)
                    if match:
                        return match.group(0)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            match = self.OWASP_PATTERN.search(item)
                            if match:
                                return match.group(0)
        return None

    def extract_patterns(self, rule: Dict) -> List[str]:
        """Extract patterns from Semgrep rule"""
        patterns = []

        # Handle pattern field
        if "pattern" in rule:
            pattern_str = rule["pattern"]
            # Extract function calls like "func(...)"
            func_matches = re.findall(r"(\w+(?:\.\w+)*)\s*\(", pattern_str)
            patterns.extend(func_matches)

        # Handle patterns list
        if "patterns" in rule:
            for p in rule["patterns"]:
                if isinstance(p, dict):
                    if "pattern" in p:
                        func_matches = re.findall(r"(\w+(?:\.\w+)*)\s*\(", p["pattern"])
                        patterns.extend(func_matches)

        # Handle pattern-either
        if "pattern-either" in rule:
            for p in rule["pattern-either"]:
                if isinstance(p, dict) and "pattern" in p:
                    func_matches = re.findall(r"(\w+(?:\.\w+)*)\s*\(", p["pattern"])
                    patterns.extend(func_matches)

        return list(set(patterns))  # Remove duplicates

    def map_severity(self, semgrep_severity: str) -> str:
        """Map Semgrep severity to TRCR severity"""
        severity_map = {
            "ERROR": "critical",
            "WARNING": "high",
            "INFO": "medium",
        }
        return severity_map.get(semgrep_severity.upper(), "medium")

    def parse_yaml_file(self, file_path: Path) -> List[Dict[str, str]]:
        """Parse a single Semgrep YAML file"""
        self.stats["total_files"] += 1
        rules = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            print(f"  ⚠️  Failed to read {file_path}: {e}")
            self.stats["skipped_files"] += 1
            return rules

        if not data or "rules" not in data:
            self.stats["skipped_files"] += 1
            return rules

        for rule in data["rules"]:
            metadata = rule.get("metadata", {})

            # Apply quality filter
            if not self.quality_filter(rule):
                self.stats["skipped_low_quality"] += 1
                continue

            # Extract fields
            rule_id = rule.get("id", "unknown")
            severity = self.map_severity(rule.get("severity", "INFO"))
            cwe = self.extract_cwe(metadata)

            # Skip if no CWE (not security-focused)
            if not cwe:
                self.stats["skipped_low_quality"] += 1
                continue

            owasp = self.extract_owasp(metadata)
            patterns = self.extract_patterns(rule)

            # Determine category from metadata
            category = "sink"  # Default
            if "category" in metadata:
                cat_str = str(metadata["category"]).lower()
                if "source" in cat_str:
                    category = "source"
                elif "sanitizer" in cat_str or "safe" in cat_str:
                    category = "sanitizer"

            # Build pattern string
            if patterns:
                pattern_str = ",".join([f"{p}:0" for p in patterns])
            else:
                pattern_str = rule_id  # Fallback to rule ID

            rules.append(
                {
                    "category": category,
                    "name": f"semgrep.{rule_id}",
                    "cwe": cwe,
                    "owasp": owasp or "",
                    "severity": severity,
                    "patterns": pattern_str,
                    "description": rule.get("message", rule_id)[:100],
                }
            )
            self.stats["extracted_rules"] += 1

        if rules:
            self.stats["parsed_files"] += 1

        return rules

    def crawl_directory(self, directory: Path) -> List[Dict[str, str]]:
        """Crawl directory for Semgrep YAML files"""
        all_rules = []

        print(f"🔍 Scanning {directory}...")

        # Find Python security rules
        yaml_files = list(directory.rglob("python/**/*.yaml")) + list(directory.rglob("python/**/*.yml"))

        # Filter security-focused directories
        security_paths = ["security", "owasp", "cwe", "injection", "crypto", "auth"]
        yaml_files = [f for f in yaml_files if any(sec in str(f).lower() for sec in security_paths)]

        print(f"📊 Found {len(yaml_files)} security-focused YAML files")
        print("")

        for yaml_file in yaml_files:
            rules = self.parse_yaml_file(yaml_file)
            for rule in rules:
                all_rules.append(rule)
                print(f"  ✅ [{len(all_rules):3d}] {rule['name']:<60} {rule['cwe']:<12} {rule['severity']}")

        return all_rules

    def print_stats(self):
        """Print crawling statistics"""
        print("")
        print("=" * 70)
        print("📊 Crawling Statistics")
        print("=" * 70)
        print(f"  Total YAML files found:   {self.stats['total_files']}")
        print(f"  Successfully parsed:      {self.stats['parsed_files']}")
        print(f"  Skipped (no rules):       {self.stats['skipped_files']}")
        print(f"  Skipped (low quality):    {self.stats['skipped_low_quality']}")
        print(f"  Extracted rules:          {self.stats['extracted_rules']}")
        print("")


def clone_semgrep_repo(target_dir: Path) -> Path:
    """Clone Semgrep rules repository"""
    print("=" * 70)
    print("🚀 Semgrep Security Rules Crawler")
    print("=" * 70)
    print("")

    if target_dir.exists():
        print(f"📂 Using existing repository: {target_dir}")
        return target_dir

    print(f"📥 Cloning Semgrep rules repository to {target_dir}...")

    # Clone with depth=1
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
            "https://github.com/semgrep/semgrep-rules.git",
            str(target_dir),
        ],
        check=True,
    )

    # Sparse checkout - only Python rules
    subprocess.run(["git", "-C", str(target_dir), "sparse-checkout", "set", "python"], check=True)

    print(f"✅ Cloned successfully: {target_dir}")
    print("")

    return target_dir


def save_to_csv(rules: List[Dict[str, str]], output_path: Path):
    """Save extracted rules to CSV"""
    print(f"💾 Saving to {output_path}...")

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        if not rules:
            print("⚠️  No rules to save")
            return

        fieldnames = ["category", "name", "cwe", "owasp", "severity", "patterns", "description"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(rules)

    print(f"✅ Saved {len(rules)} rules")


def main():
    parser = argparse.ArgumentParser(description="Crawl Semgrep security rules")
    parser.add_argument("--output", default="data/semgrep_rules.csv", help="Output CSV file")
    parser.add_argument("--quality", choices=["high", "medium", "all"], default="high", help="Quality filter")
    parser.add_argument("--cache-dir", help="Cache directory for cloned repo")

    args = parser.parse_args()

    # Setup paths
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine cache directory
    if args.cache_dir:
        cache_dir = Path(args.cache_dir)
    else:
        cache_dir = Path(tempfile.gettempdir()) / "semgrep_cache"

    try:
        # Clone or use cached repo
        rules_dir = clone_semgrep_repo(cache_dir)

        if not rules_dir.exists():
            print(f"❌ Rules directory not found: {rules_dir}")
            return 1

        # Parse YAML files
        parser_instance = SemgrepParser(quality=args.quality)
        rules = parser_instance.crawl_directory(rules_dir)

        # Print statistics
        parser_instance.print_stats()

        # Save to CSV
        save_to_csv(rules, output_path)

        print("")
        print("=" * 70)
        print("✅ Crawling Complete")
        print("=" * 70)
        print("")
        print("Next steps:")
        print(f"  1. Review rules: cat {output_path}")
        print(
            f"  2. Generate TRCR rules: just trcr-generate-csv {output_path} packages/codegraph-trcr/rules/atoms/semgrep/"
        )
        print(f"  3. Validate: just trcr-validate-all")
        print("")

        return 0

    except subprocess.CalledProcessError as e:
        print(f"❌ Git command failed: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
