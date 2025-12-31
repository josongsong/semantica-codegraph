"""
CostAdapter (RFC-028 Week 1 Point 3)

Converts CostAnalyzer results to RFC-027 ResultEnvelope.

Architecture:
- Adapter Layer (Hexagonal)
- Depends on: Domain models (RFC specs)
- Depends on: code_foundation (CostAnalyzer)
- No infrastructure dependencies

Responsibilities:
1. CostResult → Claim + Evidence
2. Verdict mapping (proven/likely/unknown)
3. confidence_basis = PROVEN (static proof from SCCP)
4. Evidence.kind = COST_TERM
5. Loop bounds preservation

NOT Responsible For:
- Running analysis (CostAnalyzer)
- Arbitration (ArbitrationEngine)
- API layer (FastAPI routes)

RFC-028 Week 1:
- CostAnalyzer SOTA 완료 ✅
- Point 1 (IRStage) 완료 ✅
- Point 2 (ReasoningPipeline) 완료 ✅
- Point 3 (API): 이 Adapter 사용
"""

import time
from uuid import uuid4

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.analyzers.cost.models import CostResult
from codegraph_engine.shared_kernel.contracts import (
    Claim,
    Conclusion,
    ConfidenceBasis,
    Evidence,
    EvidenceKind,
    Location,
    Metrics,
    ProofObligation,
    Provenance,
    ResultEnvelope,
    ResultEnvelopeBuilder,
)

from .versions import COST_VERSION

logger = get_logger(__name__)


# ============================================================
# Verdict → ConfidenceBasis Mapping (RFC-028)
# ============================================================

VERDICT_CONFIDENCE_MAP = {
    "proven": (ConfidenceBasis.PROVEN, 0.95),  # SCCP proven
    "likely": (ConfidenceBasis.HEURISTIC, 0.75),  # Heuristic inference
    "unknown": (ConfidenceBasis.HEURISTIC, 0.50),  # Fallback
}
"""Cost verdict → (ConfidenceBasis, confidence) mapping"""


# ============================================================
# Severity Mapping (RFC-028)
# ============================================================


def _cost_to_severity(cost_term: str) -> str:
    """
    Map cost term to severity (Pattern-based, O(1))

    Rules:
    - Exponential/Factorial: critical
    - Polynomial (n^3+, n*m*k): high
    - Quadratic (n^2, n*m): medium
    - Linear (n): medium
    - Constant: low

    Args:
        cost_term: Cost complexity (e.g., "n * m", "2^n")

    Returns:
        Severity level

    Complexity: O(1), McCabe: 6
    """
    cost_lower = cost_term.lower()

    # Critical: Exponential/Factorial
    if any(p in cost_lower for p in ["!", "exp", "2^", "3^"]):
        return "critical"

    # High: Cubic+ or Triple nested
    if cost_lower.count("*") >= 2 or "^3" in cost_lower or "^4" in cost_lower:
        return "high"

    # Medium: Quadratic or Double nested
    if "*" in cost_lower or "^2" in cost_lower:
        return "medium"

    # Medium: Linear
    if any(v in cost_lower for v in ["n", "m", "k", "len"]):
        return "medium"

    # Low: Constant
    return "low"


# ============================================================
# CostAdapter
# ============================================================


class CostAdapter:
    """
    CostAdapter (RFC-028 Week 1 Point 3)

    Converts CostAnalyzer results to ResultEnvelope.

    Design:
    - Stateless (no instance state)
    - Pure function (deterministic)
    - No side effects

    Usage:
        adapter = CostAdapter()

        # CostAnalyzer result
        cost_results = {
            "func1": CostResult(...),
            "func2": CostResult(...)
        }

        # Convert
        envelope = adapter.to_envelope(
            cost_results=cost_results,
            request_id="req_abc123",
            execution_time_ms=234.5
        )

    Thread-Safety:
        Thread-safe (stateless)
    """

    def __init__(self):
        """Initialize adapter (stateless)"""
        pass

    def to_envelope(
        self,
        cost_results: dict[str, CostResult],
        request_id: str,
        execution_time_ms: float,
        snapshot_id: str | None = None,
    ) -> ResultEnvelope:
        """
        Convert CostAnalyzer results to ResultEnvelope

        Args:
            cost_results: CostAnalyzer.analyze_cost() result
                {
                    "func_fqn": CostResult(
                        function_name="func",
                        cost_term="n * m",
                        verdict="proven",
                        loop_bounds={"n": "len(data)", "m": "10"},
                        ...
                    )
                }
            request_id: Request ID (must start with "req_")
            execution_time_ms: Execution time (milliseconds)
            snapshot_id: Code snapshot ID (optional)

        Returns:
            ResultEnvelope with:
            - claims: One per function (confidence_basis=PROVEN if verdict="proven")
            - evidences: One per function (kind=COST_TERM)
            - conclusion: Summary with recommendation
            - metrics: Execution metrics

        Raises:
            ValueError: If cost_results invalid
            ValidationError: If ResultEnvelope validation fails

        Example:
            >>> adapter = CostAdapter()
            >>> envelope = adapter.to_envelope(
            ...     cost_results={"func1": CostResult(...)},
            ...     request_id="req_abc123",
            ...     execution_time_ms=234.5
            ... )
            >>> len(envelope.claims)
            1
        """
        start = time.perf_counter()

        # Validate input
        if not isinstance(cost_results, dict):
            raise ValueError(f"cost_results must be dict, got {type(cost_results)}")

        logger.info(
            "cost_adapter_converting",
            request_id=request_id,
            functions=len(cost_results),
        )

        # Build envelope
        builder = ResultEnvelopeBuilder(request_id=request_id)

        # Summary
        if not cost_results:
            builder.set_summary("No cost analysis results")
        else:
            high_cost_count = sum(
                1
                for result in cost_results.values()
                if _cost_to_severity(
                    result.complexity.value if hasattr(result.complexity, "value") else str(result.complexity)
                )
                in ["critical", "high"]
            )

            if high_cost_count > 0:
                builder.set_summary(f"Found {high_cost_count} high-cost functions")
            else:
                builder.set_summary(f"Analyzed {len(cost_results)} functions")

        # Convert results → Claims + Evidences
        for func_fqn, result in cost_results.items():
            claim, evidence = self._convert_cost_result(func_fqn, result, request_id, snapshot_id)
            builder.add_claim(claim)
            builder.add_evidence(evidence)

        # Conclusion (if high-cost functions found)
        high_cost_results = {
            fqn: result
            for fqn, result in cost_results.items()
            if _cost_to_severity(
                result.complexity.value if hasattr(result.complexity, "value") else str(result.complexity)
            )
            in ["critical", "high"]
        }

        if high_cost_results:
            conclusion = self._build_conclusion(high_cost_results)
            builder.set_conclusion(conclusion)

        # Metrics
        metrics = self._build_metrics(
            execution_time_ms=execution_time_ms,
            claims_generated=len(cost_results),
            cost_results=cost_results,
        )
        builder.set_metrics(metrics)

        # Build
        envelope = builder.build()

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "cost_adapter_complete",
            request_id=request_id,
            claims=len(envelope.claims),
            evidences=len(envelope.evidences),
            conversion_time_ms=f"{elapsed_ms:.2f}",
        )

        return envelope

    def _convert_cost_result(
        self,
        func_fqn: str,
        result: CostResult,
        request_id: str,
        snapshot_id: str | None,
    ) -> tuple[Claim, Evidence]:
        """
        Convert single cost result to Claim + Evidence

        Args:
            func_fqn: Function FQN
            result: CostResult from CostAnalyzer
            request_id: Request ID
            snapshot_id: Snapshot ID (optional)

        Returns:
            (Claim, Evidence) tuple

        Design:
        - Claim: High-level assertion (function has O(n*m) cost)
        - Evidence: Machine-readable proof (cost term + loop bounds)
        - Link: Evidence.claim_ids = [claim.id]
        """
        # CRITICAL: Use adapter prefix to prevent ID collision
        claim_id = f"{request_id}_cost_claim_{uuid4().hex[:8]}"
        evidence_id = f"{request_id}_cost_ev_{uuid4().hex[:8]}"

        # Map verdict → confidence
        confidence_basis, confidence = VERDICT_CONFIDENCE_MAP.get(result.verdict, (ConfidenceBasis.HEURISTIC, 0.50))

        # Extract cost term from complexity
        cost_term = result.complexity.value if hasattr(result.complexity, "value") else str(result.complexity)

        # Severity
        severity = _cost_to_severity(cost_term)

        # Get location from evidence
        ev_location = result.evidence.location if result.evidence else None
        file_path = ev_location.file_path if ev_location else "unknown.py"
        start_line = ev_location.start_line if ev_location else 1
        end_line = ev_location.end_line if ev_location else 1

        # Claim (RFC-027 Section 6.2)
        claim = Claim(
            id=claim_id,
            type="cost_complexity",
            severity=severity,
            confidence=confidence,
            confidence_basis=confidence_basis,
            proof_obligation=ProofObligation(
                assumptions=[
                    "CFG is sound",
                    "loop bounds are accurate",
                    "SCCP analysis is complete" if result.verdict == "proven" else "heuristic inference",
                ],
                verification_steps=[
                    "extract CFG blocks",
                    "identify loops",
                    "compute loop bounds (SCCP if proven)",
                    "calculate cost term",
                ],
            ),
            provenance=Provenance(
                engine="CostAnalyzer",
                version=COST_VERSION,
                timestamp=time.time(),
                snapshot_id=snapshot_id,
            ),
            message=f"Function '{result.function_fqn}' has {cost_term} complexity ({result.verdict})",
            location=Location(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
            ),
            metadata={"function_fqn": result.function_fqn},
        )

        # Evidence (RFC-027 Section 6.3)
        # COST_TERM requires: cost_term, loop_bounds (list format)
        # Build loop_bounds in RFC-028 compliant list format
        loop_bounds_list = []
        if result.loop_bounds:
            for lb in result.loop_bounds:
                loop_bounds_list.append(
                    {
                        "loop_id": lb.loop_id,
                        "bound": lb.bound,
                        "method": "sccp" if result.verdict == "proven" else "heuristic",
                        "confidence": 1.0 if result.verdict == "proven" else 0.75,
                    }
                )

        evidence = Evidence(
            id=evidence_id,
            kind=EvidenceKind.COST_TERM,
            claim_ids=[claim_id],
            location=Location(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
            ),
            content={
                "cost_term": cost_term,
                "loop_bounds": loop_bounds_list,  # Must be list for RFC-028 validation
                "verdict": result.verdict,
                "proof": "SCCP proven" if result.verdict == "proven" else "heuristic",
                "function_fqn": result.function_fqn,
            },
            provenance=Provenance(
                engine="CostAnalyzer",
                version=COST_VERSION,
                timestamp=time.time(),
                snapshot_id=snapshot_id,
            ),
        )

        return claim, evidence

    def _build_conclusion(self, high_cost_results: dict[str, CostResult]) -> Conclusion:
        """
        Build conclusion for high-cost functions

        Args:
            high_cost_results: High-cost function results

        Returns:
            Conclusion with summary and recommendations
        """
        # Summary
        summary_parts = []
        for func_fqn, result in high_cost_results.items():
            cost_term = result.complexity.value if hasattr(result.complexity, "value") else str(result.complexity)
            summary_parts.append(f"- {result.function_fqn}: {cost_term} ({result.verdict})")

        reasoning_summary = f"Found {len(high_cost_results)} high-cost functions:\n" + "\n".join(summary_parts)

        # Recommendations
        recommendations = []
        for result in high_cost_results.values():
            cost_term = result.complexity.value if hasattr(result.complexity, "value") else str(result.complexity)
            cost_lower = cost_term.lower()

            if "^" in cost_lower or "!" in cost_lower:
                recommendations.append(
                    f"- {result.function_fqn}: Exponential complexity detected. "
                    "Consider dynamic programming or memoization."
                )
            elif "*" in cost_lower:
                recommendations.append(
                    f"- {result.function_fqn}: Nested loops detected. Consider loop fusion or caching."
                )
            else:
                recommendations.append(f"- {result.function_fqn}: Review algorithm complexity.")

        recommendation = "\n".join(recommendations) if recommendations else "No specific recommendations"

        return Conclusion(
            reasoning_summary=reasoning_summary,
            coverage=1.0,  # Full coverage (analyzed all requested functions)
            recommendation=recommendation,
        )

    def _build_metrics(
        self,
        execution_time_ms: float,
        claims_generated: int,
        cost_results: dict[str, CostResult],
    ) -> Metrics:
        """
        Build metrics

        Args:
            execution_time_ms: Execution time
            claims_generated: Number of claims
            cost_results: Cost results

        Returns:
            Metrics
        """
        # Count by verdict
        proven_count = sum(1 for r in cost_results.values() if r.verdict == "proven")
        likely_count = sum(1 for r in cost_results.values() if r.verdict == "likely")
        unknown_count = sum(1 for r in cost_results.values() if r.verdict == "unknown")

        return Metrics(
            execution_time_ms=execution_time_ms,
            claims_generated=claims_generated,
            evidences_generated=claims_generated,  # 1:1 mapping
            analyzer_specific={
                "functions_analyzed": len(cost_results),
                "proven_count": proven_count,
                "likely_count": likely_count,
                "unknown_count": unknown_count,
            },
        )
