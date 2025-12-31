"""
Evidence Models (RFC-027 + RFC-028)

Evidence는 Claim을 지지하는 machine-readable 증거입니다.

Architecture:
- Domain Layer (Pure model)
- No infrastructure dependencies
- Immutable (frozen=True)
- Type-safe (Pydantic)

RFC-027 Section 6.3: Evidence
RFC-028 Section 3: Common Evidence Schema
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EvidenceKind(str, Enum):
    """
    Evidence 종류 (RFC-027 + RFC-028)

    RFC-027 기본:
    - CODE_SNIPPET: 코드 조각
    - DATA_FLOW_PATH: 데이터 흐름 경로 (Taint)
    - CALL_PATH: 호출 경로
    - DIFF: 코드 변경 사항
    - TEST_RESULT: 테스트 실행 결과

    RFC-028 추가:
    - COST_TERM: 복잡도 표현식 (O(n), O(n²))
    - LOOP_BOUND: 루프 반복 횟수
    - RACE_WITNESS: Race condition 증거
    - LOCK_REGION: Lock 보호 영역
    - DIFF_DELTA: Differential 변경 사항
    """

    # RFC-027 Basic
    CODE_SNIPPET = "code_snippet"
    DATA_FLOW_PATH = "data_flow_path"
    CALL_PATH = "call_path"
    DIFF = "diff"
    TEST_RESULT = "test_result"

    # RFC-028 Analysis-Specific
    COST_TERM = "cost_term"
    LOOP_BOUND = "loop_bound"
    RACE_WITNESS = "race_witness"
    LOCK_REGION = "lock_region"
    DIFF_DELTA = "diff_delta"


class Location(BaseModel):
    """
    Source code location (RFC-027 Section 6.3)

    Immutable value object representing a span in source code.

    Validation:
    - file_path: non-empty, no path traversal (..)
    - line numbers: positive
    - start <= end
    """

    file_path: str = Field(..., min_length=1, description="Source file path (relative to repo root)")
    start_line: int = Field(..., ge=1, description="Start line number (1-based)")
    end_line: int = Field(..., ge=1, description="End line number (1-based)")
    start_col: int = Field(default=0, ge=0, description="Start column (0-based)")
    end_col: int = Field(default=0, ge=0, description="End column (0-based)")

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        """Validate file path (security)"""
        # Path traversal 방지
        if ".." in v:
            raise ValueError(f"Path traversal detected: {v}")

        # 절대 경로 방지 (상대 경로만)
        if v.startswith("/"):
            raise ValueError(f"Absolute path not allowed: {v}")

        return v

    @field_validator("end_line")
    @classmethod
    def validate_line_order(cls, v: int, info) -> int:
        """Validate start_line <= end_line"""
        start_line = info.data.get("start_line")
        if start_line is not None and v < start_line:
            raise ValueError(f"end_line ({v}) must be >= start_line ({start_line})")
        return v

    @field_validator("end_col")
    @classmethod
    def validate_col_order(cls, v: int, info) -> int:
        """Validate start_col <= end_col (same line)"""
        start_line = info.data.get("start_line")
        end_line = info.data.get("end_line")
        start_col = info.data.get("start_col", 0)

        # Same line이면 start_col <= end_col
        if start_line == end_line and v > 0 and v < start_col:
            raise ValueError(f"end_col ({v}) must be >= start_col ({start_col}) on same line")

        return v

    model_config = {"frozen": True}


class Provenance(BaseModel):
    """
    Evidence 출처 (RFC-027 Section 6.3)

    어느 엔진이, 언제, 어떻게 생성했는지 추적.

    Validation:
    - engine: non-empty
    - version: semantic version (optional)
    - timestamp: valid unix timestamp
    """

    engine: str = Field(..., min_length=1, description="Analysis engine name (e.g., TaintAnalyzer, CostAnalyzer)")
    template: str | None = Field(None, description="Analysis template/policy ID (e.g., sql_injection)")
    snapshot_id: str | None = Field(None, description="Code snapshot ID")
    version: str | None = Field(None, description="Engine version (semver)")
    timestamp: float = Field(default=0.0, ge=0.0, description="Unix timestamp")

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str | None) -> str | None:
        """Validate semantic version (optional)"""
        if v is None:
            return v

        # Basic semver pattern: X.Y.Z
        import re

        if not re.match(r"^\d+\.\d+\.\d+", v):
            raise ValueError(f"Invalid semver format: {v}")

        return v

    model_config = {"frozen": True}


class Evidence(BaseModel):
    """
    Evidence (RFC-027 Section 6.3 + RFC-028 Section 3)

    Machine-readable 증거.

    핵심 설계:
    - content는 dict (machine-readable, not string)
    - kind에 따라 content 구조가 다름
    - Claim과 N:M 관계 (claim_ids)

    Validation:
    - id: UUID format (req_xxx_ev_xxx)
    - kind: EvidenceKind enum
    - content: non-empty dict
    - claim_ids: non-empty list

    Examples:
        # Taint path
        Evidence(
            id="req_001_ev_001",
            kind=EvidenceKind.DATA_FLOW_PATH,
            location=Location(file_path="api.py", start_line=42, end_line=42),
            content={
                "source": "request.args",
                "sink": "cursor.execute",
                "path": ["var_1", "var_2", "call_3"],
                "has_sanitizer": False
            },
            provenance=Provenance(engine="TaintAnalyzer", template="sql_injection"),
            claim_ids=["claim_001"]
        )

        # Cost term (RFC-028)
        Evidence(
            id="req_002_ev_001",
            kind=EvidenceKind.COST_TERM,
            location=Location(file_path="utils.py", start_line=10, end_line=20),
            content={
                "cost_term": "n * m",
                "loop_bounds": [
                    {"loop_id": "loop_1", "bound": "n", "method": "pattern", "confidence": 1.0},
                    {"loop_id": "loop_2", "bound": "m", "method": "pattern", "confidence": 1.0}
                ],
                "hotspots": [
                    {"line": 15, "reason": "nested loop"}
                ]
            },
            provenance=Provenance(engine="CostAnalyzer", version="1.0.0"),
            claim_ids=["claim_002"]
        )
    """

    id: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_-]+$", description="Evidence ID (UUID format)")
    kind: EvidenceKind = Field(..., description="Evidence type")
    location: Location = Field(..., description="Source location")
    content: dict[str, Any] = Field(..., min_length=1, description="Machine-readable content (kind-specific)")
    provenance: Provenance = Field(..., description="Evidence provenance (source tracking)")
    claim_ids: list[str] = Field(..., min_length=1, description="Linked claim IDs (N:M relationship)")

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: dict[str, Any], info) -> dict[str, Any]:
        """
        Validate content structure based on kind

        CRITICAL: content는 kind에 따라 필수 필드가 다름
        """
        kind = info.data.get("kind")

        if kind == EvidenceKind.DATA_FLOW_PATH:
            # Taint path 필수 필드
            required = ["source", "sink", "path"]
            for field in required:
                if field not in v:
                    raise ValueError(f"DATA_FLOW_PATH requires '{field}' in content")

        elif kind == EvidenceKind.COST_TERM:
            # Cost term 필수 필드 (RFC-028)
            required = ["cost_term", "loop_bounds"]
            for field in required:
                if field not in v:
                    raise ValueError(f"COST_TERM requires '{field}' in content")

            # loop_bounds validation
            if not isinstance(v["loop_bounds"], list):
                raise ValueError("loop_bounds must be list")

        elif kind == EvidenceKind.RACE_WITNESS:
            # Race witness 필수 필드 (RFC-028)
            required = ["shared_variable", "accesses", "interleaving_path"]
            for field in required:
                if field not in v:
                    raise ValueError(f"RACE_WITNESS requires '{field}' in content")

        # 다른 kind들은 content가 있기만 하면 OK (확장 가능)

        return v

    @field_validator("claim_ids")
    @classmethod
    def validate_claim_ids(cls, v: list[str]) -> list[str]:
        """
        Validate claim IDs

        Special case: Allow ["pending"] for construction-time.
        - 팀 A가 Evidence 만들 때: claim_ids=["pending"]
        - 팀 B가 Claim 만든 후: claim_ids를 실제 ID로 교체
        """
        if not v:
            raise ValueError("claim_ids cannot be empty (must link to at least one claim)")

        for claim_id in v:
            if not claim_id or not claim_id.strip():
                raise ValueError(f"Invalid claim_id: '{claim_id}'")

        return v

    model_config = {"frozen": True}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization"""
        return {
            "id": self.id,
            "kind": self.kind.value,
            "location": {
                "file_path": self.location.file_path,
                "start_line": self.location.start_line,
                "end_line": self.location.end_line,
                "start_col": self.location.start_col,
                "end_col": self.location.end_col,
            },
            "content": self.content,
            "provenance": {
                "engine": self.provenance.engine,
                "template": self.provenance.template,
                "snapshot_id": self.provenance.snapshot_id,
                "version": self.provenance.version,
                "timestamp": self.provenance.timestamp,
            },
            "claim_ids": self.claim_ids,
        }


# ============================================================
# RFC-028 Typed Evidence Builders (Type-safe helpers)
# ============================================================


class CostEvidenceBuilder:
    """
    Type-safe builder for Cost Evidence (RFC-028)

    Usage:
        evidence = CostEvidenceBuilder.build(
            evidence_id="req_001_ev_001",
            location=Location(...),
            cost_term="n * m",
            loop_bounds=[...],
            hotspots=[...],
            provenance=Provenance(engine="CostAnalyzer")
        )
    """

    @staticmethod
    def build(
        evidence_id: str,
        location: Location,
        cost_term: str,
        loop_bounds: list[dict[str, Any]],
        hotspots: list[dict[str, Any]],
        provenance: Provenance,
        claim_ids: list[str],
    ) -> Evidence:
        """Build Cost Evidence with validation"""
        # Validate loop_bounds structure
        for lb in loop_bounds:
            required = ["loop_id", "bound", "method", "confidence"]
            for field in required:
                if field not in lb:
                    raise ValueError(f"loop_bound missing '{field}': {lb}")

            # Confidence range
            if not 0.0 <= lb["confidence"] <= 1.0:
                raise ValueError(f"confidence must be 0.0-1.0: {lb['confidence']}")

        # Validate hotspots
        for hs in hotspots:
            if "line" not in hs or "reason" not in hs:
                raise ValueError(f"hotspot requires 'line' and 'reason': {hs}")

        return Evidence(
            id=evidence_id,
            kind=EvidenceKind.COST_TERM,
            location=location,
            content={
                "cost_term": cost_term,
                "loop_bounds": loop_bounds,
                "hotspots": hotspots,
                "inference_method": provenance.template or "unknown",
            },
            provenance=provenance,
            claim_ids=claim_ids,
        )


class ConcurrencyEvidenceBuilder:
    """
    Type-safe builder for Concurrency Evidence (RFC-028)

    Usage:
        evidence = ConcurrencyEvidenceBuilder.build(
            evidence_id="req_002_ev_001",
            location=Location(...),
            shared_variable={"var_id": "x", "escape_status": "shared"},
            await_cuts=["node_5", "node_10"],
            lock_regions=[...],
            race_witness={...},
            provenance=Provenance(engine="RaceDetector"),
            claim_ids=["claim_002"]
        )
    """

    @staticmethod
    def build(
        evidence_id: str,
        location: Location,
        shared_variable: dict[str, Any],
        await_cuts: list[str],
        lock_regions: list[dict[str, Any]],
        race_witness: dict[str, Any] | None,
        provenance: Provenance,
        claim_ids: list[str],
    ) -> Evidence:
        """Build Concurrency Evidence with validation"""
        # Validate shared_variable
        required = ["var_id", "var_name", "escape_status"]
        for field in required:
            if field not in shared_variable:
                raise ValueError(f"shared_variable missing '{field}': {shared_variable}")

        # escape_status must be valid
        valid_escape = ["local", "shared", "unknown"]
        if shared_variable["escape_status"] not in valid_escape:
            raise ValueError(f"escape_status must be one of {valid_escape}")

        # Validate lock_regions
        for lr in lock_regions:
            required = ["lock_id", "scope", "resolved_alias"]
            for field in required:
                if field not in lr:
                    raise ValueError(f"lock_region missing '{field}': {lr}")

            # resolved_alias must be bool
            if not isinstance(lr["resolved_alias"], bool):
                raise ValueError(f"resolved_alias must be bool: {lr['resolved_alias']}")

        # Validate race_witness (optional)
        if race_witness is not None:
            required = ["access1", "access2", "interleaving_path"]
            for field in required:
                if field not in race_witness:
                    raise ValueError(f"race_witness missing '{field}': {race_witness}")

        return Evidence(
            id=evidence_id,
            kind=EvidenceKind.RACE_WITNESS if race_witness else EvidenceKind.LOCK_REGION,
            location=location,
            content={
                "shared_variable": shared_variable,  # Fixed: matches validation
                "accesses": await_cuts,  # Fixed: matches validation
                "interleaving_path": race_witness.get("interleaving_path", []) if race_witness else [],  # Fixed
                "await_cuts": await_cuts,  # Keep for backward compat
                "lock_regions": lock_regions,
                "race_witness": race_witness,
            },
            provenance=provenance,
            claim_ids=claim_ids,
        )


class DifferentialEvidenceBuilder:
    """
    Type-safe builder for Differential Evidence (RFC-028)

    Usage:
        evidence = DifferentialEvidenceBuilder.build(
            evidence_id="req_003_ev_001",
            location=Location(...),
            base_snapshot="snap_455",
            pr_snapshot="snap_456",
            scope={"changed": [...], "impact_closure": [...]},
            deltas={"sanitizer_removed": [...], ...},
            fingerprints={"before": {...}, "after": {...}},
            provenance=Provenance(engine="DifferentialAnalyzer"),
            claim_ids=["claim_003"]
        )
    """

    @staticmethod
    def build(
        evidence_id: str,
        location: Location,
        base_snapshot: str,
        pr_snapshot: str,
        scope: dict[str, Any],
        deltas: dict[str, Any],
        fingerprints: dict[str, Any],
        provenance: Provenance,
        claim_ids: list[str],
    ) -> Evidence:
        """Build Differential Evidence with validation"""
        # Validate scope
        required = ["changed_functions", "impact_closure", "total_symbols"]
        for field in required:
            if field not in scope:
                raise ValueError(f"scope missing '{field}': {scope}")

        # Validate deltas
        if not deltas:
            raise ValueError("deltas cannot be empty")

        # Validate fingerprints
        if "before" not in fingerprints or "after" not in fingerprints:
            raise ValueError("fingerprints must have 'before' and 'after'")

        return Evidence(
            id=evidence_id,
            kind=EvidenceKind.DIFF_DELTA,
            location=location,
            content={
                "base_snapshot": base_snapshot,
                "pr_snapshot": pr_snapshot,
                "scope": scope,
                "deltas": deltas,
                "fingerprints": fingerprints,
            },
            provenance=provenance,
            claim_ids=claim_ids,
        )


# ============================================================
# Evidence Collection Helpers
# ============================================================


def validate_evidence_claim_links(evidences: list[Evidence], claim_ids: set[str]) -> None:
    """
    Validate that all evidence claim_ids reference valid claims

    Args:
        evidences: List of evidences
        claim_ids: Set of valid claim IDs

    Raises:
        ValueError: If any evidence references invalid claim

    Production Guard:
    - 모든 Evidence는 반드시 유효한 Claim을 참조해야 함
    - Orphan evidence 방지
    """
    for evidence in evidences:
        for claim_id in evidence.claim_ids:
            if claim_id not in claim_ids:
                raise ValueError(f"Evidence {evidence.id} references invalid claim: {claim_id} (valid: {claim_ids})")


def group_evidences_by_kind(evidences: list[Evidence]) -> dict[EvidenceKind, list[Evidence]]:
    """
    Group evidences by kind

    Args:
        evidences: List of evidences

    Returns:
        Dict mapping EvidenceKind to list of evidences

    Usage:
        grouped = group_evidences_by_kind(evidences)
        cost_evidences = grouped.get(EvidenceKind.COST_TERM, [])
    """
    from collections import defaultdict

    grouped: dict[EvidenceKind, list[Evidence]] = defaultdict(list)

    for evidence in evidences:
        grouped[evidence.kind].append(evidence)

    return dict(grouped)
