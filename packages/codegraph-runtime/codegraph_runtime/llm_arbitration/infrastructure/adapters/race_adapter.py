"""
RaceAdapter (RFC-028 Phase 2)

Converts AsyncRaceDetector results to RFC-027 ResultEnvelope.

Architecture:
- Adapter Layer (Hexagonal)
- Depends on: Domain models (RFC specs)
- Depends on: code_foundation (AsyncRaceDetector)
- No infrastructure dependencies

Responsibilities:
1. RaceCondition → Claim + Evidence
2. Severity mapping (critical/high/medium/low)
3. confidence_basis = PROVEN (must-alias 100%)
4. Evidence.kind = RACE_WITNESS
5. Await point preservation

NOT Responsible For:
- Running analysis (AsyncRaceDetector)
- Arbitration (ArbitrationEngine)
- API layer (FastAPI routes)

RFC-028 Phase 2:
- Must-alias 100% → Proven verdict
- FastAPI/Django async views
"""

import time
from uuid import uuid4

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.analyzers.concurrency.models import (
    RaceCondition,
    RaceSeverity,
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

from .versions import RACE_VERSION

logger = get_logger(__name__)


# ============================================================
# Severity Mapping (RFC-027 Section 6.2)
# ============================================================

RACE_SEVERITY_MAP = {
    "critical": "critical",  # Write-Write
    "high": "high",  # Write-Read
    "medium": "medium",  # Read-Write
    "low": "low",  # Read-Read (informational)
}
"""Race severity → RFC severity mapping"""


# ============================================================
# Verdict Mapping (RFC-028)
# ============================================================

RACE_VERDICT_MAP = {
    "proven": (ConfidenceBasis.PROVEN, 0.95),  # Must-alias 100%
    "likely": (ConfidenceBasis.HEURISTIC, 0.75),  # May-alias or heuristic
}
"""Race verdict → (ConfidenceBasis, confidence) mapping"""


# ============================================================
# RaceAdapter
# ============================================================


class RaceAdapter:
    """
    RaceAdapter (RFC-028 Phase 2)

    Converts AsyncRaceDetector results to ResultEnvelope.

    Design:
    - Stateless (no instance state)
    - Pure function (deterministic)
    - No side effects

    Usage:
        adapter = RaceAdapter()

        # AsyncRaceDetector result
        races = [RaceCondition(...), ...]

        # Convert
        envelope = adapter.to_envelope(
            races=races,
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
        races: list[RaceCondition],
        request_id: str,
        execution_time_ms: float,
        snapshot_id: str | None = None,
    ) -> ResultEnvelope:
        """
        Convert AsyncRaceDetector results to ResultEnvelope

        Args:
            races: AsyncRaceDetector.analyze_async_function() result
                [RaceCondition(...), ...]
            request_id: Request ID (must start with "req_")
            execution_time_ms: Execution time (milliseconds)
            snapshot_id: Code snapshot ID (optional)

        Returns:
            ResultEnvelope with:
            - claims: One per race (confidence_basis=PROVEN if verdict="proven")
            - evidences: One per race (kind=RACE_WITNESS)
            - conclusion: Summary with recommendation
            - metrics: Execution metrics

        Raises:
            ValueError: If races invalid
            ValidationError: If ResultEnvelope validation fails

        Example:
            >>> adapter = RaceAdapter()
            >>> envelope = adapter.to_envelope(
            ...     races=[RaceCondition(...)],
            ...     request_id="req_abc123",
            ...     execution_time_ms=234.5
            ... )
            >>> len(envelope.claims)
            1
        """
        start = time.perf_counter()

        # Validate input
        if not isinstance(races, list):
            raise ValueError(f"races must be list, got {type(races)}")

        logger.info(
            "race_adapter_converting",
            request_id=request_id,
            races=len(races),
        )

        # Build envelope
        builder = ResultEnvelopeBuilder(request_id=request_id)

        # Summary
        if not races:
            builder.set_summary("No race conditions found")
        else:
            critical_count = sum(1 for r in races if r.severity == RaceSeverity.CRITICAL)
            high_count = sum(1 for r in races if r.severity == RaceSeverity.HIGH)

            if critical_count > 0:
                builder.set_summary(f"Found {critical_count} critical race conditions")
            else:
                builder.set_summary(f"Found {len(races)} race conditions ({high_count} high)")

        # Convert races → Claims + Evidences
        for race in races:
            claim, evidence = self._convert_race(race, request_id, snapshot_id)
            builder.add_claim(claim)
            builder.add_evidence(evidence)

        # Conclusion (if races found)
        if races:
            conclusion = self._build_conclusion(races)
            builder.set_conclusion(conclusion)

        # Metrics
        metrics = self._build_metrics(
            execution_time_ms=execution_time_ms,
            claims_generated=len(races),
            races=races,
        )
        builder.set_metrics(metrics)

        # Build
        envelope = builder.build()

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "race_adapter_complete",
            request_id=request_id,
            claims=len(envelope.claims),
            evidences=len(envelope.evidences),
            conversion_time_ms=f"{elapsed_ms:.2f}",
        )

        return envelope

    def _convert_race(
        self,
        race: RaceCondition,
        request_id: str,
        snapshot_id: str | None,
    ) -> tuple[Claim, Evidence]:
        """
        Convert single race to Claim + Evidence

        Args:
            race: RaceCondition from AsyncRaceDetector
            request_id: Request ID
            snapshot_id: Snapshot ID (optional)

        Returns:
            (Claim, Evidence) tuple

        Design:
        - Claim: High-level assertion (race exists)
        - Evidence: Machine-readable proof (await points, lock regions)
        - Link: Evidence.claim_ids = [claim.id]
        """
        # CRITICAL: Use adapter prefix to prevent ID collision
        claim_id = f"{request_id}_race_claim_{uuid4().hex[:8]}"
        evidence_id = f"{request_id}_race_ev_{uuid4().hex[:8]}"

        # Map verdict → confidence
        confidence_basis, confidence = RACE_VERDICT_MAP.get(race.verdict, (ConfidenceBasis.HEURISTIC, 0.50))

        # Severity
        severity = RACE_SEVERITY_MAP.get(race.severity.value, "medium")

        # Claim (RFC-027 Section 6.2)
        claim = Claim(
            id=claim_id,
            type="race_condition",
            severity=severity,
            confidence=confidence,
            confidence_basis=confidence_basis,
            proof_obligation=ProofObligation(
                assumptions=[
                    "must-alias analysis is sound (100%)",
                    "await points enable interleaving",
                    "lock regions are correctly identified",
                ],
                verification_steps=[
                    "detect shared variables",
                    "find all accesses (read/write)",
                    "detect await points",
                    "check lock protection",
                    "confirm must-alias (proven)" if race.verdict == "proven" else "heuristic inference",
                ],
            ),
            provenance=Provenance(
                engine="AsyncRaceDetector",
                version=RACE_VERSION,
                timestamp=time.time(),
                snapshot_id=snapshot_id,
            ),
            message=f"Race condition on '{race.shared_var}' ({race.severity.value}, {race.verdict})",
            location=Location(
                file_path=race.file_path or "unknown.py",
                start_line=race.access1[1],  # First access line
                end_line=race.access2[1],  # Second access line
            ),
        )

        # Evidence (RFC-027 Section 6.3)
        # RACE_WITNESS requires: shared_variable, accesses, interleaving_path
        evidence = Evidence(
            id=evidence_id,
            kind=EvidenceKind.RACE_WITNESS,
            claim_ids=[claim_id],
            location=Location(
                file_path=race.file_path or "unknown.py",
                start_line=race.access1[1],
                end_line=race.access2[1],
            ),
            content={
                # Required fields for RACE_WITNESS validation
                "shared_variable": race.shared_var,
                "accesses": [
                    {"line": race.access1[1], "type": race.access1[2].value},
                    {"line": race.access2[1], "type": race.access2[2].value},
                ],
                "interleaving_path": [ap.line for ap in race.await_points],
                # Additional fields for rich information
                "await_points": [{"line": ap.line, "expr": ap.await_expr} for ap in race.await_points],
                "lock_regions": [
                    {"lock_var": lr.lock_var, "start": lr.start_line, "end": lr.end_line} for lr in race.lock_regions
                ],
                "proof_trace": race.proof_trace,
                "verdict": race.verdict,
            },
            provenance=Provenance(
                engine="AsyncRaceDetector",
                version=RACE_VERSION,
                timestamp=time.time(),
                snapshot_id=snapshot_id,
            ),
        )

        return claim, evidence

    def _build_conclusion(self, races: list[RaceCondition]) -> Conclusion:
        """
        Build conclusion for race conditions

        Args:
            races: Race conditions

        Returns:
            Conclusion with summary and recommendations
        """
        # Summary
        summary_parts = []
        for race in races:
            access1_type = race.access1[2].value
            access2_type = race.access2[2].value
            summary_parts.append(
                f"- {race.shared_var}: {access1_type} (line {race.access1[1]}) "
                f"↔ {access2_type} (line {race.access2[1]}) "
                f"[{race.severity.value}]"
            )

        reasoning_summary = f"Found {len(races)} race conditions:\n" + "\n".join(
            summary_parts[:10]
        )  # Max 10 for readability

        # Recommendations
        critical_races = [r for r in races if r.severity == RaceSeverity.CRITICAL]
        recommendations = []

        if critical_races:
            recommendations.append(
                f"CRITICAL: {len(critical_races)} write-write races detected. "
                "Use asyncio.Lock to protect shared variables."
            )

        recommendations.append(
            "General: Wrap all shared variable accesses with asyncio.Lock or use "
            "asyncio-safe data structures (asyncio.Queue, etc.)"
        )

        recommendation = "\n".join(recommendations)

        return Conclusion(
            reasoning_summary=reasoning_summary,
            coverage=1.0,  # Full coverage (analyzed all async functions)
            recommendation=recommendation,
        )

    def _build_metrics(
        self,
        execution_time_ms: float,
        claims_generated: int,
        races: list[RaceCondition],
    ) -> Metrics:
        """
        Build metrics

        Args:
            execution_time_ms: Execution time
            claims_generated: Number of claims
            races: Race conditions

        Returns:
            Metrics
        """
        # Count by verdict
        proven_count = sum(1 for r in races if r.verdict == "proven")
        likely_count = sum(1 for r in races if r.verdict == "likely")

        # Count by severity
        critical_count = sum(1 for r in races if r.severity == RaceSeverity.CRITICAL)
        high_count = sum(1 for r in races if r.severity == RaceSeverity.HIGH)

        return Metrics(
            execution_time_ms=execution_time_ms,
            claims_generated=claims_generated,
            evidences_generated=claims_generated,  # 1:1 mapping
            analyzer_specific={
                "races_detected": len(races),
                "proven_count": proven_count,
                "likely_count": likely_count,
                "critical_count": critical_count,
                "high_count": high_count,
            },
        )
