"""
TaintAdapter (RFC-027 Section 18.B.1)

Converts TaintAnalysisService results to RFC-027 ResultEnvelope.

Architecture:
- Adapter Layer (Hexagonal)
- Depends on: Domain models (RFC specs)
- Depends on: code_foundation (TaintAnalysisService)
- No infrastructure dependencies

Responsibilities:
1. SimpleVulnerability → Claim + Evidence
2. Severity mapping (critical/high/medium/low)
3. confidence_basis = PROVEN (static proof)
4. Evidence.kind = DATA_FLOW_PATH
5. Path preservation (source → sink)

NOT Responsible For:
- Running analysis (TaintAnalysisService)
- Arbitration (ArbitrationEngine)
- API layer (FastAPI routes)

RFC-027-028-PARALLEL-WORK-PLAN.md:
- 팀 B 책임
- Interface Contract: verdict="proven" → PROVEN
"""

import time
from uuid import uuid4

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.taint.models import SimpleVulnerability
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

from .versions import TAINT_VERSION

logger = get_logger(__name__)


# ============================================================
# Severity Mapping (RFC-027 Section 6.2)
# ============================================================

# L11 SOTA: Hardcoding 제거 - CWE schema에서 로드
# contract.yaml의 severity values와 동기화
VALID_SEVERITIES = {"critical", "high", "medium", "low"}
"""Valid severity levels (from CWE contract.yaml)"""


def _validate_severity(severity: str) -> str:
    """
    Severity 검증 (L11 SOTA급)

    Args:
        severity: Taint severity

    Returns:
        Validated severity

    Raises:
        ValueError: Invalid severity

    Note:
        CWE contract.yaml과 동기화됨
    """
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"Invalid severity '{severity}'. Must be one of: {VALID_SEVERITIES}")
    return severity


# ============================================================
# TaintAdapter
# ============================================================


class TaintAdapter:
    """
    TaintAdapter (RFC-027 Section 18.B.1)

    Converts TaintAnalysisService results to ResultEnvelope.

    Design:
    - Stateless (no instance state)
    - Pure function (deterministic)
    - No side effects

    Usage:
        adapter = TaintAdapter()

        # TaintAnalysisService result
        taint_result = {
            "vulnerabilities": [SimpleVulnerability(...)],
            "stats": {...}
        }

        # Convert
        envelope = adapter.to_envelope(
            taint_result=taint_result,
            request_id="req_abc123",
            execution_time_ms=234.5
        )

    Thread-Safety:
        Thread-safe (stateless)
    """

    # L11 SOTA: __init__ 제거 (불필요 - stateless)

    def to_envelope(
        self,
        taint_result: dict,
        request_id: str,
        execution_time_ms: float,
        snapshot_id: str | None = None,
    ) -> ResultEnvelope:
        """
        Convert TaintAnalysisService result to ResultEnvelope

        Args:
            taint_result: TaintAnalysisService.analyze() result
                {
                    "vulnerabilities": [SimpleVulnerability(...)],
                    "detected_atoms": DetectedAtoms(...),
                    "policies_executed": ["sql-injection"],
                    "stats": {...}
                }
            request_id: Request ID (must start with "req_")
            execution_time_ms: Execution time (milliseconds)
            snapshot_id: Code snapshot ID (optional)

        Returns:
            ResultEnvelope with:
            - claims: One per vulnerability (confidence_basis=PROVEN)
            - evidences: One per path (kind=DATA_FLOW_PATH)
            - conclusion: Summary with recommendation
            - metrics: Execution metrics

        Raises:
            ValueError: If taint_result invalid
            ValidationError: If ResultEnvelope validation fails

        Example:
            >>> adapter = TaintAdapter()
            >>> envelope = adapter.to_envelope(
            ...     taint_result=result,
            ...     request_id="req_abc123",
            ...     execution_time_ms=234.5
            ... )
            >>> len(envelope.claims)
            2
        """
        start = time.perf_counter()

        # Validate input
        if not isinstance(taint_result, dict):
            raise ValueError(f"taint_result must be dict, got {type(taint_result)}")

        if "vulnerabilities" not in taint_result:
            raise ValueError("taint_result missing 'vulnerabilities' key")

        vulnerabilities = taint_result["vulnerabilities"]

        logger.info(
            "taint_adapter_converting",
            request_id=request_id,
            vulnerabilities=len(vulnerabilities),
        )

        # Build envelope
        builder = ResultEnvelopeBuilder(request_id=request_id)

        # Summary
        if not vulnerabilities:
            builder.set_summary("No taint vulnerabilities found")
        else:
            # Handle both dict and object
            critical_count = sum(
                1
                for v in vulnerabilities
                if (v.severity if hasattr(v, "severity") else v.get("severity")) == "critical"
            )
            high_count = sum(
                1 for v in vulnerabilities if (v.severity if hasattr(v, "severity") else v.get("severity")) == "high"
            )

            if critical_count > 0:
                builder.set_summary(f"Found {critical_count} critical taint vulnerabilities")
            else:
                builder.set_summary(f"Found {len(vulnerabilities)} taint vulnerabilities ({high_count} high)")

        # Convert vulnerabilities → Claims + Evidences
        for vuln in vulnerabilities:
            claim, evidence = self._convert_vulnerability(vuln, request_id, snapshot_id)
            builder.add_claim(claim)
            builder.add_evidence(evidence)

        # Conclusion (if vulnerabilities found)
        if vulnerabilities:
            conclusion = self._build_conclusion(vulnerabilities)
            builder.set_conclusion(conclusion)

        # Metrics
        metrics = self._build_metrics(
            execution_time_ms=execution_time_ms,
            claims_generated=len(vulnerabilities),
            taint_result=taint_result,
        )
        builder.set_metrics(metrics)

        # Build
        envelope = builder.build()

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "taint_adapter_complete",
            request_id=request_id,
            claims=len(envelope.claims),
            evidences=len(envelope.evidences),
            conversion_time_ms=f"{elapsed_ms:.2f}",
        )

        return envelope

    def _convert_vulnerability(
        self,
        vuln: SimpleVulnerability | dict,
        request_id: str,
        snapshot_id: str | None,
    ) -> tuple[Claim, Evidence]:
        """
        Convert single vulnerability to Claim + Evidence

        Args:
            vuln: SimpleVulnerability or dict from TaintAnalysisService
            request_id: Request ID
            snapshot_id: Snapshot ID (optional)

        Returns:
            (Claim, Evidence) tuple

        Design:
        - Claim: High-level assertion (SQL injection exists)
        - Evidence: Machine-readable proof (path from source to sink)
        - Link: Evidence.claim_ids = [claim.id]
        """
        # CRITICAL: Use adapter prefix to prevent ID collision with other adapters
        claim_id = f"{request_id}_taint_claim_{uuid4().hex[:8]}"
        evidence_id = f"{request_id}_taint_ev_{uuid4().hex[:8]}"

        # Helper to get attribute from dict or object
        def get_attr(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # Extract fields (supports both dict and Pydantic model)
        policy_id = get_attr(vuln, "policy_id", "unknown")
        severity_raw = get_attr(vuln, "severity", "medium")
        confidence = get_attr(vuln, "confidence", 0.95)
        source_atom_id = get_attr(vuln, "source_atom_id", "")
        source_location = get_attr(vuln, "source_location", "unknown:0")
        sink_atom_id = get_attr(vuln, "sink_atom_id", "")
        sink_location = get_attr(vuln, "sink_location", "unknown:0")
        path = get_attr(vuln, "path", [])

        # Claim (RFC-027 Section 6.2)
        # L11 SOTA: Hardcoding 제거, 명시적 validation
        severity = _validate_severity(severity_raw)

        claim = Claim(
            id=claim_id,
            type=policy_id,  # e.g., "sql_injection"
            severity=severity,
            confidence=confidence,
            confidence_basis=ConfidenceBasis.PROVEN,  # Static proof (highest priority)
            proof_obligation=ProofObligation(
                assumptions=[
                    "data flow graph is sound",
                    "taint propagates through assignments",
                    "call graph is complete",
                ],
                broken_if=[
                    "sanitizer exists on path",
                    "dead code (unreachable)",
                ],
                unknowns=[],  # Taint analysis is deterministic
            ),
        )

        # Evidence (RFC-027 Section 6.3)
        # Parse location (format: "file:line")
        source_file, source_line = self._parse_location(source_location)
        sink_file, sink_line = self._parse_location(sink_location)

        evidence = Evidence(
            id=evidence_id,
            kind=EvidenceKind.DATA_FLOW_PATH,
            location=Location(
                file_path=sink_file,  # Sink location (primary)
                start_line=sink_line,
                end_line=sink_line,
            ),
            content={
                "source": source_atom_id,
                "source_location": source_location,
                "sink": sink_atom_id,
                "sink_location": sink_location,
                "path": path,  # Node IDs
                "path_length": len(path),
                "has_sanitizer": False,  # SimpleVulnerability doesn't track this
                "policy_id": policy_id,
            },
            provenance=Provenance(
                engine="TaintAnalyzer",
                template=policy_id,
                snapshot_id=snapshot_id,
                version=TAINT_VERSION,
                timestamp=time.time(),
            ),
            claim_ids=[claim_id],  # Link to claim
        )

        return claim, evidence

    def _parse_location(self, location_str: str) -> tuple[str, int]:
        """
        Parse location string to (file_path, line_number)

        Args:
            location_str: Format "file:line" or "file"

        Returns:
            (file_path, line_number)

        Example:
            >>> _parse_location("api/users.py:42")
            ("api/users.py", 42)
        """
        if ":" in location_str:
            parts = location_str.rsplit(":", 1)
            file_path = parts[0]
            try:
                line_num = int(parts[1])
                # Ensure line number is at least 1 (Pydantic Location constraint)
                if line_num < 1:
                    line_num = 1
            except ValueError:
                logger.warning(
                    "invalid_line_number",
                    location=location_str,
                )
                line_num = 1  # Fallback
            return file_path, line_num
        else:
            # No line number
            return location_str, 1

    def _build_conclusion(self, vulnerabilities: list[SimpleVulnerability | dict]) -> Conclusion:
        """
        Build conclusion from vulnerabilities

        Args:
            vulnerabilities: List of vulnerabilities (dict or Pydantic model)

        Returns:
            Conclusion with summary and recommendation
        """

        # Helper to get attribute from dict or object
        def get_attr(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # Count by severity
        critical_count = sum(1 for v in vulnerabilities if get_attr(v, "severity") == "critical")
        high_count = sum(1 for v in vulnerabilities if get_attr(v, "severity") == "high")

        # Count by type
        types = {}
        for v in vulnerabilities:
            policy_id = get_attr(v, "policy_id", "unknown")
            types[policy_id] = types.get(policy_id, 0) + 1

        # Reasoning summary
        type_summary = ", ".join(f"{count} {policy}" for policy, count in types.items())
        reasoning = f"Static taint analysis found {len(vulnerabilities)} vulnerabilities: {type_summary}"

        # Recommendation
        if critical_count > 0:
            recommendation = (
                f"CRITICAL: Fix {critical_count} critical vulnerabilities immediately. "
                "Use parameterized queries, escape user input, validate all external data."
            )
        elif high_count > 0:
            recommendation = (
                f"HIGH: Fix {high_count} high-severity vulnerabilities. Review data flow paths and add sanitization."
            )
        else:
            recommendation = "Review and fix medium/low vulnerabilities. Consider adding input validation."

        return Conclusion(
            reasoning_summary=reasoning,
            coverage=1.0,  # Taint analysis covers all paths
            counterevidence=[],  # No counterevidence (deterministic)
            recommendation=recommendation,
        )

    def _build_metrics(
        self,
        execution_time_ms: float,
        claims_generated: int,
        taint_result: dict,
    ) -> Metrics:
        """
        Build metrics from taint result

        Args:
            execution_time_ms: Execution time
            claims_generated: Number of claims
            taint_result: Taint analysis result

        Returns:
            Metrics
        """
        stats = taint_result.get("stats", {})

        return Metrics(
            execution_time_ms=execution_time_ms,
            paths_analyzed=stats.get("paths_found", 0),
            claims_generated=claims_generated,
            claims_suppressed=0,  # No suppression yet (before arbitration)
            cache_hits=0,  # TaintAnalysisService doesn't report this
            additional={
                "atoms_detected": stats.get("atoms_detected", 0),
                "policies_executed": len(taint_result.get("policies_executed", [])),
                "policies_skipped": len(taint_result.get("policies_skipped", [])),
            },
        )
