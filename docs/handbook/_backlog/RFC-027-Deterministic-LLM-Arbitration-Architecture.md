# RFC-027: Deterministic Static Analysis × LLM Arbitration Architecture

> **v3.2 — Implementation-Ready RFC (Pipeline-Integrated)**

---

## Metadata

| 항목 | 내용 |
|------|------|
| **RFC ID** | RFC-027 v3.2 |
| **Status** | APPROVED · Implementation Ready |
| **Owner** | Semantica Architecture Team |
| **Created** |  |
| **Updated** |  (Pipeline Integration) |
| **Scope** | Core Engine, API, Safety, Operations, Resilience |
| **Target** | Enterprise-Grade Autonomous Code Agent |
| **Baseline** | SCCP+ Static Engine (91% coverage) + Chunk Graph + Vector Search |
| **Estimated Effort** | 4-6 weeks |
| **Related RFCs** | RFC-006 (Reasoning Pipeline), RFC-024 (SCCP), RFC-021 (Incremental) |

---

## 1. Executive Summary

### 1.1 Purpose

본 RFC는 **LLM의 확률적 추론(Stochastic Reasoning)**과 **정적 분석 엔진의 결정적 실행(Deterministic Proof)**을 구조적으로 중재(Arbitration)하는 SOTA+ AI Code Agent 아키텍처를 정의한다.

### 1.2 Core Philosophy

```
┌─────────────────────────────────────────────────────────────────┐
│  LLM은 의도(Intent)만 표현한다                                   │
│  실행·검증·판단은 결정적 엔진이 수행한다                          │
│  모든 결과는 Claim–Evidence–Conclusion 구조로만 외부에 노출된다   │
│  모든 실행은 Guarded · Replayable · Auditable 해야 한다          │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 Key Deliverables

| Deliverable | Description |
|------------|-------------|
| **Spec Contracts** | `RetrieveSpec`, `AnalyzeSpec`, `EditSpec` JSON Schema |
| **ResultEnvelope** | Claim–Evidence–Conclusion + Proof Obligation 구조 |
| **Arbitration Engine** | Deterministic > Heuristic 우선순위 규칙 |
| **Replay Infrastructure** | 모든 요청 재현 가능 |
| **RFC API Surface** | 8개 표준 엔드포인트 |

---

## 2. Current State Analysis (Gap Analysis)

### 2.1 Existing Capabilities (✅ Leverageable)

| Component | Status | Location | RFC Integration |
|-----------|--------|----------|-----------------|
| SCCP+ Static Analysis | 91% coverage (54 analyzers) | `code_foundation/` | → `Claim(confidence_basis=PROVEN)` |
| Taint Analysis | Type-aware, 8 vulnerability types | `code_foundation/infrastructure/taint/` | → `Evidence(kind=DATA_FLOW_PATH)` |
| Graph-Guided Retrieval | CostAwareExpander, FlowExpander | `retrieval_search/` | → `RetrieveSpec` 구현체 |
| Speculative Execution | GraphSimulator, DeltaGraph, RiskAnalyzer | `reasoning_engine/speculative/` | → `EditSpec.dry_run` 구현체 |
| Safety Guardrails | PII/Secret, Risk Classification | `agent/adapters/safety/` | → 기존 그대로 재사용 |
| Semantic Lock | Symbol-level locking | `agent/domain/lock_keeper.py` | → 기존 그대로 재사용 |
| Experience Store | Pattern reuse | `agent/experience_store.py` | → `FeedbackEvent` 확장 |
| **Deep Reasoning** | ToT/Beam/o1/Debate/AlphaCode | `agent/shared/reasoning/` | → `Claim` 생성 소스 |
| **Reasoning Pipeline** | Effect→Impact→Slice→Risk | `reasoning_engine/application/` | → `Conclusion` 생성 소스 |

#### 2.1.1 핵심 기존 모델 → RFC 매핑

```python
# 기존: reasoning_engine/application/reasoning_pipeline.py
@dataclass
class ReasoningResult:
    summary: str
    total_risk: RiskLevel
    total_impact: ImpactLevel
    breaking_changes: list[str]
    impacted_symbols: list[str]
    recommended_actions: list[str]

# RFC-027 변환:
def to_envelope(result: ReasoningResult) -> ResultEnvelope:
    return ResultEnvelope(
        summary=result.summary,
        claims=[Claim(
            type="risk_assessment",
            severity=result.total_risk.value,
            confidence=0.95,
            confidence_basis=ConfidenceBasis.PROVEN  # Static analysis
        )],
        conclusion=Conclusion(
            reasoning_summary=result.summary,
            recommendation="; ".join(result.recommended_actions)
        )
    )
```

```python
# 기존: reasoning_engine/domain/speculative_models.py
@dataclass
class RiskReport:
    risk_level: RiskLevel
    risk_score: float
    affected_symbols: set[str]
    breaking_changes: list[str]
    recommendation: str

# RFC-027 변환:
def risk_to_claim(report: RiskReport) -> Claim:
    return Claim(
        type="breaking_change" if report.is_breaking() else "risk_assessment",
        severity="critical" if report.is_breaking() else report.risk_level.value,
        confidence=1.0 - report.risk_score,  # 역산
        confidence_basis=ConfidenceBasis.PROVEN,
        proof_obligation=ProofObligation(
            assumptions=["call graph is complete"],
            broken_if=["dynamic dispatch unresolved"],
            unknowns=[]
        )
    )
```

#### 2.1.2 Deep Reasoning 통합

```python
# 기존: agent/shared/reasoning/deep/deep_models.py
@dataclass
class DeepReasoningResult:
    final_answer: str
    final_code: str
    reasoning_steps: list[ReasoningStep]
    verification_results: list[VerificationResult]
    final_confidence: float

# RFC-027 변환:
def deep_reasoning_to_envelope(result: DeepReasoningResult) -> ResultEnvelope:
    evidences = [
        Evidence(
            kind=EvidenceKind.CODE_SNIPPET,
            content=step.answer,
            provenance=Provenance(engine="DeepReasoning", template="o1-style")
        )
        for step in result.reasoning_steps
    ]

    # Verification → Claim confidence_basis
    confidence_basis = (
        ConfidenceBasis.PROVEN if all(v.is_valid for v in result.verification_results)
        else ConfidenceBasis.INFERRED
    )

    return ResultEnvelope(
        claims=[Claim(
            type="code_generation",
            confidence=result.final_confidence,
            confidence_basis=confidence_basis
        )],
        evidences=evidences
    )
```

### 2.2 Critical Gaps (🔴 New Implementation Required)

| Gap | RFC Section | Priority | Effort |
|-----|-------------|----------|--------|
| ResultEnvelope 부재 | §6 | P0 | 3 days |
| Spec JSON Schema 미고정 | §5 | P0 | 2 days |
| Arbitration Engine 부재 | §9 | P1 | 2 days |
| Replay Infrastructure 부재 | §14 | P1 | 3 days |
| API Endpoints 미완성 | §4 | P1 | 3 days |
| Confidence Calibration | §16 | P3 | 5 days |

### 2.3 Partial Implementations (🟡 Extension Required)

| Component | Current | Required | Code Location |
|-----------|---------|----------|---------------|
| Guardrails | 4/5 features | + Cost explosion prevention | `agent/adapters/guardrail/guardrails_adapter.py` |
| Human Escalation | Approval workflow | + `resume_token` | `agent/adapters/safety/action_gate.py` |
| Feedback Loop | Experience store | + RLHF-ready events | `agent/experience_store.py` |
| Reasoning Strategies | 6 strategies | + ResultEnvelope 출력 | `agent/orchestrator/models.py` |

### 2.4 Existing Reasoning Strategies (통합 대상)

현재 구현된 추론 전략들 (RFC-027 Claim 소스로 활용):

```python
# agent/orchestrator/models.py
class ReasoningStrategy(str, Enum):
    AUTO = "auto"       # 자동 선택 → confidence_basis: UNKNOWN
    TOT = "tot"         # Tree-of-Thought → confidence_basis: INFERRED
    BEAM = "beam"       # Beam Search → confidence_basis: INFERRED
    O1 = "o1"           # o1-style Verification → confidence_basis: PROVEN (검증 통과 시)
    DEBATE = "debate"   # Multi-Agent → confidence_basis: INFERRED (합의)
    ALPHACODE = "alphacode"  # Clustering → confidence_basis: HEURISTIC
```

**RFC-027 매핑 전략:**

| Strategy | Claim confidence_basis | Evidence kind | Arbitration Priority |
|----------|----------------------|---------------|---------------------|
| O1 (verified) | `PROVEN` | `TEST_RESULT` | 1 (highest) |
| DEBATE (consensus) | `INFERRED` | `CODE_SNIPPET` | 2 |
| BEAM/TOT | `INFERRED` | `CODE_SNIPPET` | 2 |
| ALPHACODE | `HEURISTIC` | `CODE_SNIPPET` | 3 |
| AUTO | `UNKNOWN` | `CODE_SNIPPET` | 4 (lowest) |

---

## 3. Architecture Overview

### 3.1 High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              User / CI / IDE                             │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              API Gateway                                 │
│                    /plan  /validate  /execute  /explain                  │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                             Orchestrator                                 │
│                      RFC Orchestrator (NEW)                              │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Safety Layer                                   │
│              Validator · Policy · Redact · Cost Guard                    │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Execution Layer                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │   Incremental   │  │  Graph-Guided   │  │      SCCP+ Static       │  │
│  │    Retrieval    │  │   Expansion     │  │       Analysis          │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    Speculative Execution                            ││
│  │                  (dry_run + compile/test)                           ││
│  └─────────────────────────────────────────────────────────────────────┘│
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Verification & Arbitration                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │  Claim–Evidence │  │ Proof Obligation│  │   Result Arbitration    │  │
│  │    Matching     │  │     Check       │  │        Engine           │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘  │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           ResultEnvelope                                 │
│           { claims, evidences, conclusion, replay_ref }                  │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
                 Explain         Replay          Resume
```

### 3.2 Repository Structure

```
src/
├── contexts/
│   ├── shared_kernel/
│   │   └── contracts/                    # 🆕 RFC Contracts (Pure Data)
│   │       ├── __init__.py
│   │       ├── specs.py                  # RetrieveSpec, AnalyzeSpec, EditSpec
│   │       ├── envelope.py               # Claim, Evidence, Conclusion, Envelope
│   │       └── confidence.py             # ConfidenceBasis, EvidenceKind enums
│   │
│   ├── llm_arbitration/                  # 🆕 Core RFC Context
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── __init__.py
│   │   │   ├── specs/
│   │   │   │   ├── __init__.py
│   │   │   │   └── validators.py         # Spec validation logic
│   │   │   ├── envelope/
│   │   │   │   ├── __init__.py
│   │   │   │   └── builders.py           # Envelope construction
│   │   │   └── arbitration/
│   │   │       ├── __init__.py
│   │   │       ├── rules.py              # Priority rules
│   │   │       └── conflicts.py          # Conflict resolution
│   │   │
│   │   ├── application/
│   │   │   ├── __init__.py
│   │   │   ├── plan_executor.py
│   │   │   ├── validate_executor.py
│   │   │   ├── execute_executor.py
│   │   │   └── explain_executor.py
│   │   │
│   │   ├── infrastructure/
│   │   │   ├── __init__.py
│   │   │   ├── arbitration_engine.py     # Core arbitration logic
│   │   │   ├── envelope_builder.py       # Result → Envelope conversion
│   │   │   └── adapters/
│   │   │       ├── __init__.py
│   │   │       ├── taint_adapter.py        # TaintResult → Claim+Evidence
│   │   │       ├── sccp_adapter.py         # SCCP → Claim(PROVEN)
│   │   │       ├── reasoning_adapter.py    # ReasoningResult → Conclusion
│   │   │       ├── deep_reasoning_adapter.py  # DeepReasoningResult 통합
│   │   │       ├── risk_adapter.py         # RiskReport → Claim
│   │   │       └── retrieval_adapter.py    # Search results → Evidence
│   │   │
│   │   └── ports/
│   │       ├── __init__.py
│   │       ├── arbitration_port.py
│   │       └── envelope_port.py
│   │
│   └── replay_audit/                     # 🆕 Replay & Audit Context
│       ├── __init__.py
│       ├── domain/
│       │   ├── __init__.py
│       │   └── models.py                 # RequestAuditLog, ReplayEntry
│       ├── application/
│       │   ├── __init__.py
│       │   └── replay_service.py
│       └── infrastructure/
│           ├── __init__.py
│           ├── audit_store.py            # SQLite/PostgreSQL storage
│           └── replay_repository.py
│
└── server/api_server/routes/
    └── rfc/                              # 🆕 RFC API Endpoints
        ├── __init__.py
        ├── plan.py
        ├── validate.py
        ├── execute.py
        ├── explain.py
        ├── replay.py
        ├── feedback.py
        └── sessions.py
```

---

## 4. Public API Surface

### 4.1 Endpoints

| Method | Endpoint | Description | Priority |
|--------|----------|-------------|----------|
| `POST` | `/rfc/plan` | Generate execution plan from intent | P0 |
| `POST` | `/rfc/validate` | Validate spec before execution | P0 |
| `POST` | `/rfc/execute` | Execute spec, return ResultEnvelope | P0 |
| `POST` | `/rfc/explain` | Explain result with reasoning trace | P1 |
| `POST` | `/rfc/jobs` | Async job management | P1 |
| `POST` | `/rfc/sessions` | Session lifecycle management | P2 |
| `GET` | `/rfc/replay/{request_id}` | Replay past request | P1 |
| `POST` | `/rfc/feedback` | Submit feedback for RLHF | P2 |
| `POST` | `/rfc/campaigns` | Batch job orchestration (wrapper) | P3 |

### 4.2 Request/Response Models

#### 4.2.1 Execute Request

```json
{
  "spec": {
    "intent": "analyze",
    "template_id": "sql_injection",
    "scope": {
      "repo_id": "repo:123",
      "snapshot_id": "snap:456",
      "parent_snapshot_id": "snap:455"
    },
    "params": {
      "severity_min": "medium"
    },
    "limits": {
      "max_paths": 200,
      "timeout_ms": 30000
    }
  }
}
```

#### 4.2.2 Execute Response (ResultEnvelope)

```json
{
  "request_id": "req_abc123",
  "summary": "Found 2 SQL injection vulnerabilities",
  "claims": [
    {
      "id": "claim_001",
      "type": "sql_injection",
      "severity": "critical",
      "confidence": 0.95,
      "confidence_basis": "proven",
      "proof_obligation": {
        "assumptions": ["taint propagates through data flow"],
        "broken_if": ["sanitizer exists on path"],
        "unknowns": []
      },
      "suppressed": false,
      "suppression_reason": null
    }
  ],
  "evidences": [
    {
      "id": "ev_001",
      "kind": "data_flow_path",
      "location": {
        "file_path": "src/api/users.py",
        "start_line": 42,
        "end_line": 42
      },
      "content": "cursor.execute(query)",
      "provenance": {
        "engine": "TaintAnalyzer",
        "template": "sql_injection",
        "snapshot_id": "snap:456"
      },
      "claim_ids": ["claim_001"]
    }
  ],
  "conclusion": {
    "reasoning_summary": "Static taint analysis found direct flow from user input to SQL execution",
    "coverage": 0.85,
    "counterevidence": [],
    "recommendation": "Use parameterized queries"
  },
  "metrics": {
    "execution_time_ms": 234,
    "paths_analyzed": 150,
    "claims_generated": 2,
    "claims_suppressed": 0
  },
  "escalation": null,
  "replay_ref": "replay:req_abc123"
}
```

---

## 5. Core Specs (LLM Input Contract)

### 5.1 RetrieveSpec

```python
@dataclass
class RetrieveSpec:
    """Graph-Guided, Incremental Retrieval Specification"""
    intent: Literal["retrieve"] = "retrieve"
    mode: Literal["graph_guided", "vector", "hybrid"] = "graph_guided"
    scope: Scope = field(default_factory=Scope)
    seed_symbols: list[str] = field(default_factory=list)
    expansion_policy: ExpansionPolicy = field(default_factory=ExpansionPolicy)
    include_code: bool = True
    k: int = 50

@dataclass
class Scope:
    repo_id: str
    snapshot_id: str
    parent_snapshot_id: str | None = None  # For incremental

@dataclass
class ExpansionPolicy:
    follow_calls: bool = True
    follow_imports: bool = True
    follow_inheritance: bool = True
    max_hops: int = 2
```

### 5.2 AnalyzeSpec

```python
@dataclass
class AnalyzeSpec:
    """Template-based Analysis Specification"""
    intent: Literal["analyze"] = "analyze"
    template_id: str = ""  # e.g., "sql_injection", "null_deref"
    scope: Scope = field(default_factory=Scope)
    params: dict[str, Any] = field(default_factory=dict)
    limits: AnalysisLimits = field(default_factory=AnalysisLimits)

@dataclass
class AnalysisLimits:
    max_paths: int = 200
    timeout_ms: int = 30000
    max_depth: int = 20
```

#### Analysis Primitive Model

Templates are composed of these primitives:

| Primitive | Description | Example |
|-----------|-------------|---------|
| `SOURCE(kind, trust)` | Untrusted input | `SOURCE("http", trust=0)` |
| `SINK(kind)` | Dangerous output | `SINK("sql_execute")` |
| `SANITIZER(effect)` | Taint removal | `SANITIZER("escape_sql")` |
| `FLOW(type)` | Flow edge type | `FLOW(CFG \| DFG \| PDG)` |
| `CONDITION(predicate)` | Path condition | `CONDITION("x != null")` |
| `CONTEXT(depth, sensitivity)` | Analysis context | `CONTEXT(k=2, field_sensitive=True)` |

### 5.3 EditSpec

```python
@dataclass
class EditSpec:
    """Atomic, Speculative Edit Specification"""
    intent: Literal["edit"] = "edit"
    transaction_id: str = ""
    atomic: bool = True
    dry_run: bool = True
    operations: list[EditOperation] = field(default_factory=list)
    constraints: EditConstraints = field(default_factory=EditConstraints)

@dataclass
class EditOperation:
    type: Literal["rename_symbol", "add_parameter", "remove_parameter",
                  "change_return_type", "extract_function", "inline_function"]
    target: str  # Symbol FQN
    params: dict[str, Any] = field(default_factory=dict)

@dataclass
class EditConstraints:
    max_files: int = 10
    forbidden_paths: list[str] = field(default_factory=list)
    require_tests: bool = False
```

---

## 6. ResultEnvelope (Canonical Output)

### 6.1 Structure

```python
@dataclass
class ResultEnvelope:
    """RFC-027 Canonical Output Format"""
    request_id: str
    summary: str
    claims: list[Claim]
    evidences: list[Evidence]
    conclusion: Conclusion | None
    metrics: dict[str, Any]
    escalation: Escalation | None
    replay_ref: str | None

    # 기존 코드 호환 필드 (선택)
    legacy_result: dict[str, Any] | None = None  # ReasoningResult 등 원본 보존
```

### 6.2 Claim

```python
class ConfidenceBasis(str, Enum):
    PROVEN = "proven"           # Deterministic static proof (SCCP+)
    INFERRED = "inferred"       # Path existence proof
    HEURISTIC = "heuristic"     # Pattern-based detection
    UNKNOWN = "unknown"         # Vector similarity hypothesis

@dataclass
class ProofObligation:
    """What must be true for the claim to hold"""
    assumptions: list[str]      # Assumed conditions
    broken_if: list[str]        # Conditions that invalidate
    unknowns: list[str]         # Unverified aspects

@dataclass
class Claim:
    id: str
    type: str                   # e.g., "sql_injection", "null_deref"
    severity: str               # "critical", "high", "medium", "low", "info"
    confidence: float           # 0.0 - 1.0
    confidence_basis: ConfidenceBasis
    proof_obligation: ProofObligation
    suppressed: bool = False
    suppression_reason: str | None = None
```

### 6.3 Evidence

```python
class EvidenceKind(str, Enum):
    CODE_SNIPPET = "code_snippet"
    DATA_FLOW_PATH = "data_flow_path"
    CALL_PATH = "call_path"
    DIFF = "diff"
    TEST_RESULT = "test_result"

@dataclass
class Location:
    file_path: str
    start_line: int
    end_line: int
    start_col: int = 0
    end_col: int = 0

@dataclass
class Provenance:
    engine: str                 # e.g., "TaintAnalyzer", "SCCPAnalyzer"
    template: str | None = None
    snapshot_id: str | None = None
    timestamp: float = 0.0

@dataclass
class Evidence:
    id: str
    kind: EvidenceKind
    location: Location
    content: str = ""
    provenance: Provenance
    claim_ids: list[str]        # Links to supporting claims
```

### 6.4 Conclusion

```python
@dataclass
class Conclusion:
    reasoning_summary: str      # Human-readable explanation
    coverage: float             # Analysis coverage (0.0 - 1.0)
    counterevidence: list[str]  # Evidence against claims
    recommendation: str         # Actionable recommendation
```

### 6.5 Escalation

```python
@dataclass
class Escalation:
    required: bool = False
    reason: str = ""
    decision_needed: str = ""
    options: list[str] = field(default_factory=list)
    resume_token: str | None = None  # For async resume
```

---

## 7. Result Arbitration Engine

### 7.1 Priority Rules

```python
class ArbitrationPriority(IntEnum):
    """Lower number = higher priority"""
    STATIC_PROOF = 1        # Deterministic Static Proof (SCCP+, Taint)
    PATH_EXISTENCE = 2      # Path Existence Proof (DFG traversal)
    HEURISTIC = 3           # Heuristic / Pattern-based
    VECTOR_SIMILARITY = 4   # Vector Similarity Hypothesis

CONFIDENCE_BASIS_MAP = {
    ConfidenceBasis.PROVEN: ArbitrationPriority.STATIC_PROOF,
    ConfidenceBasis.INFERRED: ArbitrationPriority.PATH_EXISTENCE,
    ConfidenceBasis.HEURISTIC: ArbitrationPriority.HEURISTIC,
    ConfidenceBasis.UNKNOWN: ArbitrationPriority.VECTOR_SIMILARITY,
}
```

### 7.2 Conflict Resolution

```python
class ArbitrationEngine:
    def arbitrate(self, claims: list[Claim]) -> list[Claim]:
        """
        Arbitrate claims based on priority rules.

        - Higher priority claims suppress lower priority claims of same type
        - Suppressed claims are returned with suppression_reason
        """
        sorted_claims = sorted(claims, key=self._get_priority)

        result = []
        seen: dict[str, Claim] = {}

        for claim in sorted_claims:
            key = f"{claim.type}:{claim.severity}"

            if key in seen:
                existing = seen[key]
                if self._get_priority(claim) > self._get_priority(existing):
                    # Suppress lower priority claim
                    claim = replace(claim,
                        suppressed=True,
                        suppression_reason=f"Superseded by {existing.id}"
                    )
            else:
                seen[key] = claim

            result.append(claim)

        return result
```

---

## 8. Validation, Safety & Error Contract

### 8.1 Guardrails

| Guard | Description | Implementation |
|-------|-------------|----------------|
| Scope Required | All specs must have valid scope | Spec validator |
| Cost Explosion | Prevent runaway analysis | `limits.max_paths`, `limits.timeout_ms` |
| Blast Radius | Limit affected files | `constraints.max_files` |
| Forbidden Paths | Hard deny patterns | `constraints.forbidden_paths` |
| PII/Secret Redaction | Strip sensitive data | `output.evidence_mode = "ref_only"` |

### 8.2 Structured Error Schema

```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "scope.repo_id is required",
  "hint_schema": {
    "required_fields": ["repo_id", "snapshot_id"],
    "optional_fields": ["parent_snapshot_id"]
  },
  "suggested_fixes": [
    {
      "field": "scope.repo_id",
      "suggestion": "Provide repository identifier"
    }
  ]
}
```

---

## 9. Replay & Determinism

### 9.1 Stored Per Request

```python
@dataclass
class RequestAuditLog:
    request_id: str

    # Input
    input_spec: dict[str, Any]
    resolved_spec: dict[str, Any]

    # Engine State
    engine_versions: dict[str, str]    # {"sccp": "1.2.0", "taint": "3.0.1"}
    index_digests: dict[str, str]      # {"chunk_index": "sha256:abc123"}

    # LLM Decisions (Bias Trace)
    llm_decisions: list[dict[str, Any]]

    # Tool Trace
    tool_trace: list[dict[str, Any]]

    # Output
    outputs: dict[str, Any]

    # Metadata
    timestamp: datetime
    duration_ms: float
```

### 9.2 Replay Endpoint

```
GET /rfc/replay/{request_id}

Response:
{
  "request_id": "req_abc123",
  "input_spec": {...},
  "resolved_spec": {...},
  "engine_versions": {"sccp": "1.2.0"},
  "index_digests": {"chunk_index": "sha256:..."},
  "timestamp": "T10:30:00Z"
}
```

---

## 10. Feedback Loop

### 10.1 Feedback Request

```json
{
  "request_id": "req_abc123",
  "feedback_type": "accept | reject | modify | defer",
  "target": {
    "type": "claim | patch",
    "id": "claim_001"
  },
  "reason": "False positive - sanitizer exists",
  "correction": {...}
}
```

### 10.2 RLHF-Ready Event Log

```python
@dataclass
class FeedbackEvent:
    event_id: str
    request_id: str
    feedback_type: Literal["accept", "reject", "modify", "defer"]
    target_type: Literal["claim", "patch"]
    target_id: str
    reason: str
    correction: dict[str, Any] | None
    timestamp: datetime
    user_id: str | None
```

---

## 11. Existing Orchestrator Integration

### 11.1 DeepReasoningOrchestrator 연동

기존 `agent/orchestrator/` 구조와 RFC-027 통합:

```python
# agent/orchestration/rfc_orchestrator.py
class RFCOrchestrator:
    """
    RFC-027 Orchestrator

    기존 DeepReasoningOrchestrator를 래핑하여
    ResultEnvelope 출력 제공
    """

    def __init__(
        self,
        deep_orchestrator: DeepReasoningOrchestrator,
        fast_orchestrator: FastPathOrchestrator,
        envelope_builder: EnvelopeBuilder,
        arbitration_engine: ArbitrationEngine,
        audit_store: AuditStore,
    ):
        self.deep = deep_orchestrator
        self.fast = fast_orchestrator
        self.envelope_builder = envelope_builder
        self.arbitration = arbitration_engine
        self.audit = audit_store

    async def execute(self, spec: dict) -> ResultEnvelope:
        """
        RFC Spec 실행 → ResultEnvelope 반환
        """
        request_id = str(uuid4())
        start_time = time.perf_counter()

        intent = spec.get("intent")

        if intent == "retrieve":
            result = await self._execute_retrieve(spec)
        elif intent == "analyze":
            result = await self._execute_analyze(spec)
        elif intent == "edit":
            result = await self._execute_edit(spec)
        else:
            raise ValueError(f"Unknown intent: {intent}")

        # Arbitration
        arbitrated_claims = self.arbitration.arbitrate(result.claims)
        result.claims = arbitrated_claims

        # Audit log
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        await self.audit.save(RequestAuditLog(
            request_id=request_id,
            input_spec=spec,
            resolved_spec=spec,
            engine_versions=self._get_engine_versions(),
            duration_ms=elapsed_ms
        ))

        result.request_id = request_id
        result.replay_ref = f"replay:{request_id}"

        return result

    async def _execute_analyze(self, spec: dict) -> ResultEnvelope:
        """분석 실행 (기존 파이프라인 활용)"""
        from src.contexts.code_foundation.application import TaintAnalysisService
        from src.contexts.reasoning_engine.application import ReasoningPipeline

        # 1. Taint Analysis
        taint_service = TaintAnalysisService.from_defaults()
        taint_result = taint_service.analyze(
            ir_doc=self._load_ir(spec["scope"]),
            policies=[spec.get("template_id")]
        )

        # 2. Reasoning Pipeline
        pipeline = ReasoningPipeline(graph=self._load_graph(spec["scope"]))
        reasoning_result = pipeline.get_result()

        # 3. 통합 → Envelope
        envelope = self.envelope_builder.new()
        envelope.from_taint_result(taint_result)
        envelope.from_reasoning_result(reasoning_result)

        return envelope.build()
```

### 11.2 Router 통합

```python
# 기존 Dynamic Router와 연동
class RFCRouter:
    """Spec → 적절한 실행 경로 라우팅"""

    def route(self, spec: dict) -> Literal["fast", "deep"]:
        intent = spec.get("intent")

        # Edit with dry_run=False → Deep path (안전 검증)
        if intent == "edit" and not spec.get("dry_run", True):
            return "deep"

        # 복잡한 분석 → Deep path
        if intent == "analyze":
            limits = spec.get("limits", {})
            if limits.get("max_paths", 0) > 100:
                return "deep"

        return "fast"
```

---

## 12. Pipeline Integration Plan

### 12.1 현재 파이프라인 구조

#### 12.1.1 인덱싱 파이프라인 (IndexingOrchestrator)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    IndexingOrchestrator Pipeline                         │
│                      (9-Stage Sequential)                                │
├─────────────────────────────────────────────────────────────────────────┤
│  Stage 1: Git Operations     │ clone/fetch/pull                         │
│  Stage 2: File Discovery     │ find all source files                    │
│  Stage 3: Parsing            │ Tree-sitter AST generation               │
│  Stage 4: IR Building        │ language-neutral IR                      │
│  Stage 5: Semantic IR        │ CFG, DFG, types, signatures              │
│  Stage 6: Graph Building     │ code graph nodes/edges                   │
│  Stage 7: Chunk Generation   │ LLM-friendly chunks                      │
│  Stage 8: RepoMap Building   │ tree, PageRank, summaries                │
│  Stage 9: Multi-Index        │ lexical, vector, symbol, fuzzy, domain   │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 12.1.2 인덱싱 모드 (IndexingMode)

| Mode | Layers | Use Case | Trigger |
|------|--------|----------|---------|
| **FAST** | L1, L2 | 빠른 피드백 | 파일 저장 |
| **BALANCED** | L1, L2, L3 | 일반 작업 | PR, 커밋 |
| **DEEP** | L1, L2, L3, L4 | 정밀 분석 | Audit, 보안 |
| **BOOTSTRAP** | L1, L2, L3_SUMMARY | 초기 인덱싱 | 새 레포 |
| **REPAIR** | 동적 | 복구 | 에러 후 |

```python
# 레이어 정의 (analysis_indexing/infrastructure/models/mode.py)
class Layer(str, Enum):
    L0 = "l0"  # 변경 감지 (git diff, mtime, hash)
    L1 = "l1"  # 파싱 (AST, 심볼 추출)
    L2 = "l2"  # 기본 IR + 청크 생성
    L3 = "l3"  # Semantic IR (요약 CFG/DFG)
    L4 = "l4"  # 고급 분석 (Full DFG, Cross-function)
```

#### 12.1.3 분석 모드 (AnalysisMode)

| Mode | 특성 | 증분 | Sound | Use Case |
|------|------|------|-------|----------|
| **QUICK** | Pattern only | ✅ | ❌ | <1s, IDE |
| **REALTIME** | 국소 고정점 | ✅ | ❌ | <, 실시간 |
| **DEEP** | 전역 고정점 | ❌ | △ | ~3s |
| **AUDIT** | 전역 고정점 + Z3 | ❌ | ✅ | 분 단위, 보안 감사 |

```python
# 분석 모드별 Pipeline (code_foundation/infrastructure/analyzers/configs/modes.py)

# Realtime: < (SCCP baseline)
def create_realtime_pipeline(ir_doc) -> AnalyzerPipeline:
    pipeline.add("sccp_baseline")
    return pipeline

# PR: <5s (SCCP + Taint + Null)
def create_pr_pipeline(ir_doc) -> AnalyzerPipeline:
    pipeline.add("sccp_baseline")
    pipeline.add("interprocedural_taint")
    pipeline.add("realtime_null")
    return pipeline

# Audit: 분 단위, Sound 보장
def create_audit_pipeline(ir_doc) -> AnalyzerPipeline:
    pipeline.add("sccp_baseline")
    pipeline.add("interprocedural_taint")
    pipeline.add("path_sensitive_taint")
    pipeline.add("audit_null")
    pipeline.add("format_string")
    return pipeline
```

### 12.2 RFC-027 통합 전략

#### 12.2.1 AnalyzeSpec → 기존 파이프라인 매핑

```python
# AnalyzeSpec.template_id → 기존 파이프라인 매핑
TEMPLATE_PIPELINE_MAP = {
    # Security Templates → Taint Pipeline
    "sql_injection": ("taint", {"policy": "sql_injection"}),
    "xss": ("taint", {"policy": "xss"}),
    "command_injection": ("taint", {"policy": "command_injection"}),

    # Null Safety → Null Pipeline
    "null_deref": ("null", {"mode": "realtime"}),
    "null_deref_audit": ("null", {"mode": "audit"}),

    # Performance → SCCP Pipeline
    "constant_propagation": ("sccp", {}),
    "dead_code": ("sccp", {"check_unreachable": True}),

    # Custom Template → Dynamic Pipeline
    "*": ("dynamic", {"from_template": True}),
}

class AnalyzeSpecExecutor:
    """AnalyzeSpec → 기존 분석 파이프라인 실행"""

    async def execute(self, spec: AnalyzeSpec) -> ResultEnvelope:
        # 1. 파이프라인 선택
        pipeline_type, params = TEMPLATE_PIPELINE_MAP.get(
            spec.template_id,
            TEMPLATE_PIPELINE_MAP["*"]
        )

        # 2. IR 로드 (증분 고려)
        ir_doc = await self._load_ir(
            spec.scope.repo_id,
            spec.scope.snapshot_id,
            spec.scope.parent_snapshot_id  # 증분용
        )

        # 3. 분석 모드 결정
        analysis_mode = self._select_analysis_mode(spec.limits)

        # 4. 파이프라인 실행
        if pipeline_type == "taint":
            result = await self._run_taint_pipeline(ir_doc, params, analysis_mode)
        elif pipeline_type == "null":
            result = await self._run_null_pipeline(ir_doc, params)
        elif pipeline_type == "sccp":
            result = await self._run_sccp_pipeline(ir_doc, params)
        else:
            result = await self._run_dynamic_pipeline(ir_doc, spec)

        # 5. ResultEnvelope 변환
        return self.envelope_builder.from_analysis_result(result).build()

    def _select_analysis_mode(self, limits: AnalysisLimits) -> AnalysisMode:
        """limits → AnalysisMode 결정"""
        if limits.timeout_ms < 1000:
            return AnalysisMode.REALTIME
        elif limits.timeout_ms < 5000:
            return AnalysisMode.DEEP
        else:
            return AnalysisMode.AUDIT
```

#### 12.2.2 RetrieveSpec → 기존 검색 파이프라인 매핑

```python
# RetrieveSpec.mode → 기존 검색 인프라 매핑
class RetrieveSpecExecutor:
    """RetrieveSpec → 기존 검색 인프라 실행"""

    def __init__(
        self,
        graph_expander: CostAwareExpander,  # retrieval_search/
        vector_index: VectorIndexService,   # multi_index/
        hybrid_ranker: HybridRanker,        # retrieval_search/
    ):
        self.graph = graph_expander
        self.vector = vector_index
        self.hybrid = hybrid_ranker

    async def execute(self, spec: RetrieveSpec) -> ResultEnvelope:
        claims = []
        evidences = []

        if spec.mode == "graph_guided":
            # 기존 CostAwareExpander 사용
            results = await self.graph.expand(
                seed_symbols=spec.seed_symbols,
                follow_calls=spec.expansion_policy.follow_calls,
                follow_imports=spec.expansion_policy.follow_imports,
                max_hops=spec.expansion_policy.max_hops,
                k=spec.k,
            )
            confidence_basis = ConfidenceBasis.INFERRED  # Graph traversal

        elif spec.mode == "vector":
            # 기존 VectorIndexService 사용
            results = await self.vector.search(
                query_embedding=spec.seed_symbols[0],  # TODO: embed
                k=spec.k,
            )
            confidence_basis = ConfidenceBasis.UNKNOWN  # Vector similarity

        else:  # hybrid
            # 기존 HybridRanker 사용
            results = await self.hybrid.search(
                query=spec.seed_symbols,
                graph_weight=0.6,
                vector_weight=0.4,
                k=spec.k,
            )
            confidence_basis = ConfidenceBasis.HEURISTIC  # Mixed

        # ResultEnvelope 생성
        for r in results:
            claim = Claim(
                type="retrieval_result",
                severity="info",
                confidence=r.score,
                confidence_basis=confidence_basis,
            )
            claims.append(claim)

            evidence = Evidence(
                kind=EvidenceKind.CODE_SNIPPET if spec.include_code else EvidenceKind.CALL_PATH,
                location=Location(file_path=r.file_path, start_line=r.line, end_line=r.line),
                content=r.code if spec.include_code else "",
                claim_ids=[claim.id],
            )
            evidences.append(evidence)

        return ResultEnvelope(
            request_id=str(uuid4()),
            claims=claims,
            evidences=evidences,
        )
```

#### 12.2.3 EditSpec → 기존 Speculative Pipeline 매핑

```python
# EditSpec → 기존 SpeculativeExecutor 매핑
class EditSpecExecutor:
    """EditSpec → 기존 Speculative 파이프라인 실행"""

    def __init__(
        self,
        graph_simulator: GraphSimulator,  # reasoning_engine/speculative/
        risk_analyzer: RiskAnalyzer,
        speculative_executor: SpeculativeExecutor,
    ):
        self.simulator = graph_simulator
        self.risk = risk_analyzer
        self.speculative = speculative_executor

    async def execute(self, spec: EditSpec) -> ResultEnvelope:
        # 1. EditSpec → SpeculativePatch 변환
        patches = self._convert_to_patches(spec)

        # 2. dry_run 여부에 따른 분기
        if spec.dry_run:
            # Virtual workspace에서 시뮬레이션
            for patch in patches:
                # Delta Graph 생성
                delta = self.simulator.simulate_patch(patch, validate=True)

                # 위험도 분석
                risk_report = self.risk.analyze_risk(patch, delta, base_graph=None)

                # forbidden_paths 체크
                if self._violates_constraints(delta, spec.constraints):
                    return self._create_blocked_envelope(spec, "forbidden_path_violation")
        else:
            # 실제 적용 (SpeculativeExecutor)
            result = await self.speculative.execute(patches)

        # 3. ResultEnvelope 생성
        claims = []
        for patch, report in zip(patches, risk_reports):
            claim = Claim(
                type="edit_risk",
                severity=report.risk_level.value,
                confidence=1.0 - report.risk_score,
                confidence_basis=ConfidenceBasis.PROVEN,  # Static analysis
                proof_obligation=ProofObligation(
                    assumptions=["call graph complete"],
                    broken_if=report.breaking_changes,
                )
            )
            claims.append(claim)

        return ResultEnvelope(
            request_id=str(uuid4()),
            claims=claims,
            conclusion=Conclusion(
                reasoning_summary=f"Edit risk: {risk_reports[0].risk_level.value}",
                recommendation=risk_reports[0].recommendation,
            )
        )
```

### 12.3 증분 분석 통합

#### 12.3.1 snapshot_id + parent_snapshot_id 활용

```python
class IncrementalAnalysisIntegration:
    """증분 분석 인프라 통합"""

    def __init__(
        self,
        change_detector: ChangeDetector,      # analysis_indexing/
        scope_expander: ScopeExpander,        # analysis_indexing/
        incremental_indexer: IncrementalIndexer,  # multi_index/
    ):
        self.detector = change_detector
        self.expander = scope_expander
        self.indexer = incremental_indexer

    async def prepare_incremental_context(
        self,
        scope: Scope,
    ) -> IncrementalContext:
        """증분 분석을 위한 컨텍스트 준비"""

        if scope.parent_snapshot_id is None:
            # Full analysis
            return IncrementalContext(mode="full", changed_files=[])

        # 1. 변경 감지
        changes = self.detector.detect_changes_between_snapshots(
            scope.snapshot_id,
            scope.parent_snapshot_id,
        )

        # 2. 영향 범위 확장 (1-hop callers)
        expanded = await self.expander.expand_to_callers(
            changes.modified_symbols,
            depth=1,
        )

        return IncrementalContext(
            mode="incremental",
            changed_files=changes.files,
            affected_symbols=expanded,
            cache_valid_from=scope.parent_snapshot_id,
        )
```

### 12.4 API Endpoint 통합 요약

| RFC Endpoint | 실행 파이프라인 | 기존 인프라 |
|--------------|----------------|-------------|
| `POST /rfc/execute` (analyze) | AnalyzeSpecExecutor | TaintAnalyzer, SCCPAnalyzer, NullAnalyzer |
| `POST /rfc/execute` (retrieve) | RetrieveSpecExecutor | CostAwareExpander, VectorIndexService |
| `POST /rfc/execute` (edit) | EditSpecExecutor | GraphSimulator, RiskAnalyzer |
| `POST /rfc/validate` | SpecValidator | GuardrailsAIAdapter |
| `POST /rfc/plan` | PlanExecutor | DeepReasoningOrchestrator |
| `POST /rfc/explain` | ExplainExecutor | ReasoningPipeline |
| `GET /rfc/replay/{id}` | ReplayService | AuditStore |
| `POST /rfc/feedback` | FeedbackService | ExperienceStore |

### 12.5 Pipeline Mode × RFC 매핑

| 트리거 | IndexingMode | AnalysisMode | RFC confidence_basis |
|--------|--------------|--------------|---------------------|
| 파일 저장 | FAST | REALTIME | `HEURISTIC` (증분) |
| PR Open | BALANCED | PR (SCCP+Taint) | `INFERRED` |
| PR Merge | DEEP | DEEP | `PROVEN` (전체) |
| Security Audit | DEEP | AUDIT (Z3) | `PROVEN` (Sound) |
| 신규 레포 | BOOTSTRAP | - | - |
| 에러 복구 | REPAIR | - | - |

---

## 13. Implementation Phases (Revised)

### Phase 1 — Core Foundation (Week 1-2) · P0

| Task | Location | Effort | 기존 코드 연동 |
|------|----------|--------|---------------|
| Spec Contracts | `shared_kernel/contracts/specs.py` | 1 day | - |
| Envelope Contracts | `shared_kernel/contracts/envelope.py` | 1 day | - |
| EnvelopeBuilder | `llm_arbitration/infrastructure/envelope_builder.py` | 1 day | - |
| TaintAdapter | `llm_arbitration/infrastructure/adapters/taint_adapter.py` | 1 day | `TaintAnalysisService` |
| SCCPAdapter | `llm_arbitration/infrastructure/adapters/sccp_adapter.py` | 0.5 day | `ConstantPropagationAnalyzer` |
| Execute Executor | `llm_arbitration/application/execute_executor.py` | 2 days | - |
| `/rfc/execute` API | `server/routes/rfc/execute.py` | 1 day | - |
| `/rfc/validate` API | `server/routes/rfc/validate.py` | 0.5 day | `GuardrailsAIAdapter` |

**Deliverable:** Single request → ResultEnvelope flow working (Taint + SCCP 결과 통합)

### Phase 2 — Arbitration & Replay (Week 3) · P1

| Task | Location | Effort | 기존 코드 연동 |
|------|----------|--------|---------------|
| ArbitrationEngine | `llm_arbitration/infrastructure/arbitration_engine.py` | 1.5 day | - |
| DeepReasoningAdapter | `llm_arbitration/infrastructure/adapters/deep_reasoning_adapter.py` | 1 day | `DeepReasoningResult` |
| RiskAdapter | `llm_arbitration/infrastructure/adapters/risk_adapter.py` | 0.5 day | `RiskReport` |
| ReasoningAdapter | `llm_arbitration/infrastructure/adapters/reasoning_adapter.py` | 0.5 day | `ReasoningResult` |
| AuditStore | `replay_audit/infrastructure/audit_store.py` | 1.5 days | - |
| `/rfc/replay/{id}` API | `server/routes/rfc/replay.py` | 1 day | - |

**Deliverable:** Arbitration 규칙 동작, 전략별 confidence_basis 매핑, Replay 인프라

### Phase 3 — Orchestrator Integration (Week 4) · P1-P2

| Task | Location | Effort | 기존 코드 연동 |
|------|----------|--------|---------------|
| RFCOrchestrator | `agent/orchestration/rfc_orchestrator.py` | 2 days | `DeepReasoningOrchestrator` |
| PlanExecutor | `llm_arbitration/application/plan_executor.py` | 1.5 day | - |
| ExplainExecutor | `llm_arbitration/application/explain_executor.py` | 1.5 day | - |
| `/rfc/plan` API | `server/routes/rfc/plan.py` | 0.5 day | - |
| `/rfc/explain` API | `server/routes/rfc/explain.py` | 0.5 day | - |
| Feedback endpoint | `server/routes/rfc/feedback.py` | 1 day | `ExperienceStore` |

**Deliverable:** Full API surface, 기존 오케스트레이터 통합

### Phase 4 — Hardening & Production (Week 5-6) · P2-P3

| Task | Location | Effort | 기존 코드 연동 |
|------|----------|--------|---------------|
| Cost explosion guard | `llm_arbitration/domain/specs/validators.py` | 1 day | - |
| resume_token 구현 | `replay_audit/domain/models.py` | 1 day | `ActionGateAdapter` |
| Error handling | All modules | 1.5 day | `StructuredError` |
| Performance optimization | All modules | 1.5 day | - |
| Documentation | `_docs/system-handbook/` | 1 day | - |
| Unit Tests | `tests/contexts/llm_arbitration/` | 2 days | - |
| Integration Tests | `tests/integration/rfc_pipeline/` | 2 days | - |

**Deliverable:** Production-ready implementation, 문서화 완료

---

## 14. Success Criteria

### 14.1 Functional

- [ ] All 8 API endpoints operational
- [ ] ResultEnvelope correctly structures all analysis results
- [ ] Arbitration engine correctly prioritizes claims
- [ ] Replay returns deterministic results
- [ ] Feedback events logged for RLHF

### 14.2 Performance

| Metric | Target |
|--------|--------|
| Envelope construction overhead | <  |
| Arbitration processing | <  for 100 claims |
| Replay lookup | <  |
| API response time | <  (P95) |

### 14.3 Quality

- [ ] 90%+ test coverage for new code
- [ ] All existing tests pass
- [ ] No regression in static analysis performance
- [ ] Documentation complete

---

## 15. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Envelope overhead | Medium | Low | Lazy construction, caching |
| Breaking existing APIs | High | Low | Backward-compatible `/rfc/` prefix |
| Complex adapter integration | Medium | Medium | Interface-first design, mocks |
| Audit store performance | Medium | Low | SQLite for dev, PostgreSQL for prod |

---

## 16. Dependencies

### 16.1 Internal

| Dependency | Status | Notes |
|------------|--------|-------|
| `code_foundation/` | ✅ Ready | Taint, SCCP analyzers |
| `retrieval_search/` | ✅ Ready | Graph-guided retrieval |
| `reasoning_engine/` | ✅ Ready | Speculative execution |
| `agent/adapters/safety/` | ✅ Ready | Guardrails |

### 16.2 External

| Dependency | Version | Notes |
|------------|---------|-------|
| Pydantic | 2.x | Request/Response models |
| FastAPI | 0.100+ | API endpoints |
| SQLite | 3.35+ | Audit store (dev) |

---

## 17. Open Questions

1. **Claim deduplication strategy** — How to handle semantically equivalent claims from different engines?
2. **Evidence pruning** — Max evidences per claim? LRU eviction?
3. **Replay retention policy** — How long to retain audit logs?
4. **Feedback anonymization** — PII handling in feedback events?

---

## 18. Appendix

### A. Mapping: Existing → RFC Components (Complete)

| Existing Component | Location | RFC Component | Transformation |
|-------------------|----------|---------------|----------------|
| `TaintResult` | `code_foundation/infrastructure/taint/` | `Claim` + `Evidence` | `TaintAdapter.to_envelope()` |
| `RiskReport` | `reasoning_engine/domain/speculative_models.py` | `Claim` (severity) | `RiskAdapter.to_claim()` |
| `ReasoningResult` | `reasoning_engine/application/reasoning_pipeline.py` | `Conclusion` | `ReasoningAdapter.to_conclusion()` |
| `DeepReasoningResult` | `agent/shared/reasoning/deep/deep_models.py` | `Claim` + `Evidence` | `DeepReasoningAdapter.to_envelope()` |
| `VerificationResult` | `agent/shared/reasoning/deep/deep_models.py` | `ProofObligation` | confidence 기반 매핑 |
| `ThoughtNode` | `agent/shared/reasoning/deep/deep_models.py` | `Evidence(CODE_SNIPPET)` | Step trace |
| `SpeculativePatch` | `reasoning_engine/domain/speculative_models.py` | `EditSpec` 결과 | `PatchType` → `EditOperation` |
| `ExperienceStore` | `agent/experience_store.py` | `FeedbackEvent` | Event wrapper |
| `ApprovalRecord` | `agent/adapters/safety/action_gate.py` | `Escalation` | `resume_token` 추가 |
| `PolicyConfig` | `agent/adapters/guardrail/guardrails_adapter.py` | Guardrails | 기존 그대로 |

### B. Adapter Implementation Specifications

#### B.1 TaintAdapter

```python
# llm_arbitration/infrastructure/adapters/taint_adapter.py
class TaintAdapter:
    """TaintAnalyzer 결과 → ResultEnvelope 변환"""

    def to_envelope(self, taint_result: dict) -> ResultEnvelope:
        claims = []
        evidences = []

        for vuln in taint_result.get("vulnerabilities", []):
            claim_id = str(uuid4())

            # Taint 분석 = Static Proof (최고 우선순위)
            claim = Claim(
                id=claim_id,
                type=vuln["policy_id"],  # sql_injection, xss, etc.
                severity=vuln["severity"],
                confidence=vuln.get("confidence", 0.95),
                confidence_basis=ConfidenceBasis.PROVEN,  # 결정적 분석
                proof_obligation=ProofObligation(
                    assumptions=["data flow graph is sound"],
                    broken_if=["sanitizer on path", "dead code"],
                    unknowns=[]
                )
            )
            claims.append(claim)

            # 각 경로 노드 → Evidence
            for node in vuln.get("path", []):
                evidence = Evidence(
                    id=str(uuid4()),
                    kind=EvidenceKind.DATA_FLOW_PATH,
                    location=Location(
                        file_path=node["file"],
                        start_line=node["line"],
                        end_line=node["line"]
                    ),
                    content=node.get("code", ""),
                    provenance=Provenance(
                        engine="TaintAnalyzer",
                        template=vuln["policy_id"]
                    ),
                    claim_ids=[claim_id]
                )
                evidences.append(evidence)

        return ResultEnvelope(
            request_id=str(uuid4()),
            summary=f"Found {len(claims)} vulnerabilities",
            claims=claims,
            evidences=evidences
        )
```

#### B.2 DeepReasoningAdapter

```python
# llm_arbitration/infrastructure/adapters/deep_reasoning_adapter.py
class DeepReasoningAdapter:
    """DeepReasoning 결과 → ResultEnvelope 변환"""

    STRATEGY_CONFIDENCE_MAP = {
        "o1": ConfidenceBasis.PROVEN,      # Verified
        "debate": ConfidenceBasis.INFERRED,  # Consensus
        "beam": ConfidenceBasis.INFERRED,
        "tot": ConfidenceBasis.INFERRED,
        "alphacode": ConfidenceBasis.HEURISTIC,
        "auto": ConfidenceBasis.UNKNOWN,
    }

    def to_envelope(
        self,
        result: DeepReasoningResult,
        strategy: str = "auto"
    ) -> ResultEnvelope:

        # Verification 통과 여부로 confidence_basis 결정
        all_verified = all(v.is_valid for v in result.verification_results)
        confidence_basis = (
            ConfidenceBasis.PROVEN if all_verified and strategy == "o1"
            else self.STRATEGY_CONFIDENCE_MAP.get(strategy, ConfidenceBasis.UNKNOWN)
        )

        claim = Claim(
            id=str(uuid4()),
            type="code_generation",
            severity="info",
            confidence=result.final_confidence,
            confidence_basis=confidence_basis,
            proof_obligation=ProofObligation(
                assumptions=[f"strategy: {strategy}"],
                broken_if=["test failure", "lint error"],
                unknowns=["runtime behavior"]
            )
        )

        # Reasoning steps → Evidence
        evidences = [
            Evidence(
                id=str(uuid4()),
                kind=EvidenceKind.CODE_SNIPPET,
                location=Location(file_path="<generated>", start_line=0, end_line=0),
                content=step.answer,
                provenance=Provenance(
                    engine="DeepReasoning",
                    template=strategy
                ),
                claim_ids=[claim.id]
            )
            for step in result.reasoning_steps
        ]

        return ResultEnvelope(
            request_id=str(uuid4()),
            summary=result.final_answer[:200],
            claims=[claim],
            evidences=evidences,
            conclusion=Conclusion(
                reasoning_summary=result.get_reasoning_trace()[:500],
                coverage=result.final_confidence,
                recommendation=""
            )
        )
```

### C. EditSpec ↔ SpeculativePatch 매핑

```python
# RFC EditSpec → 기존 SpeculativePatch 변환
EDIT_OPERATION_MAP = {
    "rename_symbol": PatchType.RENAME_SYMBOL,
    "add_parameter": PatchType.ADD_PARAMETER,
    "remove_parameter": PatchType.REMOVE_PARAMETER,
    "change_return_type": PatchType.CHANGE_RETURN_TYPE,
    "extract_function": PatchType.REFACTOR,
    "inline_function": PatchType.REFACTOR,
}

def edit_spec_to_patch(spec: EditSpec) -> list[SpeculativePatch]:
    """EditSpec → SpeculativePatch 리스트"""
    patches = []
    for op in spec.operations:
        patch = SpeculativePatch(
            patch_id=spec.transaction_id + "_" + op["target"],
            patch_type=EDIT_OPERATION_MAP.get(op["type"], PatchType.MODIFY_BODY),
            target_symbol=op["target"],
            new_name=op["params"].get("new_name"),
            parameters=op["params"].get("parameters"),
            return_type=op["params"].get("return_type"),
            confidence=1.0,
            source="rfc_spec"
        )
        patches.append(patch)
    return patches
```

### D. JSON Schema (OpenAPI)

Full OpenAPI spec will be generated from Pydantic models and published at `/rfc/openapi.json`.

### E. Test Strategy

```
tests/contexts/llm_arbitration/
├── domain/
│   ├── test_specs.py           # Spec validation
│   ├── test_envelope.py        # Envelope construction
│   └── test_arbitration.py     # Priority rules
├── application/
│   ├── test_execute_executor.py
│   └── test_plan_executor.py
├── infrastructure/
│   ├── test_arbitration_engine.py
│   ├── test_envelope_builder.py
│   └── adapters/
│       ├── test_taint_adapter.py
│       ├── test_deep_reasoning_adapter.py
│       └── test_risk_adapter.py
└── integration/
    ├── test_full_pipeline.py
    └── test_api_endpoints.py
```

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1.0 |  | Initial RFC |
| v2.0 |  | Added phasing strategy |
| v2.1 |  | Added enterprise features |
| v3.0 |  | Gap analysis, repo structure, implementation details |
| v3.1 |  | Code alignment: 기존 모델 매핑, Adapter 상세, 전략별 confidence 매핑 |
| **v3.2** | **** | **Pipeline Integration: 인덱싱/분석 파이프라인 통합 계획, Spec→Pipeline 매핑** |

---

**RFC-027 v3.2 — APPROVED · READY FOR IMPLEMENTATION**
