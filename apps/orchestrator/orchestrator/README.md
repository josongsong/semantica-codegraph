# Agent - SOTA System

Autonomous Coding Agent with Deep Reasoning (System 2) and Fast Path (System 1) execution.

## Quick Start

### CLI 사용

```bash
# Auto mode (Dynamic Router가 System 1/2 자동 선택)
python -m src.cli.agent_v8 "fix null pointer exception in payment.py"

# Force System 2 (복잡한 작업에 Deep Reasoning 강제)
python -m src.cli.agent_v8 "refactor authentication logic" --slow

# Verbose output
python -m src.cli.agent_v8 "add input validation" -v
```

### Python API 사용

```python
from src.container import Container
from src.agent import DeepReasoningOrchestrator, DeepReasoningRequest
from src.agent.domain.models import AgentTask

# Container로 Orchestrator 가져오기
container = Container()
orchestrator = container.agent_orchestrator  # DeepReasoning

# Task 생성
task = AgentTask(
    task_id="my_task",
    repo_id=".",
    description="Fix null pointer in payment.py",
    context_files=["src/payment.py"],
)

# Request 생성 및 실행
request = DeepReasoningRequest(task=task)
response = await orchestrator.execute(request)

# 결과 확인
print(f"Success: {response.success}")
print(f"Path: {response.reasoning_decision.path.value}")  # SYSTEM_1 or SYSTEM_2
print(f"Time: {response.execution_time_ms}ms")
print(f"Cost: ${response.cost_usd}")
```

## Architecture

### Execution Flow

```
Request
  ↓
Dynamic Router ──→ System 1 (Fast) ──→ FastPath ──→ Response
  │                                       ↓
  │                                 (Linear Workflow)
  │
  └──→ System 2 (Deep) ──→ Multi-Candidate ──→ Constitutional AI ──→ Response
                           ↓                    ↓
                      (Beam/o1/Debate)    (Safety Check)
```

### Components

- **DeepReasoningOrchestrator**: 메인 진입점 (System 2 - SOTA)
  - Dynamic Routing
  - Multi-Candidate Strategies (Beam/o1/Debate/AlphaCode)
  - Constitutional AI 다층 검증
  - System 1/2 분기
  - Experience Store 통합

- **FastPathOrchestrator**: 빠른 선형 실행 (System 1)
  - Analyze → Plan → Generate → Critic → Test → Heal
  - CASCADE Reproduction Engine 통합
  - Guardrail 단일 검증
  - VCS Apply

- **Dynamic Router**: 자동 복잡도 분석 및 경로 결정
  - Complexity Analysis (AST depth, cyclomatic)
  - Risk Assessment (dependency graph)
  - Cost/Time Estimation

- **Multi-Candidate Strategies**: 다중 후보 생성 및 선택
  - **Beam Search**: 병렬 탐색 (beam_width=5)
  - **o1 Reasoning**: Multi-step verification loop
  - **Debate**: Multi-agent 토론 (3 proposers + 2 critics)
  - **AlphaCode**: 대량 샘플링 (100+) + 클러스터링

- **Constitutional AI**: Rule-based safety checks
  - Severity levels (critical/warning/info)
  - 모든 전략에서 다중 검증
  - Violation 상세 추적

## Decision Criteria

### System 1 (Fast Path)
- 간단한 버그 수정
- 작은 refactoring
- 명확한 요구사항
- 낮은 위험도
- **실행 시간**: ~5초
- **안전성**: Guardrail 1회

### System 2 (Deep Reasoning)
- 복잡한 아키텍처 변경
- 다중 파일 수정
- 불명확한 요구사항
- 높은 위험도
- **실행 시간**: ~45초
- **안전성**: Constitutional AI 다층

## Configuration

### Environment Variables

```bash
# LLM
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-...

# Sandbox (Optional)
E2B_API_KEY=...

# Experience Store (Optional)
EXPERIENCE_DB_PATH=~/.semantica/experience.db
```

### Request Options

```python
from src.agent.orchestrator.models import ReasoningStrategy

request = DeepReasoningRequest(
    task=task,
    strategy="beam",  # or "o1", "debate", "alphacode", "tot"
    config={
        "max_iterations": 5,
        "beam_width": 7,          # Beam Search
        "num_proposers": 3,       # Debate
        "alphacode_num_samples": 100,  # AlphaCode
    }
)
```

## Version

**0.8.0-sota** - SOTA System with Deep Reasoning

## Migration from Legacy

### Before (Legacy - v7/v8 naming)
```python
from src.agent.orchestrator import V8AgentOrchestrator  # Old
from src.agent.orchestrator import V7AgentOrchestrator  # Old

orchestrator = V8AgentOrchestrator(...)
```

### After (New - 직관적 naming)
```python
from src.agent import DeepReasoningOrchestrator, FastPathOrchestrator

# System 2 (Deep)
orchestrator = DeepReasoningOrchestrator(...)

# System 1 (Fast)
orchestrator = FastPathOrchestrator(...)

# Or use Container (권장)
orchestrator = container.agent_orchestrator  # Returns DeepReasoning
```

### Backward Compatibility

기존 코드는 그대로 작동합니다 (aliases 제공):
```python
# 이것들도 여전히 작동
from src.agent import V8AgentOrchestrator, V8AgentRequest  # → DeepReasoning*
from src.agent import V7AgentOrchestrator, V7AgentRequest  # → FastPath*
```

## Performance

| Metric | Fast Path (System 1) | Deep Reasoning (System 2) |
|--------|----------------------|---------------------------|
| **실행 시간** | ~5초 | ~45초 |
| **비용** | $0.01 | $0.15 |
| **전략** | Linear | Beam/o1/Debate/AlphaCode |
| **안전 검증** | Guardrail 1회 | Constitutional AI 다층 |
| **사용 케이스** | 단순 작업 | 복잡/고위험 작업 |

## Testing

```bash
# Integration tests
pytest tests/integration/test_v8_orchestrator.py
pytest tests/integration/test_v8_e2e_comprehensive.py

# Unit tests
pytest tests/unit/orchestrator/

# Benchmark
pytest tests/performance/test_v8_vs_v7_benchmark.py
```

## Files Structure

```
src/agent/
├── __init__.py                           # Main exports
├── orchestrator/
│   ├── __init__.py                      # Orchestrator exports
│   ├── deep_reasoning_orchestrator.py   # System 2 (SOTA)
│   ├── fast_path_orchestrator.py        # System 1 (빠른 실행)
│   └── models.py                        # Common models
├── domain/                              # Business logic
├── application/                         # Use cases
├── adapters/                            # External integrations
├── router/                              # Unified Router
└── workflow/                            # State Machine

src/cli/
└── agent_v8.py                          # CLI

src/container.py                         # DI Container
```

## Safety Comparison

### FastPath (System 1)
- **Port 기반 Guardrail**
- 외부 adapter 교체 가능
- 단순 pass/fail
- 1회 검증

### DeepReasoning (System 2)
- **Constitutional AI**
- Rule-based 내장
- Severity level (critical/warning/info)
- 모든 전략에서 다중 검증
- Violation 추적

## Contributing

시스템 개선 시:

1. `deep_reasoning_orchestrator.py` 또는 `fast_path_orchestrator.py` 수정
2. 테스트 추가
3. 문서 업데이트
4. PR 생성

## License

MIT
