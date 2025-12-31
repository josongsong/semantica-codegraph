"""
DiffAdapter (RFC-028 Phase 3)

Converts DifferentialAnalyzer results to RFC-027 ResultEnvelope.

Architecture:
- Adapter Layer (Hexagonal)
- Depends on: Domain models (RFC specs)
- Depends on: code_foundation (DifferentialAnalyzer)
- No infrastructure dependencies

Responsibilities:
1. DiffResult → Claim + Evidence
2. Severity mapping (critical for sanitizer removal)
3. confidence_basis = PROVEN (static analysis)
4. Evidence.kind = DIFF_DELTA
5. PR context preservation

RFC-028 Week 7-8:
- Sanitizer removal: 100% recall
- Performance regression: 90%+ recall
- Breaking change: 85%+ recall
"""

import time
from uuid import uuid4

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.analyzers.differential.models import (
    BreakingChange,
    CostDiff,
    DiffResult,
    TaintDiff,
)
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

from .versions import DIFF_VERSION

logger = get_logger(__name__)


class DiffAdapter:
    """
    DiffAdapter (RFC-028 Phase 3)

    Converts Differential analysis results to ResultEnvelope.

    Design:
    - Stateless (no instance state)
    - Pure function (deterministic)
    - High severity for critical diffs

    Usage:
        adapter = DiffAdapter()
        envelope = adapter.to_envelope(diff_result, request_id, execution_time_ms)

    Thread-Safety:
        Thread-safe (stateless)
    """

    def __init__(self):
        """Initialize adapter (stateless)"""
        pass

    def to_envelope(
        self,
        diff_result: DiffResult,
        request_id: str,
        execution_time_ms: float,
        snapshot_id: str | None = None,
    ) -> ResultEnvelope:
        """
        Convert DiffResult to ResultEnvelope

        Args:
            diff_result: DifferentialAnalyzer.analyze_pr_diff() result
            request_id: Request ID
            execution_time_ms: Execution time (milliseconds)
            snapshot_id: PR snapshot ID (optional)

        Returns:
            ResultEnvelope with diff analysis results

        Raises:
            ValueError: If diff_result invalid
        """
        start = time.perf_counter()

        logger.info(
            "diff_adapter_converting",
            request_id=request_id,
            taint_diffs=len(diff_result.taint_diffs),
            cost_diffs=len(diff_result.cost_diffs),
            breaking_changes=len(diff_result.breaking_changes),
        )

        # Build envelope
        builder = ResultEnvelopeBuilder(request_id=request_id)

        # Summary
        builder.set_summary(diff_result.summary or "No critical issues found")

        # Convert diffs → Claims + Evidences

        # 1. Taint diffs (CRITICAL)
        for taint_diff in diff_result.taint_diffs:
            claim, evidence = self._convert_taint_diff(taint_diff, request_id, snapshot_id)
            builder.add_claim(claim)
            builder.add_evidence(evidence)

        # 2. Cost diffs (HIGH if regression)
        for cost_diff in diff_result.cost_diffs:
            if cost_diff.is_regression:
                claim, evidence = self._convert_cost_diff(cost_diff, request_id, snapshot_id)
                builder.add_claim(claim)
                builder.add_evidence(evidence)

        # 3. Breaking changes (HIGH)
        for breaking in diff_result.breaking_changes:
            claim, evidence = self._convert_breaking_change(breaking, request_id, snapshot_id)
            builder.add_claim(claim)
            builder.add_evidence(evidence)

        # Conclusion
        if not diff_result.is_safe:
            conclusion = self._build_conclusion(diff_result)
            builder.set_conclusion(conclusion)

        # Metrics
        metrics = Metrics(
            execution_time_ms=execution_time_ms,
            claims_generated=len(diff_result.taint_diffs)
            + sum(1 for d in diff_result.cost_diffs if d.is_regression)
            + len(diff_result.breaking_changes),
            evidences_generated=len(diff_result.taint_diffs)
            + sum(1 for d in diff_result.cost_diffs if d.is_regression)
            + len(diff_result.breaking_changes),
            analyzer_specific={
                "taint_diffs": len(diff_result.taint_diffs),
                "cost_regressions": sum(1 for d in diff_result.cost_diffs if d.is_regression),
                "breaking_changes": len(diff_result.breaking_changes),
            },
        )
        builder.set_metrics(metrics)

        # Build
        envelope = builder.build()

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "diff_adapter_complete",
            request_id=request_id,
            claims=len(envelope.claims),
            conversion_time_ms=f"{elapsed_ms:.2f}",
        )

        return envelope

    def _convert_taint_diff(
        self,
        taint_diff: TaintDiff,
        request_id: str,
        snapshot_id: str | None,
    ) -> tuple[Claim, Evidence]:
        """Convert taint diff to Claim + Evidence"""
        claim_id = f"{request_id}_taint_diff_{uuid4().hex[:8]}"
        evidence_id = f"{request_id}_taint_diff_ev_{uuid4().hex[:8]}"

        claim = Claim(
            id=claim_id,
            type="sanitizer_removed",
            severity="critical",  # Always critical!
            confidence=0.95,
            confidence_basis=ConfidenceBasis.PROVEN,
            proof_obligation=ProofObligation(
                assumptions=["taint analysis is sound", "diff is accurate"],
                verification_steps=["detect sanitizer call", "verify removal", "confirm taint flow"],
            ),
            provenance=Provenance(
                engine="DifferentialAnalyzer",
                version=DIFF_VERSION,
                timestamp=time.time(),
                snapshot_id=snapshot_id,
            ),
            message=f"Sanitizer '{taint_diff.sanitizer_name}' removed (CRITICAL)",
            location=Location(
                file_path=taint_diff.file_path,
                start_line=taint_diff.line,
                end_line=taint_diff.line,
            ),
        )

        evidence = Evidence(
            id=evidence_id,
            kind=EvidenceKind.DIFF_DELTA,
            claim_ids=[claim_id],
            location=Location(
                file_path=taint_diff.file_path,
                start_line=taint_diff.line,
                end_line=taint_diff.line,
            ),
            content={
                "change_type": "sanitizer_removed",
                "sanitizer_name": taint_diff.sanitizer_name,
                "source": taint_diff.source,
                "sink": taint_diff.sink,
                "removed_at_line": taint_diff.removed_at_line,
            },
            provenance=Provenance(
                engine="DifferentialAnalyzer",
                version=DIFF_VERSION,
                timestamp=time.time(),
                snapshot_id=snapshot_id,
            ),
        )

        return claim, evidence

    def _convert_cost_diff(
        self,
        cost_diff: CostDiff,
        request_id: str,
        snapshot_id: str | None,
    ) -> tuple[Claim, Evidence]:
        """Convert cost diff to Claim + Evidence"""
        claim_id = f"{request_id}_cost_diff_{uuid4().hex[:8]}"
        evidence_id = f"{request_id}_cost_diff_ev_{uuid4().hex[:8]}"

        claim = Claim(
            id=claim_id,
            type="performance_regression",
            severity="high" if cost_diff.regression_factor >= 2.0 else "medium",
            confidence=0.95 if cost_diff.verdict == "proven" else 0.75,
            confidence_basis=ConfidenceBasis.PROVEN if cost_diff.verdict == "proven" else ConfidenceBasis.HEURISTIC,
            proof_obligation=ProofObligation(
                assumptions=["cost analysis is sound", "diff is accurate"],
                verification_steps=["analyze cost before", "analyze cost after", "compare"],
            ),
            provenance=Provenance(
                engine="DifferentialAnalyzer",
                version=DIFF_VERSION,
                timestamp=time.time(),
                snapshot_id=snapshot_id,
            ),
            message=f"Performance regression: {cost_diff.cost_before} → {cost_diff.cost_after}",
            location=Location(
                file_path=cost_diff.file_path,
                start_line=cost_diff.line,
                end_line=cost_diff.line,
            ),
        )

        evidence = Evidence(
            id=evidence_id,
            kind=EvidenceKind.DIFF_DELTA,
            claim_ids=[claim_id],
            location=Location(
                file_path=cost_diff.file_path,
                start_line=cost_diff.line,
                end_line=cost_diff.line,
            ),
            content={
                "change_type": "performance_regression",
                "cost_before": cost_diff.cost_before,
                "cost_after": cost_diff.cost_after,
                "regression_factor": cost_diff.regression_factor,
            },
            provenance=Provenance(
                engine="DifferentialAnalyzer",
                version=DIFF_VERSION,
                timestamp=time.time(),
                snapshot_id=snapshot_id,
            ),
        )

        return claim, evidence

    def _convert_breaking_change(
        self,
        breaking: BreakingChange,
        request_id: str,
        snapshot_id: str | None,
    ) -> tuple[Claim, Evidence]:
        """Convert breaking change to Claim + Evidence"""
        claim_id = f"{request_id}_breaking_{uuid4().hex[:8]}"
        evidence_id = f"{request_id}_breaking_ev_{uuid4().hex[:8]}"

        claim = Claim(
            id=claim_id,
            type="breaking_change",
            severity="high",
            confidence=0.95,
            confidence_basis=ConfidenceBasis.PROVEN,
            proof_obligation=ProofObligation(
                assumptions=["call graph is complete", "signature analysis is sound"],
                verification_steps=["detect signature change", "find affected callers"],
            ),
            provenance=Provenance(
                engine="DifferentialAnalyzer",
                version=DIFF_VERSION,
                timestamp=time.time(),
                snapshot_id=snapshot_id,
            ),
            message=f"Breaking change: {breaking.description}",
            location=Location(
                file_path=breaking.file_path,
                start_line=breaking.line,
                end_line=breaking.line,
            ),
        )

        evidence = Evidence(
            id=evidence_id,
            kind=EvidenceKind.DIFF_DELTA,
            claim_ids=[claim_id],
            location=Location(
                file_path=breaking.file_path,
                start_line=breaking.line,
                end_line=breaking.line,
            ),
            content={
                "change_type": "breaking_change",
                "description": breaking.description,
                "affected_callers": breaking.affected_callers,
            },
            provenance=Provenance(
                engine="DifferentialAnalyzer",
                version=DIFF_VERSION,
                timestamp=time.time(),
                snapshot_id=snapshot_id,
            ),
        )

        return claim, evidence

    def _build_conclusion(self, diff_result: DiffResult) -> Conclusion:
        """Build conclusion for unsafe PR"""
        recommendations = []

        if diff_result.taint_diffs:
            recommendations.append(
                f"CRITICAL: {len(diff_result.taint_diffs)} sanitizer(s) removed. "
                "Restore sanitizers or add alternative protection."
            )

        regressions = [d for d in diff_result.cost_diffs if d.is_regression]
        if regressions:
            recommendations.append(
                f"Performance regression detected in {len(regressions)} function(s). Review algorithm complexity."
            )

        if diff_result.breaking_changes:
            recommendations.append(
                f"{len(diff_result.breaking_changes)} breaking change(s). Update callers or add deprecation."
            )

        # reasoning_summary는 최소 1글자 필요 (RFC-027 Conclusion validation)
        summary = diff_result.summary if diff_result.summary else "Differential analysis completed"
        recommendation = "\n".join(recommendations) if recommendations else "No issues detected"

        return Conclusion(
            reasoning_summary=summary,
            coverage=1.0,
            recommendation=recommendation,
        )
