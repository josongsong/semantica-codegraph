# v7 Agent 사용법

## 🚀 빠른 시작

### Python 코드에서 사용

```python
import asyncio
from dataclasses import dataclass
from src.agent.v7_container import v7_container
from src.agent.domain.models import AgentTask

@dataclass
class AgentRequest:
    task: AgentTask
    config: dict | None = None

async def main():
    # 1. Task 정의
    task = AgentTask(
        task_id="my-task-1",
        description="utils.py의 calculate_total 함수 버그 수정",
        repo_id="my-repo",
        snapshot_id="snap1",
        context_files=["utils.py", "test_utils.py"],
    )
    
    # 2. Agent 실행
    request = AgentRequest(task=task)
    response = await v7_container.agent_orchestrator.execute(request)
    
    # 3. 결과 확인
    print(f"성공: {response.success}")
    print(f"변경 파일 수: {len(response.workflow_result.changes)}")
    
    for change in response.workflow_result.changes:
        print(f"  - {change.file_path}: {change.change_type.value}")

# 실행
asyncio.run(main())
```

---

## 📋 Task 정의

```python
from src.agent.domain.models import AgentTask

task = AgentTask(
    task_id="task-001",              # 고유 ID
    description="버그 수정 또는 기능 추가 설명",  # 자연어 설명
    repo_id="my-repo",               # 레포지토리 ID
    snapshot_id="snap1",             # 스냅샷 ID
    context_files=[                  # 관련 파일 목록
        "src/utils.py",
        "tests/test_utils.py",
    ],
    priority=1,                      # 우선순위 (선택)
    is_urgent=False,                 # 긴급 여부 (선택)
)
```

---

## 🎯 Container 사용

### 전체 Orchestrator 사용

```python
from src.agent.v7_container import v7_container

orchestrator = v7_container.agent_orchestrator
response = await orchestrator.execute(request)
```

### Adapter만 사용

```python
# LLM Provider
llm = v7_container.llm_provider
result = await llm.complete("코드를 분석해줘", system="You are a code analyzer")

# Sandbox Executor
sandbox = v7_container.sandbox_executor
sandbox_id = await sandbox.create_sandbox()
result = await sandbox.execute_code(sandbox_id, "print('hello')", "python")

# Guardrail Validator
guardrail = v7_container.guardrail_validator
validation = await guardrail.validate(changes)
```

### Service만 사용

```python
# Analyze Service
analyze = v7_container.analyze_service
analysis = await analyze.analyze_task(task)

# Generate Service
generate = v7_container.generate_service
changes = await generate.generate_changes(task, plan)
```

---

## 📊 응답 구조

```python
@dataclass
class AgentResponse:
    success: bool                     # 성공 여부
    workflow_result: WorkflowResult   # 워크플로우 결과
    commit_sha: str | None            # Git 커밋 SHA (선택)
    validation_result: dict | None    # 검증 결과 (선택)

@dataclass
class WorkflowResult:
    task: AgentTask                   # 원본 Task
    changes: list[CodeChange]         # 코드 변경 목록
    test_results: list[ExecutionResult]  # 테스트 결과 목록
    errors: list[str]                 # 에러 메시지
    metadata: dict[str, Any]          # 메타데이터
```

---

## 🔧 환경 설정

### .env 파일

```bash
# OpenAI API Key (필수)
OPENAI_API_KEY=sk-...
# 또는
SEMANTICA_OPENAI_API_KEY=sk-...
```

### Python에서 설정

```python
import os
os.environ["OPENAI_API_KEY"] = "sk-..."
```

---

## 💡 실전 예제

### 버그 수정

```python
task = AgentTask(
    task_id="bug-001",
    description="calculate_total 함수가 할인율을 잘못 계산함. 퍼센트로 적용해야 함",
    repo_id="ecommerce",
    snapshot_id="snap1",
    context_files=["app/utils.py", "tests/test_utils.py"],
)

response = await v7_container.agent_orchestrator.execute(
    AgentRequest(task=task, config={"max_iterations": 3})
)
```

### 기능 추가

```python
task = AgentTask(
    task_id="feature-001",
    description="User 모델에 last_login_at 필드 추가하고 로그인 시 업데이트",
    repo_id="user-service",
    snapshot_id="snap1",
    context_files=["app/models/user.py", "app/auth/login.py"],
    priority=2,
)

response = await v7_container.agent_orchestrator.execute(
    AgentRequest(task=task, config={"max_iterations": 5})
)
```

---

## 🎯 현재 사용 가능한 기능

✅ **Phase 1 완료**
- Port/Adapter 아키텍처
- LLM Provider (LiteLLM)
- Sandbox Executor (Local)
- Guardrail Validator (Pydantic)
- VCS Applier (GitPython)
- Workflow Engine (LangGraph)
- Context Manager
- Experience Store
- Real Services (Analyze, Plan, Generate, Critic, Test, Heal)

⏳ **Phase 2-3 미완료**
- E2B Sandbox (실제 격리 환경)
- Guardrails AI (고급 정책)
- Playwright (시각적 검증)
- Incremental Execution
- Human-in-the-loop

---

## 📝 참고

- 전체 로드맵: `_backlog/agent/v7-roadmap.md`
- 통합 가이드: `.temp/v7-integration-complete.md`
- E2E 테스트: `integrated_e2e.py`

