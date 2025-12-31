"""
Dangerous Action Gate Adapter

Risk classification and human approval workflow.
Implements ActionGatePort.

SOLID: Single Responsibility - only handles action gating logic.
Hexagonal: Adapter implementing Port, can be replaced with Slack/Email approval, etc.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from apps.orchestrator.orchestrator.domain.safety.models import (
    ActionRequest,
    ActionType,
    ApprovalRecord,
    ApprovalStatus,
    RiskLevel,
)
from apps.orchestrator.orchestrator.domain.safety.policies import GateConfig


class RiskClassifier:
    """
    Classify risk level of actions.

    Stateless service (all static methods).
    """

    # Risk rules (pattern → risk level)
    CRITICAL_PATTERNS = {
        ActionType.FILE_DELETE: [
            r"\.git/",
            r"\.env",
            r"database\.db",
            r"\.ssh/",
        ],
        ActionType.SHELL_COMMAND: [
            r"rm\s+-rf\s+/",
            r"dd\s+if=",
            r"mkfs",
            r"curl.*\|\s*bash",
        ],
        ActionType.DATABASE_DELETE: [
            r"DROP\s+DATABASE",
            r"TRUNCATE\s+TABLE",
        ],
    }

    HIGH_PATTERNS = {
        ActionType.FILE_DELETE: [r"\.py$", r"\.js$", r"\.ts$"],
        ActionType.SHELL_COMMAND: [
            r"sudo",
            r"chmod.*777",
            r"wget",
            r"curl",
        ],
        ActionType.DATABASE_WRITE: [r"UPDATE.*WHERE\s+1=1"],
        ActionType.NETWORK_REQUEST: [r"http://"],  # Non-HTTPS
    }

    MEDIUM_PATTERNS = {
        ActionType.FILE_WRITE: [r"\.py$", r"\.js$", r"\.ts$"],
        ActionType.CODE_GENERATION: [r".*"],  # All code gen is medium risk
    }

    @classmethod
    def classify(
        cls,
        action_type: ActionType,
        target: str,
        context: dict[str, Any] | None = None,
    ) -> RiskLevel:
        """
        Classify risk level.

        Args:
            action_type: Type of action
            target: Target of action (file path, command, etc.)
            context: Additional context (may contain 'cmd', 'command', 'description')

        Returns:
            Risk level
        """
        # Input validation
        if target is None:
            target = ""
        if not isinstance(target, str):
            target = str(target)

        context = context or {}

        # Collect all text to check (target + context values)
        # CRITICAL FIX: Also check description, cmd, command in context
        text_to_check = [target]
        for key in ["description", "cmd", "command", "content"]:
            if key in context and context[key]:
                value = context[key]
                if isinstance(value, str):
                    text_to_check.append(value)
                else:
                    text_to_check.append(str(value))

        # Check critical patterns
        if action_type in cls.CRITICAL_PATTERNS:
            for pattern in cls.CRITICAL_PATTERNS[action_type]:
                for text in text_to_check:
                    if re.search(pattern, text, re.IGNORECASE):
                        return RiskLevel.CRITICAL

        # Check high patterns
        if action_type in cls.HIGH_PATTERNS:
            for pattern in cls.HIGH_PATTERNS[action_type]:
                for text in text_to_check:
                    if re.search(pattern, text, re.IGNORECASE):
                        return RiskLevel.HIGH

        # Check medium patterns
        if action_type in cls.MEDIUM_PATTERNS:
            for pattern in cls.MEDIUM_PATTERNS[action_type]:
                for text in text_to_check:
                    if re.search(pattern, text, re.IGNORECASE):
                        return RiskLevel.MEDIUM

        # Default to low
        return RiskLevel.LOW


class DangerousActionGateAdapter:
    """
    Dangerous action gate with human approval.

    Implements: ActionGatePort

    Features:
    - Risk classification (Low/Med/High/Critical)
    - Human approval workflow
    - Auto-approval rules (whitelist)
    - Approval history
    - Timeout handling
    - Audit trail
    """

    def __init__(
        self,
        config: GateConfig | None = None,
        approval_callback: Callable[[ActionRequest], bool] | None = None,
    ):
        self.config = config or GateConfig()
        self.approval_callback = approval_callback
        self._pending_requests: dict[str, ActionRequest] = {}
        self._approval_history: list[ApprovalRecord] = []
        self._audit_trail: list[dict[str, Any]] = []

    def request_approval(
        self,
        action_type: ActionType,
        target: str,
        description: str,
        context: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> tuple[ApprovalStatus, str | None]:
        """
        Request approval for action.

        Port: ActionGatePort.request_approval()

        Args:
            action_type: Type of action
            target: Target (file, command, etc.)
            description: Human-readable description
            context: Additional context
            request_id: Optional request ID

        Returns:
            Tuple of (status, reason)
        """
        # Input validation
        if target is None:
            target = ""
        if description is None:
            description = ""
        if not isinstance(target, str):
            target = str(target)
        if not isinstance(description, str):
            description = str(description)

        request_id = request_id or str(uuid.uuid4())
        context = context or {}

        # Classify risk (pass description in context for pattern matching)
        risk_level = RiskClassifier.classify(action_type, target, {**context, "description": description})

        # Create request
        timeout = (
            self.config.critical_timeout_seconds
            if risk_level == RiskLevel.CRITICAL
            else self.config.default_timeout_seconds
        )

        request = ActionRequest(
            id=request_id,
            action_type=action_type,
            description=description,
            risk_level=risk_level,
            context={"target": target, **context},
            timeout_seconds=timeout,
        )

        # Check auto-approval rules
        auto_approved, rule = self._check_auto_approval(request)
        if auto_approved:
            record = ApprovalRecord(
                request_id=request_id,
                status=ApprovalStatus.AUTO_APPROVED,
                auto_approved_by_rule=rule,
            )
            self._record_approval(record)
            self._audit(request, record)
            return ApprovalStatus.AUTO_APPROVED, f"Auto-approved by rule: {rule}"

        # Check blacklist
        if self._is_blacklisted(request):
            record = ApprovalRecord(
                request_id=request_id,
                status=ApprovalStatus.REJECTED,
                reason="Blacklisted action",
            )
            self._record_approval(record)
            self._audit(request, record)
            return ApprovalStatus.REJECTED, "Action is blacklisted"

        # Require human approval
        self._pending_requests[request_id] = request

        if self.approval_callback:
            # Synchronous approval
            approved = self.approval_callback(request)
            status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
            record = ApprovalRecord(
                request_id=request_id,
                status=status,
                approver="callback",
                reason="Manual review" if approved else "Rejected by reviewer",
            )
            self._record_approval(record)
            self._audit(request, record)
            return status, record.reason
        else:
            # Async approval - caller must poll
            return ApprovalStatus.PENDING, "Awaiting approval"

    def _check_auto_approval(self, request: ActionRequest) -> tuple[bool, str | None]:
        """Check if request can be auto-approved"""
        # Auto-approve low risk
        if request.risk_level == RiskLevel.LOW and self.config.auto_approve_low_risk:
            return True, "low_risk_auto_approve"

        # Auto-approve medium risk if configured
        if request.risk_level == RiskLevel.MEDIUM and self.config.auto_approve_medium_risk:
            return True, "medium_risk_auto_approve"

        # Check whitelist
        target = request.context.get("target", "")

        if request.action_type == ActionType.FILE_WRITE:
            for pattern in self.config.file_write_whitelist:
                try:
                    if re.search(pattern, target):
                        return True, f"file_write_whitelist:{pattern}"
                except re.error:
                    # Skip invalid regex patterns
                    continue

        if request.action_type == ActionType.SHELL_COMMAND:
            for pattern in self.config.command_whitelist:
                try:
                    if re.search(pattern, target):
                        return True, f"command_whitelist:{pattern}"
                except re.error:
                    continue

        if request.action_type == ActionType.NETWORK_REQUEST:
            for pattern in self.config.domain_whitelist:
                try:
                    if re.search(pattern, target):
                        return True, f"domain_whitelist:{pattern}"
                except re.error:
                    continue

        return False, None

    def _is_blacklisted(self, request: ActionRequest) -> bool:
        """Check if request is blacklisted"""
        import fnmatch

        target = request.context.get("target", "")

        if request.action_type == ActionType.FILE_DELETE:
            for pattern in self.config.file_delete_blacklist:
                # Use fnmatch for glob patterns
                if fnmatch.fnmatch(target, pattern):
                    return True

        if request.action_type == ActionType.SHELL_COMMAND:
            for pattern in self.config.command_blacklist:
                # Simple substring match for commands
                if pattern in target:
                    return True

        return False

    def approve(
        self,
        request_id: str,
        approver: str,
        reason: str | None = None,
    ) -> bool:
        """
        Approve pending request.

        Port: ActionGatePort.approve()

        Args:
            request_id: Request ID
            approver: Approver identifier
            reason: Approval reason

        Returns:
            True if approved
        """
        if request_id not in self._pending_requests:
            return False

        request = self._pending_requests[request_id]

        # Check timeout
        if self._is_timeout(request):
            record = ApprovalRecord(
                request_id=request_id,
                status=ApprovalStatus.TIMEOUT,
                reason="Approval timeout",
            )
            self._record_approval(record)
            self._audit(request, record)
            del self._pending_requests[request_id]
            return False

        # Approve
        record = ApprovalRecord(
            request_id=request_id,
            status=ApprovalStatus.APPROVED,
            approver=approver,
            reason=reason or "Manual approval",
        )
        self._record_approval(record)
        self._audit(request, record)
        del self._pending_requests[request_id]
        return True

    def reject(
        self,
        request_id: str,
        approver: str,
        reason: str | None = None,
    ) -> bool:
        """
        Reject pending request.

        Port: ActionGatePort.reject()

        Args:
            request_id: Request ID
            approver: Approver identifier
            reason: Rejection reason

        Returns:
            True if rejected
        """
        if request_id not in self._pending_requests:
            return False

        request = self._pending_requests[request_id]

        record = ApprovalRecord(
            request_id=request_id,
            status=ApprovalStatus.REJECTED,
            approver=approver,
            reason=reason or "Manual rejection",
        )
        self._record_approval(record)
        self._audit(request, record)
        del self._pending_requests[request_id]
        return True

    def get_status(self, request_id: str) -> ApprovalStatus | None:
        """
        Get approval status.

        Port: ActionGatePort.get_status()
        """
        # Check history
        for record in reversed(self._approval_history):
            if record.request_id == request_id:
                return record.status

        # Check pending
        if request_id in self._pending_requests:
            request = self._pending_requests[request_id]
            if self._is_timeout(request):
                return ApprovalStatus.TIMEOUT
            return ApprovalStatus.PENDING

        return None

    @staticmethod
    def _is_timeout(request: ActionRequest) -> bool:
        """Check if request has timed out"""
        elapsed = (datetime.now() - request.timestamp).total_seconds()
        return elapsed > request.timeout_seconds

    def _record_approval(self, record: ApprovalRecord) -> None:
        """Record approval in history"""
        self._approval_history.append(record)

    def _audit(self, request: ActionRequest, record: ApprovalRecord) -> None:
        """Add to audit trail"""
        if not self.config.enable_audit:
            return

        self._audit_trail.append(
            {
                "timestamp": datetime.now().isoformat(),
                "request_id": request.id,
                "action_type": request.action_type.value,
                "risk_level": request.risk_level.value,
                "description": request.description,
                "context": request.context,
                "status": record.status.value,
                "approver": record.approver,
                "reason": record.reason,
            }
        )

    def get_audit_trail(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get audit trail (helper method, not in Port)"""
        if not start_time and not end_time:
            return self._audit_trail.copy()

        filtered = []
        for entry in self._audit_trail:
            timestamp = datetime.fromisoformat(entry["timestamp"])
            if start_time and timestamp < start_time:
                continue
            if end_time and timestamp > end_time:
                continue
            filtered.append(entry)

        return filtered

    def get_pending_requests(self) -> list[ActionRequest]:
        """
        Get all pending requests.

        Port: ActionGatePort.get_pending_requests()
        """
        return list(self._pending_requests.values())

    def cleanup_timeouts(self) -> int:
        """
        Cleanup timed out requests.

        Port: ActionGatePort.cleanup_timeouts()

        Returns:
            Number of requests cleaned up
        """
        to_remove = []

        for request_id, request in self._pending_requests.items():
            if self._is_timeout(request):
                record = ApprovalRecord(
                    request_id=request_id,
                    status=ApprovalStatus.TIMEOUT,
                    reason="Approval timeout",
                )
                self._record_approval(record)
                self._audit(request, record)
                to_remove.append(request_id)

        for request_id in to_remove:
            del self._pending_requests[request_id]

        return len(to_remove)
