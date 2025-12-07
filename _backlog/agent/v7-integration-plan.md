# v7 Agent - 기존 구조 통합 계획

## 현재 구조 분석

```
src/
├── ports.py                           # ✅ Foundation 포트 (이미 존재)
│   └── LexicalIndexPort, VectorIndexPort, SymbolIndexPort 등
│
├── container.py                       # ✅ DI Container (이미 존재)
│
├── contexts/                          # ✅ Bounded Contexts (DDD 패턴)
│   ├── code_foundation/               # 코드 분석 기반
│   ├── repo_structure/                # 레포 구조 파싱
│   ├── analysis_indexing/             # 인덱싱
│   ├── multi_index/                   # 멀티 인덱스 조합
│   ├── session_memory/                # 세션 메모리
│   ├── retrieval_search/              # 검색
│   └── reasoning_engine/              # 추론 엔진
│
├── agent/                             # ✅ 기존 Agent (점진적 확장)
│   ├── router/
│   ├── task_graph/
│   ├── workflow/
│   ├── orchestrator/
│   ├── adapters/
│   └── prompts/
│
├── execution/                         # ✅ 실행 계층
│   ├── sandbox/
│   ├── llm_router/
│   ├── vcs/
│   └── tools/
│
├── infra/                             # ✅ 인프라
│   ├── llm/
│   ├── graph/
│   ├── cache/
│   └── observability/
│
└── common/                            # ✅ 공통 유틸
```

---

## 통합 전략: 기존 구조 활용 + v7 원칙 적용

### 원칙
1. **기존 구조 최대한 유지** (contexts 기반 DDD 구조 우수)
2. **v7의 Port/Adapter 원칙만 추가 적용**
3. **점진적 마이그레이션** (기존 코드 깨지 않음)

---

## 통합 방안 A: `src/agent/` 확장 (추천)

### 디렉토리 구조

```
src/
├── ports.py                           # 기존 Foundation 포트 유지
│   └── + Agent 관련 포트 추가
│       - IWorkflowEngine
│       - ISandboxExecutor
│       - ILLMProvider
│       - IGuardrailValidator
│       - IVCSApplier
│       - IVisualValidator
│
├── agent/
│   ├── domain/                        # 🆕 Domain Layer
│   │   ├── models.py                  # AgentTask, CodeChange (비즈니스 로직 포함)
│   │   ├── services.py                # AnalyzeService, PlanService, GenerateService
│   │   └── workflow_step.py           # WorkflowStep 추상 클래스
│   │
│   ├── adapters/                      # ✅ 기존 + 확장
│   │   ├── context_adapter.py         # 기존 유지
│   │   ├── workflow/                  # 🆕
│   │   │   └── langgraph_adapter.py   # LangGraphWorkflowAdapter
│   │   ├── sandbox/                   # 🆕
│   │   │   ├── local_adapter.py       # LocalSandboxAdapter (Phase 1)
│   │   │   └── e2b_adapter.py         # E2BSandboxAdapter (Phase 2)
│   │   ├── llm/                       # 🆕
│   │   │   └── litellm_adapter.py     # LiteLLMProviderAdapter
│   │   ├── guardrail/                 # 🆕
│   │   │   ├── pydantic_adapter.py    # PydanticValidatorAdapter (Phase 1)
│   │   │   └── guardrails_ai_adapter.py  # GuardrailsAIAdapter (Phase 2)
│   │   ├── vcs/                       # 🆕
│   │   │   └── gitpython_adapter.py   # GitPythonVCSAdapter
│   │   └── visual/                    # 🆕
│   │       ├── simple_adapter.py      # SimpleBrowserAdapter (Phase 1)
│   │       └── playwright_adapter.py  # PlaywrightVisualAdapter (Phase 2)
│   │
│   ├── dto/                           # 🆕 DTO Layer
│   │   ├── requests.py                # AgentRequestDTO
│   │   └── responses.py               # AgentResponseDTO
│   │
│   ├── orchestrator/                  # ✅ 기존 확장
│   │   └── orchestrator.py            # Port 기반으로 리팩토링
│   │
│   ├── router/                        # ✅ 기존 유지
│   ├── task_graph/                    # ✅ 기존 유지
│   ├── workflow/                      # ✅ 기존 확장
│   └── prompts/                       # ✅ 기존 유지
│
├── container.py                       # ✅ Agent 포트 DI 추가
│
└── execution/                         # ✅ 기존 유지
    ├── sandbox/                       # ShadowFS 등 기존 로직 유지
    ├── llm_router/                    # 기존 로직 Adapter로 래핑
    ├── vcs/                           # 기존 로직 Adapter로 래핑
    └── tools/
```

### 마이그레이션 단계

#### Phase 1.1: Port 정의 (Week 1)

```python
# src/ports.py에 추가
from typing import Protocol, runtime_checkable

# ============================================================
# Agent Layer Ports (v7)
# ============================================================

@runtime_checkable
class IWorkflowEngine(Protocol):
    """Workflow orchestration 포트"""
    
    async def execute(
        self, 
        steps: list[WorkflowStep], 
        initial_state: WorkflowState
    ) -> WorkflowResult:
        ...

@runtime_checkable
class ISandboxExecutor(Protocol):
    """Sandbox 실행 포트"""
    
    async def create_sandbox(self, config: SandboxConfig) -> SandboxHandle:
        ...
    
    async def execute_code(
        self, 
        handle: SandboxHandle, 
        code: str
    ) -> ExecutionResult:
        ...

# ... 나머지 포트들
```

#### Phase 1.2: Domain Model 정의 (Week 1)

```python
# src/agent/domain/models.py
from dataclasses import dataclass

@dataclass
class AgentTask:
    """Domain Model - Business logic 포함"""
    task_id: str
    description: str
    context: CodeContext
    
    def estimate_complexity(self) -> int:
        """복잡도 추정 (비즈니스 로직)"""
        return len(self.context.symbols) * 10
    
    def requires_clarification(self) -> bool:
        """명확화 필요 여부"""
        return "?" in self.description

@dataclass
class CodeChange:
    """Domain Model"""
    file_path: str
    original_lines: list[str]
    new_lines: list[str]
    change_type: str
    
    def calculate_impact_score(self) -> float:
        """영향도 점수"""
        return len(self.new_lines) / max(len(self.original_lines), 1)
```

#### Phase 1.3: WorkflowStep 추상화 (Week 1-2)

```python
# src/agent/domain/workflow_step.py
from abc import ABC, abstractmethod

class WorkflowStep(ABC):
    """Workflow 단계 추상화"""
    
    @abstractmethod
    async def execute(self, state: WorkflowState) -> WorkflowState:
        """단계 실행"""
        pass

# src/agent/domain/services.py
class AnalyzeService:
    """분석 Domain Service"""
    
    def __init__(self, llm: ILLMProvider, context_manager: ContextManager):
        self.llm = llm
        self.context_manager = context_manager
    
    async def analyze_task(self, task: AgentTask) -> AnalysisResult:
        """Task 분석"""
        context = await self.context_manager.select_relevant_context(task)
        # ... 비즈니스 로직
        return analysis_result
```

#### Phase 1.4: 기존 코드와 통합 (Week 2-4)

```python
# src/agent/adapters/workflow/langgraph_adapter.py
from langgraph.graph import StateGraph
from src.ports import IWorkflowEngine
from src.agent.domain.workflow_step import WorkflowStep

class LangGraphWorkflowAdapter(IWorkflowEngine):
    """기존 src/agent/workflow/state_machine.py를 래핑"""
    
    def __init__(self):
        self.graph = StateGraph(WorkflowStateDTO)
    
    async def execute(
        self, 
        steps: list[WorkflowStep], 
        initial_state: WorkflowState
    ) -> WorkflowResult:
        # WorkflowStep → LangGraph node 변환
        for step in steps:
            self._add_node(step)
        
        return await self.graph.ainvoke(initial_state.to_dto())

# src/agent/orchestrator/orchestrator.py (기존 리팩토링)
class AgentOrchestrator:
    """기존 orchestrator를 Port 기반으로 리팩토링"""
    
    def __init__(
        self,
        workflow_engine: IWorkflowEngine,  # Port 주입
        sandbox: ISandboxExecutor,
        llm: ILLMProvider,
        # ... 기존 의존성도 유지
        router: UnifiedRouter,  # 기존 코드 유지
        task_planner: TaskGraphPlanner,  # 기존 코드 유지
    ):
        self.workflow_engine = workflow_engine
        self.sandbox = sandbox
        self.llm = llm
        self.router = router  # 기존 유지
        self.task_planner = task_planner  # 기존 유지
    
    async def execute(self, request: AgentRequest) -> AgentResponse:
        # 기존 로직 유지하면서 Port 사용
        steps = self._create_workflow_steps()
        result = await self.workflow_engine.execute(steps, initial_state)
        # ...
```

#### Phase 1.5: DI Container 업데이트 (Week 2)

```python
# src/container.py 확장
from dependency_injector import containers, providers
from src.ports import IWorkflowEngine, ISandboxExecutor, ILLMProvider
from src.agent.adapters.workflow.langgraph_adapter import LangGraphWorkflowAdapter
from src.agent.adapters.sandbox.local_adapter import LocalSandboxAdapter
from src.agent.adapters.llm.litellm_adapter import LiteLLMProviderAdapter

class Container(containers.DeclarativeContainer):
    """기존 Container 확장"""
    
    config = providers.Configuration()
    
    # ===== 기존 providers 유지 =====
    # (기존 코드 그대로)
    
    # ===== v7 Agent providers 추가 =====
    
    # LLM Provider
    llm_provider = providers.Singleton(
        LiteLLMProviderAdapter,
        config=config.litellm
    )
    
    # Workflow Engine
    workflow_engine = providers.Factory(
        LangGraphWorkflowAdapter
    )
    
    # Sandbox Executor (Phase별 교체)
    sandbox_executor = providers.Selector(
        config.agent.phase,
        phase1=providers.Factory(LocalSandboxAdapter),
        phase2=providers.Factory(E2BSandboxAdapter, config=config.e2b)
    )
    
    # Agent Orchestrator (기존 + v7)
    agent_orchestrator = providers.Factory(
        AgentOrchestrator,
        workflow_engine=workflow_engine,
        sandbox=sandbox_executor,
        llm=llm_provider,
        # 기존 의존성도 유지
        router=...,
        task_planner=...,
    )
```

---

## 통합 방안 B: `contexts/agent_execution/` 신규 생성 (대안)

### 디렉토리 구조

```
src/
├── contexts/
│   ├── code_foundation/
│   ├── repo_structure/
│   ├── ...
│   └── agent_execution/               # 🆕 Agent Execution Bounded Context
│       ├── domain/                    # Domain Layer
│       │   ├── models.py
│       │   ├── services.py
│       │   └── workflow_step.py
│       ├── adapters/                  # Adapter Layer
│       │   ├── workflow/
│       │   ├── sandbox/
│       │   └── ...
│       ├── application/               # Application Service
│       │   └── orchestrator.py
│       └── ports.py                   # Context별 포트
│
└── agent/                             # 기존 Agent (점진적 deprecated)
    └── ...
```

**장점**: DDD Bounded Context 패턴 일관성 유지  
**단점**: 기존 `src/agent/` 마이그레이션 비용 큼

---

## 추천: 방안 A (기존 구조 확장)

### 이유

1. **기존 코드 보존**
   - `src/agent/` 이미 존재하고 잘 구조화됨
   - 점진적 마이그레이션 가능

2. **최소 변경**
   - `domain/`, `adapters/`, `dto/` 추가만으로 v7 원칙 적용
   - 기존 `router/`, `task_graph/`, `workflow/` 유지

3. **DI 통합 용이**
   - 기존 `container.py` 확장만으로 가능

4. **contexts/는 Foundation 계층**
   - `contexts/`는 검색/인덱싱/추론 등 Foundation
   - `agent/`는 Application 계층 (역할 명확)

---

## 마이그레이션 체크리스트

### Week 1-2: Port + Domain
- [ ] `src/ports.py`에 Agent 포트 6개 추가
- [ ] `src/agent/domain/` 디렉토리 생성
  - [ ] `models.py` (AgentTask, CodeChange, WorkflowState)
  - [ ] `services.py` (AnalyzeService, PlanService, ...)
  - [ ] `workflow_step.py` (WorkflowStep 추상 클래스)
- [ ] `src/agent/dto/` 디렉토리 생성
  - [ ] `requests.py`, `responses.py`

### Week 3-4: Adapter Stub
- [ ] `src/agent/adapters/workflow/langgraph_adapter.py`
- [ ] `src/agent/adapters/sandbox/local_adapter.py` (Phase 1 stub)
- [ ] `src/agent/adapters/llm/litellm_adapter.py`
- [ ] `src/agent/adapters/vcs/gitpython_adapter.py`
- [ ] `src/agent/adapters/guardrail/pydantic_adapter.py` (Phase 1 stub)

### Week 5-6: Orchestrator 리팩토링
- [ ] `src/agent/orchestrator/orchestrator.py` Port 기반으로 수정
- [ ] `src/container.py`에 Agent providers 추가
- [ ] 기존 코드와 통합 테스트

### Week 7-8: E2E 검증
- [ ] 시나리오 1-6 테스트
- [ ] 기존 기능 회귀 테스트

---

## 설정 파일

### config/agent.yaml

```yaml
agent:
  phase: phase1  # phase1 | phase2
  
  workflow:
    max_iterations: 5
    enable_full_workflow: true
  
  sandbox:
    adapter: local  # local | e2b
    timeout: 30
  
  guardrail:
    adapter: pydantic  # pydantic | guardrails_ai
  
  visual:
    adapter: simple  # simple | playwright
  
  llm:
    provider: litellm
    config_path: config/litellm_config.yaml
```

---

## 다음 단계

1. **방안 A vs B 결정**: 방안 A 추천 (기존 구조 확장)
2. **Week 1 시작**: `src/ports.py` + `src/agent/domain/` 작성
3. **기존 코드 점진적 마이그레이션**

질문 있으면 말씀하세요.

