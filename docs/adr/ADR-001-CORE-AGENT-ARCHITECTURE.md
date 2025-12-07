# ADR-001: Core Code Agent Architecture (SOTA급 통합)

**Status**: Proposed  
**Owner**: Semantica Core  
**기간**: 8주 (Phase 1 / MVP)  
**관련 문서**: v7-roadmap.md (Port/Adapter 아키텍처)

---

## 1. 메타 정보

### 1-1. 기본 정보

- **ID**: ADR-001
- **Title**: Core Code Agent Architecture (4-Layer + Port/Adapter)
- **Status**: Proposed
- **최초 대상 기간**: 8주 (Phase 1 MVP)

### 1-2. 관련 ADR 묶음

**[내부 통합] 이 ADR에 포함되는 결정**:
- 옛 ADR-001: 4-Layer Agent Architecture
- 옛 ADR-002: Router vs TaskGraph Boundary
- 옛 ADR-003: Graph Workflow Engine
- 옛 ADR-004: Sandbox Executor

**[분리 유지] 별도 ADR로 남길 것**:
- Guardrail 정책 포맷
- LLM 라우팅
- Tool Taxonomy

---

## 2. 문맥 (Context)

### 2-1. 해결하려는 문제

코드 에이전트가 다음을 일관되게 수행:
1. 사용자 자연어 요청 해석
2. 관련 코드 검색
3. 수정 계획 수립
4. 패치 생성
5. 테스트/검증
6. Shadow 환경 검증

**동시에**:
- IDE/CLI/REST 등 여러 인바운드 어댑터 재사용
- **LLM/검색/샌드박스 교체 시에도 코어 도메인 불변** (Port/Adapter)
- **Vendor Lock-in 방지** (LangGraph/E2B/Guardrails AI 교체 가능)

### 2-2. 제약 조건

- 8주 내 "버그 수정 E2E" 안정화
- SOTA 기능은 Phase 2로 분리
- Python/TypeScript, **Hexagonal + Port/Adapter** 구조
- **Domain Model = Business Logic, DTO = Serialization**

---

## 3. 설계 힘 (Forces)

### 3-1. 상충하는 요구

- 빠른 MVP vs SOTA 확장성
- 단순 직선형 vs Self-heal Loop
- 로컬 개발 vs 강력한 격리
- 단일 LLM vs Multi-LLM 라우팅
- **특정 OSS 의존 vs Vendor Lock-in 방지** ⭐

### 3-2. 의도적 타협

**Phase 1**:
- Rule 기반 Router/TaskGraph
- Local Process 테스트 (Docker는 Stub)
- Pydantic Validator (Guardrails AI는 Stub)
- In-memory State (LangGraph Checkpoint는 Phase 2)

**Phase 2**:
- Dynamic TaskGraph (LLM)
- Session-based Docker Sandbox
- Guardrails AI 통합
- LangGraph Checkpoint (Long-running task 재개)

---

## 4. 최종 결정 요약

### 4-1. 전체 결정

1. **4-Layer + MetaLayer + Port/Adapter** 구조 확립 ⭐
2. Router ↔ TaskGraph 경계를 "무조건 규칙"로 명시
3. Workflow = 6-step StateMachine + LangGraph Adapter
4. Sandbox = ISandboxExecutor Port + 3가지 Adapter
5. **모든 외부 OSS는 Adapter로 래핑** (교체 가능) ⭐
6. **Domain Model ≠ DTO** (Business Logic vs Serialization) ⭐

### 4-2. 성공 기준

**Phase 1**:
- "Fix the bug in calculate()" → 3~8초 내 완료
- 재시도 1~2회 이내
- Adapter 교체 시간 < 5분 ⭐

**Phase 2 (SOTA)**:
- Simple Query p95 < 5초
- Complex Query p95 < 30초
- Sandbox Startup < 0.5초 (Session-based)
- Token 효율 < 8K
- Success Rate > 85%

---

## 5. Port/Adapter 아키텍처 (SOTA 핵심) ⭐

### 5-1. 아키텍처 원칙

```
┌─────────────────────────────────────────┐
│          Domain Layer                    │
│  ┌───────────────────────────────────┐  │
│  │ Domain Models (Business Logic)    │  │
│  │ - AgentTask, CodeChange           │  │
│  │ - WorkflowState                   │  │
│  └───────────────────────────────────┘  │
│                                          │
│  ┌───────────────────────────────────┐  │
│  │ Ports (Interfaces)                │  │
│  │ - IWorkflowEngine                 │  │
│  │ - ISandboxExecutor                │  │
│  │ - ILLMProvider                    │  │
│  │ - IGuardrailValidator             │  │
│  │ - IVCSApplier                     │  │
│  └───────────────────────────────────┘  │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│         Adapter Layer                    │
│  - LangGraphWorkflowAdapter             │
│  - LocalSandboxAdapter → E2BAdapter     │
│  - LiteLLMProviderAdapter               │
│  - PydanticValidator → GuardrailsAI     │
│  - GitPythonVCSAdapter                  │
└─────────────────────────────────────────┘
```

### 5-2. Port 정의 (핵심 5개)

```python
# src/agent/ports.py

from typing import Protocol

class IWorkflowEngine(Protocol):
    """Workflow 실행 엔진 (LangGraph 교체 가능)"""
    async def execute(
        self,
        steps: list[WorkflowStep],
        initial_state: WorkflowState
    ) -> WorkflowState:
        ...

class ISandboxExecutor(Protocol):
    """Sandbox 실행 (Local/Docker/E2B 교체 가능)"""
    async def create_session(
        self,
        config: SandboxConfig
    ) -> SandboxHandle:
        ...
    
    async def execute_command(
        self,
        handle: SandboxHandle,
        command: str
    ) -> ExecutionResult:
        ...
    
    async def destroy_session(
        self,
        handle: SandboxHandle
    ) -> None:
        ...

class ILLMProvider(Protocol):
    """LLM 제공자 (Multi-model Routing)"""
    async def complete(
        self,
        prompt: str,
        task_type: str,  # "analyze" | "generate" | "critique"
        temperature: float = 0.2
    ) -> str:
        ...

class IGuardrailValidator(Protocol):
    """Guardrail 검증 (Pydantic/Guardrails AI)"""
    async def validate(
        self,
        changes: CodeChange,
        policies: list[Policy]
    ) -> ValidationResult:
        ...

class IVCSApplier(Protocol):
    """VCS 적용 (GitPython)"""
    async def apply_changes(
        self,
        changes: list[CodeChange],
        branch_name: str
    ) -> CommitResult:
        ...
```

### 5-3. Adapter 교체 전략

| Port | Phase 1 | Phase 2 | Phase 3 |
|------|---------|---------|---------|
| **ISandboxExecutor** | LocalProcessAdapter | SessionDockerAdapter | E2BSandboxAdapter |
| **IGuardrailValidator** | PydanticAdapter | GuardrailsAIAdapter | - |
| **IVisualValidator** | StubAdapter | PlaywrightAdapter | - |
| **IWorkflowEngine** | LangGraphAdapter | LangGraphAdapter | 커스텀 가능 |
| **ILLMProvider** | LiteLLMAdapter | LiteLLMAdapter | - |

**교체 메커니즘**:
```yaml
# config/phase1.yaml
sandbox:
  adapter: local  # LocalSandboxAdapter

# config/phase2.yaml
sandbox:
  adapter: e2b    # E2BSandboxAdapter 교체 (5분 소요)
```

---

## 6. Domain Model vs DTO (SOTA 핵심) ⭐

### 6-1. Domain Model (Business Logic 포함)

```python
# src/agent/domain/models.py

from dataclasses import dataclass

@dataclass
class AgentTask:
    """Domain Model - 비즈니스 로직 포함"""
    task_id: str
    description: str
    context: CodeContext
    
    def estimate_complexity(self) -> int:
        """복잡도 추정 (도메인 로직)"""
        return len(self.context.symbols) * 10
    
    def requires_clarification(self) -> bool:
        """명확화 필요 여부"""
        return "?" in self.description or len(self.description.split()) < 3

@dataclass
class CodeChange:
    """Domain Model"""
    file_path: str
    original_lines: list[str]
    new_lines: list[str]
    change_type: str
    
    def calculate_impact_score(self) -> float:
        """영향도 점수 (도메인 로직)"""
        return len(self.new_lines) / max(len(self.original_lines), 1)
    
    def is_breaking_change(self) -> bool:
        """Breaking change 여부"""
        # 시그니처 변경, public API 수정 등
        ...

@dataclass
class WorkflowState:
    """Domain Model - 상태 + 전이 로직"""
    current_step: str
    task: AgentTask
    changes: list[CodeChange]
    errors: list[str]
    iteration: int
    
    def can_transition_to(self, next_step: str) -> bool:
        """상태 전이 가능 여부 (비즈니스 규칙)"""
        if next_step == "test" and not self.changes:
            return False
        if self.iteration > 5:
            return False
        return True
```

### 6-2. DTO (직렬화/전송용)

```python
# src/agent/dto/workflow_dto.py

from pydantic import BaseModel

class AgentTaskDTO(BaseModel):
    """DTO - Serialization only, 로직 없음"""
    task_id: str
    description: str
    context: dict  # CodeContext의 직렬화

class CodeChangeDTO(BaseModel):
    """DTO - Pydantic만"""
    file_path: str
    original_lines: list[str]
    new_lines: list[str]
    change_type: str

class WorkflowStateDTO(BaseModel):
    """DTO - LangGraph StateGraph용"""
    current_step: str
    task: AgentTaskDTO
    changes: list[CodeChangeDTO]
    errors: list[str]
    iteration: int
```

### 6-3. 변환 책임 (Adapter Layer)

```python
# Adapter가 Domain ↔ DTO 변환
class LangGraphWorkflowAdapter(IWorkflowEngine):
    
    def _to_dto(self, state: WorkflowState) -> WorkflowStateDTO:
        """Domain → DTO"""
        return WorkflowStateDTO(
            current_step=state.current_step,
            task=AgentTaskDTO(**state.task.__dict__),
            ...
        )
    
    def _to_domain(self, dto: WorkflowStateDTO) -> WorkflowState:
        """DTO → Domain"""
        return WorkflowState(
            current_step=dto.current_step,
            task=AgentTask(**dto.task.dict()),
            ...
        )
```

---

## 7. 아키텍처 개요

### 7-0. 4-Layer + MetaLayer + Port/Adapter

**Layer 0: Context** (CodeGraph/Retrieval)
- 역할: 관련 코드 검색
- Port: `IContextProvider`
- Adapter: `CodeGraphAdapter`

**Layer 1: Router**
- 역할: Intent 분류, 전략 선택
- 출력: `RoutingPlan`, `ExecutionMode`

**Layer 2: Workflow Engine**
- 역할: 6-step StateMachine 실행
- **Port**: `IWorkflowEngine` ⭐
- **Adapter**: `LangGraphWorkflowAdapter` (교체 가능)

**Layer 3: Executor / Sandbox**
- 역할: 테스트/빌드 실행
- **Port**: `ISandboxExecutor` ⭐
- **Adapter**: `LocalProcessAdapter` → `E2BSandboxAdapter`

**MetaLayer**:
- M0: TaskGraph Planner
- M1: Critic (Guardrail + LLM)
- M2: Guardrail (Port: `IGuardrailValidator`)

### 7-1. ExecutionMode

```python
class ExecutionMode(Enum):
    FAST = "fast"         # 빠른 실행, Critic 최소
    STANDARD = "standard" # Guardrail + Test
    EXPERIMENTAL = "experimental"  # SOTA (Docker, Dynamic Replan)
```

**Phase 1**: FAST, STANDARD만 지원  
**Phase 2**: EXPERIMENTAL 추가

---

## 8. 컴포넌트별 결정

### 8-1. Orchestrator (Port만 의존)

```python
# src/agent/orchestrator.py

class AgentOrchestrator:
    """Port만 의존 - Adapter 교체 가능"""
    
    def __init__(
        self,
        workflow_engine: IWorkflowEngine,  # Port
        sandbox: ISandboxExecutor,         # Port
        llm: ILLMProvider,                 # Port
        guardrail: IGuardrailValidator,    # Port
        vcs: IVCSApplier,                  # Port
    ):
        self.workflow_engine = workflow_engine
        self.sandbox = sandbox
        self.llm = llm
        self.guardrail = guardrail
        self.vcs = vcs
    
    async def execute(
        self,
        request: AgentRequest
    ) -> AgentResult:
        """Port만 사용 - 구현체 몰라도 됨"""
        
        # 1. Workflow 실행
        steps = self._create_workflow_steps()
        result = await self.workflow_engine.execute(steps, initial_state)
        
        # 2. Guardrail 검증
        validation = await self.guardrail.validate(result.changes, policies)
        
        # 3. Sandbox 테스트
        handle = await self.sandbox.create_session(config)
        test_result = await self.sandbox.execute_command(handle, "pytest")
        
        # 4. VCS 적용
        commit = await self.vcs.apply_changes(result.changes, "feat/fix")
        
        return AgentResult(...)
```

### 8-2. LangGraph Workflow Adapter (얇은 래퍼)

```python
# src/agent/adapters/workflow/langgraph_adapter.py

from langgraph.graph import StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver

class LangGraphWorkflowAdapter(IWorkflowEngine):
    """LangGraph StateGraph 래핑 - 교체 가능"""
    
    def __init__(self, checkpoint_db: str = None):
        # Phase 1: checkpoint_db=None
        # Phase 2: checkpoint_db="checkpoints.db"
        self.checkpointer = (
            SqliteSaver.from_conn_string(checkpoint_db)
            if checkpoint_db else None
        )
    
    async def execute(
        self,
        steps: list[WorkflowStep],
        initial_state: WorkflowState
    ) -> WorkflowState:
        """LangGraph 실행 (Orchestration만)"""
        
        # 1. Domain → DTO 변환
        state_dto = self._to_dto(initial_state)
        
        # 2. StateGraph 생성
        graph = StateGraph(WorkflowStateDTO)
        
        for step in steps:
            # Node는 WorkflowStep.execute만 호출 (얇은 래퍼)
            graph.add_node(
                step.name,
                self._create_node_wrapper(step)
            )
        
        # 3. Edge 정의
        self._build_edges(graph, steps)
        
        # 4. 실행
        compiled = graph.compile(checkpointer=self.checkpointer)
        
        result_dto = await compiled.ainvoke(
            state_dto,
            config={"configurable": {"thread_id": initial_state.session_id}}
        )
        
        # 5. DTO → Domain 변환
        return self._to_domain(result_dto)
    
    def _create_node_wrapper(self, step: WorkflowStep):
        """Node wrapper - Business logic 없음"""
        async def node_func(state_dto: WorkflowStateDTO):
            # DTO → Domain
            state = self._to_domain(state_dto)
            
            # WorkflowStep.execute() 호출 (진짜 로직)
            state = await step.execute(state)
            
            # Domain → DTO
            return self._to_dto(state)
        
        return node_func
```

**Vendor Lock-in 완화**:
- LangGraph 교체 시: `LangGraphWorkflowAdapter`만 교체
- Domain Model(`WorkflowState`)은 불변

### 8-3. LLM Provider (Multi-model Routing)

```python
# src/agent/adapters/llm/litellm_adapter.py

import litellm

class LiteLLMProviderAdapter(ILLMProvider):
    """LiteLLM Router로 Task별 모델 선택"""
    
    MODEL_MAP = {
        "analyze": "gpt-4o-mini",       # 빠름, 저렴
        "generate": "claude-3.5-sonnet", # 정확, 고품질
        "critique": "gpt-4o",            # 강력, 비싸지만 정확
    }
    
    FALLBACK_CHAIN = [
        "claude-3.5-sonnet",
        "gpt-4o",
        "gpt-4o-mini",
    ]
    
    async def complete(
        self,
        prompt: str,
        task_type: str,
        temperature: float = 0.2
    ) -> str:
        """Task별 모델 선택 + Fallback"""
        
        model = self.MODEL_MAP.get(task_type, "gpt-4o-mini")
        
        # Retry with fallback
        for fallback_model in self.FALLBACK_CHAIN:
            try:
                response = await litellm.acompletion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                )
                return response.choices[0].message.content
            
            except Exception as e:
                logger.warning(f"Model {model} failed: {e}, trying {fallback_model}")
                model = fallback_model
        
        raise RuntimeError("All LLM models failed")
```

**ROI**:
- Task별 모델 선택으로 비용 30% 절감
- Fallback으로 안정성 확보

### 8-4. Sandbox Executor (Phase별 Adapter 교체)

#### Phase 1: Local Process Adapter

```python
# src/agent/adapters/sandbox/local_sandbox_adapter.py

import subprocess

class LocalProcessAdapter(ISandboxExecutor):
    """Phase 1 - subprocess 기반"""
    
    async def create_session(self, config: SandboxConfig) -> SandboxHandle:
        """임시 디렉토리 생성"""
        temp_dir = tempfile.mkdtemp(prefix="sandbox_")
        return SandboxHandle(id=temp_dir, type="local")
    
    async def execute_command(
        self,
        handle: SandboxHandle,
        command: str
    ) -> ExecutionResult:
        """subprocess 실행"""
        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            timeout=30,
            cwd=handle.id
        )
        
        return ExecutionResult(
            stdout=result.stdout.decode(),
            stderr=result.stderr.decode(),
            exit_code=result.returncode,
        )
    
    async def destroy_session(self, handle: SandboxHandle) -> None:
        """정리"""
        shutil.rmtree(handle.id)
```

#### Phase 2: Session-based Docker Adapter

```python
# src/agent/adapters/sandbox/session_docker_adapter.py

import docker

class SessionDockerAdapter(ISandboxExecutor):
    """Phase 2 - Session-based (exec_run)"""
    
    async def create_session(self, config: SandboxConfig) -> SandboxHandle:
        """컨테이너 1개 띄우기 (Keep-alive)"""
        client = docker.from_env()
        
        container = client.containers.run(
            "python:3.11-slim",
            command="tail -f /dev/null",  # Keep alive
            detach=True,
            mem_limit="512m",
            network_mode="none",
        )
        
        return SandboxHandle(id=container.id, type="docker", raw=container)
    
    async def execute_command(
        self,
        handle: SandboxHandle,
        command: str
    ) -> ExecutionResult:
        """exec_run (0.1초, 20x 빠름)"""
        container = handle.raw
        
        exec_result = container.exec_run(
            f"bash -c '{command}'",
            stdout=True,
            stderr=True,
        )
        
        return ExecutionResult(
            stdout=exec_result.output.decode(),
            exit_code=exec_result.exit_code,
        )
```

#### Phase 3: E2B Adapter

```python
# src/agent/adapters/sandbox/e2b_sandbox_adapter.py

from e2b import Sandbox

class E2BSandboxAdapter(ISandboxExecutor):
    """Phase 3 - E2B (SOTA)"""
    
    async def create_session(self, config: SandboxConfig) -> SandboxHandle:
        """E2B Sandbox 생성"""
        sandbox = await Sandbox.create(
            template="python-3.11",
            timeout=300,
        )
        return SandboxHandle(id=sandbox.id, type="e2b", raw=sandbox)
    
    async def execute_command(
        self,
        handle: SandboxHandle,
        command: str
    ) -> ExecutionResult:
        """E2B 실행 (0.3초, SOTA)"""
        sandbox = handle.raw
        result = await sandbox.run_code(command)
        
        return ExecutionResult(
            stdout=result.stdout,
            exit_code=0 if result.error is None else 1,
        )
```

**교체**:
```yaml
# config/phase1.yaml
sandbox:
  adapter: local

# config/phase2.yaml
sandbox:
  adapter: docker  # 5분만에 교체!

# config/phase3.yaml
sandbox:
  adapter: e2b
```

### 8-5. State Persistence (Long-running Task)

```python
# Phase 1: In-memory only
adapter = LangGraphWorkflowAdapter(checkpoint_db=None)

# Phase 2: SQLite Checkpoint
adapter = LangGraphWorkflowAdapter(checkpoint_db="checkpoints.db")

# 재개 (서버 재시작 후)
last_state = await adapter.graph.aget_state(
    config={"configurable": {"thread_id": session_id}}
)
result = await adapter.graph.ainvoke(last_state, ...)
```

**ROI**:
- 긴 작업(10분+) 재시작 없이 재개
- 서버 크래시 복구

---

## 9. Workflow Engine (6-step + Loop)

### 9-1. Step 정의

```python
class WorkflowStep(Enum):
    ANALYZE = "analyze"      # 관련 코드 검색
    GENERATE = "generate"    # 코드 변경안 생성
    CRITIC = "critic"        # Guardrail + LLM 리뷰
    TEST = "test"            # Sandbox 테스트
    SELF_HEAL = "self_heal"  # 오류 수정
    FINALIZE = "finalize"    # Proposal 생성
```

### 9-2. Loop 정책

**Phase 1**:
- TEST 실패 → SELF_HEAL → GENERATE
- max_iter = 2
- Error 분류: Heuristic (Syntax/Import → Self-heal)

**Phase 2**:
- Dynamic Replanning (LLM)
- max_iter = 5
- Error 분류: LLM 기반

---

## 10. Router vs TaskGraph Boundary

### 10-1. 역할 분리

**Router**:
- "무엇을 할지(What)" 결정
- 1회만 실행
- ExecutionMode, Strategy 선택

**TaskGraph**:
- "어떻게 할지(How)" 분해
- N회 실행 (Replan 가능)
- Step 시퀀스 구성

### 10-2. 경계 규칙

1. **Router Budget > TaskGraph Steps**
   - Budget 초과 시 TaskGraph가 Step 축소
   
2. **Router Strategy 우선**
   - TaskGraph는 Router Strategy 벗어날 수 없음
   
3. **Router는 1회, TaskGraph는 N회**
   - Replan 시 TaskGraph만 갱신

---

## 11. 결과 (Consequences)

### 11-1. 장점

✅ **Vendor Lock-in 방지**
- LangGraph/E2B/Guardrails AI 교체 5분
- Port/Adapter로 구현체 격리

✅ **도메인 로직 보호**
- Domain Model은 OSS와 무관
- DTO로 직렬화만 처리

✅ **SOTA 확장성**
- Phase 2/3으로 점진적 업그레이드
- 기존 코드 변경 없음

✅ **테스트 용이성**
- Port는 Mock 가능
- Domain Model 단독 테스트

### 11-2. 단점

⚠️ **초기 복잡도 증가**
- Port/Adapter 설계 필요
- DTO ↔ Domain 변환 오버헤드

⚠️ **Phase 1 제약**
- Mock Adapter 사용 (SOTA 아님)
- 성능은 Phase 2에서 개선

---

## 12. SOTA 메트릭

### 12-1. 성능 지표

| Metric | Target | 측정 방법 |
|--------|--------|----------|
| **Simple Query p95** | < 5초 | OpenTelemetry |
| **Complex Query p95** | < 30초 | - |
| **Sandbox Startup** | < 0.5초 | Session-based Docker |
| **LLM Token 효율** | < 8K tokens | Context pruning |
| **Success Rate** | > 85% | E2E tests |

### 12-2. 아키텍처 유연성

| Metric | Target |
|--------|--------|
| **Adapter 교체 시간** | < 5분 |
| **신규 Adapter 추가** | < 1일 |
| **Port 변경 없이 확장** | 100% |

### 12-3. 비용 효율

- LiteLLM Router로 Task별 모델 선택
- Claude-3.5-Sonnet (generate) vs GPT-4o-mini (analyze)
- **비용 30% 절감** (기대)

---

## 13. 구현 범위 (Phase별)

### 13-1. Phase 1 (8주, 이 ADR)

**포함**:
- ✅ 4-Layer + Port 정의
- ✅ Domain Model vs DTO 분리
- ✅ LangGraphWorkflowAdapter (In-memory)
- ✅ LocalProcessAdapter (Sandbox)
- ✅ PydanticValidatorAdapter (Guardrail)
- ✅ LiteLLMProviderAdapter (LLM Routing)
- ✅ GitPythonVCSAdapter

**제외 (Hook만 정의)**:
- ❌ LangGraph Checkpoint (Phase 2)
- ❌ Session Docker/E2B Sandbox (Phase 2)
- ❌ Guardrails AI (Phase 2)
- ❌ Dynamic TaskGraph (Phase 2)

### 13-2. Phase 2 (SOTA)

**Adapter 교체**:
```diff
- LocalProcessAdapter
+ SessionDockerAdapter (0.5초)

- checkpoint_db=None
+ checkpoint_db="checkpoints.db"

- PydanticValidatorAdapter
+ GuardrailsAIAdapter
```

**새 기능**:
- Long-running task 재개
- Dynamic Replanning (LLM)
- Visual Verification (Playwright)

---

## 14. 의존성

```toml
# pyproject.toml

[tool.poetry.dependencies]
python = "^3.12"

# Core (Phase 1)
pydantic = "^2.9"
dependency-injector = "^4.41"

# LLM & Workflow (Phase 1)
litellm = "^1.51"
langgraph = "^0.2.45"

# VCS (Phase 1)
gitpython = "^3.1"

# Sandbox (Phase 2)
e2b = "^1.0"  # Phase 1: 설치 안 함

# Safety (Phase 2)
guardrails-ai = "^0.5"  # Phase 1: 설치 안 함

# Visual (Phase 2)
playwright = "^1.48"  # Phase 1: 설치 안 함
```

---

## 15. DI Container 설정

```python
# src/agent/container.py

from dependency_injector import containers, providers

class AgentContainer(containers.DeclarativeContainer):
    """DI Container - Phase별 Adapter 교체"""
    
    config = providers.Configuration()
    
    # LLM Provider
    llm_provider = providers.Factory(
        LiteLLMProviderAdapter,
        config_path=config.llm.config_path
    )
    
    # Workflow Engine
    workflow_engine = providers.Factory(
        LangGraphWorkflowAdapter,
        checkpoint_db=config.workflow.checkpoint_db  # Phase 1: None
    )
    
    # Sandbox (Phase별 교체)
    sandbox_executor = providers.Selector(
        config.sandbox.adapter,
        local=providers.Factory(LocalProcessAdapter),
        docker=providers.Factory(SessionDockerAdapter),
        e2b=providers.Factory(E2BSandboxAdapter),
    )
    
    # Guardrail (Phase별 교체)
    guardrail_validator = providers.Selector(
        config.guardrail.adapter,
        pydantic=providers.Factory(PydanticValidatorAdapter),
        guardrails_ai=providers.Factory(GuardrailsAIAdapter),
    )
    
    # Orchestrator (Port만 의존)
    orchestrator = providers.Factory(
        AgentOrchestrator,
        workflow_engine=workflow_engine,
        sandbox=sandbox_executor,
        llm=llm_provider,
        guardrail=guardrail_validator,
    )
```

**사용**:
```python
# config/phase1.yaml 로드
container = AgentContainer()
container.config.from_yaml("config/phase1.yaml")

orchestrator = container.orchestrator()  # LocalProcessAdapter 주입

# config/phase2.yaml로 교체 (5분 소요)
container.config.from_yaml("config/phase2.yaml")
orchestrator = container.orchestrator()  # E2BSandboxAdapter 주입
```

---

## 16. 관련 문서

- **v7-roadmap.md**: Port/Adapter 아키텍처 전체 설계
- **ADR-001** (이 문서): Phase 1 구현 계획 (8주)
- **현재 구현 상태**: `src/agent/` 골격 완성

---

## 17. 승인 기준

다음 조건 충족 시 승인:

1. ✅ Port/Adapter 패턴 준수
2. ✅ Domain Model ≠ DTO 분리
3. ✅ Phase 1 범위 명확 (8주)
4. ✅ Phase 2 Adapter 교체 경로 정의
5. ✅ SOTA 메트릭 정의
6. ✅ Vendor Lock-in 완화 전략

---

**Status**: Proposed → **Ready for Implementation** ✅



