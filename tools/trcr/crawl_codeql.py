#!/usr/bin/env python3
"""
CodeQL Security Rules Crawler - High Quality Parser

Parses CodeQL .ql files to extract security patterns and convert to TRCR format.

Usage:
  python scripts/crawl_codeql.py \
    --repo https://github.com/github/codeql \
    --output data/codeql_rules.csv
"""

import argparse
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set
import csv
import shutil


class CodeQLParser:
    """Parser for CodeQL .ql query files"""

    # Pattern to extract metadata from QL files
    METADATA_PATTERN = re.compile(r"@(\w+)\s+(.+?)(?=\n\s*\*|$)", re.MULTILINE)

    # Pattern to extract CWE numbers
    CWE_PATTERN = re.compile(r"CWE[- ](\d+)", re.IGNORECASE)

    # Pattern to extract class/predicate names
    CLASS_PATTERN = re.compile(r"class\s+(\w+)\s+extends\s+(\w+)")
    PREDICATE_PATTERN = re.compile(r"(?:predicate|from)\s+(\w+)")

    # Pattern to extract call patterns from QL
    CALL_PATTERN = re.compile(r'\.getAttr\(["\'](\w+)["\']\)|\.getName\(\)\s*=\s*["\'](\w+)["\']')

    def __init__(self):
        self.stats = {
            "total_files": 0,
            "parsed_files": 0,
            "extracted_rules": 0,
            "skipped_files": 0,
        }

    def parse_metadata(self, content: str) -> Dict[str, str]:
        """Extract metadata from QL file comments"""
        metadata = {}

        # Find metadata block (/** ... */)
        metadata_match = re.search(r"/\*\*(.*?)\*/", content, re.DOTALL)
        if not metadata_match:
            return metadata

        metadata_block = metadata_match.group(1)

        # Extract @key value pairs
        for match in self.METADATA_PATTERN.finditer(metadata_block):
            key = match.group(1).lower()
            value = match.group(2).strip()
            metadata[key] = value

        return metadata

    def extract_cwe(self, content: str, metadata: Dict[str, str]) -> Optional[str]:
        """Extract CWE number from content or metadata"""
        # Try metadata tags first
        if "tags" in metadata:
            cwe_match = self.CWE_PATTERN.search(metadata["tags"])
            if cwe_match:
                return f"CWE-{cwe_match.group(1)}"

        # Try description
        if "description" in metadata:
            cwe_match = self.CWE_PATTERN.search(metadata["description"])
            if cwe_match:
                return f"CWE-{cwe_match.group(1)}"

        # Try full content
        cwe_match = self.CWE_PATTERN.search(content)
        if cwe_match:
            return f"CWE-{cwe_match.group(1)}"

        return None

    def extract_severity(self, metadata: Dict[str, str], file_path: Path) -> str:
        """Extract severity level"""
        # Check metadata precision/severity
        if "precision" in metadata:
            precision = metadata["precision"].lower()
            if precision in ["very-high", "high"]:
                return "critical"
            elif precision == "medium":
                return "high"
            elif precision == "low":
                return "medium"

        # Infer from path
        path_str = str(file_path).lower()
        if "critical" in path_str or "injection" in path_str:
            return "critical"
        elif "high" in path_str or "security" in path_str:
            return "high"
        elif "medium" in path_str:
            return "medium"

        return "medium"  # default

    def extract_category(self, file_path: Path, metadata: Dict[str, str]) -> str:
        """Extract rule category from path and metadata"""
        path_parts = file_path.parts

        # Find Security/ directory index
        try:
            sec_idx = path_parts.index("Security")
            if sec_idx + 1 < len(path_parts):
                category = path_parts[sec_idx + 1]
                # Clean up category name
                category = category.replace("-", "_").lower()
                return category
        except (ValueError, IndexError):
            pass

        # Fallback: use kind from metadata or filename
        if "kind" in metadata:
            return metadata["kind"].lower().replace(" ", "_")

        return "security"

    def extract_patterns(self, content: str) -> List[str]:
        """Extract call patterns from QL code"""
        patterns = []

        # Look for common taint tracking patterns
        # Example: source.getAttr("read") or call.getName() = "eval"
        for match in self.CALL_PATTERN.finditer(content):
            attr = match.group(1) or match.group(2)
            if attr:
                patterns.append(attr)

        # Look for class names that indicate sinks/sources
        class_matches = self.CLASS_PATTERN.findall(content)
        for class_name, base_class in class_matches:
            if "Sink" in class_name or "Source" in class_name:
                # Extract meaningful name
                name = re.sub(r"(Sink|Source|Config)", "", class_name)
                if name:
                    patterns.append(name)

        return patterns

    def parse_ql_file(self, file_path: Path) -> Optional[Dict[str, str]]:
        """Parse a single .ql file and extract rule information"""
        self.stats["total_files"] += 1

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  ⚠️  Failed to read {file_path}: {e}")
            self.stats["skipped_files"] += 1
            return None

        # Parse metadata
        metadata = self.parse_metadata(content)

        # Skip non-security queries
        if not metadata.get("kind") or "problem" not in metadata.get("kind", "").lower():
            self.stats["skipped_files"] += 1
            return None

        # Extract components
        cwe = self.extract_cwe(content, metadata)
        if not cwe:
            # Skip queries without CWE (not security-focused)
            self.stats["skipped_files"] += 1
            return None

        severity = self.extract_severity(metadata, file_path)
        category_base = self.extract_category(file_path, metadata)
        patterns = self.extract_patterns(content)

        # Build rule name from file
        rule_name = file_path.stem.replace("-", "_").replace(" ", "_")
        full_name = f"{category_base}.{rule_name}"

        # Description from metadata
        description = metadata.get("description", metadata.get("name", rule_name))

        # OWASP mapping (if in tags)
        owasp = None
        if "tags" in metadata and "owasp" in metadata["tags"].lower():
            owasp_match = re.search(r"A\d{2}:\d{4}", metadata["tags"])
            if owasp_match:
                owasp = owasp_match.group(0)

        self.stats["parsed_files"] += 1

        return {
            "category": "sink",  # Most CodeQL queries are sinks
            "name": full_name,
            "cwe": cwe,
            "owasp": owasp or "",
            "severity": severity,
            "patterns": ",".join(patterns) if patterns else rule_name,
            "description": description[:100],  # Truncate
        }

    def crawl_directory(self, directory: Path) -> List[Dict[str, str]]:
        """Crawl directory for .ql files"""
        rules = []

        print(f"🔍 Scanning {directory}...")

        # Find all .ql files
        ql_files = list(directory.rglob("*.ql"))

        print(f"📊 Found {len(ql_files)} .ql files")
        print("")

        for ql_file in ql_files:
            rule = self.parse_ql_file(ql_file)
            if rule:
                rules.append(rule)
                self.stats["extracted_rules"] += 1
                print(
                    f"  ✅ [{self.stats['extracted_rules']:3d}] {rule['name']:<50} {rule['cwe']:<12} {rule['severity']}"
                )

        return rules

    def print_stats(self):
        """Print crawling statistics"""
        print("")
        print("=" * 70)
        print("📊 Crawling Statistics")
        print("=" * 70)
        print(f"  Total .ql files found:    {self.stats['total_files']}")
        print(f"  Successfully parsed:      {self.stats['parsed_files']}")
        print(f"  Skipped (non-security):   {self.stats['skipped_files']}")
        print(f"  Extracted rules:          {self.stats['extracted_rules']}")
        print("")


def clone_codeql_repo(target_dir: Path) -> Path:
    """Clone CodeQL repository"""
    print("=" * 70)
    print("🚀 CodeQL Security Rules Crawler")
    print("=" * 70)
    print("")

    if target_dir.exists():
        print(f"📂 Using existing repository: {target_dir}")
        return target_dir / "python" / "ql" / "src" / "Security"

    print(f"📥 Cloning CodeQL repository to {target_dir}...")

    # Clone with depth=1 for speed (shallow clone)
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",  # Partial clone
            "--sparse",
            "https://github.com/github/codeql.git",
            str(target_dir),
        ],
        check=True,
    )

    # Sparse checkout - only Python security queries
    subprocess.run(["git", "-C", str(target_dir), "sparse-checkout", "set", "python/ql/src/Security"], check=True)

    security_dir = target_dir / "python" / "ql" / "src" / "Security"
    print(f"✅ Cloned successfully: {security_dir}")
    print("")

    return security_dir


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
    parser = argparse.ArgumentParser(description="Crawl CodeQL security rules")
    parser.add_argument("--repo", help="CodeQL repository URL or path")
    parser.add_argument("--output", default="data/codeql_rules.csv", help="Output CSV file")
    parser.add_argument("--cache-dir", help="Cache directory for cloned repo")

    args = parser.parse_args()

    # Setup paths
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine cache directory
    if args.cache_dir:
        cache_dir = Path(args.cache_dir)
    else:
        cache_dir = Path(tempfile.gettempdir()) / "codeql_cache"

    try:
        # Clone or use cached repo
        security_dir = clone_codeql_repo(cache_dir)

        if not security_dir.exists():
            print(f"❌ Security directory not found: {security_dir}")
            return 1

        # Parse .ql files
        parser_instance = CodeQLParser()
        rules = parser_instance.crawl_directory(security_dir)

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
            f"  2. Generate TRCR rules: python scripts/generate_from_csv.py --csv {output_path} --output packages/codegraph-trcr/rules/atoms/codeql/"
        )
        print(f"  3. Validate: python scripts/validate_rules.py packages/codegraph-trcr/rules/atoms/codeql/*.yaml")
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
