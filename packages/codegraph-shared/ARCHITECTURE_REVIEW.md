# codegraph-shared 아키텍처 리뷰

**Date:** 2025-12-29
**Reviewer:** Automated Architecture Analysis
**Package:** codegraph-shared (기반 레이어)
**Version:** v2.1.0+

---

## Executive Summary

### 종합 점수: **6.2/10** ⚠️

| Category | Score | Status |
|----------|-------|--------|
| **아키텍처 준수** | 4/10 | ❌ Critical 이슈 |
| **SOLID 원칙** | 5/10 | ⚠️ 주요 위반 |
| **코드 품질** | 8/10 | ✅ 양호 |
| **Type Safety** | 7.9/10 | ✅ 양호 |
| **의존성 관리** | 3/10 | ❌ 순환 의존성 |

### Critical 이슈 (P0)

1. 🔴 **순환 의존성**: `codegraph-shared` → `apps.orchestrator` (2개 파일)
2. 🔴 **Container Bloat**: 1,532 LOC God object
3. 🔴 **Hexagonal 미준수**: Domain/Application layer 없음

### 주요 강점 ✅

1. ✅ Rust (codegraph-ir) 의존성 없음 - Clean boundary
2. ✅ Protocol-based ports (56 protocols)
3. ✅ Type hints 78.7% coverage
4. ✅ Kernel module (domain contracts)

---

## Part 1: 패키지 현황

### 1.1 통계

| Metric | Value |
|--------|-------|
| **파일 수** | 107 Python files |
| **LOC** | 9,421 (패키지 4위) |
| **평균 LOC/파일** | 88 |
| **God classes (>500 LOC)** | 0개 ✅ |
| **Large files (300-500 LOC)** | 3개 ⚠️ |
| **Type hints coverage** | 78.7% (901/1145 functions) |

### 1.2 디렉토리 구조

```
codegraph-shared/
├── common/                      # 공통 유틸리티 (11 files, ~1,100 LOC)
│   ├── exceptions.py           # 도메인 예외
│   ├── factory.py              # Factory 패턴
│   ├── logging_config.py       # 로깅 설정
│   ├── ports.py                # 공통 포트
│   └── types.py                # 공통 타입
├── config.py                    # 글로벌 설정 (73 LOC)
├── container.py                 # ❌ DI Container (1,532 LOC - BLOATED!)
├── ports.py                     # ⚠️ 포트 정의 (313 LOC)
├── infra/                       # 인프라 구현 (74 files, ~6,900 LOC)
│   ├── cache/                  # Redis, 3-tier cache
│   ├── config/                 # 설정 관리
│   ├── db/                     # SQL schema
│   ├── git/                    # Git CLI wrapper
│   ├── graph/                  # Memgraph adapter
│   ├── jobs/                   # Job handlers (L1-L8)
│   │   └── handlers/           # ⚠️ `import codegraph_ir` (2 files)
│   ├── llm/                    # LLM 어댑터 (OpenAI, LiteLLM)
│   ├── metadata/               # 인덱싱 메타데이터
│   ├── observability/          # Metrics, tracing, cost tracking
│   ├── search/                 # 검색 인프라
│   ├── storage/                # PostgreSQL, SQLite
│   └── vector/                 # Qdrant
└── kernel/                      # ✅ 도메인 커널 (21 files, ~1,400 LOC)
    ├── contracts/              # 도메인 계약 (14 files)
    │   ├── claim.py
    │   ├── evidence.py
    │   ├── specs.py
    │   └── verification.py
    ├── infrastructure/         # 리포지토리 (3 files)
    ├── pdg/                    # PDG 프로토콜
    └── slice/                  # Slicing 프로토콜
```

---

## Part 2: Critical 아키텍처 위반

### 2.1 순환 의존성 🔴

**문제:** `codegraph-shared` (기반 레이어) → `apps.orchestrator` (응용 레이어)

**위반 파일 (2개):**

#### 1. `container.py` (Lines 39, 490-1194)

```python
# Line 39
from apps.api.shared.ports import OrchestratorService

# Lines 490-1194 (700+ LOC!)
from apps.orchestrator.orchestrator.agent.cascade import CascadeOrchestrator
from apps.orchestrator.orchestrator.agent.lats import LATSOrchestrator
from apps.orchestrator.orchestrator.agent.tot import ToTOrchestrator
from apps.orchestrator.orchestrator.domain.models import AgentExecutionRequest
from apps.orchestrator.orchestrator.infrastructure.llm_adapters import LiteLLMProviderAdapter
# ... 20+ more imports
```

**Impact:**
- ❌ 기반 레이어가 상위 레이어에 의존
- ❌ `codegraph-shared` 단독 사용 불가능
- ❌ 레이어 아키텍처 위반

#### 2. `ports.py` (Lines 15, 25)

```python
# Line 15
from apps.api.shared.ports import *

# Line 25
from apps.orchestrator.orchestrator.domain.models import (
    AgentMode,
    AgentExecutionRequest,
    AgentExecutionResult,
)
```

**Impact:**
- ❌ 포트 정의가 응용 모델에 의존
- ❌ Shared ports가 app-specific

---

### 2.2 Container Bloat (God Object) 🔴

**파일:** `container.py` (1,532 LOC)

**책임 혼재 (SRP 위반):**

| Responsibility | LOC | Layer | 위치 적정성 |
|----------------|-----|-------|------------|
| 1. 인프라 와이어링 (DB, Redis, Qdrant) | ~300 | Infrastructure | ✅ Shared OK |
| 2. 도메인 서비스 (Indexing, Search) | ~200 | Domain | ⚠️ Shared OK (기반 서비스) |
| 3. **Agent 오케스트레이션 (v7, v8, v9)** | ~700 | Application | ❌ **apps/로 이동 필요** |
| 4. **Use Cases (CASCADE, LATS, ToT)** | ~200 | Application | ❌ **apps/로 이동 필요** |
| 5. Health checks, metrics | ~132 | Infra | ✅ Shared OK |

**문제:**
```python
# Lines 490-1194: Agent containers (700+ LOC)
@cached_property
def cascade_orchestrator(self) -> CascadeOrchestrator:
    """❌ Application layer logic in shared!"""
    return CascadeOrchestrator(...)

@cached_property
def lats_orchestrator(self) -> LATSOrchestrator:
    """❌ Application layer logic in shared!"""
    return LATSOrchestrator(...)

# ... 20+ more agent-related factories
```

**권장 구조:**
```
codegraph-shared/
└── container.py (InfraContainer) - ~400 LOC
    - DB, Redis, Qdrant
    - Basic services (indexing, search)

apps/orchestrator/
└── di.py (AgentContainer) - ~700 LOC
    - CASCADE, LATS, ToT orchestrators
    - Agent-specific factories
```

---

### 2.3 Hexagonal Architecture 미준수 🔴

**현재 구조:**
```
codegraph-shared/
├── common/       # ❓ 유틸리티 (어디에도 속하지 않음)
├── infra/        # ❌ 구현 디테일 (Hexagonal의 Infrastructure Adapters)
├── kernel/       # ✅ Domain (계약, 프로토콜)
└── ports.py      # ✅ Ports (인터페이스)
```

**문제점:**
- ❌ **Domain layer 없음**: 도메인 로직이 `infra/`에 섞임
- ❌ **Application layer 없음**: Use cases가 `container.py`에 산재
- ⚠️ `ports.py`는 단일 파일 (313 LOC) - 분리 필요
- ⚠️ `infra/`는 구현이지 추상화 아님

**Hexagonal Architecture (이상적):**

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                        │
│  (Use Cases, Application Services)                          │
│  - IndexingService, SearchService                           │
└────────────────────┬────────────────────────────────────────┘
                     │ uses
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                     Domain Layer                             │
│  (Entities, Value Objects, Domain Services)                  │
│  - kernel/contracts/ (current ✅)                            │
│  - NEW: domain/ (entities, value objects)                    │
└────────────────────┬────────────────────────────────────────┘
                     │ depends on (DIP)
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                      Ports Layer                             │
│  (Interfaces/Protocols)                                      │
│  - ports.py (current - 313 LOC single file ⚠️)              │
│  - NEW: ports/ package (split by concern)                    │
│    - storage.py, llm.py, vector.py, graph.py                │
└────────────────────┬────────────────────────────────────────┘
                     │ implemented by
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Infrastructure Layer                        │
│  (Adapters, External Dependencies)                           │
│  - infra/ → infrastructure/adapters/                         │
│    - storage/ (PostgreSQL, SQLite)                           │
│    - llm/ (OpenAI, LiteLLM)                                  │
│    - vector/ (Qdrant)                                        │
└─────────────────────────────────────────────────────────────┘
```

**권장 리팩토링:**

```
codegraph-shared/
├── domain/                      # NEW: Domain layer
│   ├── entities/               # 도메인 엔티티
│   ├── value_objects/          # 값 객체
│   └── services/               # 도메인 서비스
├── application/                 # NEW: Application layer
│   ├── use_cases/              # Use cases
│   └── services/               # Application services
├── ports/                       # RENAME from ports.py
│   ├── __init__.py
│   ├── storage.py              # Storage port (Repository interfaces)
│   ├── llm.py                  # LLM port
│   ├── vector.py               # Vector store port
│   ├── graph.py                # Graph database port
│   └── cache.py                # Cache port
├── infrastructure/              # RENAME from infra/
│   └── adapters/               # Concrete implementations
│       ├── storage/            # PostgreSQL, SQLite adapters
│       ├── llm/                # OpenAI, LiteLLM adapters
│       ├── vector/             # Qdrant adapter
│       ├── graph/              # Memgraph adapter
│       └── cache/              # Redis adapter
└── container.py                 # DI Container (infra only)
```

---

## Part 3: SOLID 원칙 준수도

### 3.1 Single Responsibility Principle (SRP)

**위반 사항:**

| File | LOC | Responsibilities | Status |
|------|-----|------------------|--------|
| **container.py** | 1,532 | 5개 (infra, domain, app, agent, health) | ❌ Violated |
| ports.py | 313 | 56 protocols (너무 많음) | ⚠️ Should split |
| cost_tracking.py | 324 | Cost tracking + reporting | ✅ OK |

**container.py 책임 분리:**

```python
# 현재 (1,532 LOC - God object)
class Container:
    # Infrastructure (OK)
    postgres: PostgresAdapter
    redis: RedisCache
    qdrant: QdrantVector

    # Domain services (OK in shared)
    indexing_service: IndexingService
    search_service: SearchService

    # ❌ Application layer (should be in apps/)
    cascade_orchestrator: CascadeOrchestrator
    lats_orchestrator: LATSOrchestrator
    tot_orchestrator: ToTOrchestrator

    # ❌ Agent factories (should be in apps/orchestrator)
    create_agent_v7()
    create_agent_v8()
    create_agent_v9()
```

**권장 분리:**

```python
# codegraph-shared/container.py (~400 LOC)
class InfraContainer:
    """Infrastructure와 기반 서비스만"""
    postgres: PostgresAdapter
    redis: RedisCache
    qdrant: QdrantVector
    indexing_service: IndexingService
    search_service: SearchService

# apps/orchestrator/di.py (~700 LOC)
class AgentContainer:
    """Agent 오케스트레이션"""
    cascade_orchestrator: CascadeOrchestrator
    lats_orchestrator: LATSOrchestrator

    def create_agent_v7(self): ...
    def create_agent_v8(self): ...
```

---

### 3.2 Open/Closed Principle (OCP)

**위반 사항:**

**infra/di.py** (Lines 62-86, 131-158)

```python
def get_graph_store(config: Settings):
    """❌ Hardcoded laptop/server mode - cannot extend without modifying"""
    if config.use_laptop_mode:
        return InMemoryGraphStore()
    else:
        return MemgraphStore(config.memgraph_url)
```

**문제:**
- 새로운 그래프 스토어 추가 시 수정 필요
- Factory pattern 미사용

**권장 개선:**

```python
# ports/graph.py
class GraphStoreFactory(Protocol):
    def create(self, config: Settings) -> GraphStore: ...

# infrastructure/adapters/graph/factory.py
class ConfigBasedGraphStoreFactory:
    """OCP 준수 - 새 스토어 추가 시 수정 불필요"""
    _strategies = {
        "memgraph": MemgraphStore,
        "inmemory": InMemoryGraphStore,
        "neo4j": Neo4jStore,  # 확장 가능
    }

    def create(self, config: Settings) -> GraphStore:
        strategy = config.graph_store_type  # "memgraph", "inmemory", ...
        store_class = self._strategies[strategy]
        return store_class(config)
```

---

### 3.3 Liskov Substitution Principle (LSP)

**준수 상태:** ✅ **양호**

- Protocol-based ports 56개 정의
- 구현체 간 치환 가능 (PostgreSQL ↔ SQLite)

---

### 3.4 Interface Segregation Principle (ISP)

**준수 상태:** ⚠️ **보통**

**문제:**

**ports.py** (313 LOC, 56 protocols)

일부 인터페이스가 너무 큼:

```python
class SearchService(Protocol):
    """❌ Too many methods (12+) - clients forced to depend on unused methods"""
    def lexical_search(...): ...
    def semantic_search(...): ...
    def graph_search(...): ...
    def hybrid_search(...): ...
    def rrf_fusion(...): ...
    def search_symbols(...): ...
    # ... 12+ methods
```

**권장 분리:**

```python
# ports/search.py
class LexicalSearchPort(Protocol):
    def search(...): ...

class SemanticSearchPort(Protocol):
    def search(...): ...

class GraphSearchPort(Protocol):
    def search(...): ...

class HybridSearchPort(Protocol):
    """Composite of above"""
    lexical: LexicalSearchPort
    semantic: SemanticSearchPort
    graph: GraphSearchPort
    def rrf_fusion(...): ...
```

---

### 3.5 Dependency Inversion Principle (DIP)

**준수 상태:** ⚠️ **부분 준수**

**Good ✅:**
- `ports.py` defines 56 protocols
- `kernel/contracts/` provides abstractions

**Bad ❌:**
- `container.py` imports concrete `apps.*` modules directly
- No abstraction between shared and apps

**Example violation:**

```python
# container.py Line 500
from apps.orchestrator.orchestrator.infrastructure.llm_adapters import LiteLLMProviderAdapter

@cached_property
def litellm_provider(self) -> LiteLLMProviderAdapter:
    """❌ Depends on concrete class, should depend on ILLMProvider protocol"""
    return LiteLLMProviderAdapter(...)
```

**권장:**

```python
# ports/llm.py
class LLMProvider(Protocol):
    def generate(...): ...
    def stream(...): ...

# container.py
@cached_property
def llm_provider(self) -> LLMProvider:
    """✅ Depends on abstraction"""
    return self._create_llm_provider()  # Factory method
```

---

## Part 4: 코드 품질

### 4.1 Type Hints Coverage

**전체:** 78.7% (901/1145 functions)

**파일별 커버리지:**

| File | Coverage | Status |
|------|----------|--------|
| container.py | 85% | ✅ Good |
| ports.py | 100% | ✅ Excellent |
| kernel/contracts/*.py | 95%+ | ✅ Excellent |
| infra/jobs/handlers/*.py | 60% | ⚠️ Needs improvement |
| infra/observability/*.py | 80% | ✅ Good |

**권장:**
- Pyright strict mode 활성화
- 목표: 90%+ coverage

---

### 4.2 Large Files (300-500 LOC)

| File | LOC | Reason | Action |
|------|-----|--------|--------|
| container.py | 482 (실제 1,532) | God object | ❌ Split into 3 containers |
| infra/observability/cost_tracking.py | 324 | Cost tracking + reporting | ✅ OK (단일 책임) |
| ports.py | 313 | 56 protocols | ⚠️ Split into ports/ package |

---

### 4.3 코드 중복

**측정 필요:**
```bash
# Run code duplication analysis
pylint --disable=all --enable=duplicate-code packages/codegraph-shared/
```

**예상 중복:**
- `infra/jobs/handlers/*.py` - Handler 패턴 중복 가능성
- `infra/storage/*.py` - Repository 패턴 중복

---

## Part 5: 의존성 분석

### 5.1 External Dependencies (pyproject.toml)

**Python 패키지:**
- ✅ No `codegraph-ir` dependency (clean!)
- ✅ No `codegraph-parsers` dependency
- ⚠️ Imports `codegraph_ir` at runtime (2 files - acceptable for jobs)

**Runtime imports:**

| File | Import | Purpose | Status |
|------|--------|---------|--------|
| infra/jobs/handlers/ir_handler.py | `import codegraph_ir` | L1 IR build (Rust) | ✅ OK (runtime DI) |
| infra/jobs/handlers/cross_file_handler.py | `import codegraph_ir.codegraph_ir` | L3 cross-file | ✅ OK (runtime DI) |

**분석:**
- ✅ Import는 `try/except`로 감싸져 있음 (optional dependency)
- ✅ pyproject.toml에 선언되지 않음 (runtime injection)
- ✅ Hexagonal 원칙 준수 (ports through DI)

---

### 5.2 Internal Dependencies (CRITICAL 🔴)

**문제 의존성:**

```
codegraph-shared/
├── container.py   →  apps.orchestrator.*  ❌ (20+ imports)
└── ports.py       →  apps.api.*           ❌ (2+ imports)
                   →  apps.orchestrator.*  ❌ (4+ imports)
```

**Impact:**
- Circular dependency: `codegraph-shared` ↔ `apps`
- Shared package cannot be used standalone
- Violates layered architecture

**의존성 그래프 (현재):**

```
apps/ (Application Layer)
  ↓ depends on
codegraph-shared/ (Foundation Layer)
  ↓ ❌ WRONG: depends on
apps/ (Application Layer)  ← CIRCULAR!
```

**의존성 그래프 (권장):**

```
apps/ (Application Layer)
  ↓ depends on
codegraph-shared/ (Foundation Layer)
  ✅ No upward dependencies
```

---

## Part 6: 개선 권장 사항

### Phase 1: Critical Fixes (Week 1, P0)

#### 1.1 순환 의존성 제거 🔴

**목표:** `codegraph-shared` → `apps` 의존 제거

**Step 1: container.py 분리**

```bash
# Move agent containers to apps/orchestrator
git mv packages/codegraph-shared/codegraph_shared/container.py \
       apps/orchestrator/di/agent_container.py (lines 490-1194)
```

**Step 2: container.py 리팩토링**

```python
# codegraph-shared/container.py (BEFORE: 1,532 LOC)
class Container:
    cascade_orchestrator: CascadeOrchestrator  # ❌ Remove
    lats_orchestrator: LATSOrchestrator        # ❌ Remove
    create_agent_v7()                          # ❌ Remove

# codegraph-shared/container.py (AFTER: ~400 LOC)
class InfraContainer:
    """Infrastructure와 기반 서비스만"""
    postgres: PostgresAdapter
    redis: RedisCache
    qdrant: QdrantVector
    indexing_service: IndexingService  # OK (foundation service)
```

**Step 3: ports.py 수정**

```python
# ports.py (BEFORE)
from apps.api.shared.ports import *                    # ❌ Remove
from apps.orchestrator.orchestrator.domain.models import *  # ❌ Remove

# ports.py (AFTER)
# No apps.* imports
# Define shared protocols only
```

**Expected Impact:**
- ✅ Zero circular dependencies
- ✅ `codegraph-shared` can be used standalone
- ✅ Clean layered architecture

---

#### 1.2 Container 분할 🔴

**목표:** 1,532 LOC God object → 3개 명확한 컨테이너

**구조:**

```
codegraph-shared/
└── container.py
    class InfraContainer:       # ~300 LOC
        """Infrastructure adapters"""
        - postgres, redis, qdrant
        - memgraph, vector stores

    class DomainContainer:       # ~200 LOC
        """Domain services"""
        - indexing_service
        - search_service
        - Shared domain services only

apps/orchestrator/
└── di.py
    class AgentContainer:        # ~700 LOC
        """Agent orchestration"""
        - cascade, lats, tot orchestrators
        - Agent factories (v7, v8, v9)
        - App-specific use cases
```

**Migration guide:**

```python
# Before (monolithic)
from codegraph_shared.container import Container
container = Container()
orchestrator = container.cascade_orchestrator  # ❌

# After (layered)
from codegraph_shared.container import InfraContainer, DomainContainer
from apps.orchestrator.di import AgentContainer

infra = InfraContainer()
domain = DomainContainer(infra)
agents = AgentContainer(domain)

orchestrator = agents.cascade_orchestrator  # ✅
```

---

### Phase 2: Hexagonal Refactoring (Week 2, P1)

#### 2.1 디렉토리 구조 재구성

**목표:** Hexagonal Architecture 준수

**Before:**
```
codegraph-shared/
├── common/
├── infra/
├── kernel/
└── ports.py
```

**After:**
```
codegraph-shared/
├── domain/                      # NEW: Domain layer
│   ├── entities/               # 도메인 엔티티
│   ├── value_objects/          # 값 객체
│   └── services/               # 도메인 서비스
├── application/                 # NEW: Application layer
│   ├── use_cases/              # Use cases
│   └── services/               # Application services (위임)
├── ports/                       # RENAME from ports.py
│   ├── __init__.py
│   ├── storage.py              # 56 protocols → split by concern
│   ├── llm.py
│   ├── vector.py
│   ├── graph.py
│   └── cache.py
├── infrastructure/              # RENAME from infra/
│   └── adapters/               # Concrete implementations
│       ├── storage/            # PostgreSQL, SQLite
│       ├── llm/                # OpenAI, LiteLLM
│       ├── vector/             # Qdrant
│       ├── graph/              # Memgraph
│       └── cache/              # Redis
├── kernel/                      # KEEP: Domain contracts
└── container.py                 # Simplified DI
```

**Migration:**
```bash
# Step 1: Create new directories
mkdir -p codegraph-shared/codegraph_shared/{domain,application,ports}

# Step 2: Split ports.py
# Extract protocols by concern into ports/*.py

# Step 3: Rename infra → infrastructure/adapters
git mv codegraph-shared/codegraph_shared/infra \
       codegraph-shared/codegraph_shared/infrastructure/adapters

# Step 4: Move domain logic to domain/
# Extract domain entities from infra/ to domain/entities/
```

---

#### 2.2 ports.py 분할

**현재:** 313 LOC, 56 protocols in single file

**권장:**

```python
# ports/__init__.py
from .storage import StoragePort, RepositoryPort
from .llm import LLMPort, EmbeddingPort
from .vector import VectorStorePort
from .graph import GraphStorePort
from .cache import CachePort

# ports/storage.py (~60 LOC)
class StoragePort(Protocol):
    def save(...): ...
    def load(...): ...

class RepositoryPort(Protocol):
    def find_by_id(...): ...
    def save(...): ...

# ports/llm.py (~50 LOC)
class LLMPort(Protocol):
    def generate(...): ...
    def stream(...): ...

class EmbeddingPort(Protocol):
    def embed(...): ...

# ... 나머지 파일들도 동일하게 분리
```

---

### Phase 3: 코드 품질 개선 (Week 3, P2)

#### 3.1 Type Hints 강화

**목표:** 78.7% → 90%+

**Action items:**

```bash
# 1. Enable strict mode
# pyproject.toml
[tool.pyright]
strict = ["codegraph_shared/**/*.py"]
typeCheckingMode = "strict"

# 2. Fix missing type hints
# Focus on infra/jobs/handlers/*.py (currently 60%)

# 3. Run mypy
mypy --strict packages/codegraph-shared/
```

---

#### 3.2 Import Linting

**목표:** `apps.*` import 차단

```toml
# .import-linter.toml
[[contracts]]
name = "Shared must not depend on Apps"
type = "forbidden"
source_modules = ["codegraph_shared"]
forbidden_modules = ["apps"]
```

```bash
# Run linter
lint-imports
```

---

#### 3.3 God Class Elimination

**목표:** container.py 1,532 LOC → <400 LOC

See Phase 1.2 for details.

---

### Phase 4: 문서화 (Week 4, P3)

#### 4.1 아키텍처 문서

```markdown
# codegraph-shared/ARCHITECTURE.md

## Hexagonal Architecture

[Diagram of layers]

## Dependency Rules

1. Domain must not depend on Infrastructure
2. Ports define abstractions
3. Infrastructure implements Ports
4. No upward dependencies (no apps.* imports)
```

#### 4.2 Migration Guide

```markdown
# codegraph-shared/MIGRATION.md

## Migrating from v2.0 to v2.1

### Container Split
- Before: `Container.cascade_orchestrator`
- After: `AgentContainer.cascade_orchestrator` (in apps/)

### Ports Renaming
- Before: `from codegraph_shared.ports import SearchService`
- After: `from codegraph_shared.ports.search import SearchPort`
```

---

## Part 7: 측정 지표

### Before vs After (예상)

| Metric | Before | After (Phase 1) | After (Phase 2) | Target |
|--------|--------|-----------------|-----------------|--------|
| **순환 의존성** | 2 files | 0 ✅ | 0 ✅ | 0 |
| **Container LOC** | 1,532 | 400 ✅ | 400 ✅ | <500 |
| **God classes** | 1 (container) | 0 ✅ | 0 ✅ | 0 |
| **Hexagonal layers** | 1/4 (ports) | 2/4 | 4/4 ✅ | 4/4 |
| **Type coverage** | 78.7% | 78.7% | 90%+ ✅ | 90%+ |
| **Apps imports** | 26 imports | 0 ✅ | 0 ✅ | 0 |
| **ports.py LOC** | 313 (1 file) | 313 | 6 files (~50 each) ✅ | Split |

---

## Part 8: 우선순위별 실행 계획

### Week 1 (P0 - Critical)

**Day 1-2: 순환 의존성 제거**
- [ ] Extract agent containers from `container.py` → `apps/orchestrator/di.py`
- [ ] Remove `apps.*` imports from `ports.py`
- [ ] Add import linter to prevent regressions

**Day 3: Container 분할**
- [ ] Split `container.py` into `InfraContainer` + `DomainContainer`
- [ ] Move agent factories to `apps/orchestrator`
- [ ] Update all import paths

**Day 4-5: 테스트 및 검증**
- [ ] Run full test suite
- [ ] Verify zero circular dependencies
- [ ] Update documentation

---

### Week 2 (P1 - Important)

**Day 1-2: Hexagonal 디렉토리 구조**
- [ ] Create `domain/`, `application/`, `ports/` directories
- [ ] Split `ports.py` into `ports/*.py` by concern
- [ ] Rename `infra/` → `infrastructure/adapters/`

**Day 3-4: 도메인 로직 이동**
- [ ] Extract domain entities to `domain/entities/`
- [ ] Move use cases to `application/use_cases/`
- [ ] Update imports

**Day 5: 검증**
- [ ] Verify layer boundaries (import linter)
- [ ] Run tests
- [ ] Update ARCHITECTURE.md

---

### Week 3 (P2 - Nice to have)

**Day 1-2: Type Hints**
- [ ] Enable pyright strict mode
- [ ] Fix missing type hints (focus on infra/jobs/)
- [ ] Target: 90%+ coverage

**Day 3-4: 코드 품질**
- [ ] Run pylint for code duplication
- [ ] Refactor duplicated handler patterns
- [ ] Add pre-commit hooks (mypy, pylint)

**Day 5: 문서화**
- [ ] Write ARCHITECTURE.md
- [ ] Write MIGRATION.md
- [ ] Update README

---

## Part 9: 성공 지표

### 정량적 지표

- [ ] **순환 의존성**: 0개
- [ ] **Container LOC**: <400
- [ ] **God classes**: 0개
- [ ] **Hexagonal layers**: 4/4 (domain, application, ports, infrastructure)
- [ ] **Type coverage**: >90%
- [ ] **Apps imports**: 0개

### 정성적 지표

- [ ] `codegraph-shared` can be used standalone
- [ ] Clear separation of concerns (SRP)
- [ ] Testable architecture (DIP)
- [ ] Extensible without modification (OCP)
- [ ] Clean dependency direction (Hexagonal)

---

## Conclusion

### 현재 상태: 6.2/10 ⚠️

**Critical Issues:**
1. 🔴 Circular dependencies (shared → apps)
2. 🔴 Container bloat (1,532 LOC God object)
3. 🔴 Missing Hexagonal layers

**Strengths:**
1. ✅ No Rust dependency (clean boundary)
2. ✅ Protocol-based ports (56 protocols)
3. ✅ Type hints 78.7% coverage

### 개선 후 예상: 8.5/10 ✅

**After Phase 1+2:**
- ✅ Zero circular dependencies
- ✅ Clean layered architecture
- ✅ Hexagonal compliance
- ✅ SRP, DIP, OCP compliance

**Impact:**
- Standalone usability
- Better testability
- Easier maintenance
- Clearer boundaries

---

**Date:** 2025-12-29
**Status:** 리뷰 완료
**Next Steps:** Phase 1 실행 (순환 의존성 제거)
**Estimated Effort:** 3주 (P0: 1주, P1: 1주, P2: 1주)

