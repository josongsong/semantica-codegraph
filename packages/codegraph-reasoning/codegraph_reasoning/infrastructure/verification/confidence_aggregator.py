"""
Confidence Aggregator (RFC-101, RFC-102)

Aggregates confidence scores from multiple analyzers with veto power.
"""

from dataclasses import dataclass
from typing import Any, Optional

from ...domain.evidence_bundle import DecisionType, Evidence, EvidenceBundle, EvidenceType


@dataclass
class AnalysisResult:
    """Result from single analyzer."""

    is_breaking: bool
    confidence: float  # 0.0-1.0
    evidence: list[str]  # Proof / reasoning trace
    analyzer: str  # "rule" | "formal" | "llm"
    data: Optional[dict[str, Any]] = None  # Additional data


class ConfidenceAggregator:
    """
    Aggregates confidence scores from multiple analyzers.

    Rules:
    1. Formal proof → confidence 0.95+ (formal veto power)
    2. All agree (same is_breaking) → weighted average
    3. Disagree → max confidence but flag as uncertain
    4. LLM cannot override rule + formal consensus
    """

    # Weights (must sum to 1.0)
    WEIGHTS = {
        "rule": 0.5,  # Fast, reliable for common cases
        "formal": 0.4,  # High confidence when applicable
        "llm": 0.1,  # Assists with edge cases
    }

    # Confidence thresholds
    HIGH_CONFIDENCE = 0.9  # Can return immediately
    LOW_CONFIDENCE = 0.5  # Needs more analysis

    def aggregate(self, results: list[AnalysisResult]) -> EvidenceBundle:
        """
        Aggregate confidence from multiple analysis results.

        Args:
            results: List of analysis results from different analyzers

        Returns:
            EvidenceBundle with aggregated decision
        """
        if not results:
            return EvidenceBundle(
                decision="unknown",
                confidence=0.0,
                decision_type=DecisionType.UNDECIDABLE,
                undecidable_reason="No analysis results provided",
            )

        # Rule 1: Formal proof has veto power
        formal_results = [r for r in results if r.analyzer == "formal"]
        if formal_results and formal_results[0].confidence >= 0.95:
            return self._create_bundle_from_formal(formal_results[0])

        # Rule 2: All agree → weighted average
        if all(r.is_breaking == results[0].is_breaking for r in results):
            return self._create_consensus_bundle(results)

        # Rule 3: Disagree → handle conflict
        return self._create_conflicting_bundle(results)

    def _create_bundle_from_formal(self, formal_result: AnalysisResult) -> EvidenceBundle:
        """Create bundle from formal proof (veto power)."""
        bundle = EvidenceBundle(
            decision="is_breaking" if formal_result.is_breaking else "is_safe",
            confidence=0.95,
            decision_type=DecisionType.DECIDED,
        )

        bundle.add_evidence(
            Evidence(
                type=EvidenceType.FORMAL_PROOF,
                description="; ".join(formal_result.evidence),
                confidence=formal_result.confidence,
                weight=1.0,  # Formal proof has full weight
                data=formal_result.data or {},
                analyzer="formal",
            )
        )

        return bundle

    def _create_consensus_bundle(self, results: list[AnalysisResult]) -> EvidenceBundle:
        """Create bundle when all analyzers agree."""
        # Calculate weighted confidence
        weighted_conf = sum(r.confidence * self.WEIGHTS.get(r.analyzer, 0.1) for r in results)

        bundle = EvidenceBundle(
            decision="is_breaking" if results[0].is_breaking else "is_safe",
            confidence=weighted_conf,
            decision_type=DecisionType.DECIDED,
        )

        # Add all evidence
        for result in results:
            evidence_type = self._get_evidence_type(result.analyzer)
            bundle.add_evidence(
                Evidence(
                    type=evidence_type,
                    description="; ".join(result.evidence),
                    confidence=result.confidence,
                    weight=self.WEIGHTS.get(result.analyzer, 0.1),
                    data=result.data or {},
                    analyzer=result.analyzer,
                )
            )

        return bundle

    def _create_conflicting_bundle(self, results: list[AnalysisResult]) -> EvidenceBundle:
        """Create bundle when analyzers disagree."""
        # Separate rule/formal from LLM
        rule_formal = [r for r in results if r.analyzer in ["rule", "formal"]]
        llm_only = [r for r in results if r.analyzer == "llm"]

        # LLM cannot override rule + formal consensus
        if len(rule_formal) >= 2 and all(r.is_breaking == rule_formal[0].is_breaking for r in rule_formal):
            # Rule + formal agree, LLM disagrees
            weighted_conf = sum(r.confidence * self.WEIGHTS.get(r.analyzer, 0.1) for r in rule_formal)

            bundle = EvidenceBundle(
                decision="is_breaking" if rule_formal[0].is_breaking else "is_safe",
                confidence=max(r.confidence for r in rule_formal),
                decision_type=DecisionType.DECIDED,
            )

            # Add rule/formal evidence
            for result in rule_formal:
                evidence_type = self._get_evidence_type(result.analyzer)
                bundle.add_evidence(
                    Evidence(
                        type=evidence_type,
                        description="; ".join(result.evidence),
                        confidence=result.confidence,
                        weight=self.WEIGHTS.get(result.analyzer, 0.1),
                        data=result.data or {},
                        analyzer=result.analyzer,
                    )
                )

            # Add LLM as counter evidence
            for result in llm_only:
                bundle.add_evidence(
                    Evidence(
                        type=EvidenceType.LLM_RANKING,
                        description="; ".join(result.evidence),
                        confidence=result.confidence,
                        weight=self.WEIGHTS["llm"],
                        data=result.data or {},
                        analyzer="llm",
                    ),
                    is_supporting=False,  # Counter evidence
                )

            return bundle

        # General conflict: Flag as CONFLICTING
        best = max(results, key=lambda r: r.confidence)

        bundle = EvidenceBundle(
            decision="unknown",
            confidence=0.0,
            decision_type=DecisionType.CONFLICTING,
            undecidable_reason=f"Analyzers conflict: {len([r for r in results if r.is_breaking])} say breaking, "
            f"{len([r for r in results if not r.is_breaking])} say safe",
            required_information=[
                "Expand backward slice to find more evidence",
                "Check additional call sites",
                "Review edge cases in type constraints",
            ],
            conservative_fallback="assume_breaking",  # Fail-safe
        )

        # Add all evidence
        for result in results:
            evidence_type = self._get_evidence_type(result.analyzer)
            is_supporting = result.is_breaking  # Arbitrarily use "breaking" as supporting
            bundle.add_evidence(
                Evidence(
                    type=evidence_type,
                    description="; ".join(result.evidence),
                    confidence=result.confidence,
                    weight=self.WEIGHTS.get(result.analyzer, 0.1),
                    data=result.data or {},
                    analyzer=result.analyzer,
                ),
                is_supporting=is_supporting,
            )

        return bundle

    def _get_evidence_type(self, analyzer: str) -> EvidenceType:
        """Map analyzer to evidence type."""
        mapping = {
            "rule": EvidenceType.RULE_MATCH,
            "formal": EvidenceType.FORMAL_PROOF,
            "llm": EvidenceType.LLM_RANKING,
            "graph": EvidenceType.GRAPH_PATH,
            "slice": EvidenceType.SLICE_PATH,
            "taint": EvidenceType.TAINT_FLOW,
        }
        return mapping.get(analyzer, EvidenceType.RULE_MATCH)
