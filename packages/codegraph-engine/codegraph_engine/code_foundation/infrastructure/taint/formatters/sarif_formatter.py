"""
SARIF (Static Analysis Results Interchange Format) formatter.

Converts taint analysis results to SARIF 2.1.0 format for CI/CD integration.
Supported by: GitHub Security, GitLab, VSCode, Azure DevOps
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codegraph_engine.code_foundation.domain.taint import SimpleVulnerability


@dataclass
class SarifConfig:
    """SARIF output configuration."""

    tool_name: str = "Semantica"
    tool_version: str = "1.0.0"
    tool_info_uri: str = "https://github.com/semantica"
    include_code_flows: bool = True
    include_fixes: bool = False
    pretty_print: bool = True


@dataclass
class SarifFormatter:
    """
    Formats taint analysis results to SARIF 2.1.0 format.

    Usage:
        formatter = SarifFormatter()
        sarif_json = formatter.format(vulnerabilities, base_path)
        formatter.write_to_file(sarif_json, Path("results.sarif"))
    """

    config: SarifConfig = field(default_factory=SarifConfig)

    # CWE to SARIF level mapping
    SEVERITY_MAP: dict[str, str] = field(
        default_factory=lambda: {
            "critical": "error",
            "high": "error",
            "medium": "warning",
            "low": "note",
            "info": "note",
        }
    )

    def format(
        self,
        vulnerabilities: list[SimpleVulnerability],
        base_path: Path | None = None,
    ) -> dict[str, Any]:
        """
        Convert vulnerabilities to SARIF format.

        Args:
            vulnerabilities: List of detected vulnerabilities
            base_path: Base path for relative file URIs

        Returns:
            SARIF 2.1.0 compliant dictionary
        """
        base_path = base_path or Path.cwd()

        # Collect unique rules
        rules = self._build_rules(vulnerabilities)

        # Build results
        results = [self._build_result(vuln, base_path) for vuln in vulnerabilities]

        return {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": self.config.tool_name,
                            "version": self.config.tool_version,
                            "informationUri": self.config.tool_info_uri,
                            "rules": list(rules.values()),
                        }
                    },
                    "results": results,
                    "invocations": [
                        {
                            "executionSuccessful": True,
                            "endTimeUtc": datetime.now(timezone.utc).isoformat(),
                        }
                    ],
                }
            ],
        }

    def _build_rules(
        self,
        vulnerabilities: list[SimpleVulnerability],
    ) -> dict[str, dict[str, Any]]:
        """Build unique rule definitions from vulnerabilities."""
        rules: dict[str, dict[str, Any]] = {}

        for vuln in vulnerabilities:
            rule_id = vuln.policy_id
            if rule_id in rules:
                continue

            # Extract CWE from policy_id (e.g., "sql-injection" -> "CWE-89")
            cwe_id = self._extract_cwe(vuln)

            rules[rule_id] = {
                "id": rule_id,
                "name": self._policy_to_name(rule_id),
                "shortDescription": {
                    "text": self._policy_to_description(rule_id),
                },
                "fullDescription": {
                    "text": f"Taint flow detected from {vuln.source_atom_id} to {vuln.sink_atom_id}",
                },
                "defaultConfiguration": {
                    "level": self._get_level(vuln),
                },
                "properties": {
                    "tags": self._get_tags(rule_id, cwe_id),
                    "security-severity": self._get_security_severity(vuln),
                },
            }

            if cwe_id:
                rules[rule_id]["helpUri"] = f"https://cwe.mitre.org/data/definitions/{cwe_id.replace('CWE-', '')}.html"

        return rules

    def _build_result(
        self,
        vuln: SimpleVulnerability,
        base_path: Path,
    ) -> dict[str, Any]:
        """Build a single SARIF result from a vulnerability."""
        result: dict[str, Any] = {
            "ruleId": vuln.policy_id,
            "level": self._get_level(vuln),
            "message": {
                "text": self._build_message(vuln),
            },
            "locations": [
                self._build_location(vuln.sink_location, base_path),
            ],
        }

        # Add code flow (taint path) if enabled
        if self.config.include_code_flows and vuln.path:
            result["codeFlows"] = [self._build_code_flow(vuln, base_path)]

        # Add fingerprint for deduplication
        result["fingerprints"] = {
            "semantica/v1": self._compute_fingerprint(vuln),
        }

        return result

    def _build_location(
        self,
        location_str: str,
        base_path: Path,
    ) -> dict[str, Any]:
        """Build SARIF location from location string."""
        # Parse location string (format: "file:line" or "file:line:col")
        parts = location_str.rsplit(":", 2)

        file_path = parts[0] if parts else "unknown"
        line = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1

        # Make path relative to base
        try:
            rel_path = Path(file_path).relative_to(base_path)
        except ValueError:
            rel_path = Path(file_path)

        return {
            "physicalLocation": {
                "artifactLocation": {
                    "uri": str(rel_path),
                    "uriBaseId": "%SRCROOT%",
                },
                "region": {
                    "startLine": line,
                },
            },
        }

    def _build_code_flow(
        self,
        vuln: SimpleVulnerability,
        base_path: Path,
    ) -> dict[str, Any]:
        """Build code flow (taint path) for a vulnerability."""
        thread_flow_locations = []

        # Add source
        thread_flow_locations.append(
            {
                "location": self._build_location(vuln.source_location, base_path),
                "kinds": ["source"],
                "nestingLevel": 0,
            }
        )

        # Add intermediate steps
        for i, step in enumerate(vuln.path or []):
            if step not in (vuln.source_location, vuln.sink_location):
                thread_flow_locations.append(
                    {
                        "location": self._build_location(step, base_path),
                        "kinds": ["step"],
                        "nestingLevel": 1,
                    }
                )

        # Add sink
        thread_flow_locations.append(
            {
                "location": self._build_location(vuln.sink_location, base_path),
                "kinds": ["sink"],
                "nestingLevel": 0,
            }
        )

        return {
            "threadFlows": [
                {
                    "locations": thread_flow_locations,
                }
            ],
            "message": {
                "text": f"Taint flows from {vuln.source_atom_id} to {vuln.sink_atom_id}",
            },
        }

    def _build_message(self, vuln: SimpleVulnerability) -> str:
        """Build human-readable message for a vulnerability."""
        policy_name = self._policy_to_name(vuln.policy_id)
        return (
            f"{policy_name}: Untrusted data from '{vuln.source_atom_id}' flows to dangerous sink '{vuln.sink_atom_id}'"
        )

    def _get_level(self, vuln: SimpleVulnerability) -> str:
        """Get SARIF level from vulnerability severity."""
        return self.SEVERITY_MAP.get(vuln.severity, "warning")

    def _get_security_severity(self, vuln: SimpleVulnerability) -> str:
        """Get numeric security severity (0-10) for GitHub."""
        severity_scores = {
            "critical": "9.0",
            "high": "7.0",
            "medium": "5.0",
            "low": "3.0",
            "info": "1.0",
        }
        return severity_scores.get(vuln.severity, "5.0")

    def _extract_cwe(self, vuln: SimpleVulnerability) -> str | None:
        """Extract CWE ID from vulnerability."""
        # Map policy IDs to CWE
        cwe_map = {
            "sql-injection": "CWE-89",
            "command-injection": "CWE-78",
            "xss": "CWE-79",
            "path-traversal": "CWE-22",
            "code-injection": "CWE-94",
            "xxe": "CWE-611",
            "ssrf": "CWE-918",
            "ldap-injection": "CWE-90",
            "xpath-injection": "CWE-643",
            "nosql-injection": "CWE-943",
        }
        return cwe_map.get(vuln.policy_id)

    def _get_tags(self, policy_id: str, cwe_id: str | None) -> list[str]:
        """Get tags for a rule."""
        tags = ["security", "taint-analysis"]

        if cwe_id:
            tags.append(cwe_id)

        if "injection" in policy_id:
            tags.append("injection")

        return tags

    def _policy_to_name(self, policy_id: str) -> str:
        """Convert policy ID to human-readable name."""
        name_map = {
            "sql-injection": "SQL Injection",
            "command-injection": "OS Command Injection",
            "xss": "Cross-Site Scripting (XSS)",
            "path-traversal": "Path Traversal",
            "code-injection": "Code Injection",
            "xxe": "XML External Entity (XXE)",
            "ssrf": "Server-Side Request Forgery",
            "ldap-injection": "LDAP Injection",
            "xpath-injection": "XPath Injection",
            "nosql-injection": "NoSQL Injection",
        }
        return name_map.get(policy_id, policy_id.replace("-", " ").title())

    def _policy_to_description(self, policy_id: str) -> str:
        """Get short description for a policy."""
        desc_map = {
            "sql-injection": "Untrusted input used in SQL query",
            "command-injection": "Untrusted input used in OS command",
            "xss": "Untrusted input rendered in HTML without escaping",
            "path-traversal": "Untrusted input used in file path",
            "code-injection": "Untrusted input executed as code",
            "xxe": "XML parsing with external entities enabled",
            "ssrf": "Untrusted URL used in server-side request",
            "ldap-injection": "Untrusted input used in LDAP query",
            "xpath-injection": "Untrusted input used in XPath query",
            "nosql-injection": "Untrusted input used in NoSQL query",
        }
        return desc_map.get(policy_id, f"Security issue: {policy_id}")

    def _compute_fingerprint(self, vuln: SimpleVulnerability) -> str:
        """Compute stable fingerprint for deduplication."""
        import hashlib

        components = [
            vuln.policy_id,
            vuln.source_atom_id,
            vuln.sink_atom_id,
            vuln.source_location,
            vuln.sink_location,
        ]
        content = "|".join(str(c) for c in components)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_json(
        self,
        vulnerabilities: list[SimpleVulnerability],
        base_path: Path | None = None,
    ) -> str:
        """Convert vulnerabilities to SARIF JSON string."""
        sarif = self.format(vulnerabilities, base_path)
        indent = 2 if self.config.pretty_print else None
        return json.dumps(sarif, indent=indent, ensure_ascii=False)

    def write_to_file(
        self,
        vulnerabilities: list[SimpleVulnerability],
        output_path: Path,
        base_path: Path | None = None,
    ) -> None:
        """Write SARIF output to file."""
        json_str = self.to_json(vulnerabilities, base_path)
        output_path.write_text(json_str, encoding="utf-8")
