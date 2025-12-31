# MCP SOTA Protocol

LLM을 위한 SOTA급 MCP(Model Context Protocol) 도구 아키텍처.

## 개요

```
┌─────────────────────────────────────────────────────┐
│                    LLM Agent                        │
└────────────────────────┬────────────────────────────┘
                         │ MCP
┌────────────────────────▼────────────────────────────┐
│              MCP Tool Categories                    │
├─────────────┬─────────────┬─────────────┬───────────┤
│   Job       │  Context    │  Preview    │  Verify   │
│   (Async)   │  (Unified)  │  (Fast)     │  (Loop)   │
└─────────────┴─────────────┴─────────────┴───────────┘
```

## 도구 목록 (15개 + 5 Prompts + 4 Resources)

### Job Tools (비동기)

| Tool | 설명 | Latency |
|------|------|---------|
| `job_submit` | Heavy 분석 Job 제출 | < |
| `job_status` | Job 상태 조회 | < |
| `job_result` | Job 결과 조회 | < |
| `job_cancel` | Job 취소 | < |

### Context Tools (통합 조회)

| Tool | 설명 | Latency |
|------|------|---------|
| `get_context` | 통합 컨텍스트 (definition, callers, tests, docstring) | <2s |
| `get_definition` | 심볼 정의 조회 | < |
| `get_references` | 참조 조회 (paginated) | <1s |

### Preview Tools (빠른 미리보기)

| Tool | 설명 | Latency |
|------|------|---------|
| `preview_taint_path` | Taint 경로 존재 여부 | <2s |
| `preview_impact` | 변경 영향도 간략 조회 | <2s |
| `preview_callers` | 호출자 빠른 미리보기 | <1s |

### Verify Tools (검증 루프)

| Tool | 설명 | Latency |
|------|------|---------|
| `verify_patch_compile` | 패치 컴파일/타입체크 | <5s |
| `verify_finding_resolved` | 취약점 해결 확인 | <10s |
| `verify_no_new_findings_introduced` | Regression Proof | <30s |

### Graph Semantics Tools (RFC-SEM-022)

| Tool | 설명 | Latency |
|------|------|---------|
| `graph_slice` | Semantic Slicing (Root Cause 추출) | <5s |
| `graph_dataflow` | Dataflow 증명 (source→sink) | <10s |

## 핵심 설계 원칙

### 1. Graceful Degradation

```python
# 외부 DB 없이도 동작
builder = CallGraphQueryBuilder()  # No args
result = await builder.search_callers(...)  # Returns [] if no backend
```

**Fallback Chain:**
1. UnifiedGraphIndex (in-memory) - Primary
2. Memgraph driver - Legacy fallback
3. Empty result + warning - Graceful degradation

### 2. Pagination (Context Window 관리)

```python
class PagedResponse(BaseModel):
    items: list[T]
    next_cursor: str | None
    has_more: bool
    summary: ResultSummary | None

class PaginationParams(BaseModel):
    limit: int = 10  # 1-100
    cursor: str | None = None
    summarize: bool = True
```

### 3. Unified Context

```python
await get_context({
    "target": "function_name",
    "facets": ["definition", "callers", "tests", "docstring"],
    "max_chars": 8000
})
```

### 4. Verification Loop

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│ Analyze │────▶│ Suggest │────▶│ Verify  │────▶│ Confirm │
└─────────┘     └─────────┘     └─────────┘     └─────────┘
                                    │               │
                                    └───── Retry ───┘
```

## MCP Resources (RFC-SEM-022)

실시간 스트리밍 리소스.

| URI | 설명 | MimeType |
|-----|------|----------|
| `semantica://jobs/{job_id}/events` | Job 이벤트 SSE 스트림 | text/event-stream |
| `semantica://jobs/{job_id}/log` | Job 로그 스트림 | text/plain |
| `semantica://jobs/{job_id}/artifacts` | Job 결과물 | application/json |
| `semantica://executions/{execution_id}/findings` | Execution findings | application/json |

## MCP Prompts (RFC-SEM-022)

LLM Agent 자기비판 및 추론 가이드.

| Prompt | Arguments | 목적 |
|--------|-----------|------|
| `verify_evidence_logical_gap` | evidence_summary, claimed_conclusion | 논리적 비약 점검 |
| `suggest_additional_analysis` | current_findings, context | 추가 분석 제안 |
| `critique_patch` | patch_diff, original_finding | Patch 자기비판 |
| `plan_verification_strategy` | patch_type, impact_scope | 검증 전략 수립 |
| `interpret_dataflow_result` | dataflow_result, policy | Dataflow 해석 |

## 아키텍처

### 의존성 구조

```
server/mcp_server/handlers/
├── job_tools.py        ─── In-memory store (Production: Redis)
├── context_tools.py    ─── ContextAdapter, CallGraphQueryBuilder
├── preview_tools.py    ─── ReasoningPipeline, CallGraphQueryBuilder
└── verify_tools.py     ─── subprocess (pyright, ruff)
```

### CallGraphQueryBuilder

```python
class CallGraphQueryBuilder:
    def __init__(self, graph_store: Any = None):  # Optional!
        self.graph_store = graph_store
        self._graph_index = None  # Lazy init from DI container

    async def search_callers(...) -> list[dict]:
        # Strategy 1: UnifiedGraphIndex
        # Strategy 2: Memgraph (legacy)
        # Strategy 3: Empty result (graceful)
```

## API 서버 통합

### Routes (55개)

```
FastAPI app: OK
Routes count: 55
```

### Graph API Endpoints

| Endpoint | 설명 |
|----------|------|
| `GET /graph/callers` | 호출자 조회 |
| `GET /graph/callees` | 피호출자 조회 |
| `GET /graph/references` | 참조 조회 |
| `GET /graph/imports` | Import 조회 |

## 파일 구조

```
server/
├── api_server/
│   ├── main.py                     # FastAPI 앱
│   └── routes/
│       ├── graph.py                # Graph API (CallGraphQueryBuilder)
│       ├── graph_semantics.py      # RFC-SEM-022: slice, dataflow
│       ├── workspace.py            # RFC-SEM-022: Workspace CRUD
│       ├── search.py               # 검색 API
│       ├── indexing.py             # 인덱싱 API
│       └── rfc/
│           ├── jobs.py             # Job API
│           └── sessions.py         # Session API
│
└── mcp_server/
    ├── main.py                     # MCP 서버
    └── handlers/
        ├── __init__.py             # 도구 export
        ├── job_tools.py            # 비동기 Job (4개)
        ├── context_tools.py        # 통합 컨텍스트 (3개)
        ├── preview_tools.py        # 미리보기 (3개)
        ├── verify_tools.py         # 검증 (3개)
        └── graph_semantics_tools.py # RFC-SEM-022: slice, dataflow

src/contexts/
├── shared_kernel/
│   ├── contracts/
│   │   ├── pagination.py           # PagedResponse, PaginationParams
│   │   ├── verification.py         # VerificationSnapshot, Workspace, PatchSet
│   │   └── errors.py               # SemanticaError (Global Error Schema)
│   │
│   └── infrastructure/
│       └── execution_repository.py # SQLite/In-Memory Execution 저장소
│
└── multi_index/infrastructure/symbol/
    └── call_graph_query.py         # CallGraphQueryBuilder (Memgraph 제거)
```

## 사용 예시

### 1. Taint 분석 (비동기 Job)

```python
# Submit
job_id = await job_submit({
    "job_type": "taint_analysis",
    "target": "user_input_handler",
    "policy": "sql_injection"
})

# Poll
while True:
    status = await job_status({"job_id": job_id})
    if status["state"] == "completed":
        break
    await asyncio.sleep(1)

# Get result
result = await job_result({"job_id": job_id})
```

### 2. 컨텍스트 조회

```python
context = await get_context({
    "target": "process_payment",
    "facets": ["definition", "callers", "callees", "tests"],
    "max_chars": 10000
})
```

### 3. 검증 루프

```python
# 1. 패치 검증
ok = await verify_patch_compile({
    "file_path": "src/handler.py",
    "patch": "...",
    "check_types": True
})

# 2. 취약점 해결 확인
resolved = await verify_finding_resolved({
    "finding_id": "CWE-89-001",
    "file_path": "src/handler.py"
})
```

## 변경 이력

### Phase 1-7 완료

| Phase | 내용 | 상태 |
|-------|------|------|
| 1 | 표준화 (ResultEnvelope, Pagination) | ✅ |
| 2 | 도구 분류 (Fast/Standard/Heavy) | ✅ |
| 3 | 비동기 Job 패턴 | ✅ |
| 4 | Preview/Verify 도구 | ✅ |
| 5 | Memgraph 의존성 제거 | ✅ |
| 6 | API 서버 수정 (import 경로) | ✅ |
| 7 | RFC-SEM-022 구현 (100%) | ✅ |

### Phase 7: RFC-SEM-022 상세 (100% Complete)

| 구현 | 파일 | 설명 | Tests |
|------|------|------|-------|
| VerificationSnapshot | `contracts/verification.py` | 결정적 실행 스냅샷 | 5 |
| Workspace/PatchSet/Finding | `contracts/verification.py` | 리소스 모델 | 13 |
| Global Error Schema | `contracts/errors.py` | 표준 에러 형식 | 20 |
| ExecutionRepository | `infrastructure/execution_repository.py` | SQLite 저장소 | 20 |
| **Snapshot Factory** | `infrastructure/snapshot_factory.py` | 자동 생성 | 3 |
| **Tracing Middleware** | `middleware/tracing.py` | trace_id 전파 | 2 |
| graph.slice API | `routes/graph_semantics.py` | Semantic Slicing | 7 |
| graph.dataflow API | `routes/graph_semantics.py` | Dataflow 증명 | 6 |
| Workspace API | `routes/workspace.py` | CRUD + Branch + DI | 14 |
| Regression Proof | `verify_tools.py` | compare_findings | 4 |
| **MCP Resources** | `server/mcp_server/main.py` | 4 URIs | - |
| **MCP Prompts** | `server/mcp_server/prompts.py` | 5 prompts | - |
| **E2E Tests** | `tests/integration/test_rfc_sem_022_e2e.py` | 통합 테스트 | 8 |

**Total: 110 tests passed (1.36s)**

### 수정된 파일

| 파일 | 변경 내용 |
|------|----------|
| `call_graph_query.py` | UnifiedGraphIndex 우선, graceful fallback |
| `routes/graph.py` | KuzuSymbolIndex → CallGraphQueryBuilder |
| `routes/search.py` | src.index → src.contexts.multi_index |
| `routes/indexing.py` | 경로 수정 |
| `routes/rfc/jobs.py` | Field → Query (GET params) |
| `routes/rfc/sessions.py` | Field → Query (GET params) |
| `main.py` | infra.config → src.infra.config |
