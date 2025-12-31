"""
ResultEnvelope Models (RFC-027 Section 6)

RFC-027의 canonical output format.
모든 분석 결과는 이 형식으로 반환됩니다.

Architecture:
- Domain Layer (Pure model)
- Immutable (frozen=True for value objects)
- Type-safe (Pydantic)
- JSON serializable

RFC-027 Section 6.1: ResultEnvelope
RFC-027 Section 6.4: Conclusion
RFC-027 Section 6.5: Escalation
RFC-027 Section 8.2: Metrics
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator

from .claim import Claim
from .evidence import Evidence, validate_evidence_claim_links


class Conclusion(BaseModel):
    """
    Conclusion (RFC-027 Section 6.4)

    전체 분석 결과에 대한 결론 및 권장사항.

    Fields:
    - reasoning_summary: 추론 과정 요약 (human-readable)
    - coverage: 분석 범위 커버리지 (0.0-1.0)
    - counterevidence: 반대 증거 (Claim을 약화시키는 요소)
    - recommendation: 실행 가능한 권장사항

    Validation:
    - reasoning_summary: non-empty
    - coverage: 0.0-1.0
    - recommendation: non-empty

    Example:
        Conclusion(
            reasoning_summary="Static taint analysis found 2 SQL injection paths",
            coverage=0.85,
            counterevidence=["Sanitizer present in 1 path but disabled"],
            recommendation="Use parameterized queries in user_api.py:42 and admin_api.py:67"
        )
    """

    reasoning_summary: str = Field(..., min_length=1, description="Human-readable reasoning summary")
    coverage: float = Field(..., ge=0.0, le=1.0, description="Analysis coverage (0.0-1.0)")
    counterevidence: list[str] = Field(default_factory=list, description="Evidence against claims")
    recommendation: str = Field(..., min_length=1, description="Actionable recommendation")

    @field_validator("counterevidence")
    @classmethod
    def validate_counterevidence(cls, v: list[str]) -> list[str]:
        """Validate counterevidence items are non-empty"""
        for item in v:
            if not item or not item.strip():
                raise ValueError(f"Empty counterevidence item: {v}")
        return v

    model_config = {"frozen": True}


class Metrics(BaseModel):
    """
    Metrics (RFC-027 Section 8.2)

    분석 실행 메트릭.

    Fields:
    - execution_time_ms: 실행 시간 (밀리초)
    - paths_analyzed: 분석한 경로 수 (Taint/DFG)
    - claims_generated: 생성된 Claim 수
    - claims_suppressed: Arbitration으로 억제된 Claim 수
    - cache_hits: 캐시 히트 (증분 분석)
    - additional: 추가 메트릭 (Analyzer별 자유)

    Validation:
    - All counts >= 0
    - execution_time_ms > 0
    - claims_suppressed <= claims_generated

    Example:
        Metrics(
            execution_time_ms=234.5,
            paths_analyzed=150,
            claims_generated=3,
            claims_suppressed=1,
            cache_hits=45,
            additional={"sccp_iterations": 12}
        )
    """

    execution_time_ms: float = Field(..., gt=0.0, description="Execution time (milliseconds)")
    paths_analyzed: int = Field(default=0, ge=0, description="Paths analyzed (Taint/DFG)")
    claims_generated: int = Field(default=0, ge=0, description="Claims generated")
    claims_suppressed: int = Field(default=0, ge=0, description="Claims suppressed by arbitration")
    cache_hits: int = Field(default=0, ge=0, description="Cache hits (incremental)")
    additional: dict[str, Any] = Field(default_factory=dict, description="Additional analyzer-specific metrics")

    @field_validator("claims_suppressed")
    @classmethod
    def validate_suppressed_count(cls, v: int, info) -> int:
        """Validate claims_suppressed <= claims_generated"""
        generated = info.data.get("claims_generated", 0)
        if v > generated:
            raise ValueError(f"claims_suppressed ({v}) cannot exceed claims_generated ({generated})")
        return v

    model_config = {"frozen": True}


class Escalation(BaseModel):
    """
    Escalation (RFC-027 Section 6.5)

    Human escalation 요청.

    Fields:
    - required: Escalation 필요 여부
    - reason: 왜 필요한가?
    - decision_needed: 어떤 결정이 필요한가?
    - options: 선택 가능한 옵션들
    - resume_token: 재개 토큰 (async resume)

    Validation:
    - required=True → reason, decision_needed, options 필수
    - options: 최소 2개 이상
    - resume_token: optional (async resume용)

    Example:
        Escalation(
            required=True,
            reason="High-risk edit: 50+ symbols affected",
            decision_needed="Approve or reject symbol rename",
            options=["approve", "reject", "modify"],
            resume_token="resume:req_abc123"
        )
    """

    required: bool = Field(..., description="Escalation required?")
    reason: str = Field(default="", description="Why escalation is needed")
    decision_needed: str = Field(default="", description="What decision is needed")
    options: list[str] = Field(default_factory=list, description="Available options")
    resume_token: str | None = Field(None, description="Resume token for async workflow")

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str, info) -> str:
        """If required=True, reason must be non-empty"""
        required = info.data.get("required", False)
        if required and not v:
            raise ValueError("reason is required when escalation.required=True")
        return v

    @field_validator("decision_needed")
    @classmethod
    def validate_decision(cls, v: str, info) -> str:
        """If required=True, decision_needed must be non-empty"""
        required = info.data.get("required", False)
        if required and not v:
            raise ValueError("decision_needed is required when escalation.required=True")
        return v

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: list[str], info) -> list[str]:
        """If required=True, options must have at least 2 items"""
        required = info.data.get("required", False)
        if required and len(v) < 2:
            raise ValueError(f"At least 2 options required when escalation.required=True, got {len(v)}")

        # Validate option strings
        for option in v:
            if not option or not option.strip():
                raise ValueError(f"Empty option in list: {v}")

        return v

    model_config = {"frozen": True}


class ResultEnvelope(BaseModel):
    """
    ResultEnvelope (RFC-027 Section 6.1)

    RFC-027의 canonical output format.
    모든 분석 결과는 이 구조로 반환됩니다.

    핵심 설계:
    - Claim–Evidence–Conclusion 구조 (RFC-027 Section 8)
    - Immutable (frozen=True)
    - JSON serializable
    - Replay 가능 (replay_ref)

    필드:
    - request_id: 요청 ID (UUID)
    - summary: 한줄 요약 (human-readable)
    - claims: 주장 목록 (0개 이상)
    - evidences: 증거 목록 (0개 이상)
    - conclusion: 결론 (optional, claims 있으면 권장)
    - metrics: 실행 메트릭
    - escalation: Escalation 요청 (optional)
    - replay_ref: Replay 참조 (replay:request_id)

    Validation Rules:
    1. request_id: non-empty, pattern ^req_[a-zA-Z0-9_-]+$
    2. summary: non-empty, max 500 chars
    3. claims–evidences 링크 일관성:
       - Evidence.claim_ids는 유효한 Claim.id만 참조
       - Orphan evidence 금지
    4. conclusion.coverage와 실제 coverage 일치
    5. escalation.required=True → escalation 필수

    Example:
        ResultEnvelope(
            request_id="req_abc123",
            summary="Found 2 SQL injection vulnerabilities",
            claims=[
                Claim(...),
                Claim(...)
            ],
            evidences=[
                Evidence(...),
                Evidence(...)
            ],
            conclusion=Conclusion(...),
            metrics=Metrics(execution_time_ms=234.5, ...),
            escalation=None,
            replay_ref="replay:req_abc123"
        )
    """

    request_id: str = Field(..., min_length=1, pattern=r"^req_[a-zA-Z0-9_-]+$", description="Request ID (UUID format)")
    summary: str = Field(..., min_length=1, max_length=500, description="One-line summary (human-readable)")
    claims: list[Claim] = Field(default_factory=list, description="Claims (assertions)")
    evidences: list[Evidence] = Field(default_factory=list, description="Evidences (machine-readable proof)")
    conclusion: Conclusion | None = Field(None, description="Conclusion (recommended if claims exist)")
    metrics: Metrics = Field(..., description="Execution metrics")
    escalation: Escalation | None = Field(None, description="Escalation request (optional)")
    replay_ref: str = Field(..., pattern=r"^replay:[a-zA-Z0-9_-]+$", description="Replay reference")

    @field_validator("replay_ref")
    @classmethod
    def validate_replay_ref_consistency(cls, v: str, info) -> str:
        """Validate replay_ref matches request_id"""
        request_id = info.data.get("request_id", "")
        expected = f"replay:{request_id.replace('req_', '')}"

        if v != expected:
            raise ValueError(f"replay_ref must be 'replay:<request_id_suffix>', got {v} (expected {expected})")

        return v

    @field_validator("conclusion")
    @classmethod
    def validate_conclusion_recommendation(cls, v: Conclusion | None, info) -> Conclusion | None:
        """If claims exist, conclusion is strongly recommended"""
        claims = info.data.get("claims", [])

        # Warning (not error): conclusion 권장
        if claims and v is None:
            import warnings

            warnings.warn("Conclusion is recommended when claims exist", UserWarning, stacklevel=2)

        return v

    @field_validator("evidences")
    @classmethod
    def validate_evidence_claim_consistency(cls, v: list[Evidence], info) -> list[Evidence]:
        """
        Validate evidence–claim links (CRITICAL)

        Rule: Evidence.claim_ids must reference valid Claim.id
        Prevents orphan evidences.
        """
        claims = info.data.get("claims", [])
        if not claims:
            # No claims → no evidence validation needed
            return v

        # Collect valid claim IDs
        valid_claim_ids = {claim.id for claim in claims}

        # Validate all evidences
        validate_evidence_claim_links(v, valid_claim_ids)

        return v

    @field_validator("metrics")
    @classmethod
    def validate_metrics_consistency(cls, v: Metrics, info) -> Metrics:
        """Validate metrics consistency with claims"""
        claims = info.data.get("claims", [])

        # Check claims_generated matches actual count
        actual_generated = len(claims)
        if v.claims_generated != actual_generated:
            raise ValueError(f"metrics.claims_generated ({v.claims_generated}) != actual ({actual_generated})")

        # Check claims_suppressed matches suppressed count
        actual_suppressed = sum(1 for claim in claims if claim.suppressed)
        if v.claims_suppressed != actual_suppressed:
            raise ValueError(f"metrics.claims_suppressed ({v.claims_suppressed}) != actual ({actual_suppressed})")

        return v

    model_config = {"frozen": True}

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dict for JSON serialization

        Returns:
            Dict representation (JSON-compatible)

        Example:
            envelope = ResultEnvelope(...)
            json_data = envelope.to_dict()
            import json
            json.dumps(json_data)  # Valid JSON
        """
        return {
            "request_id": self.request_id,
            "summary": self.summary,
            "claims": [claim.to_dict() for claim in self.claims],
            "evidences": [evidence.to_dict() for evidence in self.evidences],
            "conclusion": (
                {
                    "reasoning_summary": self.conclusion.reasoning_summary,
                    "coverage": self.conclusion.coverage,
                    "counterevidence": self.conclusion.counterevidence,
                    "recommendation": self.conclusion.recommendation,
                }
                if self.conclusion
                else None
            ),
            "metrics": {
                "execution_time_ms": self.metrics.execution_time_ms,
                "paths_analyzed": self.metrics.paths_analyzed,
                "claims_generated": self.metrics.claims_generated,
                "claims_suppressed": self.metrics.claims_suppressed,
                "cache_hits": self.metrics.cache_hits,
                "additional": self.metrics.additional,
            },
            "escalation": (
                {
                    "required": self.escalation.required,
                    "reason": self.escalation.reason,
                    "decision_needed": self.escalation.decision_needed,
                    "options": self.escalation.options,
                    "resume_token": self.escalation.resume_token,
                }
                if self.escalation
                else None
            ),
            "replay_ref": self.replay_ref,
        }

    def get_actionable_claims(self) -> list[Claim]:
        """
        Get actionable claims (not suppressed)

        Returns:
            List of claims that should be shown to user

        Example:
            actionable = envelope.get_actionable_claims()
            for claim in actionable:
                print(f"[{claim.severity}] {claim.type}")
        """
        return [claim for claim in self.claims if claim.is_actionable()]

    def get_high_confidence_claims(self) -> list[Claim]:
        """
        Get high-confidence claims (confidence >= 0.8)

        Returns:
            List of high-confidence claims
        """
        return [claim for claim in self.claims if claim.is_high_confidence()]

    def get_proven_claims(self) -> list[Claim]:
        """
        Get proven claims (confidence_basis=PROVEN)

        Returns:
            List of statically proven claims
        """
        return [claim for claim in self.claims if claim.is_proven()]

    def has_escalation(self) -> bool:
        """Check if escalation is required"""
        return self.escalation is not None and self.escalation.required


# ============================================================
# ResultEnvelope Builders (Type-safe construction)
# ============================================================


class ResultEnvelopeBuilder:
    """
    Type-safe builder for ResultEnvelope

    Usage:
        builder = ResultEnvelopeBuilder(request_id="req_001")
        builder.set_summary("Found 2 issues")
        builder.add_claim(claim1)
        builder.add_claim(claim2)
        builder.add_evidence(evidence1)
        builder.set_conclusion(conclusion)
        builder.set_metrics(metrics)
        envelope = builder.build()

    Validation:
    - Claims/evidences 링크 일관성 자동 검증
    - Metrics 자동 계산
    - replay_ref 자동 생성
    """

    def __init__(self, request_id: str):
        """
        Initialize builder

        Args:
            request_id: Request ID (must match pattern req_xxx)

        Raises:
            ValueError: If request_id invalid
        """
        if not request_id.startswith("req_"):
            raise ValueError(f"request_id must start with 'req_', got {request_id}")

        self.request_id = request_id
        self.summary: str | None = None
        self.claims: list[Claim] = []
        self.evidences: list[Evidence] = []
        self.conclusion: Conclusion | None = None
        self.metrics: Metrics | None = None
        self.escalation: Escalation | None = None

    def set_summary(self, summary: str) -> "ResultEnvelopeBuilder":
        """Set summary"""
        self.summary = summary
        return self

    def add_claim(self, claim: Claim) -> "ResultEnvelopeBuilder":
        """Add claim"""
        self.claims.append(claim)
        return self

    def add_claims(self, claims: list[Claim]) -> "ResultEnvelopeBuilder":
        """Add multiple claims"""
        self.claims.extend(claims)
        return self

    def add_evidence(self, evidence: Evidence) -> "ResultEnvelopeBuilder":
        """Add evidence"""
        self.evidences.append(evidence)
        return self

    def add_evidences(self, evidences: list[Evidence]) -> "ResultEnvelopeBuilder":
        """Add multiple evidences"""
        self.evidences.extend(evidences)
        return self

    def set_conclusion(self, conclusion: Conclusion) -> "ResultEnvelopeBuilder":
        """Set conclusion"""
        self.conclusion = conclusion
        return self

    def set_metrics(self, metrics: Metrics) -> "ResultEnvelopeBuilder":
        """Set metrics (will auto-calculate claims counts if not set)"""
        self.metrics = metrics
        return self

    def set_escalation(self, escalation: Escalation) -> "ResultEnvelopeBuilder":
        """Set escalation"""
        self.escalation = escalation
        return self

    def build(self) -> ResultEnvelope:
        """
        Build ResultEnvelope

        Returns:
            ResultEnvelope (validated)

        Raises:
            ValueError: If required fields missing or validation fails
        """
        if not self.summary:
            raise ValueError("summary is required")

        # Auto-generate metrics if not set
        if not self.metrics:
            self.metrics = Metrics(
                execution_time_ms=0.1,  # Minimal valid value (100 microseconds)
                claims_generated=len(self.claims),
                claims_suppressed=sum(1 for c in self.claims if c.suppressed),
            )

        # Generate replay_ref
        replay_ref = f"replay:{self.request_id.replace('req_', '')}"

        # Build (will trigger all validations)
        return ResultEnvelope(
            request_id=self.request_id,
            summary=self.summary,
            claims=self.claims,
            evidences=self.evidences,
            conclusion=self.conclusion,
            metrics=self.metrics,
            escalation=self.escalation,
            replay_ref=replay_ref,
        )
