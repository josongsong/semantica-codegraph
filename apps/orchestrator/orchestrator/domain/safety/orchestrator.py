"""
Safety Orchestrator (Domain Service)

Multi-layer validation pipeline integrating all safety components.
Depends only on Ports (DIP).

SOLID:
- Single Responsibility: coordinates safety pipeline
- Dependency Inversion: depends on Ports, not Adapters
- Open/Closed: extensible by adding new Ports

Hexagonal: Domain Service, orchestrates Ports
"""

from __future__ import annotations

from typing import Any

from apps.orchestrator.orchestrator.ports.safety import ActionGatePort, LicenseCheckerPort, SecretScannerPort

from .models import (
    ActionType,
    ApprovalStatus,
    PolicyAction,
    ValidationContext,
    ValidationResult,
    ValidationStage,
)
from .policies import SafetyConfig


class SafetyOrchestrator:
    """
    Safety orchestrator integrating all governance components.

    Domain Service that coordinates security validation pipeline.

    Features:
    - Multi-layer validation pipeline
    - Secret/PII scrubbing
    - License compliance checking
    - Dangerous action gating
    - Metrics & alerting
    - Override management

    Dependencies:
    - SecretScannerPort
    - LicenseCheckerPort
    - ActionGatePort
    """

    def __init__(
        self,
        config: SafetyConfig | None = None,
        secret_scanner: SecretScannerPort | None = None,
        license_checker: LicenseCheckerPort | None = None,
        action_gate: ActionGatePort | None = None,
    ):
        """
        Args:
            config: Safety configuration
            secret_scanner: Secret scanner (Port)
            license_checker: License checker (Port)
            action_gate: Action gate (Port)

        SOLID: Dependency Inversion - depends on Ports, not concrete Adapters.

        Raises:
            TypeError: If provided adapters don't implement required Ports
        """
        self.config = config or SafetyConfig()

        # Runtime validation: Check if adapters implement Ports
        if secret_scanner is not None and not isinstance(secret_scanner, SecretScannerPort):
            raise TypeError(f"secret_scanner must implement SecretScannerPort, got {type(secret_scanner)}")
        if license_checker is not None and not isinstance(license_checker, LicenseCheckerPort):
            raise TypeError(f"license_checker must implement LicenseCheckerPort, got {type(license_checker)}")
        if action_gate is not None and not isinstance(action_gate, ActionGatePort):
            raise TypeError(f"action_gate must implement ActionGatePort, got {type(action_gate)}")

        # Ports (can be None if disabled)
        self.secret_scanner = secret_scanner if self.config.enable_secret_scanning else None
        self.license_checker = license_checker if self.config.enable_license_checking else None
        self.action_gate = action_gate if self.config.enable_action_gating else None

        # Metrics
        self._metrics = {
            "total_validations": 0,
            "secrets_detected": 0,
            "license_violations": 0,
            "actions_blocked": 0,
            "actions_approved": 0,
        }

    def validate_content(
        self,
        content: str,
        min_confidence: float = 0.7,
        auto_scrub: bool = True,
    ) -> ValidationResult:
        """
        Validate content for secrets/PII.

        Args:
            content: Content to validate
            min_confidence: Minimum detection confidence
            auto_scrub: Auto-scrub detected secrets

        Returns:
            Validation result
        """
        self._metrics["total_validations"] += 1

        if not self.secret_scanner or not self.config.enable_secret_scanning:
            return ValidationResult(
                passed=True,
                stage=ValidationStage.SECRET_SCAN,
                message="Secret scanning disabled",
            )

        # Scan for secrets
        if auto_scrub:
            scrubbed, detections = self.secret_scanner.scrub(content, min_confidence)
        else:
            detections = self.secret_scanner.detect(content)
            detections = [d for d in detections if d.confidence >= min_confidence]
            scrubbed = None

        if detections:
            self._metrics["secrets_detected"] += len(detections)

        # Check if passed
        passed = len(detections) == 0 or auto_scrub

        return ValidationResult(
            passed=passed,
            stage=ValidationStage.SECRET_SCAN,
            violations=detections,
            scrubbed_content=scrubbed,
            message=f"Found {len(detections)} secrets" if detections else "Clean",
        )

    def validate_licenses(
        self,
        dependencies: dict[str, str],  # {package: license_text}
    ) -> ValidationResult:
        """
        Validate dependency licenses.

        Args:
            dependencies: Dict mapping package to license text

        Returns:
            Validation result
        """
        self._metrics["total_validations"] += 1

        if not self.license_checker or not self.config.enable_license_checking:
            return ValidationResult(
                passed=True,
                stage=ValidationStage.LICENSE_CHECK,
                message="License checking disabled",
            )

        # Scan dependencies
        violations = self.license_checker.scan_dependencies(dependencies)

        if violations:
            self._metrics["license_violations"] += len(violations)

        # Check if blocked
        blocked = any(v.action == PolicyAction.BLOCK for v in violations)

        # In strict mode, fail on any violation
        if self.config.strict_mode:
            passed = len(violations) == 0
        else:
            passed = not blocked

        return ValidationResult(
            passed=passed,
            stage=ValidationStage.LICENSE_CHECK,
            violations=violations,
            message=f"Found {len(violations)} violations, {sum(1 for v in violations if v.action == PolicyAction.BLOCK)} blocked"
            if violations
            else "All licenses compliant",
        )

    def validate_action(
        self,
        action_type: ActionType,
        target: str,
        description: str,
        context: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> ValidationResult:
        """
        Validate dangerous action.

        Args:
            action_type: Type of action
            target: Target of action
            description: Human-readable description
            context: Additional context
            request_id: Optional request ID

        Returns:
            Validation result
        """
        self._metrics["total_validations"] += 1

        if not self.action_gate or not self.config.enable_action_gating:
            return ValidationResult(
                passed=True,
                stage=ValidationStage.ACTION_GATE,
                message="Action gating disabled",
            )

        # Request approval
        status, reason = self.action_gate.request_approval(
            action_type=action_type,
            target=target,
            description=description,
            context=context,
            request_id=request_id,
        )

        # Update metrics
        if status == ApprovalStatus.APPROVED or status == ApprovalStatus.AUTO_APPROVED:
            self._metrics["actions_approved"] += 1
        elif status == ApprovalStatus.REJECTED:
            self._metrics["actions_blocked"] += 1

        # Determine if passed
        passed = status in (ApprovalStatus.APPROVED, ApprovalStatus.AUTO_APPROVED)

        return ValidationResult(
            passed=passed,
            stage=ValidationStage.ACTION_GATE,
            violations=[{"status": status.value, "reason": reason}],
            message=reason or f"Action {status.value}",
        )

    def validate_pipeline(
        self,
        ctx: ValidationContext,
    ) -> list[ValidationResult]:
        """
        Run full validation pipeline.

        Args:
            ctx: Validation context

        Returns:
            List of validation results
        """
        results = []

        # Stage 1: Secret scanning
        if ctx.content and self.config.enable_secret_scanning:
            result = self.validate_content(ctx.content)
            results.append(result)

            # Stop if failed in strict mode
            if not result.passed and self.config.strict_mode:
                return results

        # Stage 2: License checking
        if ctx.dependencies and self.config.enable_license_checking:
            result = self.validate_licenses(ctx.dependencies)
            results.append(result)

            # Stop if failed in strict mode
            if not result.passed and self.config.strict_mode:
                return results

        # Stage 3: Action gating
        if ctx.action_type and self.config.enable_action_gating:
            result = self.validate_action(
                action_type=ctx.action_type,
                target=ctx.file_path or "",
                description=ctx.metadata.get("description", "") if ctx.metadata else "",
                context=ctx.metadata,
            )
            results.append(result)

        return results

    def is_safe(self, results: list[ValidationResult]) -> bool:
        """
        Check if all validations passed.

        Args:
            results: Validation results

        Returns:
            True if all passed
        """
        return all(r.passed for r in results)

    def get_metrics(self) -> dict[str, int]:
        """Get safety metrics"""
        return self._metrics.copy()

    def reset_metrics(self) -> None:
        """Reset metrics"""
        self._metrics = {
            "total_validations": 0,
            "secrets_detected": 0,
            "license_violations": 0,
            "actions_blocked": 0,
            "actions_approved": 0,
        }

    # ========================================================================
    # Delegation to Ports (convenience methods)
    # ========================================================================

    def add_whitelist(self, *values: str) -> None:
        """Add values to scrubber whitelist"""
        if self.secret_scanner:
            self.secret_scanner.add_to_whitelist(*values)

    def add_blacklist(self, *values: str) -> None:
        """Add values to scrubber blacklist"""
        if self.secret_scanner:
            self.secret_scanner.add_to_blacklist(*values)

    def approve_pending_action(
        self,
        request_id: str,
        approver: str,
        reason: str | None = None,
    ) -> bool:
        """Approve pending action"""
        if not self.action_gate:
            return False
        return self.action_gate.approve(request_id, approver, reason)

    def reject_pending_action(
        self,
        request_id: str,
        approver: str,
        reason: str | None = None,
    ) -> bool:
        """Reject pending action"""
        if not self.action_gate:
            return False
        return self.action_gate.reject(request_id, approver, reason)

    def get_pending_actions(self):
        """Get pending action requests"""
        if not self.action_gate:
            return []
        return self.action_gate.get_pending_requests()

    def cleanup(self) -> dict[str, int]:
        """
        Cleanup timed out requests and return stats.

        Returns:
            Cleanup statistics
        """
        stats = {"timeouts_cleaned": 0}

        if self.action_gate:
            stats["timeouts_cleaned"] = self.action_gate.cleanup_timeouts()

        return stats
