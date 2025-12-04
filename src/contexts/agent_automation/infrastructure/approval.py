"""
Human Approval System for Agent Operations

Provides human-in-the-loop approval for:
- Code changes
- Destructive operations
- High-risk tool executions
- Mode transitions

Supports multiple approval channels:
- WebSocket (real-time)
- HTTP callback
- CLI prompt
"""

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.contexts.agent_automation.infrastructure.types import ApprovalLevel, Change
from src.infra.observability import get_logger

logger = get_logger(__name__)


class ApprovalStatus(Enum):
    """Status of approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class ApprovalChannel(Enum):
    """Channel for approval delivery."""

    WEBSOCKET = "websocket"
    HTTP_CALLBACK = "http_callback"
    CLI = "cli"
    AUTO = "auto"  # Auto-approve based on policy


@dataclass
class ApprovalRequest:
    """Request for human approval."""

    request_id: str
    level: ApprovalLevel
    title: str
    description: str
    changes: list[Change] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    timeout_seconds: float = 300.0  # 5 minutes default
    channel: ApprovalChannel = ApprovalChannel.WEBSOCKET

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "level": self.level.value,
            "title": self.title,
            "description": self.description,
            "changes": [
                {
                    "file_path": c.file_path,
                    "change_type": c.change_type,
                    "content_preview": c.content[:200] if c.content else None,
                }
                for c in self.changes
            ],
            "metadata": self.metadata,
            "created_at": self.created_at,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class ApprovalResponse:
    """Response to approval request."""

    request_id: str
    status: ApprovalStatus
    approver: str | None = None
    comment: str | None = None
    responded_at: float = field(default_factory=time.time)


class ApprovalPolicy:
    """Policy for auto-approval decisions."""

    def __init__(
        self,
        auto_approve_levels: set[ApprovalLevel] | None = None,
        max_auto_approve_files: int = 3,
        blocked_paths: list[str] | None = None,
    ):
        """
        Initialize approval policy.

        Args:
            auto_approve_levels: Levels that can be auto-approved
            max_auto_approve_files: Max files for auto-approval
            blocked_paths: Paths that always require approval
        """
        self.auto_approve_levels = auto_approve_levels or {ApprovalLevel.LOW}
        self.max_auto_approve_files = max_auto_approve_files
        self.blocked_paths = blocked_paths or [
            ".env",
            "secrets",
            "credentials",
            ".git/config",
        ]

    def can_auto_approve(self, request: ApprovalRequest) -> bool:
        """Check if request can be auto-approved."""
        # Check level
        if request.level not in self.auto_approve_levels:
            return False

        # Check file count
        if len(request.changes) > self.max_auto_approve_files:
            return False

        # Check blocked paths
        for change in request.changes:
            for blocked in self.blocked_paths:
                if blocked in change.file_path:
                    return False

        return True


class ApprovalManager:
    """
    Manages approval requests and responses.

    Features:
    - Multiple approval channels
    - Timeout handling
    - Policy-based auto-approval
    - Request history

    Usage:
        manager = ApprovalManager()

        # Create request
        request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            level=ApprovalLevel.MEDIUM,
            title="Apply code changes",
            description="Modify 3 files",
            changes=changes,
        )

        # Wait for approval
        response = await manager.request_approval(request)

        if response.status == ApprovalStatus.APPROVED:
            # Apply changes
            ...
    """

    def __init__(
        self,
        policy: ApprovalPolicy | None = None,
        websocket_handler: Callable | None = None,
        http_callback_url: str | None = None,
    ):
        """
        Initialize approval manager.

        Args:
            policy: Approval policy for auto-approval
            websocket_handler: Handler for WebSocket notifications
            http_callback_url: URL for HTTP callbacks
        """
        self.policy = policy or ApprovalPolicy()
        self._websocket_handler = websocket_handler
        self._http_callback_url = http_callback_url

        self._pending: dict[str, ApprovalRequest] = {}
        self._responses: dict[str, asyncio.Future[ApprovalResponse]] = {}
        self._history: list[tuple[ApprovalRequest, ApprovalResponse]] = []

    async def request_approval(
        self,
        request: ApprovalRequest,
    ) -> ApprovalResponse:
        """
        Request approval and wait for response.

        Args:
            request: Approval request

        Returns:
            ApprovalResponse with status
        """
        # Check auto-approval policy
        if self.policy.can_auto_approve(request):
            logger.info(
                "auto_approved",
                request_id=request.request_id,
                level=request.level.value,
            )
            return ApprovalResponse(
                request_id=request.request_id,
                status=ApprovalStatus.APPROVED,
                approver="auto_policy",
                comment="Auto-approved by policy",
            )

        # Create future for response
        future: asyncio.Future[ApprovalResponse] = asyncio.Future()
        self._pending[request.request_id] = request
        self._responses[request.request_id] = future

        # Send notification via appropriate channel
        await self._send_notification(request)

        logger.info(
            "approval_requested",
            request_id=request.request_id,
            level=request.level.value,
            channel=request.channel.value,
        )

        try:
            # Wait for response with timeout
            response = await asyncio.wait_for(
                future,
                timeout=request.timeout_seconds,
            )
            self._history.append((request, response))
            return response

        except asyncio.TimeoutError:
            logger.warning(
                "approval_timeout",
                request_id=request.request_id,
                timeout=request.timeout_seconds,
            )
            response = ApprovalResponse(
                request_id=request.request_id,
                status=ApprovalStatus.TIMEOUT,
            )
            self._history.append((request, response))
            return response

        finally:
            self._pending.pop(request.request_id, None)
            self._responses.pop(request.request_id, None)

    async def _send_notification(self, request: ApprovalRequest) -> None:
        """Send approval notification via configured channel."""
        if request.channel == ApprovalChannel.WEBSOCKET:
            await self._notify_websocket(request)
        elif request.channel == ApprovalChannel.HTTP_CALLBACK:
            await self._notify_http(request)
        elif request.channel == ApprovalChannel.CLI:
            await self._notify_cli(request)

    async def _notify_websocket(self, request: ApprovalRequest) -> None:
        """Send WebSocket notification."""
        if self._websocket_handler:
            try:
                await self._websocket_handler(
                    {
                        "type": "approval_request",
                        "data": request.to_dict(),
                    }
                )
            except Exception as e:
                logger.error("websocket_notification_failed", error=str(e))

    async def _notify_http(self, request: ApprovalRequest) -> None:
        """Send HTTP callback notification."""
        if not self._http_callback_url:
            return

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                await client.post(
                    self._http_callback_url,
                    json={
                        "type": "approval_request",
                        "data": request.to_dict(),
                    },
                    timeout=10.0,
                )
        except Exception as e:
            logger.error("http_notification_failed", error=str(e))

    async def _notify_cli(self, request: ApprovalRequest) -> None:
        """Print CLI prompt for approval."""
        print("\n" + "=" * 60)
        print(f"APPROVAL REQUIRED: {request.title}")
        print("=" * 60)
        print(f"Level: {request.level.value}")
        print(f"Description: {request.description}")

        if request.changes:
            print(f"\nChanges ({len(request.changes)} files):")
            for change in request.changes[:5]:  # Show first 5
                print(f"  - {change.file_path} ({change.change_type})")
            if len(request.changes) > 5:
                print(f"  ... and {len(request.changes) - 5} more")

        print(f"\nRequest ID: {request.request_id}")
        print(f"Timeout: {request.timeout_seconds}s")
        print("=" * 60)

    def submit_response(
        self,
        request_id: str,
        approved: bool,
        approver: str | None = None,
        comment: str | None = None,
    ) -> bool:
        """
        Submit approval response.

        Args:
            request_id: ID of the request
            approved: Whether approved
            approver: Who approved
            comment: Optional comment

        Returns:
            True if response was accepted
        """
        if request_id not in self._responses:
            logger.warning("response_for_unknown_request", request_id=request_id)
            return False

        future = self._responses[request_id]
        if future.done():
            return False

        response = ApprovalResponse(
            request_id=request_id,
            status=ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
            approver=approver,
            comment=comment,
        )

        future.set_result(response)

        logger.info(
            "approval_response_submitted",
            request_id=request_id,
            status=response.status.value,
            approver=approver,
        )

        return True

    def cancel_request(self, request_id: str) -> bool:
        """
        Cancel pending approval request.

        Args:
            request_id: ID of the request

        Returns:
            True if cancelled
        """
        if request_id not in self._responses:
            return False

        future = self._responses[request_id]
        if future.done():
            return False

        response = ApprovalResponse(
            request_id=request_id,
            status=ApprovalStatus.CANCELLED,
        )
        future.set_result(response)

        return True

    def get_pending_requests(self) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        return list(self._pending.values())

    def get_history(
        self,
        limit: int = 100,
    ) -> list[tuple[ApprovalRequest, ApprovalResponse]]:
        """Get approval history."""
        return self._history[-limit:]

    def clear_history(self) -> None:
        """Clear approval history."""
        self._history.clear()


def create_approval_request(
    level: ApprovalLevel,
    title: str,
    description: str,
    changes: list[Change] | None = None,
    **kwargs,
) -> ApprovalRequest:
    """
    Helper to create approval request.

    Args:
        level: Approval level
        title: Request title
        description: Description
        changes: Optional list of changes
        **kwargs: Additional metadata

    Returns:
        ApprovalRequest instance
    """
    return ApprovalRequest(
        request_id=str(uuid.uuid4()),
        level=level,
        title=title,
        description=description,
        changes=changes or [],
        metadata=kwargs,
    )
