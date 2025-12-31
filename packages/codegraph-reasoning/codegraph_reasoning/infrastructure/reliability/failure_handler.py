"""
Failure Handler with Recovery Strategies (RFC-102)

Handles reasoning failures with graceful degradation.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class FailureType(Enum):
    """Taxonomy of reasoning failures."""

    # LLM failures
    LLM_TIMEOUT = "llm_timeout"
    LLM_PARSE_ERROR = "llm_parse_error"
    LLM_RATE_LIMIT = "llm_rate_limit"
    LLM_LOW_CONFIDENCE = "llm_low_confidence"

    # Verification failures
    TYPE_CHECK_FAILED = "type_check_failed"
    EFFECT_CHECK_FAILED = "effect_check_failed"
    INTENT_PRESERVATION_UNCERTAIN = "intent_preservation_uncertain"

    # Patch failures
    PATCH_CONFLICT = "patch_conflict"
    PATCH_TOO_BROAD = "patch_too_broad"
    PATCH_UNSTABLE = "patch_unstable"

    # Evidence failures
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    CANDIDATE_OVERFLOW = "candidate_overflow"


@dataclass
class FailureRecovery:
    """Recovery strategy for a failure."""

    strategy: str  # "downgrade" | "expand_evidence" | "user_gate" | "fail_open" | "fail_closed"
    fallback_method: Optional[str]  # e.g., "rule_based", "graph_only"
    escalation: bool  # Escalate to user?
    retry_allowed: bool  # Allow retry?
    max_retries: int = 0  # Max retry count (usually 0 or 1)


# Failure → Recovery mapping
FAILURE_RECOVERY_MAP: dict[FailureType, FailureRecovery] = {
    # LLM failures → Downgrade to rule-based
    FailureType.LLM_TIMEOUT: FailureRecovery(
        strategy="downgrade",
        fallback_method="rule_based",
        escalation=False,
        retry_allowed=False,  # No retry (causes drift)
        max_retries=0,
    ),
    FailureType.LLM_PARSE_ERROR: FailureRecovery(
        strategy="downgrade",
        fallback_method="rule_based",
        escalation=False,
        retry_allowed=False,
        max_retries=0,
    ),
    FailureType.LLM_RATE_LIMIT: FailureRecovery(
        strategy="downgrade",
        fallback_method="graph_only",  # Use graph pre-ranking only
        escalation=False,
        retry_allowed=True,  # Can retry after backoff
        max_retries=1,
    ),
    FailureType.LLM_LOW_CONFIDENCE: FailureRecovery(
        strategy="expand_evidence",  # Gather more evidence before LLM
        fallback_method="graph_expansion",
        escalation=False,
        retry_allowed=False,
        max_retries=0,
    ),
    # Verification failures → User gate or fail-closed
    FailureType.TYPE_CHECK_FAILED: FailureRecovery(
        strategy="fail_closed",  # Reject patch
        fallback_method=None,
        escalation=True,  # Tell user why
        retry_allowed=False,
        max_retries=0,
    ),
    FailureType.EFFECT_CHECK_FAILED: FailureRecovery(
        strategy="user_gate",  # Require user approval
        fallback_method=None,
        escalation=True,
        retry_allowed=False,
        max_retries=0,
    ),
    FailureType.INTENT_PRESERVATION_UNCERTAIN: FailureRecovery(
        strategy="user_gate",
        fallback_method=None,
        escalation=True,
        retry_allowed=False,
        max_retries=0,
    ),
    # Patch failures
    FailureType.PATCH_CONFLICT: FailureRecovery(
        strategy="fail_closed",
        fallback_method=None,
        escalation=True,
        retry_allowed=False,
        max_retries=0,
    ),
    FailureType.PATCH_TOO_BROAD: FailureRecovery(
        strategy="fail_closed",
        fallback_method="minimal_patch_mode",  # Try minimal changes only
        escalation=True,
        retry_allowed=False,
        max_retries=0,
    ),
    FailureType.PATCH_UNSTABLE: FailureRecovery(
        strategy="user_gate",  # Unstable patch → human review
        fallback_method=None,
        escalation=True,
        retry_allowed=False,
        max_retries=0,
    ),
    # Evidence failures → UNDECIDABLE
    FailureType.INSUFFICIENT_EVIDENCE: FailureRecovery(
        strategy="expand_evidence",
        fallback_method="slice_expansion",
        escalation=False,
        retry_allowed=False,
        max_retries=0,
    ),
    FailureType.CONFLICTING_EVIDENCE: FailureRecovery(
        strategy="expand_evidence",
        fallback_method="quorum_consensus",
        escalation=False,
        retry_allowed=False,
        max_retries=0,
    ),
    FailureType.CANDIDATE_OVERFLOW: FailureRecovery(
        strategy="expand_evidence",
        fallback_method="graph_pruning",  # Use graph to prune candidates
        escalation=False,
        retry_allowed=False,
        max_retries=0,
    ),
}


@dataclass
class RecoveryResult:
    """Result of failure recovery."""

    success: bool
    result: Optional[Any] = None
    method: Optional[str] = None
    warning: Optional[str] = None
    error: Optional[str] = None
    escalation_required: bool = False
    retry_recommended: bool = False
    expanded_evidence: Optional[Any] = None
    confidence: float = 1.0


class FailureHandler:
    """Handles reasoning failures with recovery strategies."""

    def handle_failure(self, failure_type: FailureType, context: dict) -> RecoveryResult:
        """
        Handle a reasoning failure.

        Args:
            failure_type: Type of failure
            context: Failure context (error, candidates, evidence, etc.)

        Returns:
            RecoveryResult with recovery action
        """
        recovery = FAILURE_RECOVERY_MAP[failure_type]

        if recovery.strategy == "downgrade":
            return self._downgrade(recovery.fallback_method, context)

        elif recovery.strategy == "expand_evidence":
            return self._expand_evidence(recovery.fallback_method, context)

        elif recovery.strategy == "user_gate":
            return self._escalate_to_user(failure_type, context)

        elif recovery.strategy == "fail_closed":
            return RecoveryResult(
                success=False,
                error=f"Failed: {failure_type.value}",
                escalation_required=recovery.escalation,
            )

        elif recovery.strategy == "fail_open":
            # Fail-open: Accept with warning
            return RecoveryResult(
                success=True,
                warning=f"Accepted despite failure: {failure_type.value}",
                confidence=0.5,  # Low confidence
            )

        # Unknown strategy
        return RecoveryResult(success=False, error=f"Unknown recovery strategy: {recovery.strategy}")

    def _downgrade(self, fallback_method: Optional[str], context: dict) -> RecoveryResult:
        """Downgrade to fallback method."""
        if fallback_method == "rule_based":
            # Use rule-based analysis only
            return RecoveryResult(
                success=True,
                result="rule_based_fallback",
                method="rule_based_fallback",
                warning="Downgraded to rule-based due to LLM failure",
            )

        elif fallback_method == "graph_only":
            # Use graph pre-ranking only (no LLM)
            return RecoveryResult(
                success=True,
                result="graph_only_fallback",
                method="graph_only_fallback",
                warning="Using graph analysis only (LLM unavailable)",
            )

        else:
            return RecoveryResult(success=False, error=f"Unknown fallback method: {fallback_method}")

    def _expand_evidence(self, expansion_method: Optional[str], context: dict) -> RecoveryResult:
        """Expand evidence before retrying."""
        if expansion_method == "graph_expansion":
            # Expand call graph 2-hop (placeholder)
            return RecoveryResult(
                success=True,
                expanded_evidence="graph_2hop_expanded",
                method="graph_expansion",
                retry_recommended=True,
            )

        elif expansion_method == "slice_expansion":
            # Expand backward slice (placeholder)
            return RecoveryResult(
                success=True,
                expanded_evidence="slice_expanded",
                method="slice_expansion",
                retry_recommended=True,
            )

        elif expansion_method == "quorum_consensus":
            # Try to reach consensus among conflicting analyzers
            return RecoveryResult(
                success=True,
                result="quorum_consensus",
                method="quorum_consensus",
                warning="Resolved conflict via quorum voting",
            )

        elif expansion_method == "graph_pruning":
            # Prune candidates using graph analysis
            return RecoveryResult(
                success=True,
                expanded_evidence="candidates_pruned",
                method="graph_pruning",
                retry_recommended=True,
            )

        else:
            return RecoveryResult(success=False, error=f"Unknown expansion method: {expansion_method}")

    def _escalate_to_user(self, failure_type: FailureType, context: dict) -> RecoveryResult:
        """Escalate to user for decision."""
        return RecoveryResult(
            success=False,
            error=f"User approval required: {failure_type.value}",
            escalation_required=True,
        )


class LLMTimeoutError(Exception):
    """Raised when LLM call times out."""

    pass
