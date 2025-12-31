"""
Evidence Bundle Standard Format (RFC-102)

Provides reusable evidence format for UI/CLI/MCP consumers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from .reasoning_context import ReasoningContext


class EvidenceType(Enum):
    """Types of evidence in reasoning."""

    RULE_MATCH = "rule_match"
    FORMAL_PROOF = "formal_proof"
    TYPE_CONSTRAINT = "type_constraint"
    GRAPH_PATH = "graph_path"
    SLICE_PATH = "slice_path"
    TAINT_FLOW = "taint_flow"
    CALL_SITE = "call_site"
    EFFECT_DIFF = "effect_diff"
    TEST_RESULT = "test_result"
    USER_FEEDBACK = "user_feedback"
    LLM_RANKING = "llm_ranking"


class DecisionType(Enum):
    """Reasoning decision types."""

    DECIDED = "decided"  # Clear decision with high confidence
    UNDECIDABLE = "undecidable"  # Insufficient evidence to decide
    CONFLICTING = "conflicting"  # Evidence conflicts (subtype of UNDECIDABLE)


@dataclass
class Evidence:
    """Single piece of evidence."""

    type: EvidenceType
    description: str  # Human-readable description
    confidence: float  # 0.0-1.0
    weight: float  # Importance weight (0.0-1.0)

    # Structured data (type-specific)
    data: dict[str, Any] = field(default_factory=dict)

    # Source
    analyzer: str = "unknown"  # "rule", "formal", "llm", "graph", etc.
    timestamp: datetime = field(default_factory=datetime.now)

    def to_display(self) -> str:
        """Human-readable display."""
        return f"[{self.type.value}] {self.description} (confidence: {self.confidence:.2f})"

    def to_dict(self) -> dict:
        """Export as dictionary."""
        return {
            "type": self.type.value,
            "description": self.description,
            "confidence": self.confidence,
            "weight": self.weight,
            "data": self.data,
            "analyzer": self.analyzer,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ReasoningTrace:
    """Decision provenance trace."""

    decision: str  # "is_breaking" | "best_match" | etc.
    confidence: float  # Final aggregated confidence

    # Decision path
    rule_matched: Optional[str] = None  # "GLOBAL_MUTATION_RULE" | None
    formal_proof: Optional[str] = None  # "Separation Logic proof: ..." | None
    llm_reasoning: Optional[str] = None  # LLM explanation | None

    # Evidence
    evidence: list[str] = field(default_factory=list)  # All supporting evidence
    counter_evidence: list[str] = field(default_factory=list)  # Contradicting evidence

    # Metadata
    reasoning_context: Optional[ReasoningContext] = None
    analyzed_at: datetime = field(default_factory=datetime.now)
    latency_ms: float = 0.0

    def to_audit_log(self) -> dict:
        """Export for compliance audit."""
        return {
            "decision": self.decision,
            "confidence": self.confidence,
            "rule_matched": self.rule_matched,
            "formal_proof": self.formal_proof,
            "llm_model": self.reasoning_context.llm_model_id if self.reasoning_context else None,
            "timestamp": self.analyzed_at.isoformat(),
            "evidence": self.evidence,
            "context_hash": self.reasoning_context.context_hash() if self.reasoning_context else None,
        }


@dataclass
class EvidenceBundle:
    """
    Standard evidence bundle for all reasoning results.

    Reusable across UI/CLI/MCP with consistent format.
    """

    # Decision
    decision: str  # "is_breaking", "best_match", etc.
    confidence: float  # Aggregated confidence
    decision_type: DecisionType  # DECIDED | UNDECIDABLE | CONFLICTING

    # Evidence
    supporting_evidence: list[Evidence] = field(default_factory=list)
    counter_evidence: list[Evidence] = field(default_factory=list)

    # Analysis artifacts (reusable)
    slice_ids: Optional[list[str]] = None  # PDG/DFG node IDs
    graph_paths: Optional[list[list[str]]] = None  # Call graph paths
    type_constraints: Optional[dict] = None  # Type resolution results
    effect_diff_summary: Optional[dict] = None  # Effect analysis results
    boundary_match_rationale: Optional[list[tuple[str, float]]] = None  # Top-K matches

    # Reasoning context & trace
    reasoning_context: Optional[ReasoningContext] = None
    reasoning_trace: Optional[ReasoningTrace] = None

    # Metadata
    latency_ms: float = 0.0
    cost_usd: float = 0.0  # Estimated cost (LLM calls)

    # UNDECIDABLE metadata
    undecidable_reason: Optional[str] = None
    required_information: Optional[list[str]] = None
    conservative_fallback: Optional[Any] = None

    def add_evidence(self, evidence: Evidence, is_supporting: bool = True):
        """Add evidence to bundle."""
        if is_supporting:
            self.supporting_evidence.append(evidence)
        else:
            self.counter_evidence.append(evidence)

    def is_decidable(self) -> bool:
        """Check if decision is decidable."""
        return self.decision_type == DecisionType.DECIDED

    def get_result_or_fallback(self) -> Any:
        """Get result or conservative fallback."""
        if self.is_decidable():
            return self.decision
        else:
            return self.conservative_fallback

    def to_json(self) -> dict:
        """Export as JSON for UI/CLI/MCP."""
        return {
            "decision": self.decision,
            "confidence": self.confidence,
            "decision_type": self.decision_type.value,
            "supporting_evidence": [e.to_dict() for e in self.supporting_evidence],
            "counter_evidence": [e.to_dict() for e in self.counter_evidence],
            "artifacts": {
                "slice_ids": self.slice_ids,
                "graph_paths": self.graph_paths,
                "type_constraints": self.type_constraints,
                "effect_diff_summary": self.effect_diff_summary,
                "boundary_match_rationale": self.boundary_match_rationale,
            },
            "metadata": {
                "latency_ms": self.latency_ms,
                "cost_usd": self.cost_usd,
                "context_hash": (self.reasoning_context.context_hash() if self.reasoning_context else None),
            },
            "undecidable": {
                "reason": self.undecidable_reason,
                "required_information": self.required_information,
                "conservative_fallback": self.conservative_fallback,
            }
            if not self.is_decidable()
            else None,
        }

    def to_markdown(self) -> str:
        """Export as Markdown for reports."""
        lines = [
            f"# Decision: {self.decision}",
            f"**Confidence**: {self.confidence:.2%}",
            f"**Type**: {self.decision_type.value}",
            "",
        ]

        if not self.is_decidable():
            lines.extend(
                [
                    "## UNDECIDABLE",
                    f"**Reason**: {self.undecidable_reason}",
                    "",
                    "**Required Information**:",
                ]
            )
            for info in self.required_information or []:
                lines.append(f"- {info}")
            lines.append("")
            if self.conservative_fallback:
                lines.append(f"**Conservative Fallback**: {self.conservative_fallback}")
            lines.append("")

        lines.append("## Supporting Evidence")
        for evidence in self.supporting_evidence:
            lines.append(f"- {evidence.to_display()}")

        if self.counter_evidence:
            lines.append("")
            lines.append("## Counter Evidence")
            for evidence in self.counter_evidence:
                lines.append(f"- {evidence.to_display()}")

        if self.reasoning_trace:
            lines.append("")
            lines.append("## Reasoning Trace")
            if self.reasoning_trace.rule_matched:
                lines.append(f"- **Rule**: {self.reasoning_trace.rule_matched}")
            if self.reasoning_trace.formal_proof:
                lines.append(f"- **Formal Proof**: {self.reasoning_trace.formal_proof}")
            if self.reasoning_trace.llm_reasoning:
                lines.append(f"- **LLM Reasoning**: {self.reasoning_trace.llm_reasoning}")

        return "\n".join(lines)

    def to_cli_summary(self) -> str:
        """Compact summary for CLI output."""
        status_emoji = "✓" if self.is_decidable() else "?"
        decision_str = self.decision if self.is_decidable() else "UNDECIDABLE"

        lines = [
            f"{status_emoji} {decision_str} (confidence: {self.confidence:.1%})",
            f"  Evidence: {len(self.supporting_evidence)} supporting, {len(self.counter_evidence)} counter",
        ]

        if not self.is_decidable() and self.undecidable_reason:
            lines.append(f"  Reason: {self.undecidable_reason}")

        if self.latency_ms > 0:
            lines.append(f"  Latency: {self.latency_ms:.0f}ms")

        return "\n".join(lines)
