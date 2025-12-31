# Semantica v2 Tool Catalog

사람과 LLM Code Agent를 위한 도구 카탈로그.

---

## 1. 사람을 위한 도구셋 (Human-Facing)

### 1.1 REST API

#### Graph API - 코드 구조 탐색

| Endpoint | Method | 설명 | 요청 예시 |
|----------|--------|------|-----------|
| `/graph/callers` | GET | 함수 호출자 조회 | `?symbol_name=process_payment&limit=20` |
| `/graph/callees` | GET | 함수가 호출하는 대상 | `?symbol_name=validate_input&limit=20` |
| `/graph/references` | GET | 심볼 참조 위치 | `?symbol_name=UserModel&limit=50` |
| `/graph/imports` | GET | 모듈 import 위치 | `?module_name=auth.utils&limit=50` |

#### Graph Semantics API (RFC-SEM-022) - 의미론적 분석

| Endpoint | Method | 설명 | 요청 예시 |
|----------|--------|------|-----------|
| `/graph/slice` | POST/GET | Semantic Slicing (Root Cause) | `?anchor=func&direction=backward` |
| `/graph/dataflow` | POST/GET | Dataflow 증명 (source→sink) | `?source=input&sink=query` |

**응답 예시:**
```json
{
  "results": [
    {
      "node_id": "abc123",
      "name": "checkout_handler",
      "fqn": "app.handlers.checkout_handler",
      "file_path": "src/handlers/checkout.py",
      "line": 45,
      "kind": "Function"
    }
  ],
  "count": 1
}
```

#### Search API - 코드 검색

| Endpoint | Method | 설명 | 요청 예시 |
|----------|--------|------|-----------|
| `/search/search` | GET | 하이브리드 검색 | `?query=payment+validation&limit=20` |
| `/search/search/lexical` | GET | Zoekt 검색 | `?query=def+process&limit=20` |
| `/search/search/vector` | GET | 의미론적 검색 | `?query=사용자+인증+처리&limit=20` |
| `/search/search/symbol` | GET | 심볼 검색 | `?query=UserService&limit=20` |
| `/search/chunks` | GET | 청크 검색 | `?query=error+handling&limit=20` |

**응답 예시:**
```json
{
  "results": [
    {
      "chunk_id": "chunk_001",
      "file_path": "src/payment/validator.py",
      "content": "def validate_payment(amount, card):\n    ...",
      "score": 0.92,
      "source": "hybrid"
    }
  ],
  "total": 15,
  "query_time_ms": 120
}
```

#### Index API - 인덱싱 관리

| Endpoint | Method | 설명 | Body |
|----------|--------|------|------|
| `/index/repo` | POST | 전체 인덱싱 | `{"repo_id": "...", "repo_path": "..."}` |
| `/index/incremental` | POST | 증분 인덱싱 | `{"repo_id": "...", "changed_files": [...]}` |
| `/index/repo` | DELETE | 인덱스 삭제 | `{"repo_id": "..."}` |
| `/index/status/{repo_id}` | GET | 상태 조회 | - |

#### Analysis API (`/api/v1/`) - 분석 실행

| Endpoint | Method | 설명 |
|----------|--------|------|
| `/api/v1/executions/execute` | POST | 분석 Spec 실행 |
| `/api/v1/validations/validate` | POST | Spec 검증 |
| `/api/v1/plans/plan` | POST | 분석 계획 생성 |
| `/api/v1/explanations/explain` | POST | 결과 설명 생성 |

#### Workspace API (`/api/v1/workspaces`) - RFC-SEM-022

| Endpoint | Method | 설명 |
|----------|--------|------|
| `/api/v1/workspaces` | POST | Workspace 생성 |
| `/api/v1/workspaces/{id}` | GET | Workspace 조회 |
| `/api/v1/workspaces` | GET | Workspace 목록 |
| `/api/v1/workspaces/branch` | POST | Branch 생성 (A/B) |
| `/api/v1/workspaces/{id}` | DELETE | Workspace 삭제 |
| `/api/v1/jobs` | POST/GET | Job 관리 |
| `/api/v1/sessions` | POST/GET | 세션 관리 |

**분석 실행 예시:**
```http
POST /api/v1/executions/execute
Content-Type: application/json

{
  "spec": {
    "type": "taint_analysis",
    "target": "src/handlers/",
    "policy": "sql_injection"
  },
  "repo_id": "my-repo"
}
```

**응답:**
```json
{
  "envelope": {
    "claims": [
      {
        "claim_id": "C001",
        "type": "vulnerability",
        "severity": "high",
        "message": "SQL Injection detected"
      }
    ],
    "evidences": [...],
    "conclusion": {
      "severity": "high",
      "summary": "1 SQL Injection vulnerability found"
    }
  }
}
```

#### Agent API - 자동화 태스크

| Endpoint | Method | 설명 |
|----------|--------|------|
| `/agent/analyze` | POST | 코드 분석 요청 |
| `/agent/fix` | POST | 자동 수정 요청 |
| `/agent/task` | POST | 커스텀 태스크 |
| `/agent/tasks` | GET | 태스크 목록 |
| `/agent/task/{task_id}` | GET | 태스크 상태 |

---

### 1.2 MCP Tools (Human-Friendly)

IDE/에디터에서 직접 호출 가능한 도구.

#### 빠른 조회 (<2s)

| Tool | 설명 | 사용 예시 |
|------|------|----------|
| `get_context` | 통합 컨텍스트 조회 | 함수 정의, 호출자, 테스트 한번에 조회 |
| `get_definition` | 심볼 정의 조회 | 함수/클래스 정의로 이동 |
| `get_references` | 참조 조회 | 이 심볼을 사용하는 모든 곳 |
| `preview_callers` | 호출자 미리보기 | 이 함수를 호출하는 곳 빠르게 확인 |

#### 분석 미리보기 (2-10s)

| Tool | 설명 | 사용 예시 |
|------|------|----------|
| `preview_taint_path` | Taint 경로 확인 | SQL Injection 경로 존재 여부 |
| `preview_impact` | 변경 영향도 | 이 파일 수정 시 영향받는 범위 |

#### 검증 도구 (2-10s)

| Tool | 설명 | 사용 예시 |
|------|------|----------|
| `verify_patch_compile` | 패치 컴파일 검증 | 수정 코드가 컴파일되는지 확인 |
| `verify_finding_resolved` | 취약점 해결 확인 | 수정 후 취약점이 해결되었는지 |

---

## 2. LLM Code Agent를 위한 도구셋

### 2.1 설계 원칙

```
┌─────────────────────────────────────────────────────┐
│                 LLM Code Agent                      │
│  ┌───────────────────────────────────────────────┐  │
│  │ 1. 컨텍스트 수집 (get_context, preview_*)     │  │
│  │ 2. 분석 실행 (job_submit → job_result)       │  │
│  │ 3. 수정 제안 (generate code)                 │  │
│  │ 4. 검증 (verify_patch_compile)               │  │
│  │ 5. 확인 (verify_finding_resolved)            │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**핵심 원칙:**
1. **Latency 분류**: Fast(<2s) / Standard(2-10s) / Heavy(>10s)
2. **Pagination**: Context window 관리
3. **Graceful Degradation**: 실패 시 안전한 fallback
4. **Verification Loop**: 분석 → 수정 → 검증 → 확인

---

### 2.2 MCP Tools (LLM-Optimized)

#### Fast Tools (<2s) - 즉시 호출

| Tool | Input | Output | 용도 |
|------|-------|--------|------|
| `get_context` | `{target, facets, max_chars}` | 통합 컨텍스트 JSON | 코드 이해 |
| `get_definition` | `{symbol, file_path}` | 정의 코드 | 심볼 확인 |
| `get_references` | `{symbol, limit, cursor}` | Paginated 참조 목록 | 사용처 파악 |
| `preview_callers` | `{symbol, repo_id}` | 호출자 목록 (간략) | 의존성 파악 |

**get_context 예시:**
```json
// Input
{
  "target": "process_payment",
  "facets": ["definition", "callers", "callees", "tests"],
  "max_chars": 8000
}

// Output
{
  "definition": {
    "file": "src/payment/processor.py",
    "line": 45,
    "code": "def process_payment(amount, card_info):\n    ..."
  },
  "callers": [
    {"name": "checkout_handler", "file": "src/handlers/checkout.py", "line": 23}
  ],
  "callees": [
    {"name": "validate_card", "file": "src/payment/validator.py", "line": 12}
  ],
  "tests": [
    {"name": "test_process_payment", "file": "tests/test_payment.py", "line": 45}
  ]
}
```

#### Standard Tools (2-10s) - 분석/검증

| Tool | Input | Output | 용도 |
|------|-------|--------|------|
| `preview_taint_path` | `{source, sink, policy}` | 경로 존재 여부 | 취약점 탐지 |
| `preview_impact` | `{file_path, changes}` | 영향 범위 | 변경 영향 분석 |
| `graph_slice` | `{anchor, direction, max_depth}` | 코드 조각 | Root Cause 추출 |
| `graph_dataflow` | `{source, sink, policy}` | 경로 증명 | 값 흐름 분석 |
| `verify_patch_compile` | `{file_path, patch}` | 컴파일 결과 | 코드 유효성 |
| `verify_finding_resolved` | `{finding_id, file_path}` | 해결 여부 | 수정 확인 |
| `verify_no_new_findings_introduced` | `{baseline_execution_id}` | Regression 여부 | 회귀 방지 |

**verify_patch_compile 예시:**
```json
// Input
{
  "file_path": "src/db/query.py",
  "patch": "cursor.execute(sql, (user_id,))",
  "check_types": true
}

// Output
{
  "success": true,
  "compile_ok": true,
  "type_check_ok": true,
  "warnings": []
}
```

#### Heavy Tools (>10s) - 비동기 Job

| Tool | Input | Output | 용도 |
|------|-------|--------|------|
| `job_submit` | `{job_type, target, options}` | job_id | Job 제출 |
| `job_status` | `{job_id}` | 상태/진행률 | 폴링 |
| `job_result` | `{job_id}` | 분석 결과 | 결과 조회 |
| `job_cancel` | `{job_id}` | 취소 결과 | 중단 |

**비동기 워크플로우:**
```python
# 1. Job 제출
job_id = await job_submit({
    "job_type": "taint_analysis",
    "target": "src/handlers/",
    "policy": "sql_injection"
})

# 2. 폴링
while True:
    status = await job_status({"job_id": job_id})
    if status["state"] == "completed":
        break
    if status["state"] == "failed":
        raise Error(status["error"])
    await sleep(2)

# 3. 결과 조회
result = await job_result({"job_id": job_id})
```

---

### 2.3 REST API (LLM Agent용)

LLM이 HTTP로 호출하는 경우.

#### 분석 실행

```http
POST /api/v1/executions/execute
Content-Type: application/json

{
  "spec": {
    "type": "impact_analysis",
    "target": ["src/auth/session.py"],
    "depth": 3
  }
}
```

#### Job 관리

```http
POST /api/v1/jobs
Content-Type: application/json

{
  "job_type": "full_taint_scan",
  "target": "src/",
  "timeout_seconds": 300
}
```

```http
GET /api/v1/jobs/{job_id}
```

#### 검색

```http
GET /search/search?query=authentication+bypass&limit=10
```

---

### 2.4 LLM Agent 워크플로우 예시

#### 취약점 발견 및 수정

```
1. [get_context] 대상 함수 컨텍스트 수집
   → 함수 정의, 호출자, 데이터 흐름 파악

2. [preview_taint_path] Taint 경로 빠른 확인
   → SQL Injection 가능성 탐지

3. [job_submit] 상세 Taint 분석 실행
   → 전체 경로 추적 (비동기)

4. [job_result] 분석 결과 조회
   → 취약점 상세 정보 획득

5. [LLM] 수정 코드 생성
   → Parameterized query로 변경

6. [verify_patch_compile] 컴파일 검증
   → 문법/타입 오류 확인

7. [verify_finding_resolved] 취약점 해결 확인
   → Taint 경로 차단 확인

8. [완료] 수정 제안 제출
```

#### 리팩토링 영향 분석

```
1. [get_context] 변경 대상 컨텍스트
   → 함수 정의 및 사용처

2. [preview_impact] 영향 범위 미리보기
   → 어떤 파일이 영향받는지

3. [get_references] 모든 참조 조회
   → 변경해야 할 위치 목록

4. [LLM] 리팩토링 계획 수립

5. [verify_patch_compile] 각 변경 검증

6. [완료] 리팩토링 PR 생성
```

---

## 3. 도구 분류 요약

### 3.1 By 대상

| 분류 | 도구 | 특징 |
|------|------|------|
| **Human** | REST API + IDE MCP | UI 친화적, 상세 응답 |
| **LLM** | MCP Tools (주로) | JSON 구조화, Pagination |

### 3.2 By Latency

| 분류 | 도구 | Latency |
|------|------|---------|
| **Fast** | get_context, get_definition, preview_callers | <2s |
| **Standard** | preview_taint, verify_patch | 2-10s |
| **Heavy** | job_submit → job_result | >10s |

### 3.3 By 기능

| 분류 | 도구 |
|------|------|
| **탐색** | get_context, get_definition, get_references, graph/* |
| **검색** | search/* |
| **분석** | job_submit (taint, impact, slice) |
| **검증** | verify_patch_compile, verify_finding_resolved |
| **관리** | index/*, job_status, job_cancel |

---

## 4. 기술 스택

```
┌─────────────────────────────────────────────────────┐
│                    Clients                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐             │
│  │  IDE    │  │  CLI    │  │  LLM    │             │
│  └────┬────┘  └────┬────┘  └────┬────┘             │
└───────┼────────────┼────────────┼───────────────────┘
        │            │            │
        ▼            ▼            ▼
┌─────────────────────────────────────────────────────┐
│              API Layer                              │
│  ┌─────────────┐  ┌─────────────┐                  │
│  │ FastAPI     │  │ MCP Server  │                  │
│  │ (REST)      │  │ (Tools)     │                  │
│  └──────┬──────┘  └──────┬──────┘                  │
└─────────┼────────────────┼──────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────────────────────────────────────────┐
│              Core Services                          │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐       │
│  │ Reasoning │  │ Retrieval │  │ Indexing  │       │
│  │ Pipeline  │  │ Service   │  │ Service   │       │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘       │
└────────┼──────────────┼──────────────┼──────────────┘
         │              │              │
         ▼              ▼              ▼
┌─────────────────────────────────────────────────────┐
│              Infrastructure                         │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐    │
│  │ Graph  │  │ Qdrant │  │ Zoekt  │  │ SQLite │    │
│  │ Index  │  │ Vector │  │ Lexical│  │ / PG   │    │
│  └────────┘  └────────┘  └────────┘  └────────┘    │
└─────────────────────────────────────────────────────┘
```

---

## 5. 엔드포인트 전체 목록

### REST API (40개)

```
GET      /graph/callers
GET      /graph/callees
GET      /graph/references
GET      /graph/imports
GET      /search/search
GET      /search/search/lexical
GET      /search/search/vector
GET      /search/search/symbol
GET      /search/chunks
GET      /search/symbols
POST     /index/repo
POST     /index/incremental
DELETE   /index/repo
GET      /index/status/{repo_id}
GET      /index/health
POST     /api/v1/executions/execute
GET      /api/v1/executions/replay/{request_id}
POST     /api/v1/validations/validate
POST     /api/v1/plans/plan
POST     /api/v1/explanations/explain
POST     /api/v1/jobs
GET      /api/v1/jobs
GET      /api/v1/jobs/{job_id}
POST     /api/v1/sessions
GET      /api/v1/sessions
GET      /api/v1/sessions/{session_id}
POST     /api/v1/feedback
POST     /agent/analyze
POST     /agent/fix
POST     /agent/task
GET      /agent/tasks
GET      /agent/task/{task_id}
GET      /agent/stats
GET      /agent/performance
GET      /health/
GET      /health/ready
GET      /metrics
GET      /docs
GET      /redoc
GET      /openapi.json
POST/GET /graph/slice
POST/GET /graph/dataflow
POST     /api/v1/workspaces
GET      /api/v1/workspaces
GET      /api/v1/workspaces/{id}
POST     /api/v1/workspaces/branch
DELETE   /api/v1/workspaces/{id}
```

### MCP Tools (15개)

```
# Job (Async)
job_submit                          # Job 제출
job_status                          # Job 상태
job_result                          # Job 결과
job_cancel                          # Job 취소

# Context
get_context                         # 통합 컨텍스트
get_definition                      # 심볼 정의
get_references                      # 참조 조회

# Graph Semantics (RFC-SEM-022)
graph_slice                         # Semantic Slicing
graph_dataflow                      # Dataflow 증명

# Preview
preview_taint_path                  # Taint 미리보기
preview_impact                      # 영향도 미리보기
preview_callers                     # 호출자 미리보기

# Verify (RFC-SEM-022)
verify_patch_compile                # 패치 컴파일 검증
verify_finding_resolved             # 취약점 해결 확인
verify_no_new_findings_introduced   # Regression Proof
```

### MCP Resources (4개, RFC-SEM-022)

실시간 스트리밍 리소스.

| URI | 설명 |
|-----|------|
| `semantica://jobs/{job_id}/events` | Job 이벤트 SSE 스트림 |
| `semantica://jobs/{job_id}/log` | Job 로그 스트림 |
| `semantica://jobs/{job_id}/artifacts` | Job 결과물 |
| `semantica://executions/{execution_id}/findings` | Execution findings |

### MCP Prompts (5개, RFC-SEM-022)

LLM Agent 자기비판 가이드.

| Prompt | 목적 |
|--------|------|
| `verify_evidence_logical_gap` | 논리적 비약 자기점검 |
| `suggest_additional_analysis` | 추가 분석 제안 |
| `critique_patch` | Patch 자기비판 |
| `plan_verification_strategy` | 검증 전략 수립 |
| `interpret_dataflow_result` | Dataflow 해석 |
