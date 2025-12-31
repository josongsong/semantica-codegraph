# RFC-027 & RFC-028 병행 작업 계획
**Status**: READY FOR PARALLEL EXECUTION
**Date**: 2025-01-16
**Teams**: 팀 A (RFC-028 Analysis) + 팀 B (RFC-027 API Layer)

---

## ✅ 확정 완료 (공통 기반)

### Evidence 스키마 — LOCKED ✅

**위치**: `src/agent/domain/rfc_specs/evidence.py`

```python
class EvidenceKind(str, Enum):
    # RFC-027 기본
    CODE_SNIPPET = "code_snippet"
    DATA_FLOW_PATH = "data_flow_path"
    CALL_PATH = "call_path"
    DIFF = "diff"
    TEST_RESULT = "test_result"

    # RFC-028 추가
    COST_TERM = "cost_term"
    LOOP_BOUND = "loop_bound"
    RACE_WITNESS = "race_witness"
    LOCK_REGION = "lock_region"
    DIFF_DELTA = "diff_delta"

@dataclass
class Evidence:
    id: str
    kind: EvidenceKind
    location: Location
    content: dict[str, Any]  # Machine-readable
    provenance: Provenance
    claim_ids: list[str]
```

**상태**: ✅ **구현 완료, 테스트 통과**
**변경 금지**: 이제부터 이 스키마는 **고정** (양 팀 공통 의존)

### Claim 스키마 — LOCKED ✅

**위치**: `src/agent/domain/rfc_specs/claim.py`

```python
class ConfidenceBasis(str, Enum):
    PROVEN = "proven"      # RFC-028 verdict="proven" 매핑
    INFERRED = "inferred"  # RFC-028 verdict="likely" 매핑
    HEURISTIC = "heuristic"  # RFC-028 verdict="heuristic" 매핑
    UNKNOWN = "unknown"

@dataclass
class Claim:
    id: str
    type: str
    severity: str
    confidence: float
    confidence_basis: ConfidenceBasis  # ← 핵심!
    proof_obligation: ProofObligation
    suppressed: bool = False
    suppression_reason: str | None = None
```

**상태**: ✅ **구현 완료, 테스트 통과**
**변경 금지**: 이제부터 이 스키마는 **고정**

---

## 🔀 팀 분리 (병행 작업)

### 팀 A: RFC-028 (Analysis Implementation)

**책임**: Cost/Concurrency/Differential Analyzer 구현

**작업 위치**:
```
src/contexts/code_foundation/infrastructure/analyzers/
├── cost/                     # ← 팀 A 작업
│   ├── cost_analyzer.py
│   ├── loop_bound_analyzer.py
│   └── models.py
└── concurrency/              # ← 팀 A 작업
    ├── race_detector.py
    ├── shared_var_tracker.py
    └── models.py

src/contexts/reasoning_engine/infrastructure/differential/  # ← 팀 A 작업
└── taint_diff_analyzer.py
```

**출력 형식** (Interface Contract):
```python
# 팀 A는 이 형식으로 반환
@dataclass
class CostResult:
    function_fqn: str
    complexity: str  # "O(n)", "O(n²)"
    verdict: Literal["proven", "likely", "heuristic"]  # ← 매핑 키
    confidence: float
    evidence: Evidence  # ← 팀 공통 스키마 사용!
    explanation: str
```

**의존성**:
- ✅ Evidence 스키마 (고정됨)
- ✅ 기존 인프라 (SCCP, SSA, CFG, Call Graph)
- ❌ ResultEnvelope 불필요 (팀 B가 변환)

---

### 팀 B: RFC-027 (API Layer Implementation)

**책임**: API Surface + ResultEnvelope + Arbitration

**작업 위치**:
```
src/agent/domain/rfc_specs/
├── envelope.py              # ← 팀 B 작업
├── specs.py                 # ← 팀 B 작업 (RetrieveSpec, AnalyzeSpec)
└── arbitration.py           # ← 팀 B 작업

server/api_server/routes/rfc/
├── execute.py               # ← 팀 B 작업
├── validate.py              # ← 팀 B 작업
└── explain.py               # ← 팀 B 작업
```

**입력 형식** (Interface Contract):
```python
# 팀 B는 팀 A의 결과를 이렇게 받음
cost_result: CostResult = team_a.cost_analyzer.analyze(...)

# 팀 B가 변환
claim = Claim(
    id="claim_001",
    type="performance_issue",
    severity="high",
    confidence=cost_result.confidence,
    confidence_basis=VERDICT_MAPPING[cost_result.verdict],  # ← 매핑
    proof_obligation=...
)

envelope = ResultEnvelope(
    claims=[claim],
    evidences=[cost_result.evidence],  # ← 팀 A가 만든 Evidence
    conclusion=...
)
```

**의존성**:
- ✅ Evidence 스키마 (고정됨)
- ✅ Claim 스키마 (고정됨)
- ❌ 팀 A의 Analyzer 불필요 (Mock 가능)

---

## 🔗 Interface Contract (양 팀 계약)

### Contract 1: Evidence 생성 규칙

**팀 A가 지켜야 할 것**:
```python
# ✅ GOOD: CostEvidenceBuilder 사용
evidence = CostEvidenceBuilder.build(
    evidence_id="req_001_ev_001",
    location=Location(...),
    cost_term="n * m",
    loop_bounds=[...],  # ← 필수 필드 준수
    hotspots=[...],
    provenance=Provenance(engine="CostAnalyzer", version="1.0.0"),
    claim_ids=["claim_001"]
)

# ❌ BAD: 직접 생성 (validation 우회)
evidence = Evidence(
    kind=EvidenceKind.COST_TERM,
    content={"term": "n * m"}  # ← 필드명 틀림!
)
```

**검증 방법**:
```python
# 팀 A는 테스트에서 이렇게 검증
def test_cost_evidence_schema_compliance():
    evidence = my_analyzer.analyze(...)

    # Evidence 타입 확인
    assert isinstance(evidence, Evidence)

    # Content 필수 필드 확인
    assert "cost_term" in evidence.content
    assert "loop_bounds" in evidence.content
```

---

### Contract 2: Verdict → ConfidenceBasis 매핑

**매핑 테이블** (양 팀 공유):
```python
# src/agent/domain/rfc_specs/mappings.py (공통)

VERDICT_TO_CONFIDENCE_BASIS = {
    "proven": ConfidenceBasis.PROVEN,
    "likely": ConfidenceBasis.INFERRED,
    "heuristic": ConfidenceBasis.HEURISTIC
}

# 팀 A 사용
result = CostResult(
    verdict="proven",  # ← 이 값 사용
    confidence=0.95,
    ...
)

# 팀 B 사용
claim = Claim(
    confidence_basis=VERDICT_TO_CONFIDENCE_BASIS[result.verdict],  # ← 변환
    ...
)
```

---

### Contract 3: Result → Envelope 변환 인터페이스

**팀 B가 구현할 것** (팀 A는 Mock 사용 가능):
```python
# src/agent/adapters/rfc/converters.py (팀 B)

def cost_result_to_claim(
    result: CostResult,  # ← 팀 A 출력
    claim_id: str
) -> Claim:
    """CostResult → Claim 변환 (팀 B 책임)"""
    return Claim(
        id=claim_id,
        type="performance_issue",
        severity=_cost_to_severity(result.complexity),
        confidence=result.confidence,
        confidence_basis=VERDICT_TO_CONFIDENCE_BASIS[result.verdict],
        proof_obligation=ProofObligation(
            assumptions=["loop bound inference correct"],
            broken_if=[],
            unknowns=result.evidence.content.get("unknowns", [])
        )
    )
```

---

## 📅 병행 작업 타임라인

### Week 1: 독립 작업 ✅

**팀 A**:
- [ ] Day 1-2: CostAnalyzer 기본 구현
- [ ] Day 3: Loop bound inference
- [ ] Day 4-5: SCCP integration

**팀 B**:
- [ ] Day 1: ResultEnvelope 구조 정의
- [ ] Day 2-3: /execute API 구현 (Mock analyzer 사용)
- [ ] Day 4-5: Arbitration Engine 기본

**의존성**: ✅ **없음** (Evidence 스키마 확정됨)

---

### Week 2: 조율 포인트 ⚠️ SYNC

**Day 10: Integration Test Day** (양 팀 협업)

```python
# 통합 테스트
def test_cost_analyzer_to_envelope():
    """팀 A 출력 → 팀 B 변환 테스트"""

    # 팀 A: Cost 분석
    cost_result = cost_analyzer.analyze("process_data")

    # 팀 B: Envelope 변환
    envelope = result_to_envelope(cost_result)

    # 검증
    assert envelope.claims[0].confidence_basis == ConfidenceBasis.PROVEN
    assert envelope.evidences[0].kind == EvidenceKind.COST_TERM
    assert envelope.evidences[0].content["cost_term"] == "n * m"
```

**확인 사항**:
- [ ] Evidence 형식 일치 (팀 A가 CostEvidenceBuilder 사용했는지)
- [ ] Verdict 매핑 정확 (proven → PROVEN)
- [ ] Content 필수 필드 포함 (loop_bounds, cost_term)

---

### Week 3-4: 독립 작업 ✅

**팀 A**:
- [ ] Day 11-14: Cost 4-Point Integration
- [ ] Day 15-18: Concurrency 구현 시작

**팀 B**:
- [ ] Day 11-14: Replay Infrastructure
- [ ] Day 15-18: Feedback Loop

**의존성**: ✅ **없음** (Interface 확정됨)

---

### Week 4: 중간 통합 ⚠️ SYNC

**Day 28: Mid-Point Integration** (양 팀 협업)

```python
# 실제 Cost Analyzer + 실제 API 통합
@router.post("/execute")
async def execute(spec: ExecuteSpec) -> ResultEnvelope:
    # 팀 A의 실제 구현 사용
    cost_result = foundation.cost_analyzer.analyze(...)

    # 팀 B의 변환 레이어
    envelope = converter.to_envelope(cost_result)

    return envelope
```

---

### Week 5-8: 독립 작업 ✅

**팀 A**: Concurrency + Differential
**팀 B**: API 완성 + Arbitration

**의존성**: ✅ **없음**

---

## 🛡️ 작업 충돌 방지 규칙

### Rule 1: 파일 소유권

| 디렉토리 | 소유 팀 | 다른 팀 접근 |
|---------|---------|------------|
| `src/agent/domain/rfc_specs/evidence.py` | **공통** | ⚠️  변경 금지 (확정됨) |
| `src/agent/domain/rfc_specs/claim.py` | **공통** | ⚠️  변경 금지 (확정됨) |
| `src/agent/domain/rfc_specs/envelope.py` | 팀 B | 팀 A는 import만 |
| `src/contexts/code_foundation/infrastructure/analyzers/cost/` | 팀 A | 팀 B는 접근 금지 |
| `server/api_server/routes/rfc/` | 팀 B | 팀 A는 접근 금지 |

### Rule 2: Evidence 생성 책임

**팀 A만 Evidence 생성 가능**:
```python
# ✅ 팀 A가 하는 것
evidence = CostEvidenceBuilder.build(...)

# ❌ 팀 B는 하지 않음
# 팀 B는 팀 A가 만든 Evidence를 받아서 Envelope에 넣기만
```

### Rule 3: Verdict 변환 책임

**팀 B만 Verdict → ConfidenceBasis 변환**:
```python
# ✅ 팀 B가 하는 것
claim = Claim(
    confidence_basis=VERDICT_TO_CONFIDENCE_BASIS[result.verdict],
    ...
)

# ❌ 팀 A는 하지 않음
# 팀 A는 verdict="proven" 문자열만 반환
```

---

## 📝 팀별 작업 명세

### 팀 A: RFC-028 (6-8주)

#### Week 1-2: Cost Analysis
```python
# 구현할 것
class CostAnalyzer:
    def analyze_function(self, func_fqn: str) -> CostResult:
        """
        Returns:
            CostResult(
                function_fqn="process_data",
                complexity="O(n²)",
                verdict="proven",  # ← 문자열
                confidence=0.95,
                evidence=Evidence(...),  # ← 스키마 준수!
                explanation="Nested loop detected"
            )
        """
        ...

# Evidence 생성 (CostEvidenceBuilder 사용 필수!)
evidence = CostEvidenceBuilder.build(
    evidence_id=f"req_{request_id}_ev_{uuid4()}",
    location=Location(...),
    cost_term="n * m",
    loop_bounds=[
        {"loop_id": "loop_1", "bound": "n", "method": "pattern", "confidence": 1.0}
    ],
    hotspots=[{"line": 15, "reason": "nested loop"}],
    provenance=Provenance(engine="CostAnalyzer", version="1.0.0"),
    claim_ids=[]  # 팀 B가 나중에 채움
)
```

#### Week 3-4: Integration
```python
# 4-Point Integration
# 1. IRStage
# 2. ReasoningPipeline
# 3. API Routes (팀 B가 만든 것 사용)
# 4. MCP Server
```

#### Week 5-6: Concurrency
```python
# 동일 패턴
class ConcurrencyResult:
    verdict: Literal["proven", "likely", "heuristic"]
    evidence: Evidence  # ← ConcurrencyEvidenceBuilder 사용!
    ...
```

#### Week 7-8: Differential
```python
# 동일 패턴
class DifferentialResult:
    verdict: Literal["proven", "likely", "heuristic"]
    evidence: Evidence  # ← DifferentialEvidenceBuilder 사용!
    ...
```

**팀 A가 하지 않는 것**:
- ❌ ResultEnvelope 생성 (팀 B 책임)
- ❌ Claim 생성 (팀 B 책임)
- ❌ Verdict → ConfidenceBasis 변환 (팀 B 책임)
- ❌ API 엔드포인트 구현 (팀 B 책임)

---

### 팀 B: RFC-027 (4-6주)

#### Week 1-2: Core Models + API
```python
# 구현할 것

# 1. ResultEnvelope
@dataclass
class ResultEnvelope:
    request_id: str
    summary: str
    claims: list[Claim]
    evidences: list[Evidence]  # ← 팀 A가 만든 것
    conclusion: Conclusion
    metrics: Metrics
    escalation: Escalation | None
    replay_ref: str

# 2. Converter (팀 A 결과 → Envelope)
def cost_result_to_envelope(
    cost_result: CostResult,  # ← 팀 A 출력
    request_id: str
) -> ResultEnvelope:
    # Claim 생성 (팀 B 책임!)
    claim = Claim(
        id=f"{request_id}_claim_001",
        type="performance_issue",
        severity=_cost_to_severity(cost_result.complexity),
        confidence=cost_result.confidence,
        confidence_basis=VERDICT_TO_CONFIDENCE_BASIS[cost_result.verdict],  # ← 매핑
        proof_obligation=ProofObligation(
            assumptions=["loop bound inference correct"],
            broken_if=[],
            unknowns=cost_result.evidence.content.get("unknowns", [])
        )
    )

    # Evidence는 그대로 (팀 A가 만듦)
    evidence = cost_result.evidence
    evidence.claim_ids = [claim.id]  # ← 팀 B가 링크

    return ResultEnvelope(
        request_id=request_id,
        claims=[claim],
        evidences=[evidence],
        ...
    )

# 3. API
@router.post("/rfc/execute")
async def execute(spec: ExecuteSpec) -> ResultEnvelope:
    # 팀 A의 Analyzer 호출 (실제 또는 Mock)
    cost_result = cost_analyzer.analyze(...)

    # 팀 B의 변환
    envelope = cost_result_to_envelope(cost_result, request_id)

    return envelope
```

#### Week 3-4: Arbitration + Replay
```python
# Arbitration Engine
class ResultArbitrator:
    def prioritize(self, claims: list[Claim]) -> list[Claim]:
        """
        PROVEN > INFERRED > HEURISTIC 우선순위
        """
        ...

# Replay
class RequestStore:
    def save(self, request_id: str, spec: dict, result: ResultEnvelope):
        ...
```

#### Week 5-6: Feedback + Streaming
```python
# Feedback Loop
@router.post("/rfc/feedback")
async def feedback(...):
    ...
```

**팀 B가 하지 않는 것**:
- ❌ Evidence 생성 (팀 A 책임)
- ❌ Loop bound inference (팀 A 책임)
- ❌ Race detection (팀 A 책임)
- ❌ Cost 계산 (팀 A 책임)

---

## 🔄 조율 포인트 (3회)

### Sync Point 1: Week 2 Day 10

**목적**: Interface 확인

**양 팀 체크리스트**:
- [ ] 팀 A: CostResult 반환 형식 확인
- [ ] 팀 B: Converter 구현 확인
- [ ] **통합 테스트**: Cost → Envelope 변환 검증

**테스트 코드**:
```python
# tests/integration/test_rfc_integration.py

def test_cost_to_envelope_integration():
    """팀 A + 팀 B 통합 테스트"""
    # 팀 A Mock
    cost_result = CostResult(
        function_fqn="test_func",
        complexity="O(n)",
        verdict="proven",
        confidence=0.95,
        evidence=CostEvidenceBuilder.build(...),
        explanation="Simple loop"
    )

    # 팀 B Converter
    envelope = cost_result_to_envelope(cost_result, "req_001")

    # 검증
    assert len(envelope.claims) == 1
    assert envelope.claims[0].confidence_basis == ConfidenceBasis.PROVEN
    assert len(envelope.evidences) == 1
    assert envelope.evidences[0].kind == EvidenceKind.COST_TERM
```

---

### Sync Point 2: Week 4 Day 28

**목적**: Mid-point 통합

**양 팀 체크리스트**:
- [ ] 팀 A: Cost 4-Point Integration 완료
- [ ] 팀 B: API /execute 구현 완료
- [ ] **End-to-end 테스트**: 실제 Cost Analyzer + 실제 API

---

### Sync Point 3: Week 8 Final

**목적**: 전체 통합

**양 팀 체크리스트**:
- [ ] 팀 A: Cost + Concurrency + Differential 완료
- [ ] 팀 B: API + Arbitration + Replay 완료
- [ ] **Production 테스트**: 실제 PR로 전체 플로우 검증

---

## 🚨 충돌 가능 지점 & 해결 방안

### 충돌 1: Evidence.content 구조 불일치

**위험**:
```python
# 팀 A가 만듦
content = {"cost_expr": "n * m"}  # ← 필드명 틀림

# 팀 B가 기대
content = {"cost_term": "n * m"}  # ← 필드명 다름
```

**해결**:
- ✅ CostEvidenceBuilder 강제 사용 (validation 있음)
- ✅ Week 2 통합 테스트에서 조기 발견

---

### 충돌 2: Verdict 값 불일치

**위험**:
```python
# 팀 A가 만듦
verdict = "PROVEN"  # ← 대문자

# 팀 B가 기대
VERDICT_MAPPING = {"proven": ...}  # ← 소문자
```

**해결**:
- ✅ `Literal["proven", "likely", "heuristic"]` 타입 힌트 (오타 방지)
- ✅ 매핑 테이블 공유 (`mappings.py`)

---

### 충돌 3: Evidence.claim_ids 타이밍

**위험**:
```python
# 팀 A가 만들 때
evidence = CostEvidenceBuilder.build(
    claim_ids=[]  # ← 아직 모름
)

# 팀 B가 Claim 만든 후 링크해야 함
# 하지만 Evidence는 immutable (frozen=True)!
```

**해결**:
```python
# Option 1: 팀 A는 claim_ids 비워둠 (validation 통과하도록)
# Builder 수정 필요
evidence = CostEvidenceBuilder.build(
    claim_ids=["pending"]  # ← 임시값
)

# Option 2: 팀 B가 Evidence 재생성
evidence_with_links = Evidence(
    id=evidence.id,
    kind=evidence.kind,
    location=evidence.location,
    content=evidence.content,
    provenance=evidence.provenance,
    claim_ids=[claim.id]  # ← 팀 B가 링크
)
```

**즉시 수정 필요** ⚠️

---

## 🔧 즉시 수정 사항

<function_calls>
<invoke name="search_replace">
<parameter name="file_path">/Users/songmin/Documents/code-jo/semantica-v2/codegraph/src/agent/domain/rfc_specs/evidence.py
