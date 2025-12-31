# RFC-053: Tiered MCP Tool Architecture

## Status: Draft
## Author: Codegraph Team  
## Created: 2025-12-23
## Supersedes: RFC-052 (Tool Design 부분)

---

## 1. 문제 정의

### 1.1 현재 상황 (RFC-052 구현)

```
총 22개 Tools (MCP Catalog)
├─ 검색: search_chunks, search_symbols
├─ 조회: get_chunk, get_symbol, get_definition
├─ 그래프: get_callers, get_callees, preview_callers
├─ 컨텍스트: get_context, get_references
├─ 분석: analyze_cost, analyze_race, graph_slice, graph_dataflow
├─ 프리뷰: preview_taint_path, preview_impact, preview_callers
├─ Job: job_submit, job_status, job_result, job_cancel
└─ 검증: verify_patch_compile, verify_finding_resolved
```

### 1.2 문제점

#### A. 에이전트 인지 부하 (Cognitive Overload)
- LLM이 22개 중 어떤 툴을 선택할지 고민 → Hallucination 증가
- 유사 기능 중복: `get_symbol` vs `get_definition`, `get_callers` vs `preview_callers`
- 첫 선택지가 너무 많음 (에이전트 안정성 저하)

#### B. 명확한 Escalation Path 부재
```python
# 현재: 평면적 구조
search_chunks() or search_symbols()?  # 에이전트가 매번 고민
get_callers() or preview_callers()?   # 언제 뭘 써야 하나?
analyze_cost() or job_submit()?       # 비용/시간 예측 불가
```

#### C. 비용/시간 예측 불가
- 모든 툴이 동등해 보임 → Heavy 작업 실수 호출 위험
- Timeout/Limit 메타데이터 없음
- Preview vs Full 구분 불명확

---

## 2. 설계 원칙

### 2.1 핵심 원칙

1. **첫 선택지 ≤ 3개** (Tier 0): 에이전트 안정성 확보
2. **Preview/Full/Async 명확 분리**: 비용·시간 예측 가능
3. **판단 로직 없음**: 도구는 관측/분석만, 판단은 에이전트가
4. **메타데이터 필수**: 모든 툴에 `timeout`, `limit`, `cost_hint` 포함

### 2.2 Escalation Path

```
사용자 질문
  ↓
Tier 0 (3개) - 1-2초, 저렴
  ├─ search: 어디를 볼지 모를 때
  ├─ get_context: 심볼이 뭔지 빠르게 파악
  └─ graph_slice: 버그 원인 추적
  ↓ (부족하면)
Tier 1 (9개) - 5-10초, 중간
  ├─ 정밀 조회: get_chunk, get_symbol, get_references
  ├─ 그래프 탐색: get_callers, get_callees, graph_dataflow
  └─ 분석: analyze_cost, preview_impact, verify_patch_compile
  ↓ (여전히 부족하면)
Tier 2 (7개) - 30초+, 비쌈, 명시적 승인
  ├─ Heavy: analyze_race, preview_taint_path
  └─ Async: job_submit, job_status, job_result, job_cancel
```

---

## 3. Tiered Tool 설계

### 3.1 Tier 0 — 에이전트 기본 진입점 (3개)

> **원칙**: 대부분의 질문은 여기서 시작하도록 강제

#### Tool 1: `search`

**용도**: "어디를 볼지 모를 때" 하이브리드 검색

```python
{
  "name": "search",
  "description": "하이브리드 검색 (chunks + symbols 통합)",
  "inputSchema": {
    "query": {"type": "string", "description": "검색 쿼리"},
    "types": {
      "type": "array",
      "items": {"enum": ["chunks", "symbols", "all"]},
      "default": ["all"]
    },
    "limit": {"type": "integer", "default": 10},
    "repo_id": {"type": "string", "default": "default"}
  },
  "meta": {
    "timeout_seconds": 2,
    "cost_hint": "low",
    "typical_duration_ms": 500
  }
}
```

**통합 대상**:
- ~~`search_chunks`~~
- ~~`search_symbols`~~

**반환 형식**:
```json
{
  "query": "UserService",
  "results": {
    "symbols": [
      {"id": "sym_123", "name": "UserService", "kind": "class", "score": 0.95}
    ],
    "chunks": [
      {"id": "chunk_456", "content": "...", "score": 0.88}
    ]
  },
  "mixed_ranking": [...],  // 통합 랭킹
  "took_ms": 342
}
```

---

#### Tool 2: `get_context`

**용도**: "이게 뭔지/어디서 쓰이는지 빠르게 파악"

```python
{
  "name": "get_context",
  "description": "통합 컨텍스트 조회 (definition + 핵심 usages + callers 요약 + top chunks)",
  "inputSchema": {
    "target": {
      "type": "string",
      "description": "symbol_id | fqn | file:line"
    },
    "facets": {
      "type": "array",
      "items": {
        "enum": ["definition", "usages", "references", "docstring", 
                 "skeleton", "tests", "callers", "callees"]
      },
      "default": ["definition", "usages", "callers"]
    },
    "budget": {
      "type": "object",
      "properties": {
        "max_chars": {"type": "integer", "default": 8000},
        "max_items": {"type": "integer", "default": 20}
      }
    }
  },
  "meta": {
    "timeout_seconds": 3,
    "cost_hint": "low",
    "typical_duration_ms": 1200
  }
}
```

**기존 유지**: 이미 통합 툴이므로 변경 없음

**반환 형식**:
```json
{
  "target": "UserService",
  "definition": {...},
  "usages_summary": {
    "total": 145,
    "top_10": [...]
  },
  "callers_summary": {
    "total": 23,
    "top_5": [...]
  },
  "budget_used": {
    "chars": 7234,
    "items": 18
  }
}
```

---

#### Tool 3: `graph_slice`

**용도**: "버그/원인 분석" - Semantic Slicing (Root Cause 추출)

```python
{
  "name": "graph_slice",
  "description": "Semantic Slicing - 버그/이슈의 Root Cause만 최소 단위로 추출",
  "inputSchema": {
    "anchor": {"type": "string", "description": "앵커 심볼 (변수/함수/클래스)"},
    "direction": {
      "type": "string",
      "enum": ["backward", "forward", "both"],
      "default": "backward"
    },
    "max_depth": {"type": "integer", "default": 5},
    "max_lines": {"type": "integer", "default": 100},
    "file_scope": {"type": "string", "description": "파일 제한 (optional)"}
  },
  "meta": {
    "timeout_seconds": 5,
    "cost_hint": "medium",
    "typical_duration_ms": 2000
  }
}
```

**기존 유지**: 변경 없음

---

### 3.2 Tier 1 — 일반 분석 도구 (9개)

> **원칙**: Tier 0으로 부족할 때만 선택되는 정밀 도구

#### 조회 도구 (3개)

##### `get_chunk`
```python
{
  "name": "get_chunk",
  "description": "청크 ID로 전체 내용 조회",
  "meta": {"timeout_seconds": 1, "cost_hint": "low"}
}
```

##### `get_symbol`
```python
{
  "name": "get_symbol",
  "description": "심볼 ID/FQN으로 정의 조회 (body 포함)",
  "inputSchema": {
    "symbol": {"type": "string"},
    "fields": {
      "type": "array",
      "items": {"enum": ["definition", "body", "signature", "docstring"]},
      "default": ["definition", "signature"]
    }
  },
  "meta": {"timeout_seconds": 1, "cost_hint": "low"}
}
```

**통합 대상**:
- ~~`get_definition`~~ → `get_symbol(fields=["definition"])`

##### `get_references`
```python
{
  "name": "get_references",
  "description": "참조 조회 (pagination 전용, 대량 참조용)",
  "inputSchema": {
    "symbol": {"type": "string"},
    "limit": {"type": "integer", "default": 50},
    "cursor": {"type": "string"}
  },
  "meta": {"timeout_seconds": 3, "cost_hint": "medium"}
}
```

---

#### 그래프 도구 (3개)

##### `get_callers`
```python
{
  "name": "get_callers",
  "description": "호출자 조회 (depth/limit/timeout 조절 가능)",
  "inputSchema": {
    "symbol": {"type": "string"},
    "depth": {"type": "integer", "default": 1},
    "limit": {"type": "integer", "default": 100},
    "mode": {
      "type": "string",
      "enum": ["preview", "full"],
      "default": "preview",
      "description": "preview: top 50 + 2초, full: 전체 + depth 제한"
    }
  },
  "meta": {
    "timeout_seconds": 5,
    "cost_hint": "medium",
    "typical_duration_ms": 1500
  }
}
```

**통합 대상**:
- ~~`preview_callers`~~ → `get_callers(mode="preview", limit=50)`

##### `get_callees`
```python
{
  "name": "get_callees",
  "description": "호출 대상 조회",
  "inputSchema": {
    "symbol": {"type": "string"},
    "depth": {"type": "integer", "default": 1}
  },
  "meta": {"timeout_seconds": 3, "cost_hint": "medium"}
}
```

##### `graph_dataflow`
```python
{
  "name": "graph_dataflow",
  "description": "Dataflow Analysis - source → sink 도달 가능성 증명",
  "inputSchema": {
    "source": {"type": "string"},
    "sink": {"type": "string"},
    "policy": {"type": "string", "description": "sql_injection, xss 등"},
    "max_depth": {"type": "integer", "default": 10}
  },
  "meta": {"timeout_seconds": 10, "cost_hint": "high"}
}
```

---

#### 분석 도구 (3개)

##### `analyze_cost`
```python
{
  "name": "analyze_cost",
  "description": "비용 복잡도 분석 (RFC-028)",
  "meta": {"timeout_seconds": 5, "cost_hint": "medium"}
}
```

##### `preview_impact`
```python
{
  "name": "preview_impact",
  "description": "변경 영향도 근사 (변경된 심볼 → 영향받는 코드)",
  "inputSchema": {
    "changed_symbols": {"type": "array", "items": {"type": "string"}},
    "top_k": {"type": "integer", "default": 20}
  },
  "meta": {"timeout_seconds": 3, "cost_hint": "medium"}
}
```

##### `verify_patch_compile`
```python
{
  "name": "verify_patch_compile",
  "description": "패치 문법/타입/빌드 검증",
  "inputSchema": {
    "file_path": {"type": "string"},
    "patch": {"type": "string"},
    "language": {"enum": ["python", "typescript", "javascript"]},
    "check_types": {"type": "boolean", "default": true}
  },
  "meta": {"timeout_seconds": 10, "cost_hint": "high"}
}
```

---

### 3.3 Tier 2 — Heavy / Async / Expert (7개)

> **원칙**: 비용·시간이 큰 작업, 명시적 승격 필요

#### Heavy 분석 (2개)

##### `analyze_race`
```python
{
  "name": "analyze_race",
  "description": "Race condition 분석 (RFC-028 Phase 2, Heavy)",
  "inputSchema": {
    "repo_id": {"type": "string"},
    "snapshot_id": {"type": "string"},
    "functions": {"type": "array", "items": {"type": "string"}}
  },
  "meta": {
    "timeout_seconds": 60,
    "cost_hint": "very_high",
    "requires_approval": true
  }
}
```

##### `preview_taint_path`
```python
{
  "name": "preview_taint_path",
  "description": "Taint 경로 프리뷰 (보안 전용, 1-2초 존재성 확인)",
  "inputSchema": {
    "source_pattern": {"type": "string"},
    "sink_pattern": {"type": "string"},
    "limit": {"type": "integer", "default": 5}
  },
  "meta": {"timeout_seconds": 2, "cost_hint": "medium"}
}
```

---

#### Async Job 시스템 (4개)

##### `job_submit`
```python
{
  "name": "job_submit",
  "description": "비동기 Job 제출 (Heavy 분석용)",
  "inputSchema": {
    "tool": {"type": "string", "description": "실행할 도구 (analyze_taint, analyze_impact, etc.)"},
    "args": {"type": "object"},
    "priority": {"enum": ["low", "medium", "high", "critical"]},
    "timeout_seconds": {"type": "integer", "default": 300}
  },
  "meta": {"cost_hint": "async"}
}
```

##### `job_status`
```python
{
  "name": "job_status",
  "description": "Job 상태 조회",
  "meta": {"timeout_seconds": 1, "cost_hint": "free"}
}
```

##### `job_result`
```python
{
  "name": "job_result",
  "description": "Job 결과 조회 (with pagination)",
  "meta": {"timeout_seconds": 2, "cost_hint": "low"}
}
```

##### `job_cancel`
```python
{
  "name": "job_cancel",
  "description": "Job 취소",
  "meta": {"timeout_seconds": 1, "cost_hint": "free"}
}
```

---

#### 검증 도구 (1개)

##### `verify_finding_resolved`
```python
{
  "name": "verify_finding_resolved",
  "description": "Finding 해결 확인 (분석→수정→검증 루프)",
  "inputSchema": {
    "finding_type": {"type": "string"},
    "original_location": {"type": "object"},
    "patch": {"type": "string"}
  },
  "meta": {"timeout_seconds": 15, "cost_hint": "high"}
}
```

---

### 3.4 MCP Resources (4개)

> **별도 카테고리**: Tool 아님, URI 기반 스트리밍/조회

```python
[
  "semantica://jobs/{job_id}/events",        # SSE 스트림
  "semantica://jobs/{job_id}/log",           # 로그
  "semantica://jobs/{job_id}/artifacts",     # 결과물
  "semantica://executions/{execution_id}/findings"  # 취약점 목록
]
```

---

## 4. 최종 요약

### 4.1 Tool 수 비교

| 카테고리 | Before (RFC-052) | After (RFC-053) | 변화 |
|---------|------------------|-----------------|------|
| Tier 0 (진입점) | - | **3** | +3 |
| Tier 1 (일반) | - | **9** | +9 |
| Tier 2 (Heavy) | - | **7** | +7 |
| **Total Tools** | **22** | **19** | **-3** |
| Resources | 4 | 4 | 0 |

### 4.2 통합/제거 내역

| 작업 | Before | After | 방식 |
|-----|--------|-------|------|
| 통합 | `search_chunks` + `search_symbols` | `search(types=[...])` | 파라미터 통합 |
| 통합 | `preview_callers` | `get_callers(mode="preview")` | 옵션 통합 |
| 통합 | `get_definition` | `get_symbol(fields=["definition"])` | 필드 통합 |
| 유지 | `get_context` | `get_context` | 이미 통합 툴 |
| 유지 | `get_references` | `get_references` | Pagination 전용 |

### 4.3 에이전트 관점 변화

#### Before (평면적 22개)
```
사용자: "UserService가 뭔지 알려줘"
에이전트: search_symbols? get_symbol? get_definition? get_context? 🤔
```

#### After (계층적 19개)
```
사용자: "UserService가 뭔지 알려줘"
에이전트: Tier 0 → get_context("UserService") ✅
```

```
사용자: "UserService 호출자 많을 것 같은데..."
에이전트: Tier 0 → get_context(facets=["callers"])
         → 부족 → Tier 1 → get_callers(mode="preview")
         → 여전히 부족 → get_callers(mode="full", depth=3)
```

---

## 5. 구현 계획

### Phase 1: Tier 0 구현/검증 (1주)

- [ ] `search` 통합 (chunks + symbols 하이브리드)
- [ ] `get_context` 최적화 (budget 제어)
- [ ] `graph_slice` 성능 검증
- [ ] **목표**: 80% 일반 질문 커버

### Phase 2: Tier 1 추가 (1주)

- [ ] 조회 도구: `get_symbol(fields=...)` 통합
- [ ] 그래프 도구: `get_callers(mode=...)` 통합
- [ ] 분석 도구: 메타데이터 추가
- [ ] **목표**: 95% 질문 커버

### Phase 3: Tier 2 통합 (1주)

- [ ] Job 시스템 안정화
- [ ] Heavy 분석 옵트인 메커니즘
- [ ] 비용 추적/리포팅
- [ ] **목표**: 전체 시스템 통합

### Phase 4: 레거시 제거

- [ ] `server/mcp_server/main.py` 리팩토링
- [ ] 구 핸들러 제거 (`apps/mcp_server/handlers/`)
- [ ] 테스트 업데이트
- [ ] 문서 동기화

---

## 6. 측정 지표

### 6.1 에이전트 안정성
- Tool Selection Accuracy: > 90%
- Hallucination Rate: < 5%
- 평균 Tool Call Depth: < 3

### 6.2 성능
- Tier 0 Response Time: < 2s (p95)
- Tier 1 Response Time: < 10s (p95)
- Tier 2 Job Queue Time: < 60s (p95)

### 6.3 사용 패턴
- Tier 0 Coverage: > 80%
- Tier 1 Coverage: 15-18%
- Tier 2 Coverage: < 5%

---

## 7. 참고 자료

- RFC-052: MCP Service Layer Architecture
- RFC-028: Cost/Race Analysis
- MCP Protocol Specification: https://modelcontextprotocol.io

---

## 8. 결정 사항

### 승인 필요
- [ ] Tier 구조 승인
- [ ] Tool 통합 방식 승인
- [ ] 구현 일정 승인

### 이슈
- `search` 하이브리드 랭킹 알고리즘 미정
- `get_callers(mode=...)` vs 별도 툴 논쟁 가능

---

**End of RFC-053**

