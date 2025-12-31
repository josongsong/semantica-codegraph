"""
UNDECIDABLE Handler (RFC-102)

Handles cases where evidence is insufficient for decision.
"""

from typing import Any, Optional

from ...domain.evidence_bundle import DecisionType, EvidenceBundle
from .confidence_aggregator import AnalysisResult


class UNDECIDABLEHandler:
    """
    Handles UNDECIDABLE states.

    Returns UNDECIDABLE if:
    1. Confidence < threshold
    2. Evidence conflicts
    3. Candidate count too high
    4. Analyzers disagree significantly
    """

    # Confidence threshold for DECIDED vs UNDECIDABLE
    DECIDABLE_THRESHOLD = 0.85
    MAX_CANDIDATES = 50  # Too many candidates → UNDECIDABLE

    def evaluate_decision(self, analysis_results: list[AnalysisResult], context: dict) -> EvidenceBundle:
        """
        Evaluate whether we can make a decision.

        Args:
            analysis_results: Results from multiple analyzers
            context: Analysis context (task, candidates, etc.)

        Returns:
            EvidenceBundle (DECIDED or UNDECIDABLE)
        """
        if not analysis_results:
            return self._create_undecidable_bundle(
                reason="No analysis results available",
                context=context,
            )

        # Check 1: Confidence threshold
        max_confidence = max(r.confidence for r in analysis_results)
        if max_confidence < self.DECIDABLE_THRESHOLD:
            return self._create_undecidable_bundle(
                reason=f"Low confidence: {max_confidence:.2f} < {self.DECIDABLE_THRESHOLD}",
                required_info=[
                    "More context about usage patterns",
                    "Additional type constraints",
                    "Runtime behavior data",
                ],
                context=context,
            )

        # Check 2: Evidence conflicts
        decisions = [r.is_breaking for r in analysis_results]
        if len(set(decisions)) > 1:  # Not unanimous
            # Calculate conflict severity
            breaking_count = sum(decisions)
            non_breaking_count = len(decisions) - breaking_count

            if min(breaking_count, non_breaking_count) >= 2:  # Significant conflict
                return self._create_conflicting_bundle(
                    breaking_count=breaking_count,
                    non_breaking_count=non_breaking_count,
                    results=analysis_results,
                    context=context,
                )

        # Check 3: Candidate overflow
        if "candidates" in context and len(context["candidates"]) > self.MAX_CANDIDATES:
            return self._create_undecidable_bundle(
                reason=f"Too many candidates: {len(context['candidates'])} > {self.MAX_CANDIDATES}",
                required_info=[
                    "More specific boundary spec (add filters)",
                    "Additional graph constraints",
                    "Narrower search scope",
                ],
                context=context,
            )

        # Decidable - use ConfidenceAggregator to create bundle
        return None  # Caller should use ConfidenceAggregator

    def _create_undecidable_bundle(
        self,
        reason: str,
        required_info: Optional[list[str]] = None,
        context: Optional[dict] = None,
    ) -> EvidenceBundle:
        """Create UNDECIDABLE bundle."""
        bundle = EvidenceBundle(
            decision="unknown",
            confidence=0.0,
            decision_type=DecisionType.UNDECIDABLE,
            undecidable_reason=reason,
            required_information=required_info or [],
            conservative_fallback=self._conservative_fallback(context or {}),
        )

        return bundle

    def _create_conflicting_bundle(
        self,
        breaking_count: int,
        non_breaking_count: int,
        results: list[AnalysisResult],
        context: dict,
    ) -> EvidenceBundle:
        """Create CONFLICTING bundle."""
        from ...domain.evidence_bundle import Evidence, EvidenceType

        bundle = EvidenceBundle(
            decision="unknown",
            confidence=0.0,
            decision_type=DecisionType.CONFLICTING,
            undecidable_reason=f"Conflicting evidence: {breaking_count} breaking, {non_breaking_count} non-breaking",
            required_information=[
                "Expand backward slice to find more evidence",
                "Check additional call sites",
                "Review edge cases in type constraints",
            ],
            conservative_fallback=self._conservative_fallback(context),
        )

        # Add breaking evidence
        for result in results:
            if result.is_breaking:
                bundle.add_evidence(
                    Evidence(
                        type=EvidenceType.RULE_MATCH,
                        description="; ".join(result.evidence),
                        confidence=result.confidence,
                        weight=0.5,
                        analyzer=result.analyzer,
                    ),
                    is_supporting=True,
                )
            else:
                bundle.add_evidence(
                    Evidence(
                        type=EvidenceType.RULE_MATCH,
                        description="; ".join(result.evidence),
                        confidence=result.confidence,
                        weight=0.5,
                        analyzer=result.analyzer,
                    ),
                    is_supporting=False,
                )

        return bundle

    def _conservative_fallback(self, context: dict) -> Any:
        """Provide conservative fallback for UNDECIDABLE cases."""
        task = context.get("task", "")

        if task == "breaking_change_detection":
            # When uncertain, assume breaking (fail-safe)
            return {
                "is_breaking": True,
                "severity": "medium",
                "confidence": 0.0,
                "reason": "Conservative fallback: insufficient evidence to prove non-breaking",
            }
        elif task == "boundary_matching":
            # No fallback for boundary matching (return None)
            return None
        else:
            return None
