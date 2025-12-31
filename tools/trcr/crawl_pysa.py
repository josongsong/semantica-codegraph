#!/usr/bin/env python3
"""
Meta Pysa Taint Rules Crawler - High Quality Parser

Parses Pysa .pysa files to extract taint specifications and convert to TRCR format.

Usage:
  python tools/trcr/crawl_pysa.py \
    --output data/pysa_rules.csv
"""

import argparse
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
import csv


class PysaParser:
    """Parser for Pysa .pysa taint specification files"""

    # Pattern to extract taint specifications
    TAINT_SPEC_PATTERN = re.compile(r"def\s+(\w+(?:\.\w+)*)\s*\(([^)]*)\)\s*->\s*TaintSource\[(\w+)\]")

    SINK_PATTERN = re.compile(r"def\s+(\w+(?:\.\w+)*)\s*\(([^)]*TaintSink\[(\w+)\][^)]*)\)")

    SANITIZER_PATTERN = re.compile(r"def\s+(\w+(?:\.\w+)*)\s*\(([^)]*Sanitize[^)]*)\)")

    # CWE mapping for common taint kinds
    CWE_MAPPING = {
        "RemoteCodeExecution": "CWE-094",
        "SQL": "CWE-089",
        "XSS": "CWE-079",
        "CommandInjection": "CWE-078",
        "PathTraversal": "CWE-022",
        "SSRF": "CWE-918",
        "XMLExternalEntity": "CWE-611",
        "Deserialization": "CWE-502",
        "LDAP": "CWE-090",
        "HeaderInjection": "CWE-113",
        "OpenRedirect": "CWE-601",
        "FileDisclosure": "CWE-200",
        "UserControlledData": "CWE-20",
    }

    def __init__(self):
        self.stats = {
            "total_files": 0,
            "parsed_files": 0,
            "extracted_sources": 0,
            "extracted_sinks": 0,
            "extracted_sanitizers": 0,
            "skipped_files": 0,
        }

    def extract_cwe(self, taint_kind: str) -> str:
        """Map Pysa taint kind to CWE"""
        for key, cwe in self.CWE_MAPPING.items():
            if key.lower() in taint_kind.lower():
                return cwe
        return "CWE-20"  # Default: Improper Input Validation

    def extract_severity(self, taint_kind: str) -> str:
        """Infer severity from taint kind"""
        critical_kinds = ["RemoteCodeExecution", "SQL", "CommandInjection", "Deserialization"]
        high_kinds = ["XSS", "SSRF", "PathTraversal", "XXE", "LDAP"]

        for kind in critical_kinds:
            if kind.lower() in taint_kind.lower():
                return "critical"

        for kind in high_kinds:
            if kind.lower() in taint_kind.lower():
                return "high"

        return "medium"

    def parse_pysa_file(self, file_path: Path) -> List[Dict[str, str]]:
        """Parse a single .pysa file and extract taint rules"""
        self.stats["total_files"] += 1
        rules = []

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  ⚠️  Failed to read {file_path}: {e}")
            self.stats["skipped_files"] += 1
            return rules

        # Extract sources
        for match in self.TAINT_SPEC_PATTERN.finditer(content):
            func_name = match.group(1)
            taint_kind = match.group(3)

            cwe = self.extract_cwe(taint_kind)
            severity = self.extract_severity(taint_kind)

            # Convert to TRCR format
            base_type, _, call = func_name.rpartition(".")
            pattern = f"{func_name}:0" if "." in func_name else f"{func_name}:0"

            rules.append(
                {
                    "category": "source",
                    "name": f"pysa.{taint_kind.lower()}.{call.lower()}",
                    "cwe": cwe,
                    "owasp": "",
                    "severity": severity,
                    "patterns": pattern,
                    "description": f"Pysa source: {taint_kind}",
                }
            )
            self.stats["extracted_sources"] += 1

        # Extract sinks
        for match in self.SINK_PATTERN.finditer(content):
            func_name = match.group(1)
            args_str = match.group(2)

            # Extract sink kind from args
            sink_match = re.search(r"TaintSink\[(\w+)\]", args_str)
            if not sink_match:
                continue

            taint_kind = sink_match.group(1)
            cwe = self.extract_cwe(taint_kind)
            severity = self.extract_severity(taint_kind)

            base_type, _, call = func_name.rpartition(".")
            pattern = f"{func_name}:0" if "." in func_name else f"{func_name}:0"

            rules.append(
                {
                    "category": "sink",
                    "name": f"pysa.{taint_kind.lower()}.{call.lower()}",
                    "cwe": cwe,
                    "owasp": "",
                    "severity": severity,
                    "patterns": pattern,
                    "description": f"Pysa sink: {taint_kind}",
                }
            )
            self.stats["extracted_sinks"] += 1

        # Extract sanitizers
        for match in self.SANITIZER_PATTERN.finditer(content):
            func_name = match.group(1)

            base_type, _, call = func_name.rpartition(".")
            pattern = f"{func_name}:0" if "." in func_name else f"{func_name}:0"

            rules.append(
                {
                    "category": "sanitizer",
                    "name": f"pysa.sanitizer.{call.lower()}",
                    "cwe": "",
                    "owasp": "",
                    "severity": "medium",
                    "patterns": pattern,
                    "description": f"Pysa sanitizer",
                }
            )
            self.stats["extracted_sanitizers"] += 1

        if rules:
            self.stats["parsed_files"] += 1

        return rules

    def crawl_directory(self, directory: Path) -> List[Dict[str, str]]:
        """Crawl directory for .pysa files"""
        all_rules = []

        print(f"🔍 Scanning {directory}...")

        # Find all .pysa files
        pysa_files = list(directory.rglob("*.pysa"))

        print(f"📊 Found {len(pysa_files)} .pysa files")
        print("")

        for pysa_file in pysa_files:
            rules = self.parse_pysa_file(pysa_file)
            for rule in rules:
                all_rules.append(rule)
                category_emoji = {"source": "🌊", "sink": "🎯", "sanitizer": "🛡️"}
                emoji = category_emoji.get(rule["category"], "📝")
                print(f"  {emoji} [{len(all_rules):3d}] {rule['name']:<60} {rule['cwe']:<12} {rule['severity']}")

        return all_rules

    def print_stats(self):
        """Print crawling statistics"""
        print("")
        print("=" * 70)
        print("📊 Crawling Statistics")
        print("=" * 70)
        print(f"  Total .pysa files found:  {self.stats['total_files']}")
        print(f"  Successfully parsed:      {self.stats['parsed_files']}")
        print(f"  Skipped:                  {self.stats['skipped_files']}")
        print(f"  Extracted sources:        {self.stats['extracted_sources']}")
        print(f"  Extracted sinks:          {self.stats['extracted_sinks']}")
        print(f"  Extracted sanitizers:     {self.stats['extracted_sanitizers']}")
        print(
            f"  Total rules:              {sum([self.stats['extracted_sources'], self.stats['extracted_sinks'], self.stats['extracted_sanitizers']])}"
        )
        print("")


def clone_pysa_repo(target_dir: Path) -> Path:
    """Clone Pyre-check repository (contains Pysa)"""
    print("=" * 70)
    print("🚀 Meta Pysa Taint Rules Crawler")
    print("=" * 70)
    print("")

    if target_dir.exists():
        print(f"📂 Using existing repository: {target_dir}")
        return target_dir / "stubs" / "taint"

    print(f"📥 Cloning Pyre-check repository to {target_dir}...")

    # Clone with depth=1 for speed
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
            "https://github.com/facebook/pyre-check.git",
            str(target_dir),
        ],
        check=True,
    )

    # Sparse checkout - only taint stubs
    subprocess.run(["git", "-C", str(target_dir), "sparse-checkout", "set", "stubs/taint"], check=True)

    taint_dir = target_dir / "stubs" / "taint"
    print(f"✅ Cloned successfully: {taint_dir}")
    print("")

    return taint_dir


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
    parser = argparse.ArgumentParser(description="Crawl Meta Pysa taint rules")
    parser.add_argument("--output", default="data/pysa_rules.csv", help="Output CSV file")
    parser.add_argument("--cache-dir", help="Cache directory for cloned repo")

    args = parser.parse_args()

    # Setup paths
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine cache directory
    if args.cache_dir:
        cache_dir = Path(args.cache_dir)
    else:
        cache_dir = Path(tempfile.gettempdir()) / "pysa_cache"

    try:
        # Clone or use cached repo
        taint_dir = clone_pysa_repo(cache_dir)

        if not taint_dir.exists():
            print(f"❌ Taint directory not found: {taint_dir}")
            return 1

        # Parse .pysa files
        parser_instance = PysaParser()
        rules = parser_instance.crawl_directory(taint_dir)

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
            f"  2. Generate TRCR rules: just trcr-generate-csv {output_path} packages/codegraph-trcr/rules/atoms/pysa/"
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
