"""Approval UI - CLI-based approval interface."""

from dataclasses import dataclass
from enum import Enum

from src.infra.observability import get_logger

logger = get_logger(__name__)


class ApprovalDecision(str, Enum):
    """Approval decision."""

    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"  # Need more info


@dataclass
class ApprovalRequest:
    """Request for human approval."""

    patch_id: str
    file_path: str
    description: str
    risk_level: str
    reasons: list[str]
    diff_preview: str


class ApprovalUI:
    """CLI-based approval interface.

    Displays diffs and prompts for approval in terminal.
    """

    def __init__(self, interactive: bool = True):
        """Initialize approval UI.

        Args:
            interactive: Enable interactive prompts (False for testing)
        """
        self.interactive = interactive

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Request approval from user.

        Args:
            request: Approval request

        Returns:
            ApprovalDecision
        """
        if not self.interactive:
            # Non-interactive mode: auto-reject high-risk
            logger.warning(
                "non_interactive_auto_reject",
                patch_id=request.patch_id,
                risk_level=request.risk_level,
            )
            return ApprovalDecision.REJECTED

        # Display approval request
        self._display_request(request)

        # Prompt for decision
        decision = self._prompt_decision()

        logger.info(
            "approval_decision",
            patch_id=request.patch_id,
            decision=decision.value,
        )

        return decision

    def _display_request(self, request: ApprovalRequest) -> None:
        """Display approval request in terminal.

        Args:
            request: Approval request
        """
        print("\n" + "=" * 80)
        print(f"APPROVAL REQUIRED - Risk Level: {request.risk_level.upper()}")
        print("=" * 80)
        print(f"\nPatch ID: {request.patch_id}")
        print(f"File: {request.file_path}")
        print(f"Description: {request.description}")

        if request.reasons:
            print("\nReasons:")
            for reason in request.reasons:
                print(f"  - {reason}")

        print("\nDiff Preview:")
        print("-" * 80)
        print(request.diff_preview[:1000])  # First 1000 chars
        if len(request.diff_preview) > 1000:
            print(f"\n... ({len(request.diff_preview) - 1000} more characters)")
        print("-" * 80)

    def _prompt_decision(self) -> ApprovalDecision:
        """Prompt user for approval decision.

        Returns:
            ApprovalDecision
        """
        while True:
            response = input("\nApprove this change? [y/n/d (defer)]: ").strip().lower()

            if response == "y":
                return ApprovalDecision.APPROVED
            elif response == "n":
                return ApprovalDecision.REJECTED
            elif response == "d":
                return ApprovalDecision.DEFERRED
            else:
                print("Invalid input. Please enter y, n, or d.")

    async def batch_approval(self, requests: list[ApprovalRequest]) -> dict[str, ApprovalDecision]:
        """Request approval for multiple patches.

        Args:
            requests: List of approval requests

        Returns:
            Dict mapping patch_id to decision
        """
        decisions = {}

        print(f"\n{len(requests)} patches require approval\n")

        for i, request in enumerate(requests, 1):
            print(f"\n[{i}/{len(requests)}]")
            decision = await self.request_approval(request)
            decisions[request.patch_id] = decision

            if decision == ApprovalDecision.DEFERRED:
                print("Deferring remaining patches...")
                # Mark rest as deferred
                for remaining in requests[i:]:
                    decisions[remaining.patch_id] = ApprovalDecision.DEFERRED
                break

        return decisions
