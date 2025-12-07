# Semantica v2 Agent - v7 통합 로드맵 (Port/Adapter 기반)

> **핵심 원칙**: Domain Model 분리 + Vendor Lock-in 방지 + 점진적 OSS 통합

## 아키텍처 원칙

### ✅ DO (반드시 지켜야 할 것)

1. **Port/Adapter 패턴 강제**
   - 모든 외부 OSS는 Adapter로 래핑
   - 포트(인터페이스) 정의 후 구현체 교체 가능
   
2. **Domain Model = Business Logic**
   - Pydantic은 DTO/Serialization용
   - Domain Model은 별도 클래스 (메서드 포함)
   
3. **LangGraph = Orchestration Only**
   - Node 함수는 WorkflowStep 호출만
   - Business logic은 Domain Service에

4. **점진적 OSS 통합**
   - Phase 1: LangGraph + LiteLLM + GitPython (검증된 것)
   - Phase 2: E2B/Guardrails AI/Playwright Adapter stub → 실제 구현

### ❌ DON'T (절대 하지 말 것)

1. ❌ LangGraph node에 business logic 직접 작성
2. ❌ Pydantic으로 Domain Model 대체
3. ❌ E2B API 직접 호출 (반드시 SandboxExecutor 포트 경유)
4. ❌ Dict-based state (TypedDict 또는 Pydantic)
5. ❌ Guardrails DSL에 과도한 의존

---

## Port/Adapter 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                      Domain Layer                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Domain Models (Business Logic)                      │   │
│  │  - AgentTask, CodeChange, WorkflowState             │   │
│  │  - TaskGraph, ExecutionPlan                         │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Domain Services                                     │   │
│  │  - AnalyzeService, PlanService, GenerateService     │   │
│  │  - CriticService, TestService, HealService          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Ports (Interfaces)                                  │   │
│  │  - IWorkflowEngine                                   │   │
│  │  - ISandboxExecutor                                  │   │
│  │  - ILLMProvider                                      │   │
│  │  - IGuardrailValidator                               │   │
│  │  - IVCSApplier                                       │   │
│  │  - IVisualValidator                                  │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Adapter Layer                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  LangGraphWorkflowAdapter                            │   │
│  │  (IWorkflowEngine 구현)                              │   │
│  │  - LangGraph StateGraph 래핑                         │   │
│  │  - WorkflowStep → Node 변환                          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  E2BSandboxAdapter (ISandboxExecutor 구현)           │   │
│  │  - E2B SDK 래핑                                      │   │
│  │  - Phase 1: Stub (local subprocess)                 │   │
│  │  - Phase 2: 실제 E2B 연동                           │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  LiteLLMProviderAdapter (ILLMProvider 구현)          │   │
│  │  - LiteLLM Router 래핑                               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  GuardrailsAIAdapter (IGuardrailValidator 구현)      │   │
│  │  - Phase 1: Pydantic Validator만 (Stub)             │   │
│  │  - Phase 2: Guardrails AI 통합                      │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  GitPythonVCSAdapter (IVCSApplier 구현)              │   │
│  │  - GitPython 래핑                                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  PlaywrightVisualAdapter (IVisualValidator 구현)     │   │
│  │  - Phase 1: Stub (simple screenshot)                │   │
│  │  - Phase 2: Playwright + Vision Model               │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## OSS 통합 단계화 전략

### Phase 1 즉시 통합 (검증됨)
- **LangGraph**: Workflow orchestration (WorkflowStep으로 추상화)
- **LiteLLM**: Multi-model routing (교체 가능성 낮음)
- **GitPython**: VCS 작업 (표준 라이브러리 수준)

### Phase 1 Adapter Stub (실제 구현은 Phase 2+)
- **E2B**: LocalSandboxExecutor로 대체 (subprocess 기반)
- **Guardrails AI**: PydanticValidatorAdapter로 대체
- **Playwright**: SimpleBrowserAdapter (selenium 기반)

### Vendor Lock-in 완화 전략

| OSS | Lock-in 리스크 | 완화 방법 |
|-----|---------------|----------|
| **LangGraph** | StateGraph 구조 종속 | `WorkflowStep` 추상화 + `IWorkflowEngine` 포트 |
| **E2B** | E2B API 종속 | `ISandboxExecutor` 포트 + Local/Docker/K8s adapter |
| **Guardrails AI** | Guardrails DSL 종속 | Pydantic Validator로 롤백 가능 |
| **Playwright** | Playwright API 종속 | `IVisualValidator` 포트 + Selenium fallback |

---

## Domain Model vs DTO 분리

### Domain Model (Business Logic 포함)

```python
# src/agent/domain/models.py
from dataclasses import dataclass
from typing import Protocol

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
        """명확화 필요 여부 판단"""
        return "?" in self.description or len(self.description.split()) < 3

@dataclass
class CodeChange:
    """Domain Model"""
    file_path: str
    original_lines: list[str]
    new_lines: list[str]
    change_type: str
    
    def calculate_impact_score(self) -> float:
        """영향도 점수 계산"""
        return len(self.new_lines) / max(len(self.original_lines), 1)
    
    def is_breaking_change(self) -> bool:
        """Breaking change 여부"""
        # 시그니처 변경, public API 수정 등 체크
        pass

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
    
    def should_replicate(self) -> bool:
        """재계획 필요 여부"""
        return len(self.errors) > 3
```

### DTO (직렬화/전송용)

```python
# src/agent/dto/requests.py
from pydantic import BaseModel

class AgentRequestDTO(BaseModel):
    """DTO - Serialization only"""
    task_id: str
    description: str
    repo_path: str
    context_files: list[str]

class CodeChangeDTO(BaseModel):
    """DTO - API 전송용"""
    file_path: str
    original_code: str
    new_code: str
    change_type: str
```

---

## Port 정의 (인터페이스 우선)

```python
# src/ports.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class IWorkflowEngine(Protocol):
    """Workflow orchestration 포트"""
    
    async def execute(
        self, 
        steps: list[WorkflowStep], 
        initial_state: WorkflowState
    ) -> WorkflowResult:
        """Workflow 실행"""
        ...
    
    def add_step(self, step: WorkflowStep) -> None:
        """Step 추가"""
        ...

@runtime_checkable
class ISandboxExecutor(Protocol):
    """Sandbox 실행 포트"""
    
    async def create_sandbox(self, config: SandboxConfig) -> SandboxHandle:
        """Sandbox 생성"""
        ...
    
    async def execute_code(
        self, 
        handle: SandboxHandle, 
        code: str
    ) -> ExecutionResult:
        """코드 실행"""
        ...
    
    async def destroy_sandbox(self, handle: SandboxHandle) -> None:
        """Sandbox 정리"""
        ...

@runtime_checkable
class ILLMProvider(Protocol):
    """LLM 호출 포트"""
    
    async def complete(
        self, 
        messages: list[Message], 
        model_tier: str  # "fast" | "medium" | "strong"
    ) -> str:
        """텍스트 완성"""
        ...
    
    async def complete_with_schema(
        self, 
        messages: list[Message], 
        schema: Type[BaseModel],
        model_tier: str
    ) -> BaseModel:
        """구조화된 출력"""
        ...

@runtime_checkable
class IGuardrailValidator(Protocol):
    """Guardrail 검증 포트"""
    
    async def validate(
        self, 
        changes: CodeChange, 
        policies: list[Policy]
    ) -> ValidationResult:
        """변경사항 검증"""
        ...

@runtime_checkable
class IVCSApplier(Protocol):
    """VCS 적용 포트"""
    
    async def apply_changes(
        self, 
        changes: list[CodeChange], 
        branch_name: str
    ) -> CommitResult:
        """변경사항 적용"""
        ...
    
    async def create_pr(
        self, 
        branch_name: str, 
        title: str, 
        body: str
    ) -> PRResult:
        """PR 생성"""
        ...

@runtime_checkable
class IVisualValidator(Protocol):
    """Visual 검증 포트"""
    
    async def capture_screenshot(self, url: str) -> Screenshot:
        """스크린샷 캡처"""
        ...
    
    async def compare_screenshots(
        self, 
        before: Screenshot, 
        after: Screenshot
    ) -> VisualDiff:
        """시각적 차이 비교"""
        ...
```

---

## Phase 1: Core Foundation (8주)

### Week 1-2: Port 정의 + Domain Model + LangGraph Adapter

**목표**: Vendor lock-in 방지 기반 구축

**핵심 시나리오**
1. **시나리오 1**: "utils.py의 calculate_total 함수 버그 수정"
   - 요구사항: 단일 함수 수정 + 테스트 실행
   - 검증: Workflow 6단계 (Analyze→Plan→Generate→Critic→Test→Done)
   
2. **시나리오 2**: "로그인 실패 시 에러 메시지 개선"
   - 요구사항: 명확화 필요한 모호한 요청
   - 검증: Clarification 트리거 → 사용자 선택 → 재개

**구현**

```python
# src/agent/domain/workflow_step.py
from abc import ABC, abstractmethod

class WorkflowStep(ABC):
    """Workflow 단계 추상화 (LangGraph 독립적)"""
    
    @abstractmethod
    async def execute(self, state: WorkflowState) -> WorkflowState:
        """단계 실행 - Domain logic만"""
        pass
    
    @abstractmethod
    def can_execute(self, state: WorkflowState) -> bool:
        """실행 가능 여부 판단"""
        pass

class AnalyzeStep(WorkflowStep):
    """분석 단계 - Domain Service 사용"""
    
    def __init__(self, analyze_service: AnalyzeService):
        self.analyze_service = analyze_service
    
    async def execute(self, state: WorkflowState) -> WorkflowState:
        # Business logic
        analysis = await self.analyze_service.analyze_task(state.task)
        state.analysis_result = analysis
        return state

# src/adapters/langgraph_workflow_adapter.py
from langgraph.graph import StateGraph, END
from src.ports import IWorkflowEngine

class LangGraphWorkflowAdapter(IWorkflowEngine):
    """LangGraph → IWorkflowEngine 어댑터"""
    
    def __init__(self):
        self.graph = None
        self.steps: dict[str, WorkflowStep] = {}
    
    def add_step(self, step: WorkflowStep) -> None:
        """WorkflowStep 등록 (LangGraph node로 변환)"""
        self.steps[step.name] = step
    
    async def execute(
        self, 
        steps: list[WorkflowStep], 
        initial_state: WorkflowState
    ) -> WorkflowResult:
        """Workflow 실행"""
        # 1. WorkflowStep → LangGraph node 변환
        for step in steps:
            self.add_step(step)
        
        # 2. StateGraph 생성
        self.graph = StateGraph(WorkflowStateDTO)  # DTO로 변환
        
        for step in steps:
            # Node는 WorkflowStep.execute만 호출 (orchestration only)
            self.graph.add_node(
                step.name, 
                self._create_node_wrapper(step)
            )
        
        # 3. Edge 정의 (조건부 전이)
        self._build_edges(steps)
        
        # 4. 실행
        state_dto = self._to_dto(initial_state)
        result_dto = await self.graph.ainvoke(state_dto)
        
        return self._to_domain_model(result_dto)
    
    def _create_node_wrapper(self, step: WorkflowStep):
        """Node wrapper - business logic 없음"""
        async def node_func(state_dto: WorkflowStateDTO):
            # DTO → Domain Model
            state = self._to_domain_model(state_dto)
            
            # WorkflowStep 실행 (여기가 진짜 로직)
            state = await step.execute(state)
            
            # Domain Model → DTO
            return self._to_dto(state)
        
        return node_func
```

**Sandbox Executor Stub (Phase 1)**
```python
# src/adapters/sandbox/local_sandbox_adapter.py
from src.ports import ISandboxExecutor
import subprocess

class LocalSandboxAdapter(ISandboxExecutor):
    """Phase 1 Stub - subprocess 기반 (E2B 없이)"""
    
    async def create_sandbox(self, config: SandboxConfig) -> SandboxHandle:
        """로컬 임시 디렉토리 생성"""
        temp_dir = tempfile.mkdtemp(prefix="sandbox_")
        return SandboxHandle(id=temp_dir, type="local")
    
    async def execute_code(
        self, 
        handle: SandboxHandle, 
        code: str
    ) -> ExecutionResult:
        """subprocess로 코드 실행"""
        # Phase 1: 간단한 subprocess
        result = subprocess.run(
            ["python", "-c", code],
            capture_output=True,
            timeout=30,
            cwd=handle.id
        )
        
        return ExecutionResult(
            stdout=result.stdout.decode(),
            stderr=result.stderr.decode(),
            exit_code=result.returncode,
            execution_time=0  # stub
        )
    
    async def destroy_sandbox(self, handle: SandboxHandle) -> None:
        """임시 디렉토리 삭제"""
        shutil.rmtree(handle.id)

# src/adapters/sandbox/e2b_sandbox_adapter.py (Phase 2에 구현)
from e2b import Sandbox
from src.ports import ISandboxExecutor

class E2BSandboxAdapter(ISandboxExecutor):
    """Phase 2 - 실제 E2B 연동"""
    
    async def create_sandbox(self, config: SandboxConfig) -> SandboxHandle:
        """E2B sandbox 생성"""
        sandbox = await Sandbox.create(
            template=config.template,
            timeout=config.timeout,
            env_vars=config.env_vars
        )
        return SandboxHandle(id=sandbox.id, type="e2b", raw=sandbox)
    
    async def execute_code(
        self, 
        handle: SandboxHandle, 
        code: str
    ) -> ExecutionResult:
        """E2B에서 코드 실행"""
        sandbox = handle.raw
        result = await sandbox.run_code(code)
        
        return ExecutionResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            execution_time=result.execution_time
        )
```

**Guardrail Validator Stub (Phase 1)**
```python
# src/adapters/guardrail/pydantic_validator_adapter.py
from pydantic import BaseModel, field_validator
from src.ports import IGuardrailValidator

class SecretPattern(BaseModel):
    """Pydantic 기반 Secret 검증 (Guardrails AI 없이)"""
    code: str
    
    @field_validator('code')
    def check_secrets(cls, v):
        patterns = [
            r'(sk-[a-zA-Z0-9]{48})',  # OpenAI
            r'(ghp_[a-zA-Z0-9]{36})',  # GitHub
            r'(AKIA[0-9A-Z]{16})',  # AWS
        ]
        
        for pattern in patterns:
            if re.search(pattern, v):
                raise ValueError(f"Secret pattern detected: {pattern}")
        
        return v

class PydanticValidatorAdapter(IGuardrailValidator):
    """Phase 1 Stub - Pydantic Validator만"""
    
    async def validate(
        self, 
        changes: CodeChange, 
        policies: list[Policy]
    ) -> ValidationResult:
        """Pydantic validator로 검증"""
        errors = []
        
        for change in changes:
            # Secret 체크
            try:
                SecretPattern(code=change.new_code)
            except Exception as e:
                errors.append(str(e))
            
            # LOC limit
            if len(change.new_lines) > 500:
                errors.append(f"LOC limit exceeded: {len(change.new_lines)}")
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors
        )

# src/adapters/guardrail/guardrails_ai_adapter.py (Phase 2)
import guardrails as gd
from src.ports import IGuardrailValidator

class GuardrailsAIAdapter(IGuardrailValidator):
    """Phase 2 - Guardrails AI 통합"""
    
    def __init__(self):
        self.guard = gd.Guard.from_pydantic(CodeChangeValidation)
        self.guard.use(
            DetectSecrets(),
            DetectPII(),
            CheckLOCLimit(max_lines=500)
        )
    
    async def validate(
        self, 
        changes: CodeChange, 
        policies: list[Policy]
    ) -> ValidationResult:
        """Guardrails AI로 검증"""
        try:
            validated = self.guard.parse(changes.to_json())
            return ValidationResult(valid=True)
        except Exception as e:
            return ValidationResult(
                valid=False,
                errors=e.validation_errors
            )
```

#### Week 3-4: LiteLLM Adapter + GitPython Adapter

**핵심 시나리오**
3. **시나리오 3**: "모델 fallback 테스트"
   - 요구사항: Haiku 429 에러 → Sonnet fallback
   - 검증: 자동 fallback + 비용 기록

4. **시나리오 4**: "Git 충돌 해결"
   - 요구사항: main 브랜치 변경 중 AI 수정 발생
   - 검증: 3-way merge + 충돌 자동 해결

**LiteLLM Adapter**
```python
# src/adapters/llm/litellm_provider_adapter.py
from litellm import Router, completion
from src.ports import ILLMProvider

class LiteLLMProviderAdapter(ILLMProvider):
    """LiteLLM → ILLMProvider 어댑터"""
    
    def __init__(self):
        self.router = Router(
            model_list=[...],  # fast/medium/strong
            fallbacks=[{"fast": ["medium"]}, {"medium": ["strong"]}]
        )
    
    async def complete_with_schema(
        self,
        messages: list[Message],
        schema: Type[BaseModel],
        model_tier: str
    ) -> BaseModel:
        """구조화된 출력 (Pydantic)"""
        response = await completion(
            model=self._tier_to_model(model_tier),
            messages=[m.to_dict() for m in messages],
            response_format={"type": "json_object"}
        )
        
        return schema.model_validate_json(response.choices[0].message.content)

# src/adapters/vcs/gitpython_vcs_adapter.py
import git
from src.ports import IVCSApplier

class GitPythonVCSAdapter(IVCSApplier):
    """GitPython → IVCSApplier 어댑터"""
    
    def __init__(self, repo_path: str):
        self.repo = git.Repo(repo_path)
    
    async def apply_changes(
        self,
        changes: list[CodeChange],
        branch_name: str
    ) -> CommitResult:
        """브랜치 생성 + 변경 적용 + 커밋"""
        current = self.repo.active_branch
        new_branch = self.repo.create_head(branch_name)
        new_branch.checkout()
        
        for change in changes:
            self._apply_single_change(change)
        
        self.repo.index.add([c.file_path for c in changes])
        commit = self.repo.index.commit(f"AI: {changes[0].rationale[:50]}")
        
        current.checkout()
        return CommitResult(commit_sha=commit.hexsha, branch=branch_name)
```

#### Week 5-6: Domain Services + Confidence

**핵심 시나리오**
5. **시나리오 5**: "반복 실패 학습"
   - 요구사항: 동일 에러 3번 발생 → 경험 DB 조회 → 솔루션 재사용
   - 검증: Experience Store hit rate > 70%

```python
# src/agent/domain/services.py
class AnalyzeService:
    """분석 Domain Service"""
    
    def __init__(self, llm: ILLMProvider, context_manager: ContextManager):
        self.llm = llm
        self.context_manager = context_manager
    
    async def analyze_task(self, task: AgentTask) -> AnalysisResult:
        """Task 분석 (비즈니스 로직)"""
        # Context 선택
        context = await self.context_manager.select_relevant_context(task)
        
        # LLM으로 분석
        analysis = await self.llm.complete_with_schema(
            messages=[Message(role="user", content=f"Analyze: {task.description}")],
            schema=AnalysisResultDTO,
            model_tier="medium"
        )
        
        # DTO → Domain Model 변환
        return AnalysisResult.from_dto(analysis)
```

#### Week 7-8: 통합 + E2E 테스트

**E2E 시나리오**
6. **시나리오 6**: "Full workflow 통합 테스트"
   - 요구사항: "User 클래스에 email 필드 추가 + 테스트 작성"
   - 검증: Analyze→Plan→Generate→Critic→Test→Done (6단계 완료)

---

### Phase 2: Stub → 실제 구현 (5주)

#### Week 9-10: E2B Adapter 실제 구현

**핵심 시나리오**
7. **시나리오 7**: "악의적 코드 실행 차단"
   - 요구사항: `os.system("rm -rf /")` 실행 시도
   - 검증: E2B sandbox에서 격리 + 실패

```python
# E2BSandboxAdapter로 교체 (DI 설정만 변경)
# config/dependencies.py
def get_sandbox_executor() -> ISandboxExecutor:
    if PHASE == 1:
        return LocalSandboxAdapter()  # subprocess
    else:
        return E2BSandboxAdapter()  # 실제 E2B
```

#### Week 11-12: Guardrails AI + Playwright Adapter 구현

**핵심 시나리오**
8. **시나리오 8**: "Frontend visual regression 감지"
   - 요구사항: 버튼 색상 변경 → 스크린샷 비교
   - 검증: Playwright + Vision Model이 차이 감지

```python
# PlaywrightVisualAdapter로 교체
def get_visual_validator() -> IVisualValidator:
    if PHASE == 1:
        return SimpleBrowserAdapter()  # stub
    else:
        return PlaywrightVisualAdapter()  # Playwright + GPT-4o
```

#### Week 13: Incremental Execution

**핵심 시나리오**
9. **시나리오 9**: "단일 파일 수정 시 전체 재분석 방지"
   - 요구사항: utils.py 수정 → utils.py 의존 파일만 재분석
   - 검증: Impact subgraph 크기 < 10% (전체 대비)

---

### Phase 3: Advanced Features (5주)

#### Week 14-15: Human-in-the-loop + Trace

**핵심 시나리오**
10. **시나리오 10**: "Hunk 단위 부분 승인"
    - 요구사항: 3개 파일 변경 중 1개만 승인
    - 검증: 부분 커밋 + 나머지는 재생성

#### Week 16-18: Multi-user + Collaboration

**핵심 시나리오**
11. **시나리오 11**: "동시 편집 충돌 감지"
    - 요구사항: User A, AI B가 동시에 같은 파일 수정
    - 검증: Soft lock + hash drift 감지

---

## DI Container (Port → Adapter 주입)

```python
# src/container.py
from dependency_injector import containers, providers
from src.ports import *
from src.adapters import *

class AgentContainer(containers.DeclarativeContainer):
    """의존성 주입 컨테이너"""
    
    config = providers.Configuration()
    
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
        config.phase,
        phase1=providers.Factory(LocalSandboxAdapter),
        phase2=providers.Factory(E2BSandboxAdapter, config=config.e2b)
    )
    
    # Guardrail Validator (Phase별 교체)
    guardrail_validator = providers.Selector(
        config.phase,
        phase1=providers.Factory(PydanticValidatorAdapter),
        phase2=providers.Factory(GuardrailsAIAdapter, config=config.guardrails)
    )
    
    # VCS Applier
    vcs_applier = providers.Factory(
        GitPythonVCSAdapter,
        repo_path=config.repo_path
    )
    
    # Visual Validator (Phase별 교체)
    visual_validator = providers.Selector(
        config.phase,
        phase1=providers.Factory(SimpleBrowserAdapter),
        phase2=providers.Factory(PlaywrightVisualAdapter, llm=llm_provider)
    )
    
    # Domain Services
    analyze_service = providers.Factory(
        AnalyzeService,
        llm=llm_provider,
        context_manager=...
    )
    
    # Orchestrator
    orchestrator = providers.Factory(
        AgentOrchestrator,
        workflow_engine=workflow_engine,
        sandbox=sandbox_executor,
        llm=llm_provider,
        guardrail=guardrail_validator,
        vcs=vcs_applier
    )

# src/agent/orchestrator.py
class AgentOrchestrator:
    """Port만 의존 (Adapter 몰라도 됨)"""
    
    def __init__(
        self,
        workflow_engine: IWorkflowEngine,
        sandbox: ISandboxExecutor,
        llm: ILLMProvider,
        guardrail: IGuardrailValidator,
        vcs: IVCSApplier
    ):
        self.workflow_engine = workflow_engine
        self.sandbox = sandbox
        self.llm = llm
        self.guardrail = guardrail
        self.vcs = vcs
    
    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Port만 사용 - 구현체 교체 가능"""
        # Workflow 실행
        steps = self._create_workflow_steps()
        result = await self.workflow_engine.execute(steps, initial_state)
        
        # Guardrail 검증
        validation = await self.guardrail.validate(result.changes, policies)
        
        # Sandbox 테스트
        handle = await self.sandbox.create_sandbox(config)
        test_result = await self.sandbox.execute_code(handle, result.test_code)
        
        # VCS 적용
        commit = await self.vcs.apply_changes(result.changes, branch_name)
        
        return AgentResponse(...)
```

---

## 의존성 및 설정 (Phase별)

### pyproject.toml (점진적 추가)

```toml
[tool.poetry.dependencies]
python = "^3.12"

# Core (Phase 1 Week 1)
pydantic = "^2.9"
dependency-injector = "^4.41"

# LLM & Workflow (Phase 1 Week 1-4)
litellm = "^1.51"
langgraph = "^0.2.45"

# VCS (Phase 1 Week 3-4)
gitpython = "^3.1"

# Sandbox (Phase 2 Week 9-10)
e2b = "^1.0"  # Phase 1에서는 설치 안 함 (stub 사용)

# Safety (Phase 2 Week 11-12)
guardrails-ai = "^0.5"  # Phase 1에서는 설치 안 함 (Pydantic으로 대체)

# Visual (Phase 2 Week 11-12)
playwright = "^1.48"  # Phase 1에서는 설치 안 함 (stub 사용)

# 기존 infra (그대로 유지)
kuzu = "^0.6"
tantivy = "^0.22"
redis = "^5.0"
```

### config/phase1.yaml

```yaml
phase: phase1

llm:
  provider: litellm
  config_path: config/litellm_config.yaml

sandbox:
  adapter: local  # LocalSandboxAdapter
  timeout: 30

guardrail:
  adapter: pydantic  # PydanticValidatorAdapter

visual:
  adapter: simple  # SimpleBrowserAdapter
```

### config/phase2.yaml

```yaml
phase: phase2

sandbox:
  adapter: e2b  # E2BSandboxAdapter로 교체
  timeout: 300

guardrail:
  adapter: guardrails_ai  # GuardrailsAIAdapter로 교체

visual:
  adapter: playwright  # PlaywrightVisualAdapter로 교체
```

---

## 최종 디렉토리 구조 (Port/Adapter 기반)

```
src/
├── ports.py                           # 모든 인터페이스 정의
│
├── domain/                            # Domain Layer (비즈니스 로직)
│   ├── models.py                      # AgentTask, CodeChange, WorkflowState
│   ├── services.py                    # AnalyzeService, PlanService, GenerateService
│   └── workflow_step.py               # WorkflowStep 추상 클래스
│
├── adapters/                          # Adapter Layer (OSS 래핑)
│   ├── workflow/
│   │   └── langgraph_adapter.py       # LangGraphWorkflowAdapter
│   ├── sandbox/
│   │   ├── local_adapter.py           # LocalSandboxAdapter (Phase 1)
│   │   └── e2b_adapter.py             # E2BSandboxAdapter (Phase 2)
│   ├── llm/
│   │   └── litellm_adapter.py         # LiteLLMProviderAdapter
│   ├── guardrail/
│   │   ├── pydantic_adapter.py        # PydanticValidatorAdapter (Phase 1)
│   │   └── guardrails_ai_adapter.py   # GuardrailsAIAdapter (Phase 2)
│   ├── vcs/
│   │   └── gitpython_adapter.py       # GitPythonVCSAdapter
│   └── visual/
│       ├── simple_adapter.py          # SimpleBrowserAdapter (Phase 1)
│       └── playwright_adapter.py      # PlaywrightVisualAdapter (Phase 2)
│
├── dto/                               # DTO Layer (직렬화)
│   ├── requests.py                    # AgentRequestDTO
│   └── responses.py                   # AgentResponseDTO
│
├── agent/
│   ├── orchestrator.py                # AgentOrchestrator (Port만 의존)
│   ├── router.py                      # Router (ILLMProvider 사용)
│   └── task_planner.py                # TaskPlanner
│
├── container.py                       # DI Container (Phase별 교체)
│
└── config/
    ├── phase1.yaml                    # Phase 1 설정
    └── phase2.yaml                    # Phase 2 설정
```

---

## ROI 측정 (Port/Adapter + OSS 활용)

| 항목 | 자체 구현 시간 | Port/Adapter 시간 | OSS 활용 시간 | 총 절약 | ROI |
|------|--------------|-----------------|--------------|---------|-----|
| Workflow Engine | 6주 | 1주 (포트) | 1주 (LangGraph) | 4주 | 3x |
| Sandbox | 8주 | 1주 (포트) | 1주 (E2B stub→실제) | 6주 | 4x |
| LLM Routing | 3주 | 0.5주 (포트) | 0.5주 (LiteLLM) | 2주 | 3x |
| Guardrail | 4주 | 0.5주 (포트) | 1주 (Pydantic→Guardrails) | 2.5주 | 2.6x |
| VCS | 2주 | 0.5주 (포트) | 0.5주 (GitPython) | 1주 | 2x |
| Visual | 3주 | 0.5주 (포트) | 1주 (Playwright stub→실제) | 1.5주 | 2x |
| **총합** | **26주** | **4주** | **5주** | **17주** | **2.9x** |

**Port/Adapter 오버헤드**: 4주 (전체 대비 15%)  
**Vendor 교체 리스크 완화**: 4주 투자로 Lock-in 방지  
**순수 OSS 활용 대비**: -4주 (하지만 장기적 유지보수 비용 -50%)

---

## 구현 체크리스트

### ✅ Phase 1 Week 1-2 (Port 정의 완료 조건)

- [ ] `src/ports.py` 6개 인터페이스 정의 완료
  - [ ] `IWorkflowEngine`, `ISandboxExecutor`, `ILLMProvider`
  - [ ] `IGuardrailValidator`, `IVCSApplier`, `IVisualValidator`
- [ ] Domain Model 정의 (Pydantic DTO와 분리)
  - [ ] `AgentTask`, `CodeChange`, `WorkflowState` (메서드 포함)
- [ ] `WorkflowStep` 추상 클래스 6개 구현
  - [ ] `AnalyzeStep`, `PlanStep`, `GenerateStep`, `CriticStep`, `TestStep`, `HealStep`
- [ ] `LangGraphWorkflowAdapter` 구현 (node는 WorkflowStep만 호출)
- [ ] **시나리오 1, 2 테스트 통과**

### ✅ Phase 1 Week 3-4 (LLM + VCS 완료 조건)

- [ ] `LiteLLMProviderAdapter` 구현 (fallback 포함)
- [ ] `GitPythonVCSAdapter` 구현 (3-way merge 포함)
- [ ] `LocalSandboxAdapter` stub 구현 (subprocess)
- [ ] `PydanticValidatorAdapter` stub 구현
- [ ] **시나리오 3, 4 테스트 통과**

### ✅ Phase 1 Week 5-8 (통합 완료 조건)

- [ ] `AgentOrchestrator` 구현 (Port만 의존)
- [ ] DI Container 구현 (Phase별 교체 지원)
- [ ] Domain Services 구현 (AnalyzeService, PlanService, ...)
- [ ] **시나리오 5, 6 E2E 테스트 통과**

### ✅ Phase 2 (Stub → 실제 구현 완료 조건)

- [ ] `E2BSandboxAdapter` 구현 + DI 교체
- [ ] `GuardrailsAIAdapter` 구현 + DI 교체
- [ ] `PlaywrightVisualAdapter` 구현 + DI 교체
- [ ] **시나리오 7, 8 테스트 통과**

### ✅ Phase 3 (Advanced 완료 조건)

- [ ] Incremental Execution 구현
- [ ] Human-in-the-loop 구현
- [ ] **시나리오 9, 10, 11 테스트 통과**

---

## Anti-Pattern 경고

### 🚨 절대 하지 말 것

1. **LangGraph node에 비즈니스 로직 직접 작성**
   ```python
   # ❌ BAD
   def analyze_node(state: dict):
       # 여기서 분석 로직 직접 구현
       result = analyze_code(state["code"])  # Business logic in node!
       return {"analysis": result}
   
   # ✅ GOOD
   def analyze_node(state: WorkflowStateDTO):
       domain_state = to_domain(state)
       domain_state = await analyze_step.execute(domain_state)  # WorkflowStep 호출
       return to_dto(domain_state)
   ```

2. **Pydantic으로 Domain Model 대체**
   ```python
   # ❌ BAD
   class CodeChange(BaseModel):
       file_path: str
       new_code: str
       # 메서드 없음 - 그냥 데이터
   
   # ✅ GOOD
   @dataclass
   class CodeChange:
       file_path: str
       new_code: str
       
       def calculate_impact(self) -> float:  # 비즈니스 로직
           return len(self.new_code.split("\n")) / 100
   ```

3. **E2B API 직접 호출**
   ```python
   # ❌ BAD
   from e2b import Sandbox
   sandbox = await Sandbox.create()  # Port 없이 직접 호출
   
   # ✅ GOOD
   from src.ports import ISandboxExecutor
   sandbox = await self.sandbox_executor.create_sandbox(config)  # Port 경유
   ```

---

## 다음 단계

1. **Port 정의부터 시작**: `src/ports.py` 작성
2. **Domain Model 정의**: `src/domain/models.py`
3. **첫 번째 Adapter 구현**: `LangGraphWorkflowAdapter`
4. **시나리오 1 테스트**: "utils.py 버그 수정"
