# ADR-002: v8.1 SOTA-Grade Hexagonal Package Structure

**Status**: Proposed  
**Date**: 2025-12-07  
**Depends on**: ADR-001-V8-ROADMAP  
**Architecture**: Hexagonal (Ports & Adapters)

---

## 1. Hexagonal Architecture Principles

### 1.1 핵심 원칙

```
┌─────────────────────────────────────────────────┐
│              Application Layer                  │
│         (Use Cases / Orchestration)             │
│  ┌───────────────────────────────────────────┐  │
│  │          Domain Layer (Core)              │  │
│  │     - Pure Business Logic                 │  │
│  │     - Framework Independent               │  │
│  │     - No External Dependencies            │  │
│  └───────────────────────────────────────────┘  │
│                     ▲                           │
│                     │                           │
│              ┌──────┴──────┐                    │
│              │    Ports    │                    │
│              │ (Interfaces)│                    │
│              └──────┬──────┘                    │
│                     ▼                           │
│  ┌──────────────────────────────────────────┐  │
│  │           Adapters Layer                 │  │
│  │   - LLM Adapters                         │  │
│  │   - Storage Adapters                     │  │
│  │   - Execution Adapters                   │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 1.2 의존성 규칙

```
Adapters → Ports → Domain ✅
Domain → Ports ❌
Domain → Adapters ❌
Application → Domain ✅
Application → Ports ✅
```

---

## 2. v8.1 Final Package Structure

```
src/agent/
│
├── 📦 domain/                          # ⭐ Domain Layer (Core Business Logic)
│   ├── __init__.py
│   │
│   ├── 🧠 reasoning/                   # v8.1 NEW: Reasoning Domain
│   │   ├── __init__.py
│   │   ├── models.py                   # QueryFeatures, ReasoningPath, etc.
│   │   ├── router.py                   # DynamicReasoningRouter (Domain Logic)
│   │   ├── tot_scorer.py               # TreeOfThoughtScorer (Domain Logic)
│   │   ├── reflection_judge.py         # SelfReflectionJudge (Domain Logic)
│   │   ├── graph_stability.py          # GraphStabilityAnalyzer
│   │   └── strategies.py               # CodeCandidate, Strategy models
│   │
│   ├── 💾 experience/                  # v8.1 NEW: Experience Domain
│   │   ├── __init__.py
│   │   ├── models.py                   # ExperienceV2, ExperienceQuery
│   │   ├── policies.py                 # Experience Save Policy (Domain)
│   │   ├── reliability.py              # Reliability Manager (Domain)
│   │   └── matchers.py                 # Experience Matching Logic
│   │
│   ├── 🔧 workflow/                    # v7.1 Existing: Workflow Domain
│   │   ├── __init__.py
│   │   ├── models.py                   # WorkflowState, WorkflowStep
│   │   ├── steps.py                    # 6 Workflow Steps
│   │   └── state_machine.py            # State Transitions
│   │
│   ├── 👥 collaboration/               # v7.1 Existing: Multi-Agent Domain
│   │   ├── __init__.py
│   │   ├── models.py                   # SoftLock, Conflict, etc.
│   │   ├── soft_lock_manager.py
│   │   ├── conflict_resolver.py
│   │   └── agent_coordinator.py
│   │
│   ├── 🤝 human_interaction/           # v7.1 Existing: HITL Domain
│   │   ├── __init__.py
│   │   ├── models.py                   # DiffRecord, ApprovalSession
│   │   ├── diff_manager.py
│   │   ├── approval_manager.py
│   │   └── partial_committer.py
│   │
│   └── 🛡️ safety/                      # v8.1 NEW: Fail-Safe Domain
│       ├── __init__.py
│       ├── models.py                   # FailureRecord, RecoveryStrategy
│       ├── fail_safe.py                # FailSafeLayer (Domain Logic)
│       └── circuit_breaker.py          # Circuit Breaker Pattern
│
├── 🔌 ports/                           # ⭐ Ports (Interfaces)
│   ├── __init__.py
│   │
│   ├── reasoning.py                    # v8.1 NEW: Reasoning Ports
│   │   # IComplexityAnalyzer
│   │   # IRiskAssessor
│   │   # IGraphAnalyzer
│   │   # IToTExecutor
│   │
│   ├── experience.py                   # v8.1 NEW: Experience Ports
│   │   # IExperienceStore
│   │   # IEmbeddingModel
│   │   # IExperienceRetriever
│   │
│   ├── workflow.py                     # v7.1 Existing
│   │   # IWorkflowEngine
│   │
│   ├── llm.py                          # v7.1 Existing
│   │   # ILLMProvider
│   │
│   ├── execution.py                    # v7.1 Existing
│   │   # ISandboxExecutor
│   │   # IVCSApplier
│   │
│   └── validation.py                   # v7.1 Existing
│       # IGuardrailValidator
│       # IVisualValidator
│
├── 🔧 adapters/                        # ⭐ Adapters (Infrastructure)
│   ├── __init__.py
│   │
│   ├── reasoning/                      # v8.1 NEW: Reasoning Adapters
│   │   ├── __init__.py
│   │   ├── complexity_analyzer.py      # CFG/Cyclomatic Complexity
│   │   ├── risk_assessor.py            # Historical Risk Model
│   │   └── graph_analyzer_adapter.py   # Memgraph/NetworkX Adapter
│   │
│   ├── experience/                     # v8.1 NEW: Experience Adapters
│   │   ├── __init__.py
│   │   ├── qdrant_store.py             # Qdrant Implementation
│   │   ├── openai_embedding.py         # OpenAI Embedding
│   │   └── local_embedding.py          # Local Embedding (fallback)
│   │
│   ├── llm/                            # v7.1 Existing
│   │   ├── litellm_adapter.py
│   │   ├── cached_llm_adapter.py
│   │   └── optimized_llm_adapter.py
│   │
│   ├── sandbox/                        # v7.1 Existing
│   │   ├── e2b_adapter.py
│   │   └── stub_sandbox.py
│   │
│   ├── guardrail/                      # v7.1 Existing
│   │   ├── guardrails_adapter.py
│   │   └── pydantic_validator.py
│   │
│   ├── vcs/                            # v7.1 Existing
│   │   └── gitpython_adapter.py
│   │
│   └── workflow/                       # v7.1 Existing
│       └── langgraph_adapter.py
│
├── 🎯 application/                     # ⭐ Application Layer (Use Cases)
│   ├── __init__.py
│   │
│   ├── use_cases/                      # v8.1 NEW: Use Cases
│   │   ├── __init__.py
│   │   ├── analyze_code_use_case.py    # System 1 Use Case
│   │   ├── reason_with_tot_use_case.py # System 2 Use Case
│   │   ├── learn_from_experience.py    # Experience Learning
│   │   └── recover_from_failure.py     # Fail-Safe Recovery
│   │
│   └── orchestrators/                  # Orchestration Layer
│       ├── __init__.py
│       ├── v7_orchestrator.py          # v7.1 System 1 (유지)
│       ├── v8_orchestrator.py          # v8.1 System 2 (신규)
│       ├── v8_hybrid_orchestrator.py   # v8.1 Hybrid (Router 통합)
│       └── parallel_orchestrator.py    # Multi-Agent (유지)
│
├── 📋 dto/                             # Data Transfer Objects
│   ├── __init__.py
│   ├── reasoning_dto.py                # v8.1 NEW
│   ├── experience_dto.py               # v8.1 NEW
│   ├── workflow_dto.py                 # v7.1 Existing
│   └── llm_dto.py                      # v7.1 Existing
│
├── 🧪 tests/                           # Domain Tests (Unit)
│   ├── domain/
│   │   ├── reasoning/
│   │   │   ├── test_router.py
│   │   │   ├── test_tot_scorer.py
│   │   │   └── test_reflection_judge.py
│   │   ├── experience/
│   │   │   ├── test_policies.py
│   │   │   └── test_matchers.py
│   │   └── safety/
│   │       └── test_fail_safe.py
│   │
│   ├── adapters/                       # Adapter Tests
│   │   ├── reasoning/
│   │   └── experience/
│   │
│   └── integration/                    # Integration Tests
│       ├── test_v8_e2e.py
│       └── test_hybrid_orchestrator.py
│
└── __init__.py
```

---

## 3. Layer별 상세 설계

### 3.1 Domain Layer (핵심 비즈니스 로직)

#### 3.1.1 Reasoning Domain

```python
# src/agent/domain/reasoning/models.py

from dataclasses import dataclass
from enum import Enum

class ReasoningPath(Enum):
    """추론 경로"""
    SYSTEM_1 = "fast"      # Linear, v7 Engine
    SYSTEM_2 = "slow"      # ReAct + ToT, v8 Engine

@dataclass
class QueryFeatures:
    """Query 분석 피처 (Domain Model)"""
    
    # Code Complexity
    file_count: int
    impact_nodes: int
    cyclomatic_complexity: float
    
    # Risk Factors
    has_test_failure: bool
    touches_security_sink: bool
    regression_risk: float
    
    # Historical Context
    similar_success_rate: float
    previous_attempts: int
    
    def calculate_complexity_score(self) -> float:
        """복잡도 점수 계산 (Domain Logic)"""
        return (
            self.file_count * 0.2 +
            self.impact_nodes / 100 * 0.3 +
            self.cyclomatic_complexity / 50 * 0.5
        )
    
    def calculate_risk_score(self) -> float:
        """위험도 점수 계산 (Domain Logic)"""
        score = self.regression_risk * 0.5
        
        if self.has_test_failure:
            score += 0.3
        
        if self.touches_security_sink:
            score += 0.2
        
        return min(score, 1.0)


@dataclass
class ReasoningDecision:
    """추론 결정 결과 (Domain Model)"""
    
    path: ReasoningPath
    confidence: float
    reasoning: str
    
    complexity_score: float
    risk_score: float
    
    estimated_cost: float
    estimated_time: float
```

```python
# src/agent/domain/reasoning/router.py

from typing import Protocol

class IComplexityAnalyzer(Protocol):
    """복잡도 분석 Port (Interface)"""
    def analyze(self, code: str) -> float: ...

class IRiskAssessor(Protocol):
    """위험도 평가 Port (Interface)"""
    def assess(self, query: Query) -> float: ...


class DynamicReasoningRouter:
    """
    Dynamic Reasoning Router (Domain Logic)
    
    순수 비즈니스 로직, 외부 의존성 없음
    """
    
    # Domain Constants
    COMPLEXITY_THRESHOLD = 0.3
    RISK_THRESHOLD = 0.4
    
    def __init__(
        self,
        complexity_analyzer: IComplexityAnalyzer,
        risk_assessor: IRiskAssessor
    ):
        """
        의존성은 Port(Interface)로만 주입
        """
        self._complexity_analyzer = complexity_analyzer
        self._risk_assessor = risk_assessor
    
    def decide(self, features: QueryFeatures) -> ReasoningDecision:
        """
        순수 Domain Logic
        - Framework 독립적
        - 테스트 가능
        - 비즈니스 규칙 명확
        """
        complexity = features.calculate_complexity_score()
        risk = features.calculate_risk_score()
        
        # Business Rule: Simple & Safe → Fast Path
        if complexity < self.COMPLEXITY_THRESHOLD and risk < self.RISK_THRESHOLD:
            return ReasoningDecision(
                path=ReasoningPath.SYSTEM_1,
                confidence=0.9,
                reasoning="Low complexity, low risk → Fast path",
                complexity_score=complexity,
                risk_score=risk,
                estimated_cost=0.01,  # $
                estimated_time=5.0    # seconds
            )
        
        # Business Rule: Complex or Risky → Slow Path
        return ReasoningDecision(
            path=ReasoningPath.SYSTEM_2,
            confidence=0.7,
            reasoning="High complexity or risk → Slow path with ToT",
            complexity_score=complexity,
            risk_score=risk,
            estimated_cost=0.15,
            estimated_time=45.0
        )
```

#### 3.1.2 Experience Domain

```python
# src/agent/domain/experience/models.py

@dataclass
class ExperienceV2:
    """Experience Domain Model"""
    
    # Identity
    experience_id: str
    created_at: datetime
    
    # Problem Space
    problem_description: str
    error_pattern: str
    problem_hash: str  # 중복 방지
    
    # Strategy Space
    strategy_description: str
    code_diff: str
    approach_type: str  # "refactor", "bugfix", etc.
    
    # Outcome
    success: bool
    outcome_score: float
    failure_reason: str | None
    
    # Graph Impact (Domain Data)
    cfg_delta: int
    dfg_impact_radius: int
    graph_stability: float
    
    # Metadata
    reflection_note: str
    times_referenced: int
    success_rate: float
    
    def is_trustworthy(self, trust_window_days: int = 30) -> bool:
        """신뢰도 판단 (Domain Logic)"""
        age = (datetime.now() - self.created_at).days
        
        return (
            age <= trust_window_days
            and self.success_rate > 0.6
            and self.times_referenced > 0
        )
    
    def calculate_relevance(self, query_hash: str) -> float:
        """관련성 계산 (Domain Logic)"""
        # 해시 유사도 기반
        # Vector 유사도는 Adapter에서 계산, Domain은 비즈니스 규칙만
        if self.problem_hash == query_hash:
            return 1.0
        
        return 0.0  # Simplified, actual logic in adapter
```

```python
# src/agent/domain/experience/policies.py

class ExperienceSavePolicy:
    """
    Experience 저장 정책 (Domain Logic)
    
    "무엇을 경험으로 남길 것인가"는 순수 비즈니스 규칙
    """
    
    MIN_EXECUTION_TIME = 5.0      # 5초 이상
    MIN_GRAPH_IMPACT = 3          # 3개 노드 이상
    
    def should_save(self, candidate: ExperienceCandidate) -> bool:
        """저장 여부 판단 (Domain Rule)"""
        
        # Rule 1: 너무 간단한 것은 저장 안 함
        if candidate.execution_time < self.MIN_EXECUTION_TIME:
            return False
        
        # Rule 2: 영향도가 없으면 저장 안 함
        if candidate.graph_impact < self.MIN_GRAPH_IMPACT:
            return False
        
        # Rule 3: 실패했지만 교훈이 있으면 저장
        if not candidate.success and candidate.has_valuable_lesson:
            return True
        
        # Rule 4: 성공한 것은 저장
        if candidate.success:
            return True
        
        return False
```

### 3.2 Ports Layer (Interfaces)

```python
# src/agent/ports/reasoning.py

from typing import Protocol

class IComplexityAnalyzer(Protocol):
    """복잡도 분석 Port"""
    
    def analyze_cyclomatic(self, code: str) -> float:
        """Cyclomatic Complexity 계산"""
        ...
    
    def analyze_cognitive(self, code: str) -> float:
        """Cognitive Complexity 계산"""
        ...
    
    def count_impact_nodes(self, file_path: str) -> int:
        """CFG 영향 노드 수"""
        ...


class IRiskAssessor(Protocol):
    """위험도 평가 Port"""
    
    def assess_regression_risk(self, query: Query) -> float:
        """Regression 위험도 평가"""
        ...
    
    def check_security_sink(self, code: str) -> bool:
        """보안 sink 접근 여부"""
        ...


class IGraphAnalyzer(Protocol):
    """그래프 분석 Port"""
    
    def calculate_stability(
        self,
        before: Graph,
        after: Graph
    ) -> float:
        """Graph 안정성 계산"""
        ...
    
    def calculate_impact_radius(self, changed_nodes: set[str]) -> int:
        """영향 반경 계산"""
        ...


class IToTExecutor(Protocol):
    """Tree-of-Thought 실행 Port"""
    
    async def generate_strategies(
        self,
        problem: str,
        count: int = 3
    ) -> list[CodeCandidate]:
        """LLM으로 전략 생성"""
        ...
    
    async def execute_strategy(
        self,
        strategy: CodeCandidate
    ) -> ExecutionResult:
        """Sandbox에서 전략 실행"""
        ...
```

```python
# src/agent/ports/experience.py

class IExperienceStore(Protocol):
    """Experience Store Port"""
    
    async def save(self, experience: ExperienceV2) -> None:
        """경험 저장"""
        ...
    
    async def retrieve_similar(
        self,
        problem_vector: list[float],
        top_k: int = 5
    ) -> list[ExperienceV2]:
        """유사 경험 검색"""
        ...
    
    async def update_success_rate(
        self,
        experience_id: str,
        success: bool
    ) -> None:
        """성공률 업데이트"""
        ...


class IEmbeddingModel(Protocol):
    """임베딩 모델 Port"""
    
    async def embed(self, text: str) -> list[float]:
        """텍스트 → 벡터"""
        ...
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """배치 임베딩"""
        ...
```

### 3.3 Adapters Layer (Infrastructure)

```python
# src/agent/adapters/reasoning/complexity_analyzer.py

from radon.complexity import cc_visit
from radon.metrics import mi_visit

class RadonComplexityAnalyzer:
    """
    Radon 기반 복잡도 분석 Adapter
    
    IComplexityAnalyzer Port 구현
    """
    
    def analyze_cyclomatic(self, code: str) -> float:
        """Radon으로 Cyclomatic Complexity 계산"""
        try:
            results = cc_visit(code)
            if not results:
                return 0.0
            
            # 평균 복잡도
            return sum(r.complexity for r in results) / len(results)
        
        except Exception:
            return 0.0
    
    def analyze_cognitive(self, code: str) -> float:
        """Cognitive Complexity (간접 계산)"""
        # Radon은 cognitive 미지원, MI로 대체
        try:
            mi = mi_visit(code, multi=True)
            # MI → Cognitive 변환 (간략화)
            return max(0, (100 - mi) / 10)
        except Exception:
            return 0.0
    
    def count_impact_nodes(self, file_path: str) -> int:
        """CFG 분석으로 영향 노드 수 계산"""
        # Code Foundation의 CFG 재사용
        from src.contexts.code_foundation.infrastructure.graph import CFGBuilder
        
        cfg = CFGBuilder().build(file_path)
        return len(cfg.nodes)
```

```python
# src/agent/adapters/experience/qdrant_store.py

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct

class QdrantExperienceStore:
    """
    Qdrant 기반 Experience Store Adapter
    
    IExperienceStore Port 구현
    """
    
    COLLECTION = "experiences_v2"
    
    def __init__(
        self,
        qdrant_client: AsyncQdrantClient,
        embedding_model: IEmbeddingModel
    ):
        self.qdrant = qdrant_client
        self.embedding = embedding_model
    
    async def save(self, experience: ExperienceV2) -> None:
        """Qdrant에 저장"""
        # 임베딩 생성 (Adapter 책임)
        problem_vec = await self.embedding.embed(
            experience.problem_description
        )
        
        # Qdrant 저장
        await self.qdrant.upsert(
            collection_name=self.COLLECTION,
            points=[
                PointStruct(
                    id=experience.experience_id,
                    vector=problem_vec,
                    payload=asdict(experience)
                )
            ]
        )
    
    async def retrieve_similar(
        self,
        problem_vector: list[float],
        top_k: int = 5
    ) -> list[ExperienceV2]:
        """유사 경험 검색"""
        results = await self.qdrant.search(
            collection_name=self.COLLECTION,
            query_vector=problem_vector,
            limit=top_k,
            score_threshold=0.7
        )
        
        return [
            ExperienceV2(**r.payload)
            for r in results
        ]
```

### 3.4 Application Layer (Use Cases)

```python
# src/agent/application/use_cases/reason_with_tot_use_case.py

class ReasonWithToTUseCase:
    """
    System 2 Reasoning Use Case
    
    Application Layer:
    - Domain 조합
    - Port 조율
    - Transaction 관리
    """
    
    def __init__(
        self,
        router: DynamicReasoningRouter,           # Domain
        tot_scorer: TreeOfThoughtScorer,          # Domain
        reflection_judge: SelfReflectionJudge,    # Domain
        tot_executor: IToTExecutor,               # Port
        experience_store: IExperienceStore,       # Port
    ):
        self.router = router
        self.tot_scorer = tot_scorer
        self.reflection_judge = reflection_judge
        self.tot_executor = tot_executor
        self.experience_store = experience_store
    
    async def execute(self, query: Query) -> Result:
        """
        System 2 Reasoning 전체 플로우
        """
        # 1. Feature Extraction
        features = await self._extract_features(query)
        
        # 2. Routing Decision (Domain)
        decision = self.router.decide(features)
        
        if decision.path != ReasoningPath.SYSTEM_2:
            raise ValueError("This use case is for System 2 only")
        
        # 3. Generate Strategies (ToT)
        candidates = await self.tot_executor.generate_strategies(
            query.description,
            count=3
        )
        
        # 4. Execute & Score (Domain + Adapter)
        results = []
        for candidate in candidates:
            exec_result = await self.tot_executor.execute_strategy(candidate)
            score = self.tot_scorer.score(exec_result)
            results.append((exec_result, score))
        
        # 5. Select Best
        results.sort(key=lambda x: x[1], reverse=True)
        best_candidate, best_score = results[0]
        
        # 6. Self-Reflection (Domain)
        reflection = await self.reflection_judge.evaluate(
            ReflectionInput(
                original_problem=query.description,
                strategy=best_candidate,
                ...
            )
        )
        
        # 7. Apply or Retry
        if reflection.verdict == 'ACCEPT':
            await self._apply(best_candidate)
            await self._save_experience(query, best_candidate, success=True)
            return Result(success=True, ...)
        
        elif reflection.verdict == 'RETRY':
            # Retry with alternative strategy
            return await self._retry(query, results[1:])
        
        else:  # ROLLBACK
            return Result(success=False, reason=reflection.reasoning)
```

---

## 4. Dependency Injection (Container)

```python
# src/container.py 업데이트

class Container:
    """v8.1 Container with Hexagonal DI"""
    
    # ======================================================================
    # Domain Layer (Pure Business Logic)
    # ======================================================================
    
    @cached_property
    def v8_reasoning_router(self) -> DynamicReasoningRouter:
        """Dynamic Reasoning Router (Domain)"""
        from src.agent.domain.reasoning.router import DynamicReasoningRouter
        
        return DynamicReasoningRouter(
            complexity_analyzer=self.complexity_analyzer,  # Port → Adapter
            risk_assessor=self.risk_assessor,              # Port → Adapter
        )
    
    @cached_property
    def v8_tot_scorer(self) -> TreeOfThoughtScorer:
        """Tree-of-Thought Scorer (Domain)"""
        from src.agent.domain.reasoning.tot_scorer import TreeOfThoughtScorer
        
        return TreeOfThoughtScorer()  # No dependencies (Pure Logic)
    
    @cached_property
    def v8_reflection_judge(self) -> SelfReflectionJudge:
        """Self-Reflection Judge (Domain)"""
        from src.agent.domain.reasoning.reflection_judge import SelfReflectionJudge
        
        return SelfReflectionJudge(
            graph_analyzer=self.graph_analyzer,  # Port → Adapter
            risk_model=self.risk_model,          # Port → Adapter
        )
    
    # ======================================================================
    # Adapters Layer (Infrastructure)
    # ======================================================================
    
    @cached_property
    def complexity_analyzer(self) -> IComplexityAnalyzer:
        """Complexity Analyzer Adapter"""
        from src.agent.adapters.reasoning.complexity_analyzer import (
            RadonComplexityAnalyzer
        )
        
        return RadonComplexityAnalyzer()
    
    @cached_property
    def risk_assessor(self) -> IRiskAssessor:
        """Risk Assessor Adapter"""
        from src.agent.adapters.reasoning.risk_assessor import (
            HistoricalRiskAssessor
        )
        
        return HistoricalRiskAssessor(
            experience_store=self.experience_store_v2
        )
    
    @cached_property
    def experience_store_v2(self) -> IExperienceStore:
        """Experience Store v2 Adapter"""
        from src.agent.adapters.experience.qdrant_store import (
            QdrantExperienceStore
        )
        
        return QdrantExperienceStore(
            qdrant_client=self.qdrant_async,
            embedding_model=self.embedding_model
        )
    
    # ======================================================================
    # Application Layer (Use Cases)
    # ======================================================================
    
    @cached_property
    def reason_with_tot_use_case(self) -> ReasonWithToTUseCase:
        """System 2 Reasoning Use Case"""
        from src.agent.application.use_cases.reason_with_tot_use_case import (
            ReasonWithToTUseCase
        )
        
        return ReasonWithToTUseCase(
            router=self.v8_reasoning_router,
            tot_scorer=self.v8_tot_scorer,
            reflection_judge=self.v8_reflection_judge,
            tot_executor=self.tot_executor,
            experience_store=self.experience_store_v2,
        )
```

---

## 5. Testing Strategy (Hexagonal)

### 5.1 Domain Tests (Pure Unit Tests)

```python
# tests/domain/reasoning/test_router.py

def test_router_simple_query_goes_to_system_1():
    """Domain Logic 테스트 (Mock 없이)"""
    
    # Fake Adapters
    class FakeComplexityAnalyzer:
        def analyze(self, code): return 0.1
    
    class FakeRiskAssessor:
        def assess(self, query): return 0.2
    
    # Domain Object
    router = DynamicReasoningRouter(
        complexity_analyzer=FakeComplexityAnalyzer(),
        risk_assessor=FakeRiskAssessor()
    )
    
    # Test Pure Logic
    features = QueryFeatures(
        file_count=1,
        impact_nodes=5,
        cyclomatic_complexity=2.0,
        ...
    )
    
    decision = router.decide(features)
    
    assert decision.path == ReasoningPath.SYSTEM_1
    assert decision.confidence > 0.8
```

### 5.2 Adapter Tests

```python
# tests/adapters/reasoning/test_complexity_analyzer.py

async def test_radon_complexity_analyzer():
    """Adapter 테스트 (실제 Radon 사용)"""
    
    analyzer = RadonComplexityAnalyzer()
    
    code = """
def simple():
    return 42
"""
    
    complexity = analyzer.analyze_cyclomatic(code)
    
    assert complexity < 5.0  # Simple function
```

### 5.3 Integration Tests

```python
# tests/integration/test_v8_e2e.py

async def test_system_2_reasoning_e2e():
    """E2E 테스트 (Container 사용)"""
    
    container = Container()
    use_case = container.reason_with_tot_use_case
    
    query = Query(
        description="Refactor calculateDiscount to support multiple tiers",
        ...
    )
    
    result = await use_case.execute(query)
    
    assert result.success
    assert result.reasoning_path == ReasoningPath.SYSTEM_2
```

---

## 6. Migration Path (v7 → v8)

### Phase 0: 구조 준비 (Week 0)

```bash
# 디렉토리 생성
mkdir -p src/agent/domain/reasoning
mkdir -p src/agent/domain/experience
mkdir -p src/agent/domain/safety
mkdir -p src/agent/ports
mkdir -p src/agent/adapters/reasoning
mkdir -p src/agent/adapters/experience
mkdir -p src/agent/application/use_cases
```

### Phase 1: Domain 구현 (Week 1-2)

```
1. src/agent/domain/reasoning/models.py
2. src/agent/domain/reasoning/router.py
3. src/agent/ports/reasoning.py
4. tests/domain/reasoning/test_router.py
```

### Phase 2: Adapters 구현 (Week 3-4)

```
1. src/agent/adapters/reasoning/complexity_analyzer.py
2. src/agent/adapters/reasoning/risk_assessor.py
3. src/container.py (DI 등록)
4. tests/adapters/reasoning/
```

### Phase 3: Use Cases 구현 (Week 5-6)

```
1. src/agent/application/use_cases/reason_with_tot_use_case.py
2. src/agent/application/orchestrators/v8_hybrid_orchestrator.py
3. tests/integration/test_v8_e2e.py
```

---

## 7. Benefits of This Structure

### 7.1 Testability

```
Domain Layer: 100% Pure Unit Tests (No Mocks)
Adapters: Integration Tests (Real Dependencies)
Application: E2E Tests (Full Stack)
```

### 7.2 Maintainability

```
변경 격리:
- LLM API 변경 → Adapters만 수정
- 비즈니스 규칙 변경 → Domain만 수정
- Orchestration 변경 → Application만 수정
```

### 7.3 Extensibility

```
새로운 Adapter 추가:
- Domain/Ports는 그대로
- Adapter만 추가
- Container에서 교체
```

---

## 8. Success Criteria

- [ ] Domain Layer에 외부 의존성 0개
- [ ] Port Interface 커버리지 100%
- [ ] Domain 단위 테스트 100% (Mock 없이)
- [ ] Adapter 통합 테스트 90%+
- [ ] Cyclic Dependency 0개

---

## 9. Conclusion

이 패키지 구조는:

1. **Hexagonal 원칙 준수**: Domain 중심, Ports/Adapters 분리
2. **SOTA 수준**: DDD + Clean Architecture + Hexagonal
3. **v7.1 호환**: 기존 구조 유지하며 확장
4. **테스트 가능**: Layer별 독립 테스트
5. **유지보수성**: 변경 격리, 확장 용이

**다음 단계**: Phase 0부터 점진적 구현
