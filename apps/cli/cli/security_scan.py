#!/usr/bin/env python3
"""
Semantica Security Scanner CLI

Usage:
    python -m src.cli.security_scan ./my-project
    python -m src.cli.security_scan ./my-project --output sarif -o results.sarif
    python -m src.cli.security_scan ./my-project --policy sql-injection,xss
    python -m src.cli.security_scan ./my-project --severity high,critical
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.taint.models import SimpleVulnerability


def main():
    parser = argparse.ArgumentParser(
        description="Semantica Security Scanner - SOTA Taint Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Scan current directory
    python -m src.cli.security_scan .

    # Output SARIF for GitHub Security
    python -m src.cli.security_scan ./src --output sarif -o results.sarif

    # Filter by policy
    python -m src.cli.security_scan . --policy sql-injection,command-injection

    # Filter by severity
    python -m src.cli.security_scan . --severity critical,high
        """,
    )

    parser.add_argument(
        "path",
        type=Path,
        help="Path to scan (file or directory)",
    )

    parser.add_argument(
        "--output",
        "-f",
        choices=["text", "json", "sarif"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument(
        "-o",
        "--output-file",
        type=Path,
        help="Write output to file instead of stdout",
    )

    parser.add_argument(
        "--policy",
        "-p",
        help="Comma-separated list of policies to check (e.g., sql-injection,xss)",
    )

    parser.add_argument(
        "--severity",
        "-s",
        help="Minimum severity to report (e.g., high,critical)",
    )

    parser.add_argument(
        "--exclude",
        help="Glob patterns to exclude (e.g., '**/test/**,**/vendor/**')",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching",
    )

    parser.add_argument(
        "--no-path-verify",
        action="store_true",
        help="Disable DFG path verification (faster but may have FPs)",
    )

    args = parser.parse_args()

    # Validate path
    if not args.path.exists():
        print(f"Error: Path not found: {args.path}", file=sys.stderr)
        sys.exit(1)

    # Run scan
    try:
        vulnerabilities = asyncio.run(
            run_scan(
                path=args.path,
                policies=args.policy.split(",") if args.policy else None,
                severities=args.severity.split(",") if args.severity else None,
                exclude_patterns=args.exclude.split(",") if args.exclude else None,
                verbose=args.verbose,
                use_cache=not args.no_cache,
                verify_paths=not args.no_path_verify,
            )
        )

        # Format and output
        output = format_output(vulnerabilities, args.output, args.path)

        if args.output_file:
            args.output_file.write_text(output)
            print(f"Results written to: {args.output_file}", file=sys.stderr)
        else:
            print(output)

        # Exit with error code if vulnerabilities found
        sys.exit(1 if vulnerabilities else 0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(2)


async def run_scan(
    path: Path,
    policies: list[str] | None = None,
    severities: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    verbose: bool = False,
    use_cache: bool = True,
    verify_paths: bool = True,
) -> list[SimpleVulnerability]:
    """
    Run taint analysis scan using trcr SDK.

    SOTA implementation with:
    - Full expression extraction
    - Constraint validation (arg_type, kwarg constraints)
    - DFG-based path verification
    - Guard detection for sanitizer awareness
    """
    from codegraph_engine.code_foundation.application.taint_analysis_service import (
        TaintAnalysisService,
    )
    from codegraph_engine.code_foundation.domain.semantic_ir.mode import SemanticIrBuildMode
    from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import (
        LayeredIRBuilder,
        LayeredIRConfig,
    )

    if verbose:
        print(f"Scanning: {path.absolute()}", file=sys.stderr)

    # Collect Python files
    if path.is_file():
        files = [path]
    else:
        files = list(path.rglob("*.py"))

        # Apply exclude patterns
        if exclude_patterns:
            import fnmatch

            files = [f for f in files if not any(fnmatch.fnmatch(str(f), pat) for pat in exclude_patterns)]

    if verbose:
        print(f"Found {len(files)} Python files", file=sys.stderr)

    if not files:
        return []

    # Build IR with full semantic analysis
    from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig

    config = LayeredIRConfig()
    builder = LayeredIRBuilder(path if path.is_dir() else path.parent, config=config)

    # Use new BuildConfig API
    build_config = BuildConfig.for_security_audit()
    result = await builder.build(files=files, config=build_config)
    ir_docs = result.ir_documents

    if verbose:
        print(f"Built IR for {len(ir_docs)} files", file=sys.stderr)

    # Initialize trcr-based TaintAnalysisService
    # Rules path is auto-resolved from settings
    taint_service = TaintAnalysisService()

    # Analyze each file
    all_vulns: list[SimpleVulnerability] = []

    for file_path, ir_doc in ir_docs.items():
        if verbose:
            print(f"  Analyzing: {file_path}", file=sys.stderr)

        # Inject file_path for proper location tracking
        ir_doc.file_path = str(file_path)  # type: ignore

        result = taint_service.analyze(
            ir_doc,
            verify_paths=verify_paths,
        )
        vulns = result.get("vulnerabilities", [])

        # Filter by policy
        if policies:
            vulns = [v for v in vulns if v.policy_id in policies]

        # Filter by severity
        if severities:
            vulns = [v for v in vulns if getattr(v, "severity", "high") in severities]

        all_vulns.extend(vulns)

    if verbose:
        print(f"Found {len(all_vulns)} vulnerabilities", file=sys.stderr)

    return all_vulns


def format_output(
    vulnerabilities: list[SimpleVulnerability],
    output_format: str,
    base_path: Path,
) -> str:
    """Format vulnerabilities for output."""
    if output_format == "sarif":
        from codegraph_engine.code_foundation.infrastructure.taint.formatters import (
            SarifFormatter,
        )

        formatter = SarifFormatter()
        return formatter.to_json(vulnerabilities, base_path)

    elif output_format == "json":
        results = []
        for vuln in vulnerabilities:
            results.append(
                {
                    "policy": vuln.policy_id,
                    "severity": vuln.severity,
                    "source": vuln.source_location,
                    "sink": vuln.sink_location,
                    "source_atom": vuln.source_atom_id,
                    "sink_atom": vuln.sink_atom_id,
                    "path": vuln.path,
                }
            )
        return json.dumps(results, indent=2, ensure_ascii=False)

    else:  # text
        if not vulnerabilities:
            return "No vulnerabilities found."

        lines = [
            f"Found {len(vulnerabilities)} vulnerabilities:",
            "",
        ]

        for i, vuln in enumerate(vulnerabilities, 1):
            lines.extend(
                [
                    f"[{i}] {vuln.policy_id.upper()} ({vuln.severity})",
                    f"    Source: {vuln.source_location} ({vuln.source_atom_id})",
                    f"    Sink:   {vuln.sink_location} ({vuln.sink_atom_id})",
                ]
            )
            if vuln.path:
                lines.append(f"    Path:   {' -> '.join(vuln.path)}")
            lines.append("")

        return "\n".join(lines)


if __name__ == "__main__":
    main()
