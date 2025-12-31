# codegraph-shared 리팩토링 계획

**Date:** 2025-12-29
**Priority:** P0 (Critical)
**Estimated Effort:** 1 week (Day 1-5)

---

## Executive Summary

### 목표

1. 🔴 **순환 의존성 제거**: `codegraph-shared` → `apps` 의존 제거
2. 🔴 **Container 분할**: 1,532 LOC God object → 3개 명확한 컨테이너
3. ✅ **Standalone 사용 가능**: `codegraph-shared` 패키지 독립 사용

### 현재 상태

| Metric | Current | Target |
|--------|---------|--------|
| **Container LOC** | 1,532 | <400 |
| **apps.* imports** | 67개 | 0개 |
| **순환 의존성** | 2 files | 0 files |
| **책임 혼재** | 5개 layer | 1개 layer (infra) |

### Expected Impact

- ✅ Zero circular dependencies
- ✅ Clean layered architecture
- ✅ Standalone `codegraph-shared` package
- ✅ Better testability (mock agents easily)
- ✅ Faster development (clear boundaries)

---

## Part 1: 현황 분석

### 1.1 container.py 구조 (1,532 LOC)

**책임 분석:**

| Lines | Responsibility | Layer | Belongs In |
|-------|----------------|-------|------------|
| 1-100 | Init, Sub-containers | Infrastructure | ✅ codegraph-shared |
| 101-300 | Infrastructure wiring (DB, Redis, Qdrant) | Infrastructure | ✅ codegraph-shared |
| 301-490 | Domain services (Indexing, Search, Memory) | Domain | ✅ codegraph-shared |
| **491-1194** | **Agent orchestration (v7, v8, v9)** | **Application** | ❌ **→ apps/orchestrator** |
| 1195-1532 | Health checks, Factories, Utils | Infrastructure | ✅ codegraph-shared |

**Agent 관련 코드 (Lines 491-1194, ~700 LOC):**

```python
# Lines 500-1194: Agent Container (67 apps.* imports)

@cached_property
def litellm_provider(self):
    from apps.orchestrator.orchestrator.adapters.llm.litellm_adapter import LiteLLMProviderAdapter
    return LiteLLMProviderAdapter(...)

@cached_property
def e2b_sandbox(self):
    from apps.orchestrator.orchestrator.adapters.sandbox.e2b_adapter import E2BSandboxAdapter
    return E2BSandboxAdapter(...)

@cached_property
def context_manager(self):
    from apps.orchestrator.orchestrator.context_manager import ContextManager
    return ContextManager(...)

# ... 20+ more agent-related factories
# Total: ~700 LOC, 67 apps.* imports
```

---

### 1.2 ports.py 구조 (313 LOC)

**apps.* imports (Lines 15, 25):**

```python
# Line 15
from apps.api.shared.ports import *  # ❌

# Line 25
from apps.orchestrator.orchestrator.domain.models import (
    AgentMode,
    AgentExecutionRequest,
    AgentExecutionResult,
)  # ❌
```

**Impact:**
- Shared ports depend on app-specific models
- Cannot use ports without apps/ package

---

## Part 2: 리팩토링 전략

### Strategy: Extract + Delegate

**Principle:** Move application layer code to application package

```
BEFORE:
codegraph-shared/container.py (1,532 LOC)
├── Infrastructure (✅ Keep)
├── Domain Services (✅ Keep)
└── Agent Orchestration (❌ Extract)

AFTER:
codegraph-shared/container.py (~400 LOC)
└── Infrastructure + Domain Services

apps/orchestrator/di.py (~700 LOC, NEW)
└── Agent Orchestration
```

---

## Part 3: 단계별 실행 계획

### Phase 1: Preparation (Day 1)

#### Step 1.1: Identify extraction boundaries

**Goal:** Mark exact lines to extract from `container.py`

```bash
# Analyze container.py structure
grep -n "@cached_property" packages/codegraph-shared/codegraph_shared/container.py > analysis.txt

# Identify agent-related methods
grep -n "from apps.orchestrator" packages/codegraph-shared/codegraph_shared/container.py
```

**Extraction boundaries:**
- Start: Line 491 (first `apps.orchestrator` import)
- End: Line 1194 (last agent-related factory)
- Total: ~700 LOC

#### Step 1.2: Create target directory

```bash
# Create apps/orchestrator/di/ if not exists
mkdir -p apps/orchestrator/di
touch apps/orchestrator/di/__init__.py
touch apps/orchestrator/di/agent_container.py
```

#### Step 1.3: Design AgentContainer interface

**File:** `apps/orchestrator/di/agent_container.py`

```python
"""
Agent Orchestration Container

Extracted from codegraph_shared.container (Lines 491-1194).
Depends on InfraContainer and DomainContainer from codegraph-shared.
"""

from functools import cached_property
from typing import TYPE_CHECKING

from codegraph_shared.container import InfraContainer, DomainContainer


class AgentContainer:
    """
    Agent orchestration container.

    Depends on:
    - InfraContainer (DB, Redis, Qdrant from codegraph-shared)
    - DomainContainer (Indexing, Search services from codegraph-shared)

    Provides:
    - Agent orchestrators (CASCADE, LATS, ToT)
    - LLM adapters (LiteLLM, OpenAI)
    - Sandbox adapters (E2B, Local)
    - Reasoning engines
    """

    def __init__(
        self,
        infra: InfraContainer,
        domain: DomainContainer,
    ):
        self.infra = infra
        self.domain = domain

    # Extract all agent-related @cached_property from container.py
    # Lines 491-1194 (~700 LOC)
    ...
```

---

### Phase 2: Extract Agent Container (Day 2)

#### Step 2.1: Copy agent code to AgentContainer

**Process:**

1. Copy Lines 491-1194 from `container.py`
2. Paste into `apps/orchestrator/di/agent_container.py`
3. Update references:
   - `self._infra` → `self.infra`
   - `self._foundation` → `self.domain.foundation`
   - `self._index` → `self.domain.index`

**Example:**

```python
# BEFORE (in codegraph-shared/container.py)
@cached_property
def litellm_provider(self):
    from apps.orchestrator.orchestrator.adapters.llm.litellm_adapter import LiteLLMProviderAdapter
    return LiteLLMProviderAdapter(
        settings=settings,
        logger=self._infra.logger,  # ← self._infra
    )

# AFTER (in apps/orchestrator/di/agent_container.py)
@cached_property
def litellm_provider(self):
    from apps.orchestrator.orchestrator.adapters.llm.litellm_adapter import LiteLLMProviderAdapter
    return LiteLLMProviderAdapter(
        settings=settings,
        logger=self.infra.logger,  # ← self.infra
    )
```

#### Step 2.2: Update Container to delegate

**File:** `codegraph-shared/container.py`

```python
# BEFORE (Lines 491-1194 = agent code)
class Container:
    @cached_property
    def litellm_provider(self):
        from apps.orchestrator... import ...
        return ...

# AFTER (delegation)
class Container:
    @cached_property
    def agents(self):
        """Lazy-load AgentContainer (depends on InfraContainer + DomainContainer)"""
        from apps.orchestrator.di import AgentContainer
        return AgentContainer(
            infra=self._infra,
            domain=self,  # self provides domain services
        )

    # Delegate agent access
    @property
    def litellm_provider(self):
        return self.agents.litellm_provider
```

**Benefits:**
- ✅ Zero `apps.*` imports in `container.py`
- ✅ Clear dependency direction (apps → shared, not shared → apps)
- ✅ Can still access via `container.litellm_provider` (backward compatible)

---

### Phase 3: Fix ports.py (Day 3)

#### Step 3.1: Remove apps.* imports

**File:** `codegraph-shared/ports.py`

```python
# BEFORE
from apps.api.shared.ports import *  # ❌ Line 15
from apps.orchestrator.orchestrator.domain.models import (
    AgentMode,
    AgentExecutionRequest,
    AgentExecutionResult,
)  # ❌ Line 25

# AFTER
# Remove above imports
# Define shared protocols only (no app-specific models)
```

#### Step 3.2: Move app-specific protocols to apps/

**If `ports.py` defines app-specific protocols:**

```python
# BEFORE (in codegraph-shared/ports.py)
class AgentOrchestrator(Protocol):
    """❌ App-specific protocol in shared!"""
    def execute(self, request: AgentExecutionRequest): ...

# AFTER (move to apps/orchestrator/ports.py)
# apps/orchestrator/ports.py
class AgentOrchestrator(Protocol):
    """✅ App-specific protocol in app!"""
    def execute(self, request: AgentExecutionRequest): ...
```

---

### Phase 4: Simplify Container (Day 4)

#### Step 4.1: Split Container into InfraContainer + DomainContainer

**Goal:** Make `Container` composition of sub-containers

**File:** `codegraph-shared/container.py`

```python
# AFTER
class InfraContainer:
    """Infrastructure adapters (DB, Redis, Qdrant, etc.)"""
    # Lines 101-300 (~200 LOC)
    # No apps.* imports

class DomainContainer:
    """Domain services (Indexing, Search, Memory, etc.)"""
    def __init__(self, infra: InfraContainer):
        self.infra = infra
    # Lines 301-490 (~200 LOC)
    # No apps.* imports

class Container:
    """Main container (composition)"""
    def __init__(self):
        self._infra = InfraContainer(settings)
        self._domain = DomainContainer(self._infra)

    @property
    def infra(self):
        return self._infra

    @property
    def domain(self):
        return self._domain

    @cached_property
    def agents(self):
        """Lazy-load AgentContainer (from apps/)"""
        from apps.orchestrator.di import AgentContainer
        return AgentContainer(
            infra=self._infra,
            domain=self._domain,
        )
```

**Final LOC:**
- `InfraContainer`: ~200 LOC
- `DomainContainer`: ~200 LOC
- `Container` (composition): ~100 LOC
- **Total: ~500 LOC** (down from 1,532!)

---

### Phase 5: Add Import Linter (Day 5)

#### Step 5.1: Configure import-linter

**File:** `.import-linter.toml` (create)

```toml
[[contracts]]
name = "Shared must not depend on Apps"
type = "forbidden"
source_modules = ["codegraph_shared"]
forbidden_modules = ["apps"]

[[contracts]]
name = "Shared must not depend on Engine"
type = "layers"
layers = [
    "codegraph_shared",
    "codegraph_engine | codegraph_search | codegraph_runtime",
    "apps",
]
```

#### Step 5.2: Run linter

```bash
# Install
pip install import-linter

# Run
lint-imports

# Expect: All contracts passed ✅
```

#### Step 5.3: Add pre-commit hook

**File:** `.pre-commit-config.yaml`

```yaml
- repo: local
  hooks:
    - id: import-linter
      name: Check import boundaries
      entry: lint-imports
      language: system
      pass_filenames: false
```

---

## Part 4: 테스트 전략

### 4.1 Unit Tests

**Test backward compatibility:**

```python
# tests/test_container_refactoring.py

def test_container_litellm_provider_backward_compatible():
    """Test that container.litellm_provider still works after delegation"""
    from codegraph_shared.container import Container

    container = Container()
    provider = container.litellm_provider

    assert provider is not None
    assert hasattr(provider, "generate")

def test_zero_apps_imports_in_shared():
    """Test that codegraph-shared has zero apps.* imports"""
    import ast
    from pathlib import Path

    shared_path = Path("packages/codegraph-shared/codegraph_shared")
    for py_file in shared_path.rglob("*.py"):
        with open(py_file) as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not node.module.startswith("apps."), f"Found apps.* import in {py_file}"
```

### 4.2 Integration Tests

```python
def test_agent_container_standalone():
    """Test AgentContainer can be created standalone"""
    from apps.orchestrator.di import AgentContainer
    from codegraph_shared.container import InfraContainer, DomainContainer

    infra = InfraContainer(settings)
    domain = DomainContainer(infra)
    agents = AgentContainer(infra, domain)

    assert agents.litellm_provider is not None
```

---

## Part 5: Migration Guide

### For Users of Container

**No changes needed!** Backward compatible.

```python
# Before (still works after refactoring)
from codegraph_shared.container import Container

container = Container()
provider = container.litellm_provider  # ✅ Still works (delegates to agents)
```

### For Advanced Users

**Can now use AgentContainer directly:**

```python
# After refactoring (new capability)
from apps.orchestrator.di import AgentContainer
from codegraph_shared.container import InfraContainer, DomainContainer

# Option 1: Use full Container (same as before)
container = Container()
agents = container.agents

# Option 2: Create AgentContainer directly (new!)
infra = InfraContainer(settings)
domain = DomainContainer(infra)
agents = AgentContainer(infra, domain)
```

---

## Part 6: Rollback Plan

### If Refactoring Fails

**Revert commits:**

```bash
# Revert Phase 2 (extract)
git revert <commit-sha-phase2>

# Revert Phase 3 (ports.py)
git revert <commit-sha-phase3>

# Restore original container.py
git checkout main -- packages/codegraph-shared/codegraph_shared/container.py
```

**Risk Mitigation:**
- ✅ Each phase is a separate commit
- ✅ Tests run after each phase
- ✅ Backward compatible (users don't change code)

---

## Part 7: Success Criteria

### Metrics (Before → After)

| Metric | Before | After | Status |
|--------|--------|-------|--------|
| **Container LOC** | 1,532 | ~500 | ✅ 67% reduction |
| **apps.* imports** | 67 | 0 | ✅ Zero |
| **Circular deps** | 2 files | 0 | ✅ Fixed |
| **Layers** | 5 mixed | 3 clear | ✅ Separated |
| **Testability** | Hard | Easy | ✅ Improved |

### Checklist

- [ ] `codegraph-shared` has 0 `apps.*` imports
- [ ] `AgentContainer` created in `apps/orchestrator/di/`
- [ ] `container.litellm_provider` still works (backward compatible)
- [ ] Import linter passes
- [ ] All tests pass
- [ ] Container LOC < 600

---

## Part 8: Timeline

### Week 1 (Day 1-5)

| Day | Phase | Tasks | Hours |
|-----|-------|-------|-------|
| **Day 1** | Preparation | Identify boundaries, Create target files | 4h |
| **Day 2** | Extract | Copy agent code, Create AgentContainer | 6h |
| **Day 3** | Fix ports.py | Remove apps.* imports | 3h |
| **Day 4** | Simplify | Split into Infra + Domain containers | 4h |
| **Day 5** | Verify | Tests, Import linter, Documentation | 3h |

**Total:** 20h (1 week)

---

## Part 9: 다음 단계 (After This Refactoring)

### Phase 2: Hexagonal Architecture (Week 2)

After fixing circular dependencies:

1. Create `domain/` directory
2. Create `application/` directory
3. Split `ports.py` → `ports/` package
4. Rename `infra/` → `infrastructure/adapters/`

See [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) Part 6 for details.

---

## Appendix: Code Snippets

### A. AgentContainer Template

**File:** `apps/orchestrator/di/agent_container.py`

```python
"""
Agent Orchestration Container

Extracted from codegraph_shared.container (Lines 491-1194).
Total: ~700 LOC, 67 agent-related factories.

Dependencies:
- InfraContainer (codegraph-shared)
- DomainContainer (codegraph-shared)

Provides:
- LLM adapters (LiteLLM, OpenAI)
- Sandbox adapters (E2B, Local)
- Agent orchestrators (CASCADE, LATS, ToT)
- Reasoning engines
- Experience stores
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph_shared.container import InfraContainer, DomainContainer


class AgentContainer:
    """Agent orchestration container (application layer)"""

    def __init__(
        self,
        infra: InfraContainer,
        domain: DomainContainer,
    ):
        """
        Initialize AgentContainer.

        Args:
            infra: Infrastructure container (DB, Redis, Qdrant)
            domain: Domain services (Indexing, Search, Memory)
        """
        self.infra = infra
        self.domain = domain

    # ═══════════════════════════════════════════════════════════
    # LLM Adapters
    # ═══════════════════════════════════════════════════════════

    @cached_property
    def litellm_provider(self):
        """LiteLLM provider adapter"""
        from apps.orchestrator.orchestrator.adapters.llm.litellm_adapter import LiteLLMProviderAdapter
        return LiteLLMProviderAdapter(
            settings=settings,
            logger=self.infra.logger,
        )

    # ═══════════════════════════════════════════════════════════
    # Sandbox Adapters
    # ═══════════════════════════════════════════════════════════

    @cached_property
    def e2b_sandbox(self):
        """E2B sandbox adapter"""
        from apps.orchestrator.orchestrator.adapters.sandbox.e2b_adapter import E2BSandboxAdapter
        return E2BSandboxAdapter(...)

    # ... Copy all 67 agent-related factories from container.py
    # Lines 491-1194 (~700 LOC)
```

---

**Date:** 2025-12-29
**Status:** 계획 수립 완료
**Next:** Phase 1 실행 (Day 1: Preparation)

