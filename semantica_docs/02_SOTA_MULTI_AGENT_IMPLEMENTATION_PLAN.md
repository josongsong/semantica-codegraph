# SOTA Multi-Agent Code Editing Pipeline - 풀 구현 계획

Version: v1.0  
Date: 2024-11-29  
Status: ✅ **구현 완료** (2025-11-29)  
Implementation: 모든 Phase (0-3) 완료  

---

## ⚠️ 이 문서는 아카이브되었습니다

**구현 완료 일자**: 2025-11-29  
**최신 문서**: `_recap/05_AGENT.md` 참고  

아래 내용은 초기 계획 문서이며, 실제 구현 상태는 다음을 확인하세요:
- **Agent 시스템**: `_recap/05_AGENT.md`
- **구현 위치**: `src/contexts/agent_automation/infrastructure/` (모든 하위 디렉토리)
- **Index Version**: `src/contexts/multi_index/infrastructure/version/`
- **마이그레이션**: `migrations/021_*.sql`, `migrations/022_*.sql`

---

## 1. 현재 상태 분석

### 1.1 이미 구현된 것 (80% Ready)

| 컴포넌트 | 상태 | 위치 |
|----------|------|------|
| FSM (23개 모드) | ✅ 완료 | `src/contexts/agent_automation/infrastructure/fsm.py` |
| Mode Handlers | ✅ 완료 | `src/contexts/agent_automation/infrastructure/modes/` |
| Tool System (14개) | ✅ 완료 | `src/contexts/agent_automation/infrastructure/tools/` |
| Patch Tools | ✅ 완료 | `src/contexts/agent_automation/infrastructure/tools/patch_tools.py` |
| Conflict Resolver | ✅ 완료 | `src/contexts/agent_automation/infrastructure/tools/conflict_resolver.py` |
| Indexing Pipeline | ✅ 완료 | `src/contexts/indexing_pipeline/infrastructure/orchestrator.py` |
| Index Metadata Store | ✅ 완료 | `src/infra/metadata/indexing_metadata_store.py` |
| Memory System | ✅ 완료 | `src/contexts/session_memory/infrastructure/` |
| Retriever | ✅ 완료 | `src/contexts/retrieval_search/infrastructure/` |

### 1.2 ADR 문서 (설계 완료)

| ADR | 제목 | 상태 |
|-----|------|------|
| ADR-001 | Parallel Multi-Agent Orchestrator | Proposed |
| ADR-002 | Patch Conflict Resolver | Proposed |
| ADR-003 | LSP/Formatter/Hook Coordinator | Proposed |
| ADR-004 | Branch/Workspace Manager | Proposed |
| ADR-005 | Test Runner Cache | Proposed |
| ADR-006 | Agent-Index Version Sync | Proposed |

### 1.3 현재 Gap

1. **PatchQueue 없음** - 패치가 직접 적용됨, staging/approval 없음
2. **ApplyGateway 없음** - 충돌 해결 + 포맷 + 린트 + 롤백 통합 없음
3. **Workspace 격리 없음** - git worktree 미활용
4. **병렬 실행 없음** - FSM은 순차 실행만 지원
5. **Index 버전 동기화 없음** - stale index 사용 가능

---

## 2. 최종 합의된 우선순위

### RFC 논의 결과

```
1. Index Version Sync (최소 버전) ← P1 (기반)
2. Patch Queue + Conflict Resolver
3. Apply Gateway v1 + Rollback
4. Workspace Manager
5. Test Runner (pytest-testmon)
6. Multi-Agent Orchestrator (LangGraph)
7. Automatic Context Builder
8. Prompt Caching
9. Rate Limiting, Human-in-the-loop
```

---

## 3. PoC 범위 (Phase 0)

**목표**: 핵심 설계 원칙 4개를 한 번에 검증

```
✅ Diff-Only Agent
✅ Single Writer (Apply Gateway)
✅ Incremental Test (pytest-testmon)
✅ Index Version Stamping
```

### PoC 범위

| 기능 | 포함 | 비고 |
|------|------|------|
| Index Version Stamping | ✅ | 메타데이터 + 에이전트 요청 stamp |
| Patch Queue | ✅ | FIFO + base version 추적 |
| Apply Gateway v1 | ✅ | 파일 단위 apply + rollback |
| pytest-testmon 연동 | ✅ | 변경 테스트만 실행 |
| LangGraph | ❌ | Phase 1에서 추가 |
| Workspace Manager | ❌ | Phase 1에서 추가 |

---

## 4. 전체 구현 계획

### Phase 0: PoC (2일)

#### P0-1: Index Version Sync (0.5일)

**파일 생성/수정:**
```
src/contexts/multi_index/infrastructure/version/
├── __init__.py
├── store.py          # IndexVersionStore
├── checker.py        # IndexVersionChecker
└── middleware.py     # VersionCheckMiddleware

migrations/
└── 021_index_versions.up.sql
```

**작업 내용:**
1. DB 마이그레이션 스크립트 작성
2. `IndexVersionStore` 구현
3. `IndexVersionChecker` 구현 (staleness 정책)
4. `src/contexts/indexing_pipeline/infrastructure/orchestrator.py` 수정 - 버전 생성/완료
5. 에이전트 요청에 version_id stamp

#### P0-2: Patch Queue (0.5일)

**파일 생성/수정:**
```
src/contexts/agent_automation/infrastructure/queue/
├── __init__.py
├── patch_queue.py    # PatchQueue (FIFO)
├── models.py         # QueuedPatch
└── store.py          # PostgresPatchStore

migrations/
└── 022_patch_proposals.up.sql
```

**작업 내용:**
1. `QueuedPatch` 모델 정의 (base_version, index_version 포함)
2. `PatchQueue` FIFO 구현
3. `PostgresPatchStore` 영속화
4. `ProposePatchTool` 수정 - queue에 추가

#### P0-3: Apply Gateway v1 (0.5일)

**파일 생성/수정:**
```
src/contexts/agent_automation/infrastructure/apply_gateway/
├── __init__.py
├── gateway.py        # ApplyGateway
├── rollback.py       # RollbackManager
└── formatter.py      # FormatterChain
```

**작업 내용:**
1. `ApplyGateway` 구현
   - queue에서 patch 가져오기
   - `PatchConflictResolver`로 충돌 해결
   - 파일 적용 + 백업
   - 실패 시 rollback
2. `FormatterChain` 구현 (ruff format)
3. `RollbackManager` 구현 (patch 단위 all-or-nothing)

#### P0-4: pytest-testmon 연동 (0.5일)

**파일 생성/수정:**
```
src/contexts/agent_automation/infrastructure/test_runner/
├── __init__.py
├── testmon_runner.py # TestmonRunner
└── impact.py         # TestImpactAnalyzer
```

**작업 내용:**
1. `pytest-testmon` 의존성 추가
2. `TestmonRunner` 구현
3. `TestImpactAnalyzer` 구현 (변경 파일 → 영향 테스트)
4. `ApplyGateway`에 테스트 실행 연동

---

### Phase 1: 인프라 강화 (3일)

#### P1-1: Workspace Manager (1일)

**파일 생성/수정:**
```
src/contexts/agent_automation/infrastructure/workspace/
├── __init__.py
├── manager.py        # WorkspaceManager
├── worktree.py       # GitWorktreeAdapter
└── session.py        # WorkspaceSession
```

**작업 내용:**
1. `GitWorktreeAdapter` 구현 (git worktree add/remove)
2. `WorkspaceSession` 구현 (세션별 격리된 workspace)
3. `WorkspaceManager` 구현
   - workspace 풀 관리
   - 자동 정리 (TTL)
4. `ApplyGateway`와 통합

#### P1-2: LSP/Formatter/Hook Coordinator (1일)

**파일 생성/수정:**
```
src/contexts/agent_automation/infrastructure/apply_gateway/
├── lsp_client.py     # LSPClient (Pyright)
├── pre_commit.py     # PreCommitRunner
└── coordinator.py    # FormatLintCoordinator
```

**작업 내용:**
1. `LSPClient` 구현 (Pyright 진단)
2. `PreCommitRunner` 구현 (pre-commit run)
3. `FormatLintCoordinator` 구현
   - ruff format → ruff check --fix → pre-commit
4. `ApplyGateway` 파이프라인 확장

#### P1-3: Index Version Sync 강화 (0.5일)

**작업 내용:**
1. staleness 정책 세분화
2. auto_reindex 옵션 구현
3. 메트릭 추가 (index_staleness_seconds)
4. 알림 (Redis Pub/Sub 옵션)

#### P1-4: Human-in-the-loop (0.5일)

**파일 생성/수정:**
```
src/contexts/agent_automation/infrastructure/approval/
├── __init__.py
├── policy.py         # ApprovalPolicy
└── ui.py             # ApprovalUI (CLI)
```

**작업 내용:**
1. `ApprovalPolicy` 구현
   - 위험도 기반 자동/수동 분류
   - high-risk 변경은 사람 승인 필요
2. `ApprovalUI` 구현 (CLI diff 표시)
3. `ApplyGateway`에 승인 체크 추가

---

### Phase 2: Multi-Agent (3일)

#### P2-1: LangGraph 기반 구조 (1일)

**파일 생성/수정:**
```
src/contexts/agent_automation/infrastructure/orchestrator_v2/
├── __init__.py
├── graph.py          # ParallelOrchestrator
├── state.py          # AgentState
├── nodes.py          # 노드 정의
└── adapter.py        # FSM → LangGraph 어댑터
```

**작업 내용:**
1. `langgraph` 의존성 추가
2. `AgentState` TypedDict 정의
3. FSM Mode → LangGraph 노드 어댑터
4. 기본 StateGraph 구성

#### P2-2: Planner 노드 (0.5일)

**작업 내용:**
1. 태스크 분해 로직 (LLM 기반)
2. 서브태스크 병렬 가능 여부 판단
3. 의존성 그래프 생성

#### P2-3: 병렬 실행 (0.5일)

**작업 내용:**
1. 병렬 브랜치 설정
2. 파일 접근 Lock (asyncio.Lock)
3. 에이전트별 workspace 할당

#### P2-4: Merger 노드 (0.5일)

**작업 내용:**
1. 병렬 결과 병합 로직
2. 충돌 감지 및 해결
3. 최종 패치 생성

#### P2-5: Rate Limiting (0.5일)

**파일 생성/수정:**
```
src/contexts/agent_automation/infrastructure/rate_limit/
├── __init__.py
├── limiter.py        # RateLimiter
└── config.py         # ProviderQuota
```

**작업 내용:**
1. `RateLimiter` 구현 (asyncio.Semaphore)
2. provider별 quota 설정
3. LangGraph 노드에 적용

---

### Phase 3: Context & Caching (2일)

#### P3-1: Automatic Context Builder (1일)

**파일 생성/수정:**
```
src/contexts/agent_automation/infrastructure/context/
├── __init__.py
├── builder.py        # AutoContextBuilder
├── sources.py        # ContextSources
└── ranker.py         # ContextRanker
```

**작업 내용:**
1. CodeGraph 기반 관련 파일 추출
2. 테스트 파일 자동 포함
3. 문서/스펙 파일 연결
4. URL 스크래핑 (선택적)
5. 컨텍스트 크기 조절 (토큰 제한)

#### P3-2: Prompt Caching (1일)

**파일 생성/수정:**
```
src/contexts/agent_automation/infrastructure/cache/
├── __init__.py
├── prompt_cache.py   # PromptCache
├── hasher.py         # PromptHasher
└── store.py          # RedisCacheStore
```

**작업 내용:**
1. 프롬프트 해싱 로직
2. Redis 기반 캐시 저장소
3. Anthropic/OpenAI 캐시 hit 최적화
4. TTL 관리

---

## 5. 파일 구조 (최종)

```
src/contexts/agent_automation/infrastructure/
├── fsm.py                    # 기존 FSM (유지)
├── types.py
├── schemas.py
├── modes/                    # 기존 23개 모드 (유지)
├── tools/
│   ├── patch_tools.py        # 기존 (수정)
│   ├── conflict_resolver.py  # 기존 (유지)
│   └── ...
├── queue/                    # NEW: Patch Queue
│   ├── __init__.py
│   ├── patch_queue.py
│   ├── models.py
│   └── store.py
├── apply_gateway/            # NEW: Apply Gateway
│   ├── __init__.py
│   ├── gateway.py
│   ├── rollback.py
│   ├── formatter.py
│   ├── lsp_client.py
│   ├── pre_commit.py
│   └── coordinator.py
├── workspace/                # NEW: Workspace Manager
│   ├── __init__.py
│   ├── manager.py
│   ├── worktree.py
│   └── session.py
├── test_runner/              # NEW: Test Runner
│   ├── __init__.py
│   ├── testmon_runner.py
│   └── impact.py
├── approval/                 # NEW: Approval System
│   ├── __init__.py
│   ├── policy.py
│   └── ui.py
├── orchestrator_v2/          # NEW: LangGraph Orchestrator
│   ├── __init__.py
│   ├── graph.py
│   ├── state.py
│   ├── nodes.py
│   └── adapter.py
├── context/                  # NEW: Context Builder
│   ├── __init__.py
│   ├── builder.py
│   ├── sources.py
│   └── ranker.py
├── cache/                    # NEW: Prompt Cache
│   ├── __init__.py
│   ├── prompt_cache.py
│   ├── hasher.py
│   └── store.py
└── rate_limit/               # NEW: Rate Limiter
    ├── __init__.py
    ├── limiter.py
    └── config.py

src/contexts/multi_index/infrastructure/version/            # NEW: Index Version
├── __init__.py
├── store.py
├── checker.py
└── middleware.py
```

---

## 6. 의존성 추가

```toml
# pyproject.toml
[project.dependencies]
# Phase 0
diff-match-patch = ">=20230430"
pytest-testmon = ">=2.1.0"

# Phase 1
# (기존 의존성으로 충분)

# Phase 2
langgraph = ">=0.2.0"

# Phase 3
# (기존 redis 사용)
```

---

## 7. DB 마이그레이션

```sql
-- migrations/021_index_versions.up.sql
CREATE TABLE IF NOT EXISTS index_versions (
    repo_id VARCHAR(255) NOT NULL,
    version_id BIGINT NOT NULL,
    git_commit VARCHAR(40) NOT NULL,
    indexed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    file_count INT DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'indexing',
    duration_ms FLOAT DEFAULT 0,
    error_message TEXT,
    PRIMARY KEY (repo_id, version_id)
);

CREATE INDEX idx_versions_repo ON index_versions(repo_id);
CREATE INDEX idx_versions_commit ON index_versions(repo_id, git_commit);

-- migrations/022_patch_proposals.up.sql
CREATE TABLE IF NOT EXISTS patch_proposals (
    patch_id UUID PRIMARY KEY,
    repo_id VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    base_content TEXT,
    base_version_id BIGINT,
    index_version_id BIGINT,
    new_code TEXT NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    applied_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (repo_id, base_version_id) REFERENCES index_versions(repo_id, version_id)
);

CREATE INDEX idx_patches_repo ON patch_proposals(repo_id);
CREATE INDEX idx_patches_status ON patch_proposals(status);
```

---

## 8. 테스트 계획

### Phase 0 테스트

```python
# tests/agent/test_patch_queue.py
def test_patch_queue_fifo():
    """패치가 FIFO 순서로 처리되는지 확인."""

def test_patch_version_stamp():
    """패치에 index_version이 포함되는지 확인."""

# tests/agent/test_apply_gateway.py
def test_apply_success():
    """정상 패치 적용."""

def test_apply_conflict_detection():
    """충돌 감지 및 마커 삽입."""

def test_apply_rollback():
    """실패 시 롤백."""

# tests/agent/test_testmon_runner.py
def test_affected_tests_only():
    """변경 파일에 영향받는 테스트만 실행."""
```

### Phase 1 테스트

```python
# tests/agent/test_workspace_manager.py
def test_worktree_creation():
    """git worktree 생성."""

def test_workspace_isolation():
    """세션별 격리."""

# tests/agent/test_format_lint.py
def test_format_chain():
    """ruff format → pre-commit 체인."""
```

### Phase 2 테스트

```python
# tests/agent/test_parallel_orchestrator.py
def test_parallel_execution():
    """병렬 노드 실행."""

def test_rate_limiting():
    """동시성 제한."""
```

---

## 9. 마일스톤

| Phase | 기간 | 목표 | 검증 기준 |
|-------|------|------|-----------|
| P0 | 2일 | PoC 완료 | 단일 에이전트 + Patch Queue + Apply Gateway + testmon |
| P1 | 3일 | 인프라 강화 | Workspace 격리 + LSP/Format + Human-in-the-loop |
| P2 | 3일 | Multi-Agent | LangGraph 병렬 실행 + Rate Limiting |
| P3 | 2일 | Context & Cache | Auto Context + Prompt Cache |
| **Total** | **10일** | **SOTA 완성** | 모든 6대 기준 충족 |

---

## 10. 리스크 & 완화

| 리스크 | 영향 | 완화 방안 |
|--------|------|-----------|
| LangGraph 버전 변경 | 높음 | 버전 고정 + 정기 업데이트 |
| pytest-testmon 정확도 | 중간 | fallback으로 전체 테스트 |
| 대용량 파일 성능 | 중간 | chunk 단위 처리 |
| Git worktree 제한 | 낮음 | 풀 크기 제한 + TTL |

---

## 11. 성공 기준 (6대 SOTA 기준)

| 기준 | 검증 방법 |
|------|-----------|
| Consistency | 병렬 에이전트 10개 동시 실행 테스트 |
| Deterministic Indexing | 동일 커밋 → 동일 index_version |
| Diff-Only Agents | 에이전트 코드에 직접 파일 쓰기 없음 |
| Automatic Context | 관련 파일 recall@5 > 80% |
| Safe Auto-Apply | rollback 테스트 통과율 100% |
| Cost Efficiency | prompt cache hit rate > 70% |

---

## 12. 다음 단계

1. **Phase 0 시작**: Index Version Sync 구현
2. **ADR 상태 업데이트**: Proposed → Accepted
3. **의존성 추가**: diff-match-patch, pytest-testmon
4. **마이그레이션 실행**: 021, 022

---

*이 문서는 RFC 논의 결과를 바탕으로 작성되었습니다.*
