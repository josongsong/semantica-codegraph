# RFC-027 LLM Arbitration Context

결정적 정적 분석과 LLM 추론을 중재하는 핵심 Context.

## 아키텍처

```
llm_arbitration/
├── application/           # Use cases
│   ├── execute_executor.py     # Spec 실행
│   ├── validate_executor.py    # Spec 검증
│   ├── plan_executor.py        # Intent → Spec 변환
│   └── explain_executor.py     # 결과 설명 생성
├── infrastructure/        # 구현체
│   ├── adapters/          # Producer → ResultEnvelope 변환
│   │   ├── taint_adapter.py
│   │   ├── sccp_adapter.py (TODO)
│   │   ├── reasoning_adapter.py
│   │   ├── risk_adapter.py
│   │   └── deep_reasoning_adapter.py
│   ├── arbitration_engine.py   # Claim 우선순위 중재
│   └── envelope_builder.py     # ResultEnvelope 조합
└── domain/                # Domain logic (TODO)
```

## 핵심 컴포넌트

### 1. Adapters

기존 분석 결과 → RFC-027 ResultEnvelope 변환:

```python
from src.contexts.llm_arbitration.infrastructure.adapters import TaintAdapter

adapter = TaintAdapter()
envelope = adapter.to_envelope(taint_result)
```

**Adapter 목록:**
- `TaintAdapter`: TaintAnalyzer → Envelope (PROVEN)
- `ReasoningAdapter`: ReasoningResult → Conclusion
- `RiskAdapter`: RiskReport → Claim
- `DeepReasoningAdapter`: DeepReasoningResult → Envelope (전략별 confidence_basis)

### 2. EnvelopeBuilder

여러 분석 결과를 하나의 ResultEnvelope로 조합:

```python
from src.contexts.llm_arbitration.infrastructure import EnvelopeBuilder

builder = EnvelopeBuilder(request_id="req_123")
builder.from_taint_result(taint_result)
builder.from_reasoning_result(reasoning_result)
envelope = builder.build()
```

### 3. ArbitrationEngine

Claim 우선순위 중재 (PROVEN > INFERRED > HEURISTIC > UNKNOWN):

```python
from src.contexts.llm_arbitration.infrastructure import ArbitrationEngine

engine = ArbitrationEngine()
arbitrated_claims = engine.arbitrate(claims)
```

**중재 규칙:**
- 동일 (type, severity)에 대해 낮은 우선순위 Claim 억제
- 억제된 Claim은 `suppressed=True`, `suppression_reason` 설정

### 4. Executors

#### ExecuteExecutor

Spec 실행 → ResultEnvelope:

```python
from src.contexts.llm_arbitration.application import ExecuteExecutor

executor = ExecuteExecutor()
envelope = await executor.execute(spec)
```

#### ValidateExecutor

Spec 유효성 검증:

```python
from src.contexts.llm_arbitration.application import ValidateExecutor

validator = ValidateExecutor()
result = validator.validate_spec(spec)  # {"valid": True/False, "errors": [...]}
```

## 사용 예시

### End-to-end 플로우

```python
# 1. Spec 생성
spec = {
    "intent": "analyze",
    "template_id": "sql_injection",
    "scope": {
        "repo_id": "repo:123",
        "snapshot_id": "snap:456",
    },
    "limits": {
        "max_paths": 200,
        "timeout_ms": 30000,
    }
}

# 2. Validation
validator = ValidateExecutor()
validation_result = validator.validate_spec(spec)
if not validation_result["valid"]:
    print(f"Errors: {validation_result['errors']}")
    exit(1)

# 3. Execution
executor = ExecuteExecutor()
envelope = await executor.execute(spec)

# 4. Arbitration (자동)
print(f"Found {len(envelope.claims)} claims")
print(f"Suppressed: {sum(1 for c in envelope.claims if c.suppressed)}")

# 5. Replay reference
print(f"Replay: {envelope.replay_ref}")
```

## API Endpoints

### POST /rfc/execute

Spec 실행:

```bash
curl -X POST /rfc/execute \\
  -H "Content-Type: application/json" \\
  -d '{
    "spec": {
      "intent": "analyze",
      "template_id": "sql_injection",
      "scope": {"repo_id": "repo:123", "snapshot_id": "snap:456"}
    }
  }'
```

### POST /rfc/validate

Spec 검증:

```bash
curl -X POST /rfc/validate \\
  -H "Content-Type: application/json" \\
  -d '{
    "spec": {
      "intent": "analyze",
      "template_id": "sql_injection"
    }
  }'
```

### POST /rfc/plan

Intent → Spec 변환:

```bash
curl -X POST /rfc/plan \\
  -H "Content-Type: application/json" \\
  -d '{
    "intent": "Find SQL injection vulnerabilities",
    "context": {"repo_id": "repo:123", "snapshot_id": "snap:456"}
  }'
```

### GET /rfc/replay/{request_id}

요청 재현 정보:

```bash
curl /rfc/replay/req_abc123
```

## 통합 가이드

### 새로운 Analyzer 통합

1. Adapter 생성:

```python
# infrastructure/adapters/my_analyzer_adapter.py
class MyAnalyzerAdapter:
    def to_envelope(self, result: MyAnalyzerResult) -> ResultEnvelope:
        claims = [...]
        evidences = [...]
        return ResultEnvelope(claims=claims, evidences=evidences)
```

2. EnvelopeBuilder에 추가:

```python
# infrastructure/envelope_builder.py
def from_my_analyzer_result(self, result: MyAnalyzerResult) -> "EnvelopeBuilder":
    envelope = self.my_analyzer_adapter.to_envelope(result)
    self.claims.extend(envelope.claims)
    return self
```

### 새로운 Template 추가

```python
# application/execute_executor.py
TEMPLATE_PIPELINE_MAP = {
    "my_new_template": ("my_pipeline", {"param": "value"}),
}
```
