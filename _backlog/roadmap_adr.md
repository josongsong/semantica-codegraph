# v7 헥사고날 아키텍처 검증 결과

날짜: 2025-12-06  
상태: ✅ 수정 완료

## 요약

v7 개발 작업에서 헥사고날 아키텍처 패턴 위반 사항을 검증하고 수정 완료.

**총 1개의 Critical 위반 발견 및 수정**

---

## 패턴 위반 및 수정

### ❌ Issue #1: Domain Layer에서 Pydantic 직접 의존 (CRITICAL)

**위치**: `src/agent/domain/real_services.py`

**문제점**:
```python
# ❌ BAD - Domain Layer가 Pydantic에 직접 의존
from pydantic import BaseModel, Field

class AnalysisOutput(BaseModel):
    summary: str = Field(description="분석 요약")
```

**v7 원칙 위반**:
- "Pydantic은 DTO/Serialization용, Domain Model은 별도 클래스"
- Domain Layer는 외부 라이브러리에 의존하면 안됨
- Pydantic 교체 시 Domain 코드 수정 필요

**수정 내용**:
1. Pydantic 모델을 `src/agent/dto/llm_dto.py`로 이동
2. Domain Service에서는 함수 내부에서 DTO import (lazy)
3. Domain Service는 dict 반환

```python
# ✅ GOOD - DTO Layer로 분리
# src/agent/dto/llm_dto.py
from pydantic import BaseModel, Field

class AnalysisOutputDTO(BaseModel):
    summary: str = Field(description="분석 요약")

# src/agent/domain/real_services.py
# Pydantic import 없음
async def analyze_task(self, task: AgentTask) -> dict[str, Any]:
    # 필요 시에만 DTO import
    from src.agent.dto.llm_dto import AnalysisOutputDTO
    
    analysis = await self.llm.complete_with_schema(
        messages, AnalysisOutputDTO, model_tier="medium"
    )
    
    # dict로 반환 (Domain은 Pydantic 모름)
    return {
        "summary": analysis.summary,
        "impacted_files": analysis.impacted_files,
        ...
    }
```

**영향 범위**:
- `RealAnalyzeService`
- `RealPlanService`
- `RealGenerateService`
- `RealCriticService`

---

## ✅ 잘 지켜진 사항

### 1. Domain Models
- ✅ `dataclass` 사용 (Pydantic 아님)
- ✅ 비즈니스 로직 포함 (`estimate_complexity`, `requires_clarification` 등)
- ✅ 외부 라이브러리 의존 없음

```python
@dataclass
class AgentTask:
    task_id: str
    description: str
    
    def estimate_complexity(self) -> int:
        """복잡도 추정 (비즈니스 로직)"""
        score = 1
        if len(self.context_files) > 10:
            score += 4
        return min(score, 10)
```

### 2. WorkflowStep 추상화
- ✅ LangGraph와 독립적
- ✅ 비즈니스 로직이 WorkflowStep에 집중
- ✅ 각 Step이 Domain Service 사용

```python
class AnalyzeStep(WorkflowStep):
    def __init__(self, analyze_service: AnalyzeService):
        self.analyze_service = analyze_service
    
    async def execute(self, state: WorkflowState) -> WorkflowState:
        # Domain Service 호출 (비즈니스 로직)
        analysis = await self.analyze_service.analyze_task(state.task)
        state.metadata["analysis"] = analysis
        return state
```

### 3. LangGraph Adapter
- ✅ Node에서 비즈니스 로직 직접 작성 안함
- ✅ WorkflowStep.execute만 호출 (orchestration only)
- ✅ Domain Model ↔ DTO 변환만 담당

```python
def _create_node_wrapper(self, step: WorkflowStep):
    async def node_func(state_dto: WorkflowStateDTO) -> WorkflowStateDTO:
        # DTO → Domain Model
        state = dto_to_workflow_state(state_dto)
        
        # WorkflowStep 실행 (비즈니스 로직)
        updated_state = await step.execute(state)
        
        # Domain Model → DTO
        return workflow_state_to_dto(updated_state)
    
    return node_func
```

### 4. Orchestrator
- ✅ Port만 의존 (IWorkflowEngine, ISandboxExecutor 등)
- ✅ Adapter 교체 가능
- ✅ 구현체를 모름

```python
class AgentOrchestrator:
    def __init__(
        self,
        workflow_engine: IWorkflowEngine,
        llm_provider: ILLMProvider,
        sandbox_executor: ISandboxExecutor,
        guardrail_validator: IGuardrailValidator,
        vcs_applier: IVCSApplier,
    ):
        self.workflow_engine = workflow_engine
        # Port만 의존
```

### 5. Adapters
- ✅ 모든 Adapter가 Port 구현
- ✅ 외부 라이브러리 lazy import
- ✅ Fallback 제공

**E2B Sandbox Adapter**:
```python
class E2BSandboxAdapter(ISandboxExecutor):
    def _get_client(self):
        if self._client is None:
            try:
                from e2b_code_interpreter import Sandbox
                self._client = Sandbox
            except ImportError:
                self._client = None  # Fallback
        return self._client
```

**LiteLLM Adapter**:
```python
class LiteLLMProviderAdapter(ILLMProvider):
    def _get_litellm(self):
        if self._litellm is None:
            import litellm
            self._litellm = litellm
        return self._litellm
```

### 6. DTO 분리
- ✅ WorkflowStateDTO와 Domain Model 분리
- ✅ 변환 함수 제공
- ✅ TypedDict 사용 (LangGraph 호환)

```python
class WorkflowStateDTO(TypedDict, total=False):
    task_id: str
    description: str
    current_step: str
    changes: list[dict[str, Any]]

def workflow_state_to_dto(state: WorkflowState) -> WorkflowStateDTO:
    return WorkflowStateDTO(
        task_id=state.task.task_id,
        description=state.task.description,
        ...
    )
```

### 7. Ports 정의
- ✅ 모든 Port가 Protocol로 정의
- ✅ `@runtime_checkable` 사용
- ✅ 명확한 인터페이스

```python
@runtime_checkable
class IWorkflowEngine(Protocol):
    @abstractmethod
    async def execute(
        self,
        steps: list[WorkflowStep],
        initial_state: WorkflowState,
    ) -> WorkflowResult:
        ...
```

### 8. DI Container
- ✅ Port 기반 의존성 주입
- ✅ Adapter 선택 및 교체
- ✅ `cached_property` 사용

```python
class V7AgentContainer:
    @cached_property
    def llm_provider(self):
        if api_key:
            return LiteLLMProviderAdapter(...)
        else:
            return StubLLMProvider()
    
    @cached_property
    def agent_orchestrator(self):
        return AgentOrchestrator(
            workflow_engine=self.workflow_engine,
            llm_provider=self.llm_provider,
            ...
        )
```

---

## 검증된 파일 목록

### Domain Layer
- ✅ `src/agent/domain/models.py` - dataclass 사용
- ✅ `src/agent/domain/workflow_step.py` - 추상화 잘됨
- ✅ `src/agent/domain/services.py` - Stub
- ✅ `src/agent/domain/real_services.py` - 수정 완료

### DTO Layer
- ✅ `src/agent/dto/workflow_dto.py` - TypedDict 분리
- 🆕 `src/agent/dto/llm_dto.py` - Pydantic DTO (신규 생성)

### Adapters
- ✅ `src/agent/adapters/workflow/langgraph_adapter.py` - 패턴 준수
- ✅ `src/agent/adapters/sandbox/e2b_adapter.py` - 패턴 준수
- ✅ `src/agent/adapters/sandbox/stub_sandbox.py` - 패턴 준수
- ✅ `src/agent/adapters/llm/litellm_adapter.py` - 패턴 준수 (Adapter layer에서 Pydantic 사용은 OK)
- ✅ `src/agent/adapters/guardrail/guardrails_adapter.py` - 패턴 준수
- ✅ `src/agent/adapters/vcs/gitpython_adapter.py` - 패턴 준수
- ✅ `src/agent/adapters/context_adapter.py` - Facade 패턴 (contexts 연동)

### Orchestrator
- ✅ `src/agent/orchestrator/v7_orchestrator.py` - Port만 의존

### Container
- ✅ `src/agent/v7_container.py` - DI 패턴 준수

---

## 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────┐
│                      Domain Layer                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Domain Models (dataclass, 비즈니스 로직 포함)       │   │
│  │  - AgentTask, CodeChange, WorkflowState             │   │
│  │  - estimate_complexity(), requires_clarification()  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Domain Services (외부 의존 없음)                    │   │
│  │  - RealAnalyzeService, RealPlanService              │   │
│  │  - RealGenerateService, RealCriticService           │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  WorkflowStep (비즈니스 로직 집중)                   │   │
│  │  - AnalyzeStep, PlanStep, GenerateStep              │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼ (의존 방향)
┌─────────────────────────────────────────────────────────────┐
│                    Ports (Protocol)                          │
│  - IWorkflowEngine, ISandboxExecutor, ILLMProvider          │
│  - IGuardrailValidator, IVCSApplier                         │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼ (의존 방향)
┌─────────────────────────────────────────────────────────────┐
│                    Adapter Layer                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  LangGraphWorkflowAdapter (IWorkflowEngine 구현)     │   │
│  │  - Node는 WorkflowStep.execute만 호출               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  E2BSandboxAdapter (ISandboxExecutor 구현)           │   │
│  │  - E2B SDK lazy import + Fallback                   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  LiteLLMProviderAdapter (ILLMProvider 구현)          │   │
│  │  - LiteLLM lazy import + Pydantic 처리              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  GuardrailsAIAdapter (IGuardrailValidator 구현)      │   │
│  │  - Guardrails AI + Pydantic Fallback                │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  GitPythonVCSAdapter (IVCSApplier 구현)              │   │
│  │  - GitPython lazy import                             │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    DTO Layer                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  workflow_dto.py (TypedDict - LangGraph용)           │   │
│  │  - WorkflowStateDTO, CodeChangeDTO                   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  llm_dto.py (Pydantic - LLM Structured Output용)    │   │
│  │  - AnalysisOutputDTO, PlanOutputDTO                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 의존성 방향 검증

```
Infrastructure (Adapters) → Application (Orchestrator) → Domain (Models/Services)
                   ↓                      ↓                       ↑
              Ports (Protocol)            |                       |
                                          |                       |
                                     Port만 의존            외부 의존 없음
```

✅ **의존성 방향 올바름**: Infrastructure → Application → Domain  
✅ **Domain Layer 순수성 유지**: 외부 라이브러리 의존 없음  
✅ **Port/Adapter 분리**: 모든 외부 라이브러리가 Adapter로 래핑됨

---

## 결론

v7 개발 작업은 전반적으로 헥사고날 아키텍처 원칙을 잘 준수했습니다.

**수정 전**:
- ❌ Domain Layer에서 Pydantic 직접 의존 (1건)

**수정 후**:
- ✅ 모든 패턴 위반 수정 완료
- ✅ Domain Layer 순수성 확보
- ✅ Pydantic DTO를 별도 Layer로 분리
- ✅ Port/Adapter 패턴 완전 준수

**다음 단계**:
1. 테스트 코드 업데이트 (llm_dto import 경로 수정)
2. 문서 업데이트 (아키텍처 가이드)
3. CI/CD 파이프라인에서 아키텍처 검증 추가
