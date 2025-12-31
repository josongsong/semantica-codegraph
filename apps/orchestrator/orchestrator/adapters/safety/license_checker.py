"""
License Compliance Checker Adapter

SPDX license detection and policy enforcement.
Implements LicenseCheckerPort.

SOLID: Single Responsibility - only handles license compliance logic.
Hexagonal: Adapter implementing Port, can be replaced with GitHub API, etc.
"""

from __future__ import annotations

import re
from pathlib import Path

from apps.orchestrator.orchestrator.domain.safety.models import (
    LicenseCategory,
    LicenseInfo,
    LicenseType,
    LicenseViolation,
    PolicyAction,
)
from apps.orchestrator.orchestrator.domain.safety.policies import LicenseCompatibility, LicensePolicy


class LicenseComplianceCheckerAdapter:
    """
    Enterprise license compliance checker.

    Implements: LicenseCheckerPort

    Features:
    - SPDX license detection
    - License compatibility matrix
    - Dependency license scanning
    - Policy enforcement (GPL, AGPL blocking)
    - Audit logging
    - License report generation
    """

    # SPDX license patterns
    SPDX_PATTERNS = {
        LicenseType.MIT: [
            r"MIT License",
            r"Permission is hereby granted, free of charge",
            r"MIT-style",
        ],
        LicenseType.APACHE_2: [
            r"Apache License.*Version 2\.0",
            r"Licensed under the Apache License",
        ],
        LicenseType.GPL_2: [
            r"GNU GENERAL PUBLIC LICENSE.*Version 2",
            r"GPL-2\.0",
        ],
        LicenseType.GPL_3: [
            r"GNU GENERAL PUBLIC LICENSE.*Version 3",
            r"GPL-3\.0",
            r"GPLv3",
        ],
        LicenseType.LGPL_2: [
            r"GNU LESSER GENERAL PUBLIC LICENSE.*Version 2",
            r"LGPL-2\.1",
        ],
        LicenseType.LGPL_3: [
            r"GNU LESSER GENERAL PUBLIC LICENSE.*Version 3",
            r"LGPL-3\.0",
        ],
        LicenseType.AGPL_3: [
            r"GNU AFFERO GENERAL PUBLIC LICENSE.*Version 3",
            r"AGPL-3\.0",
            r"AGPLv3",
        ],
        LicenseType.BSD_2: [
            r"BSD 2-Clause",
            r"Redistribution and use in source and binary forms.*2 clauses",
        ],
        LicenseType.BSD_3: [
            r"BSD 3-Clause",
            r"Redistribution and use in source and binary forms.*3 clauses",
        ],
        LicenseType.MPL_2: [
            r"Mozilla Public License.*Version 2\.0",
            r"MPL-2\.0",
        ],
        LicenseType.ISC: [
            r"ISC License",
            r"Permission to use, copy, modify",
        ],
    }

    # License category mapping
    CATEGORIES = {
        LicenseType.MIT: LicenseCategory.PERMISSIVE,
        LicenseType.APACHE_2: LicenseCategory.PERMISSIVE,
        LicenseType.BSD_2: LicenseCategory.PERMISSIVE,
        LicenseType.BSD_3: LicenseCategory.PERMISSIVE,
        LicenseType.ISC: LicenseCategory.PERMISSIVE,
        LicenseType.LGPL_2: LicenseCategory.WEAK_COPYLEFT,
        LicenseType.LGPL_3: LicenseCategory.WEAK_COPYLEFT,
        LicenseType.MPL_2: LicenseCategory.WEAK_COPYLEFT,
        LicenseType.GPL_2: LicenseCategory.STRONG_COPYLEFT,
        LicenseType.GPL_3: LicenseCategory.STRONG_COPYLEFT,
        LicenseType.AGPL_3: LicenseCategory.NETWORK_COPYLEFT,
        LicenseType.PROPRIETARY: LicenseCategory.PROPRIETARY,
        LicenseType.UNKNOWN: LicenseCategory.UNKNOWN,
    }

    def __init__(
        self,
        policy: LicensePolicy | None = None,
        compatibility: LicenseCompatibility | None = None,
    ):
        self.policy = policy or LicensePolicy()
        self.compatibility = compatibility or LicenseCompatibility()
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns"""
        self.compiled_patterns: dict[LicenseType, list[re.Pattern]] = {}
        for license_type, patterns in self.SPDX_PATTERNS.items():
            self.compiled_patterns[license_type] = [
                re.compile(pattern, re.IGNORECASE | re.DOTALL) for pattern in patterns
            ]

    def detect_license(self, text: str, source: str | None = None) -> LicenseInfo | None:
        """
        Detect license from text.

        Port: LicenseCheckerPort.detect_license()

        Args:
            text: License text or file content
            source: Source identifier (file path, package name)

        Returns:
            Detected license info or None
        """
        # Input validation
        if not text or not isinstance(text, str):
            return None

        # Try SPDX patterns
        for license_type, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    return LicenseInfo(
                        type=license_type,
                        category=self.CATEGORIES[license_type],
                        text=text[:500],  # First 500 chars
                        source=source,
                        confidence=0.9,
                    )

        # Try SPDX identifier in text
        spdx_match = re.search(r"SPDX-License-Identifier:\s*([A-Za-z0-9.-]+)", text)
        if spdx_match:
            identifier = spdx_match.group(1)
            license_type = self._parse_spdx_identifier(identifier)
            if license_type:
                return LicenseInfo(
                    type=license_type,
                    category=self.CATEGORIES.get(license_type, LicenseCategory.UNKNOWN),
                    text=text[:500],
                    source=source,
                    confidence=1.0,
                )

        return None

    @staticmethod
    def _parse_spdx_identifier(identifier: str) -> LicenseType | None:
        """Parse SPDX identifier to license type"""
        mapping = {
            "MIT": LicenseType.MIT,
            "Apache-2.0": LicenseType.APACHE_2,
            "GPL-2.0": LicenseType.GPL_2,
            "GPL-3.0": LicenseType.GPL_3,
            "LGPL-2.1": LicenseType.LGPL_2,
            "LGPL-3.0": LicenseType.LGPL_3,
            "AGPL-3.0": LicenseType.AGPL_3,
            "BSD-2-Clause": LicenseType.BSD_2,
            "BSD-3-Clause": LicenseType.BSD_3,
            "MPL-2.0": LicenseType.MPL_2,
            "ISC": LicenseType.ISC,
        }
        return mapping.get(identifier)

    def scan_file(self, file_path: Path) -> LicenseInfo | None:
        """
        Scan file for license.

        Helper method (not in Port).

        Args:
            file_path: Path to file

        Returns:
            Detected license or None
        """
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            return self.detect_license(text, source=str(file_path))
        except Exception:
            return None

    def check_compliance(
        self,
        license: LicenseInfo,
        package: str | None = None,
    ) -> LicenseViolation | None:
        """
        Check license against policy.

        Port: LicenseCheckerPort.check_compliance()

        Args:
            license: License to check
            package: Package name

        Returns:
            Violation if policy violated, None otherwise
        """
        # Check if blocked
        if license.type in self.policy.blocked:
            return LicenseViolation(
                license=license,
                action=PolicyAction.BLOCK,
                reason=f"License {license.type.value} is blocked by policy",
                package=package,
            )

        # Check if review required
        if license.type in self.policy.review_required:
            return LicenseViolation(
                license=license,
                action=PolicyAction.REQUIRE_REVIEW,
                reason=f"License {license.type.value} requires manual review",
                package=package,
            )

        # Check if unknown and blocked
        if license.type == LicenseType.UNKNOWN and self.policy.block_unknown:
            return LicenseViolation(
                license=license,
                action=PolicyAction.BLOCK,
                reason="Unknown license blocked by policy",
                package=package,
            )

        # Check if allowed
        if license.type in self.policy.allowed:
            return None

        # Warn for everything else
        return LicenseViolation(
            license=license,
            action=PolicyAction.WARN,
            reason=f"License {license.type.value} not explicitly allowed",
            package=package,
        )

    def check_compatibility(
        self,
        source_license: str,
        target_license: str,
    ) -> bool:
        """
        Check if two licenses are compatible.

        Port: LicenseCheckerPort.check_compatibility()

        Args:
            source_license: Source code license (SPDX ID)
            target_license: Dependency license (SPDX ID)

        Returns:
            True if compatible
        """
        # Convert string to LicenseType
        source_type = self._parse_spdx_identifier(source_license)
        target_type = self._parse_spdx_identifier(target_license)

        if not source_type or not target_type:
            return False

        allowed = self.compatibility.compatibility.get(source_type, [])
        return target_type in allowed

    def scan_dependencies(
        self,
        dependencies: dict[str, str],  # {package: license_text}
    ) -> list[LicenseViolation]:
        """
        Scan dependencies for license compliance.

        Port: LicenseCheckerPort.scan_dependencies()

        Args:
            dependencies: Dict mapping package names to license texts

        Returns:
            List of violations
        """
        # Input validation
        if not dependencies or not isinstance(dependencies, dict):
            return []

        violations = []

        for package, license_text in dependencies.items():
            # Skip invalid entries (None, non-string values)
            if not isinstance(license_text, str):
                if self.policy.require_license:
                    violations.append(
                        LicenseViolation(
                            license=LicenseInfo(
                                type=LicenseType.UNKNOWN,
                                category=LicenseCategory.UNKNOWN,
                            ),
                            action=PolicyAction.BLOCK,
                            reason="Invalid license text (not a string)",
                            package=package,
                        )
                    )
                continue
            license_info = self.detect_license(license_text, source=package)

            if not license_info:
                if self.policy.require_license:
                    violations.append(
                        LicenseViolation(
                            license=LicenseInfo(
                                type=LicenseType.UNKNOWN,
                                category=LicenseCategory.UNKNOWN,
                            ),
                            action=PolicyAction.BLOCK,
                            reason="No license detected",
                            package=package,
                        )
                    )
                continue

            violation = self.check_compliance(license_info, package=package)
            if violation:
                violations.append(violation)

        return violations

    def generate_report(
        self,
        licenses: list[LicenseInfo],
        violations: list[LicenseViolation] | None = None,
    ) -> str:
        """
        Generate license audit report.

        Helper method (not in Port).

        Args:
            licenses: List of detected licenses
            violations: List of violations

        Returns:
            Formatted report
        """
        report = ["# License Compliance Report\n"]

        # Summary
        report.append("## Summary\n")
        report.append(f"Total licenses scanned: {len(licenses)}\n")

        if violations:
            report.append(f"Violations found: {len(violations)}\n")
            blocked = sum(1 for v in violations if v.action == PolicyAction.BLOCK)
            warnings = sum(1 for v in violations if v.action == PolicyAction.WARN)
            review = sum(1 for v in violations if v.action == PolicyAction.REQUIRE_REVIEW)

            report.append(f"- Blocked: {blocked}\n")
            report.append(f"- Review required: {review}\n")
            report.append(f"- Warnings: {warnings}\n")

        # License breakdown
        report.append("\n## License Distribution\n")
        license_counts: dict[LicenseType, int] = {}
        for lic in licenses:
            license_counts[lic.type] = license_counts.get(lic.type, 0) + 1

        for license_type, count in sorted(license_counts.items(), key=lambda x: x[1], reverse=True):
            category = self.CATEGORIES.get(license_type, LicenseCategory.UNKNOWN)
            report.append(f"- {license_type.value} ({category.value}): {count}\n")

        # Violations detail
        if violations:
            report.append("\n## Violations\n")
            for violation in violations:
                report.append(f"\n### {violation.package or 'Unknown'}\n")
                report.append(f"- License: {violation.license.type.value}\n")
                report.append(f"- Action: {violation.action.value}\n")
                report.append(f"- Reason: {violation.reason}\n")

        return "".join(report)
