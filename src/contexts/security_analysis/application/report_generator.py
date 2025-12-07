"""
Security Report Generator

Generates human-readable security scan reports.
"""

import json
from datetime import datetime
from pathlib import Path

from ..domain.models.vulnerability import ScanResult, Severity, Vulnerability


class SecurityReportGenerator:
    """
    Generate security scan reports in various formats

    Formats:
    - Text (human-readable)
    - JSON (machine-readable)
    - Markdown (documentation)
    """

    def generate_text_report(self, result: ScanResult) -> str:
        """
        Generate text report

        Args:
            result: Scan results

        Returns:
            Formatted text report
        """
        lines = []

        # Header
        lines.append("=" * 80)
        lines.append("SECURITY SCAN REPORT")
        lines.append("=" * 80)
        lines.append("")

        # Summary
        summary = result.get_summary()
        lines.append("SUMMARY")
        lines.append("-" * 80)
        lines.append(f"Files Scanned:    {summary['files_scanned']}")
        lines.append(f"Duration:         {summary['scan_duration_ms']}ms")
        lines.append(f"Total Findings:   {summary['total']}")
        lines.append("")

        # By Severity
        if summary["by_severity"]:
            lines.append("By Severity:")
            for sev, count in sorted(summary["by_severity"].items(), key=lambda x: Severity(x[0]), reverse=True):
                emoji = self._get_severity_emoji(Severity(sev))
                lines.append(f"  {emoji} {sev.upper():8s}: {count}")
        lines.append("")

        # By CWE
        if summary["by_cwe"]:
            lines.append("By CWE:")
            for cwe, count in sorted(summary["by_cwe"].items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {cwe}: {count}")
        lines.append("")

        # Detailed findings
        if result.vulnerabilities:
            lines.append("=" * 80)
            lines.append("DETAILED FINDINGS")
            lines.append("=" * 80)
            lines.append("")

            for i, vuln in enumerate(result.vulnerabilities, 1):
                lines.extend(self._format_vulnerability(i, vuln))
                lines.append("")
        else:
            lines.append("No vulnerabilities found! 🎉")

        lines.append("=" * 80)

        return "\n".join(lines)

    def generate_json_report(self, result: ScanResult) -> str:
        """
        Generate JSON report

        Args:
            result: Scan results

        Returns:
            JSON string
        """
        report = {
            "summary": result.get_summary(),
            "vulnerabilities": [vuln.to_dict() for vuln in result.vulnerabilities],
            "metadata": result.metadata,
            "generated_at": datetime.now().isoformat(),
        }

        return json.dumps(report, indent=2)

    def generate_markdown_report(self, result: ScanResult) -> str:
        """
        Generate Markdown report

        Args:
            result: Scan results

        Returns:
            Markdown string
        """
        lines = []

        # Title
        lines.append("# Security Scan Report")
        lines.append("")

        # Summary
        summary = result.get_summary()
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Files Scanned**: {summary['files_scanned']}")
        lines.append(f"- **Duration**: {summary['scan_duration_ms']}ms")
        lines.append(f"- **Total Findings**: {summary['total']}")
        lines.append("")

        # By Severity
        if summary["by_severity"]:
            lines.append("### By Severity")
            lines.append("")
            for sev, count in sorted(summary["by_severity"].items(), key=lambda x: Severity(x[0]), reverse=True):
                emoji = self._get_severity_emoji(Severity(sev))
                lines.append(f"- {emoji} **{sev.upper()}**: {count}")
            lines.append("")

        # Detailed findings
        if result.vulnerabilities:
            lines.append("## Detailed Findings")
            lines.append("")

            for i, vuln in enumerate(result.vulnerabilities, 1):
                lines.extend(self._format_vulnerability_markdown(i, vuln))
                lines.append("")

        return "\n".join(lines)

    def save_report(
        self,
        result: ScanResult,
        output_path: Path,
        format: str = "text",
    ):
        """
        Save report to file

        Args:
            result: Scan results
            output_path: Output file path
            format: Report format (text, json, markdown)
        """
        if format == "json":
            content = self.generate_json_report(result)
        elif format == "markdown":
            content = self.generate_markdown_report(result)
        else:
            content = self.generate_text_report(result)

        output_path.write_text(content)

    def _format_vulnerability(self, index: int, vuln: Vulnerability) -> list[str]:
        """Format single vulnerability for text report"""
        lines = []

        emoji = vuln.get_severity_emoji()
        lines.append(f"[{index}] {emoji} {vuln.title}")
        lines.append("-" * 80)
        lines.append(f"CWE:         {vuln.cwe.value} - {vuln.cwe.get_name()}")
        lines.append(f"Severity:    {vuln.severity.value.upper()}")
        lines.append(f"Confidence:  {vuln.confidence:.0%}")
        lines.append("")
        lines.append(f"Description: {vuln.description}")
        lines.append("")
        lines.append(f"Source:      {vuln.source_location}")
        lines.append(f"Sink:        {vuln.sink_location}")
        lines.append(f"Path Length: {len(vuln.taint_path)}")

        if vuln.recommendation:
            lines.append("")
            lines.append("Recommendation:")
            for rec_line in vuln.recommendation.split("\n"):
                lines.append(f"  {rec_line}")

        return lines

    def _format_vulnerability_markdown(
        self,
        index: int,
        vuln: Vulnerability,
    ) -> list[str]:
        """Format single vulnerability for markdown report"""
        lines = []

        emoji = vuln.get_severity_emoji()
        lines.append(f"### {emoji} [{index}] {vuln.title}")
        lines.append("")
        lines.append(f"- **CWE**: {vuln.cwe.value} - {vuln.cwe.get_name()}")
        lines.append(f"- **Severity**: {vuln.severity.value.upper()}")
        lines.append(f"- **Confidence**: {vuln.confidence:.0%}")
        lines.append("")
        lines.append(f"**Description**: {vuln.description}")
        lines.append("")
        lines.append(f"**Source**: `{vuln.source_location}`")
        lines.append(f"**Sink**: `{vuln.sink_location}`")

        if vuln.recommendation:
            lines.append("")
            lines.append("**Recommendation**:")
            lines.append("```")
            lines.append(vuln.recommendation)
            lines.append("```")

        return lines

    def _get_severity_emoji(self, severity: Severity) -> str:
        """Get emoji for severity"""
        return {
            Severity.CRITICAL: "🔴",
            Severity.HIGH: "🟠",
            Severity.MEDIUM: "🟡",
            Severity.LOW: "🟢",
            Severity.INFO: "🔵",
        }.get(severity, "⚪")


# Convenience function


def generate_report(
    result: ScanResult,
    format: str = "text",
) -> str:
    """
    Generate security report

    Args:
        result: Scan results
        format: Report format (text, json, markdown)

    Returns:
        Formatted report string

    Example:
        result = engine.scan_file(ir_doc)
        report = generate_report(result, format="markdown")
        print(report)
    """
    generator = SecurityReportGenerator()

    if format == "json":
        return generator.generate_json_report(result)
    elif format == "markdown":
        return generator.generate_markdown_report(result)
    else:
        return generator.generate_text_report(result)
