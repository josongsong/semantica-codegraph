# RFC-027 Contracts

RFC-027의 핵심 데이터 구조 정의.

## 구조

```
contracts/
├── __init__.py          # 전체 export
├── confidence.py        # ConfidenceBasis, EvidenceKind enums
├── envelope.py          # ResultEnvelope, Claim, Evidence, Conclusion
├── specs.py             # RetrieveSpec, AnalyzeSpec, EditSpec
└── mappings.py          # 변환 매핑 테이블
```

## 핵심 타입

### ResultEnvelope

모든 RFC 분석 결과의 표준 출력 형식:

```python
@dataclass
class ResultEnvelope:
    request_id: str
    summary: str
    claims: list[Claim]
    evidences: list[Evidence]
    conclusion: Conclusion | None
    metrics: Metrics | None
    escalation: Escalation | None
    replay_ref: str | None
```

### Claim

코드베이스에 대한 주장 (버그, 취약점, 위험도 등):

```python
@dataclass
class Claim:
    id: str
    type: str
    severity: str
    confidence: float
    confidence_basis: ConfidenceBasis  # PROVEN | INFERRED | HEURISTIC | UNKNOWN
    proof_obligation: ProofObligation
    suppressed: bool
    suppression_reason: str | None
```

### ConfidenceBasis

Claim의 신뢰 근거 (우선순위):

- **PROVEN**: 결정적 정적 분석 (SCCP+, Taint) - 최고 우선순위
- **INFERRED**: 경로 존재 증명 (DFG 순회)
- **HEURISTIC**: 패턴 기반 탐지
- **UNKNOWN**: 벡터 유사도 가설 - 최저 우선순위

### Evidence

Claim을 뒷받침하는 증거:

```python
@dataclass
class Evidence:
    id: str
    kind: EvidenceKind  # CODE_SNIPPET, DATA_FLOW_PATH, CALL_PATH, ...
    location: Location
    content: dict[str, Any] | str
    provenance: Provenance
    claim_ids: list[str]
```

## Spec 타입

### AnalyzeSpec

분석 실행 스펙:

```python
@dataclass
class AnalyzeSpec:
    intent: Literal["analyze"] = "analyze"
    template_id: str  # "sql_injection", "null_deref", ...
    scope: Scope
    params: dict[str, Any]
    limits: AnalysisLimits
```

### RetrieveSpec

검색 실행 스펙:

```python
@dataclass
class RetrieveSpec:
    intent: Literal["retrieve"] = "retrieve"
    mode: Literal["graph_guided", "vector", "hybrid"]
    scope: Scope
    seed_symbols: list[str]
    expansion_policy: ExpansionPolicy
    include_code: bool
    k: int
```

## 사용 예시

### ResultEnvelope 생성

```python
from src.contexts.shared_kernel.contracts import (
    ResultEnvelope,
    Claim,
    ConfidenceBasis,
    ProofObligation,
)

claim = Claim(
    id="claim_001",
    type="sql_injection",
    severity="critical",
    confidence=0.95,
    confidence_basis=ConfidenceBasis.PROVEN,
    proof_obligation=ProofObligation(
        assumptions=["data flow graph is sound"],
        broken_if=["sanitizer on path"],
    ),
)

envelope = ResultEnvelope(
    request_id="req_123",
    summary="Found 1 SQL injection",
    claims=[claim],
    evidences=[],
)
```

### Spec 생성

```python
from src.contexts.shared_kernel.contracts import AnalyzeSpec, Scope

spec = AnalyzeSpec(
    template_id="sql_injection",
    scope=Scope(
        repo_id="repo:123",
        snapshot_id="snap:456",
    ),
)
```
