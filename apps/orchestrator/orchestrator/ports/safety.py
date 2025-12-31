"""
Safety Ports

Hexagonal Architecture Ports for Safety domain.
Domain depends on these protocols, Adapters implement them.

SOLID: Dependency Inversion Principle (DIP)
- Domain (high-level) depends on Ports (abstractions)
- Adapters (low-level) depend on Ports (abstractions)
- No direct dependency from Domain to Adapter
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from apps.orchestrator.orchestrator.domain.safety.models import (
        ActionRequest,
        ActionType,
        ApprovalStatus,
        DetectionResult,
        LicenseInfo,
        LicenseViolation,
    )


# ============================================================================
# Secret Scanner Port
# ============================================================================


@runtime_checkable
class SecretScannerPort(Protocol):
    """
    Port for secret/PII detection.

    Implementations: RegexSecretScanner, EntropyScanner, MLBasedScanner, etc.
    """

    def detect(self, text: str) -> list[DetectionResult]:
        """
        Detect secrets and PII in text.

        Args:
            text: Input text to scan

        Returns:
            List of detected secrets/PII with confidence scores
        """
        ...

    def scrub(
        self,
        text: str,
        min_confidence: float = 0.7,
        redaction_func: Callable[[DetectionResult], str] | None = None,
    ) -> tuple[str, list[DetectionResult]]:
        """
        Scrub (redact) secrets from text.

        Args:
            text: Input text
            min_confidence: Minimum confidence threshold
            redaction_func: Optional custom redaction function

        Returns:
            Tuple of (scrubbed_text, detections)
        """
        ...

    def validate_clean(
        self,
        text: str,
        min_confidence: float = 0.7,
    ) -> tuple[bool, list[DetectionResult]]:
        """
        Validate that text contains no secrets.

        Args:
            text: Input text
            min_confidence: Minimum confidence threshold

        Returns:
            Tuple of (is_clean, violations)
        """
        ...

    def add_to_whitelist(self, *values: str) -> None:
        """Add values to whitelist (won't be flagged)."""
        ...

    def add_to_blacklist(self, *values: str) -> None:
        """Add values to blacklist (always flagged)."""
        ...


# ============================================================================
# License Checker Port
# ============================================================================


@runtime_checkable
class LicenseCheckerPort(Protocol):
    """
    Port for license compliance checking.

    Implementations: SPDXLicenseChecker, GithubLicenseAPI, etc.
    """

    def detect_license(self, text: str, source: str | None = None) -> LicenseInfo | None:
        """
        Detect license from text.

        Args:
            text: License text or file content
            source: Source identifier (file path, package name)

        Returns:
            Detected license info or None
        """
        ...

    def check_compliance(
        self,
        license: LicenseInfo,
        package: str | None = None,
    ) -> LicenseViolation | None:
        """
        Check license against policy.

        Args:
            license: License to check
            package: Package name

        Returns:
            Violation if policy violated, None otherwise
        """
        ...

    def check_compatibility(
        self,
        source_license: str,
        target_license: str,
    ) -> bool:
        """
        Check if two licenses are compatible.

        Args:
            source_license: Source code license
            target_license: Dependency license

        Returns:
            True if compatible
        """
        ...

    def scan_dependencies(
        self,
        dependencies: dict[str, str],  # {package: license_text}
    ) -> list[LicenseViolation]:
        """
        Scan dependencies for license compliance.

        Args:
            dependencies: Dict mapping package names to license texts

        Returns:
            List of violations
        """
        ...


# ============================================================================
# Action Gate Port
# ============================================================================


@runtime_checkable
class ActionGatePort(Protocol):
    """
    Port for dangerous action gating.

    Implementations: HumanApprovalGate, AutoApprovalGate, SlackApprovalGate, etc.
    """

    def request_approval(
        self,
        action_type: ActionType,
        target: str,
        description: str,
        context: dict | None = None,
        request_id: str | None = None,
    ) -> tuple[ApprovalStatus, str | None]:
        """
        Request approval for dangerous action.

        Args:
            action_type: Type of action
            target: Target (file, command, URL, etc.)
            description: Human-readable description
            context: Additional context
            request_id: Optional request ID

        Returns:
            Tuple of (approval_status, reason)
        """
        ...

    def approve(
        self,
        request_id: str,
        approver: str,
        reason: str | None = None,
    ) -> bool:
        """
        Approve pending request.

        Args:
            request_id: Request ID
            approver: Approver identifier
            reason: Approval reason

        Returns:
            True if approved successfully
        """
        ...

    def reject(
        self,
        request_id: str,
        approver: str,
        reason: str | None = None,
    ) -> bool:
        """
        Reject pending request.

        Args:
            request_id: Request ID
            approver: Approver identifier
            reason: Rejection reason

        Returns:
            True if rejected successfully
        """
        ...

    def get_status(self, request_id: str) -> ApprovalStatus | None:
        """Get approval status for request."""
        ...

    def get_pending_requests(self) -> list[ActionRequest]:
        """Get all pending approval requests."""
        ...

    def cleanup_timeouts(self) -> int:
        """
        Cleanup timed out requests.

        Returns:
            Number of requests cleaned up
        """
        ...
