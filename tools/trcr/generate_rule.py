#!/usr/bin/env python3
"""
TRCR Rule Generator - 룰 자동 생성 도구

Usage:
  python scripts/generate_rule.py \\
    --category sink \\
    --name info_leak.stack_trace \\
    --cwe CWE-209 \\
    --owasp "A01:2021-Broken Access Control" \\
    --severity high \\
    --patterns "traceback.format_exc:0,sys.exc_info:0"

  python scripts/generate_rule.py \\
    --category barrier \\
    --name validation.length_check \\
    --patterns "len:0,max:0"
"""

import argparse
import yaml
from pathlib import Path


TEMPLATE = """
- id: {rule_id}
  kind: {kind}
  tags: {tags}
  severity: {severity}
  {cwe_line}
  {owasp_line}
  description: {description}
  match:
{match_patterns}
""".strip()


def generate_match_pattern(pattern_str: str) -> str:
    """
    Generate match pattern from string.

    Examples:
      "traceback.format_exc:0" → base_type: traceback, call: format_exc, args: [0]
      "len:0" → call: len, args: [0]
      "request.GET" → base_type: request, read: GET
    """
    patterns = []

    for p in pattern_str.split(","):
        p = p.strip()

        # Parse pattern: "base_type.call:arg_index" or "call:arg_index" or "base_type.read"
        if ":" in p:
            func_part, arg_idx = p.split(":")
            arg_idx = int(arg_idx)
        else:
            func_part = p
            arg_idx = None

        # Split base_type and call/read
        if "." in func_part:
            parts = func_part.split(".")
            if len(parts) == 2:
                base_type, call_or_read = parts
            else:
                # Multiple dots: take last as call, rest as base_type
                base_type = ".".join(parts[:-1])
                call_or_read = parts[-1]
        else:
            base_type = None
            call_or_read = func_part

        # Determine if it's a call or read (heuristic: all caps = read)
        is_read = call_or_read.isupper() or call_or_read in ["args", "form", "query_params"]

        # Build pattern
        pattern_lines = []
        if base_type:
            pattern_lines.append(f"base_type: {base_type}")

        if is_read:
            pattern_lines.append(f"read: {call_or_read}")
        else:
            pattern_lines.append(f"call: {call_or_read}")

        if arg_idx is not None:
            pattern_lines.append(f"args: [{arg_idx}]")
            pattern_lines.append(f"constraints:")
            pattern_lines.append(f"  arg_type: not_const")

        patterns.append("  - " + "\n    ".join(pattern_lines))

    return "\n".join(patterns)


def generate_rule(
    category: str,
    name: str,
    patterns: str,
    cwe: str = None,
    owasp: str = None,
    severity: str = "medium",
    description: str = None,
) -> str:
    """Generate a TRCR rule YAML."""

    # Determine kind
    kind_map = {
        "sink": "sink",
        "source": "source",
        "input": "source",
        "barrier": "sanitizer",
        "sanitizer": "sanitizer",
        "prop": "propagator",
        "propagator": "propagator",
    }
    kind = kind_map.get(category, "sink")

    # Generate rule_id
    rule_id = f"{category}.{name}"

    # Generate tags (from name)
    name_parts = name.split(".")
    tags = list(name_parts)
    if category == "sink":
        tags.append("vulnerability")
    elif category == "source":
        tags.append("untrusted")
    elif category == "barrier":
        tags.append("safety")

    # Generate description
    if description is None:
        description = f"{name.replace('.', ' ').replace('_', ' ').title()}"

    # Properly escape description for YAML (quote if it contains special characters)
    import re
    import json

    if re.search(r'[:\[\]{}#&*!|>\'"%@`]', description):
        # Use JSON encoding for simple string escaping (compatible with YAML)
        description = json.dumps(description)

    # CWE/OWASP lines
    cwe_line = f'cwe: ["{cwe}"]' if cwe else ""
    owasp_line = f'owasp: "{owasp}"' if owasp else ""

    # Match patterns
    match_patterns = generate_match_pattern(patterns)

    # Fill template
    rule_yaml = TEMPLATE.format(
        rule_id=rule_id,
        kind=kind,
        tags=tags,
        severity=severity,
        cwe_line=cwe_line,
        owasp_line=owasp_line,
        description=description,
        match_patterns=match_patterns,
    )

    # Remove empty lines
    lines = [line for line in rule_yaml.split("\n") if line.strip()]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate TRCR rules")
    parser.add_argument(
        "--category",
        required=True,
        choices=["sink", "source", "input", "barrier", "sanitizer", "prop", "propagator"],
        help="Rule category",
    )
    parser.add_argument("--name", required=True, help="Rule name (e.g., info_leak.stack_trace)")
    parser.add_argument("--patterns", required=True, help="Match patterns (comma-separated)")
    parser.add_argument("--cwe", help="CWE ID (e.g., CWE-209)")
    parser.add_argument("--owasp", help="OWASP category (e.g., A01:2021-...)")
    parser.add_argument("--severity", default="medium", choices=["low", "medium", "high", "critical"])
    parser.add_argument("--description", help="Custom description")
    parser.add_argument("--output", help="Output file (default: stdout)")

    args = parser.parse_args()

    # Generate rule
    rule_yaml = generate_rule(
        category=args.category,
        name=args.name,
        patterns=args.patterns,
        cwe=args.cwe,
        owasp=args.owasp,
        severity=args.severity,
        description=args.description,
    )

    # Output
    if args.output:
        output_path = Path(args.output)

        # Append to existing file or create new
        if output_path.exists():
            with open(output_path, "a") as f:
                f.write("\n\n" + rule_yaml)
            print(f"✅ Appended rule to {output_path}")
        else:
            # Create new file with atoms: header
            with open(output_path, "w") as f:
                f.write("# TRCR Rules - Auto-generated\n\natoms:\n")
                f.write(rule_yaml)
            print(f"✅ Created {output_path}")
    else:
        print(rule_yaml)


if __name__ == "__main__":
    main()
