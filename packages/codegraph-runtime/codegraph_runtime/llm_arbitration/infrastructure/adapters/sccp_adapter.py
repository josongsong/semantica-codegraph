"""
SCCPAdapter (RFC-027 Section 18.B)

Converts ConstantPropagationResult to RFC-027 ResultEnvelope.

Architecture:
- Adapter Layer (Hexagonal)
- Depends on: Domain models (RFC specs)
- Depends on: code_foundation (ConstantPropagationResult)

Responsibilities:
1. ConstantPropagationResult → Claim (dead code detection)
2. Unreachable blocks → Evidence (CODE_SNIPPET)
3. confidence_basis = PROVEN (static proof)
4. Constants → Evidence (constant values)

NOT Responsible For:
- Running SCCP analysis (ConstantPropagationAnalyzer)
- Arbitration (ArbitrationEngine)

RFC-027 Section 12.2.1: AnalyzeSpec → Pipeline mapping
"""

import time
from uuid import uuid4

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.constant_propagation.models import ConstantPropagationResult
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

from .versions import SCCP_VERSION

logger = get_logger(__name__)


class SCCPAdapter:
    """
    SCCPAdapter (RFC-027)

    Converts SCCP analysis results to ResultEnvelope.

    Focus:
    - Dead code detection (unreachable blocks)
    - Constant propagation results
    - confidence_basis = PROVEN (deterministic)

    Usage:
        adapter = SCCPAdapter()

        # SCCP result
        sccp_result = ConstantPropagationResult(
            constants_found=25,
            unreachable_blocks={"block_5", "block_7"},
            ...
        )

        # Convert
        envelope = adapter.to_envelope(
            sccp_result=sccp_result,
            request_id="req_abc123",
            execution_time_ms=15.3
        )

    Thread-Safety:
        Thread-safe (stateless)
    """

    def __init__(self):
        """Initialize adapter (stateless)"""
        pass

    def to_envelope(
        self,
        sccp_result: ConstantPropagationResult,
        request_id: str,
        execution_time_ms: float,
        ir_file_path: str | None = None,
        snapshot_id: str | None = None,
    ) -> ResultEnvelope:
        """
        Convert ConstantPropagationResult to ResultEnvelope

        Args:
            sccp_result: SCCP analysis result
            request_id: Request ID (must start with "req_")
            execution_time_ms: Execution time (milliseconds)
            ir_file_path: IR file path (for Evidence location)
            snapshot_id: Code snapshot ID (optional)

        Returns:
            ResultEnvelope with:
            - claims: Dead code claims (if unreachable blocks found)
            - evidences: Unreachable block locations
            - conclusion: Summary with constant count
            - metrics: Execution metrics

        Raises:
            ValueError: If sccp_result invalid
            ValidationError: If ResultEnvelope validation fails

        Example:
            >>> adapter = SCCPAdapter()
            >>> envelope = adapter.to_envelope(
            ...     sccp_result=result,
            ...     request_id="req_abc123",
            ...     execution_time_ms=15.3,
            ...     ir_file_path="api/users.py"
            ... )
            >>> len(envelope.claims)
            1  # Dead code claim
        """
        start = time.perf_counter()

        # Validate input
        if not isinstance(sccp_result, ConstantPropagationResult):
            raise ValueError(f"sccp_result must be ConstantPropagationResult, got {type(sccp_result)}")

        logger.info(
            "sccp_adapter_converting",
            request_id=request_id,
            constants=sccp_result.constants_found,
            unreachable=len(sccp_result.unreachable_blocks),
        )

        # Build envelope
        builder = ResultEnvelopeBuilder(request_id=request_id)

        # Summary
        if sccp_result.unreachable_blocks:
            builder.set_summary(
                f"Found {sccp_result.constants_found} constants, "
                f"{len(sccp_result.unreachable_blocks)} unreachable blocks (dead code)"
            )
        else:
            builder.set_summary(f"Found {sccp_result.constants_found} constants, no dead code")

        # Convert unreachable blocks → Claims + Evidences
        if sccp_result.unreachable_blocks:
            for block_id in sccp_result.unreachable_blocks:
                claim, evidence = self._convert_unreachable_block(
                    block_id=block_id,
                    request_id=request_id,
                    ir_file_path=ir_file_path or "unknown.py",
                    snapshot_id=snapshot_id,
                )
                builder.add_claim(claim)
                builder.add_evidence(evidence)

        # Conclusion
        conclusion = self._build_conclusion(sccp_result)
        builder.set_conclusion(conclusion)

        # Metrics
        metrics = self._build_metrics(
            execution_time_ms=execution_time_ms,
            claims_generated=len(sccp_result.unreachable_blocks),
            sccp_result=sccp_result,
        )
        builder.set_metrics(metrics)

        # Build
        envelope = builder.build()

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "sccp_adapter_complete",
            request_id=request_id,
            claims=len(envelope.claims),
            evidences=len(envelope.evidences),
            conversion_time_ms=f"{elapsed_ms:.2f}",
        )

        return envelope

    def _convert_unreachable_block(
        self,
        block_id: str,
        request_id: str,
        ir_file_path: str,
        snapshot_id: str | None,
    ) -> tuple[Claim, Evidence]:
        """
        Convert unreachable block to Claim + Evidence

        Args:
            block_id: CFG block ID
            request_id: Request ID
            ir_file_path: File path
            snapshot_id: Snapshot ID

        Returns:
            (Claim, Evidence) tuple
        """
        # CRITICAL: Use adapter prefix to prevent ID collision with other adapters
        claim_id = f"{request_id}_sccp_claim_{uuid4().hex[:8]}"
        evidence_id = f"{request_id}_sccp_ev_{uuid4().hex[:8]}"

        # Claim: Dead code (PROVEN)
        claim = Claim(
            id=claim_id,
            type="dead_code",
            severity="low",  # Dead code is low severity (not security)
            confidence=1.0,  # SCCP is deterministic
            confidence_basis=ConfidenceBasis.PROVEN,  # Static proof
            proof_obligation=ProofObligation(
                assumptions=[
                    "CFG is sound",
                    "conditional constants correctly propagated",
                ],
                broken_if=[
                    "dynamic dispatch unresolved",
                    "exception handling incomplete",
                ],
                unknowns=[],  # SCCP is deterministic
            ),
        )

        # Evidence: Unreachable block location
        # Parse block_id to extract line info (if available)
        # Format: "cfg:function_name:block:N" or just block_id
        line_num = self._extract_line_from_block_id(block_id)

        evidence = Evidence(
            id=evidence_id,
            kind=EvidenceKind.CODE_SNIPPET,  # Dead code snippet
            location=Location(
                file_path=ir_file_path,
                start_line=line_num,
                end_line=line_num,
            ),
            content={
                "block_id": block_id,
                "reachable": False,
                "reason": "Unreachable due to constant propagation",
                "analysis": "SCCP",
            },
            provenance=Provenance(
                engine="SCCPAnalyzer",
                template="constant_propagation",
                snapshot_id=snapshot_id,
                version=SCCP_VERSION,
                timestamp=time.time(),
            ),
            claim_ids=[claim_id],
        )

        return claim, evidence

    def _extract_line_from_block_id(self, block_id: str) -> int:
        """
        Extract line number from block_id (best effort)

        Args:
            block_id: CFG block ID (e.g., "cfg:func:block:5")

        Returns:
            Line number (default 1 if not extractable)
        """
        # Try to extract number from block_id
        parts = block_id.split(":")
        for part in reversed(parts):
            try:
                return int(part)
            except ValueError:
                continue

        # Fallback
        return 1

    def _build_conclusion(self, sccp_result: ConstantPropagationResult) -> Conclusion:
        """
        Build conclusion from SCCP result

        Args:
            sccp_result: SCCP result

        Returns:
            Conclusion
        """
        # Reasoning summary
        reasoning = f"Sparse Conditional Constant Propagation found {sccp_result.constants_found} constants. "

        if sccp_result.unreachable_blocks:
            reasoning += f"{len(sccp_result.unreachable_blocks)} unreachable blocks detected (dead code). "

        # Coverage (based on reachable vs total blocks)
        total_blocks = len(sccp_result.reachable_blocks) + len(sccp_result.unreachable_blocks)
        coverage = len(sccp_result.reachable_blocks) / total_blocks if total_blocks > 0 else 1.0

        # Recommendation
        if sccp_result.unreachable_blocks:
            recommendation = (
                f"Remove {len(sccp_result.unreachable_blocks)} unreachable blocks to improve code quality. "
                "Consider refactoring conditional logic."
            )
        else:
            recommendation = "No dead code detected. Code is well-structured."

        return Conclusion(
            reasoning_summary=reasoning,
            coverage=coverage,
            counterevidence=[],
            recommendation=recommendation,
        )

    def _build_metrics(
        self,
        execution_time_ms: float,
        claims_generated: int,
        sccp_result: ConstantPropagationResult,
    ) -> Metrics:
        """
        Build metrics from SCCP result

        Args:
            execution_time_ms: Execution time
            claims_generated: Number of claims
            sccp_result: SCCP result

        Returns:
            Metrics
        """
        stats = sccp_result.get_statistics()

        return Metrics(
            execution_time_ms=execution_time_ms,
            paths_analyzed=0,  # SCCP doesn't analyze paths
            claims_generated=claims_generated,
            claims_suppressed=0,
            cache_hits=0,  # SCCP doesn't report cache hits
            additional={
                "constants_found": stats["constants_found"],
                "unreachable_blocks": stats["unreachable_blocks"],
                "reachable_blocks": stats["reachable_blocks"],
                "bottom_count": stats.get("bottom_count", 0),
            },
        )
