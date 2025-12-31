#!/usr/bin/env python3
"""
Type Synchronization Verifier

Verifies that Rust and Python IR types are in sync.
Run this after modifying NodeKind, EdgeKind, or other shared types.

Usage:
    python tools/verify_type_sync.py
"""

import re
import sys
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Type definitions to verify
SYNC_CHECKS = [
    {
        "name": "NodeKind",
        "python_file": "packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/models/kinds.py",
        "rust_files": [
            "packages/codegraph-rust/codegraph-ir/src/shared/models/node.rs",
            "packages/codegraph-rust/codegraph-core/src/types.rs",
        ],
        "python_pattern": r'(\w+)\s*=\s*"(\w+)"',  # NAME = "Value"
        "rust_pattern": r"^\s+(\w+),",  # Enum variant
    },
    {
        "name": "EdgeKind",
        "python_file": "packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/models/kinds.py",
        "rust_files": [
            "packages/codegraph-rust/codegraph-ir/src/shared/models/edge.rs",
            "packages/codegraph-rust/codegraph-core/src/types.rs",
        ],
        "python_pattern": r'(\w+)\s*=\s*"(\w+)"',
        "rust_pattern": r"^\s+(\w+),",
    },
]


def extract_python_enum(file_path: Path, enum_name: str, pattern: str) -> dict[str, str]:
    """Extract enum values from Python file."""
    content = file_path.read_text()

    # Find the enum class
    enum_match = re.search(rf"class {enum_name}\([^)]+\):(.*?)(?=\nclass |\Z)", content, re.DOTALL)
    if not enum_match:
        return {}

    enum_body = enum_match.group(1)
    values = {}

    for match in re.finditer(pattern, enum_body):
        name, value = match.groups()
        if name.isupper():  # Only enum members (uppercase)
            values[name] = value

    return values


def extract_rust_enum(file_path: Path, enum_name: str, pattern: str) -> list[str]:
    """Extract enum variants from Rust file."""
    content = file_path.read_text()

    # Find the enum
    enum_match = re.search(rf"pub enum {enum_name}\s*\{{([^}}]+)\}}", content, re.DOTALL)
    if not enum_match:
        return []

    enum_body = enum_match.group(1)
    variants = []

    for match in re.finditer(pattern, enum_body, re.MULTILINE):
        variant = match.group(1)
        if variant and not variant.startswith("//"):
            variants.append(variant)

    return variants


def check_serde_rename(file_path: Path, enum_name: str) -> str | None:
    """Check serde rename_all attribute."""
    content = file_path.read_text()

    # Find enum with its attributes
    pattern = rf'#\[serde\(rename_all\s*=\s*"([^"]+)"\)\]\s*pub enum {enum_name}'
    match = re.search(pattern, content)

    return match.group(1) if match else None


def verify_sync(check: dict) -> list[str]:
    """Verify a single sync check. Returns list of issues."""
    issues = []
    name = check["name"]

    # Extract Python values
    python_path = PROJECT_ROOT / check["python_file"]
    if not python_path.exists():
        issues.append(f"❌ Python file not found: {check['python_file']}")
        return issues

    python_values = extract_python_enum(python_path, name, check["python_pattern"])
    if not python_values:
        issues.append(f"⚠️  No Python {name} values found")

    print(f"\n{'=' * 60}")
    print(f"🔍 Checking {name}")
    print(f"{'=' * 60}")
    print(f"📄 Python ({len(python_values)} values): {check['python_file']}")
    for k, v in list(python_values.items())[:5]:
        print(f'   {k} = "{v}"')
    if len(python_values) > 5:
        print(f"   ... and {len(python_values) - 5} more")

    # Check each Rust file
    for rust_file in check["rust_files"]:
        rust_path = PROJECT_ROOT / rust_file
        if not rust_path.exists():
            issues.append(f"❌ Rust file not found: {rust_file}")
            continue

        rust_variants = extract_rust_enum(rust_path, name, check["rust_pattern"])
        serde_rename = check_serde_rename(rust_path, name)

        print(f"\n📄 Rust ({len(rust_variants)} variants): {rust_file}")
        print(f'   serde(rename_all = "{serde_rename}")')
        for v in rust_variants[:5]:
            print(f"   {v}")
        if len(rust_variants) > 5:
            print(f"   ... and {len(rust_variants) - 5} more")

        # Check serde format matches Python
        if name == "NodeKind":
            expected_serde = "PascalCase"
            if serde_rename != expected_serde:
                issues.append(f'❌ {rust_file}: serde should be "{expected_serde}", got "{serde_rename}"')
        elif name == "EdgeKind":
            expected_serde = "SCREAMING_SNAKE_CASE"
            if serde_rename != expected_serde:
                issues.append(f'❌ {rust_file}: serde should be "{expected_serde}", got "{serde_rename}"')

        # Check variant coverage
        rust_set = set(rust_variants)
        python_keys = set(python_values.keys())

        # Core variants that MUST exist in Rust
        core_variants = {"FILE", "MODULE", "CLASS", "FUNCTION", "METHOD", "VARIABLE", "FIELD", "IMPORT"}
        missing_core = core_variants - {v.upper() for v in rust_set}

        if missing_core:
            issues.append(f"❌ {rust_file}: Missing core variants: {missing_core}")

        # Check Python values match expected serde output
        if serde_rename == "PascalCase":
            for py_name, py_value in python_values.items():
                rust_variant = py_name.title().replace("_", "")
                if rust_variant in rust_set and py_value != rust_variant:
                    issues.append(
                        f'⚠️  Value mismatch: Python {py_name}="{py_value}" vs Rust PascalCase "{rust_variant}"'
                    )

    return issues


def main():
    print("🔄 Type Synchronization Verifier")
    print("=" * 60)

    all_issues = []

    for check in SYNC_CHECKS:
        issues = verify_sync(check)
        all_issues.extend(issues)

    print("\n" + "=" * 60)
    print("📊 Summary")
    print("=" * 60)

    if all_issues:
        print(f"\n❌ Found {len(all_issues)} issue(s):\n")
        for issue in all_issues:
            print(f"   {issue}")
        sys.exit(1)
    else:
        print("\n✅ All types are in sync!")
        sys.exit(0)


if __name__ == "__main__":
    main()
