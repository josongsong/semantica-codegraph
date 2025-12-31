# RFC-053: Implementation Guide

## Tiered MCP Tool Architecture - 구현 가이드

---

## 1. Phase 1: Tier 0 구현 (1주)

### 1.1 `search` 통합 구현

#### 목표
`search_chunks` + `search_symbols` → `search(types=[...])`

#### 파일 수정

**1) 핸들러 생성**: `server/mcp_server/handlers/search.py`

```python
"""Tier 0: search - 하이브리드 검색"""

import json
from typing import Literal

from core.core.mcp.services import MCPSearchService


async def search(
    service: MCPSearchService,
    arguments: dict
) -> str:
    """
    하이브리드 검색 (chunks + symbols 통합).
    
    Args:
        query: 검색 쿼리
        types: ["chunks", "symbols", "all"]
        limit: 결과 수 (default: 10)
        repo_id: 리포지토리 ID
        
    Returns:
        {
          "query": str,
          "results": {
            "symbols": [...],
            "chunks": [...]
          },
          "mixed_ranking": [...],
          "took_ms": int
        }
    """
    query = arguments["query"]
    types = arguments.get("types", ["all"])
    limit = arguments.get("limit", 10)
    repo_id = arguments.get("repo_id", "default")
    
    import time
    start = time.time()
    
    results = {}
    
    # Types 처리
    search_chunks = "all" in types or "chunks" in types
    search_symbols = "all" in types or "symbols" in types
    
    # Chunks 검색
    if search_chunks:
        chunks_result = await service.search_chunks(query, limit=limit)
        results["chunks"] = chunks_result
    
    # Symbols 검색
    if search_symbols:
        symbols_result = await service.search_symbols(query, limit=limit)
        results["symbols"] = symbols_result
    
    # Mixed ranking (간단한 score 기반)
    mixed = []
    if search_chunks and search_symbols:
        all_results = [
            {"type": "chunk", **chunk} 
            for chunk in results.get("chunks", [])
        ] + [
            {"type": "symbol", **symbol} 
            for symbol in results.get("symbols", [])
        ]
        mixed = sorted(
            all_results, 
            key=lambda x: x.get("score", 0), 
            reverse=True
        )[:limit]
    
    took_ms = int((time.time() - start) * 1000)
    
    return json.dumps({
        "query": query,
        "results": results,
        "mixed_ranking": mixed,
        "took_ms": took_ms,
        "meta": {
            "timeout_seconds": 2,
            "cost_hint": "low"
        }
    }, indent=2)
```

**2) main.py 업데이트**

```python
# server/mcp_server/main.py

from server.mcp_server.handlers import (
    search,  # NEW
    # ... 기존 handlers
)

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ============================================================
        # Tier 0 — 에이전트 기본 진입점 (3개)
        # ============================================================
        Tool(
            name="search",
            description="하이브리드 검색 (chunks + symbols 통합) - 어디를 볼지 모를 때 첫 선택",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색 쿼리"},
                    "types": {
                        "type": "array",
                        "items": {"enum": ["chunks", "symbols", "all"]},
                        "default": ["all"],
                        "description": "검색 대상"
                    },
                    "limit": {"type": "integer", "default": 10},
                    "repo_id": {"type": "string", "default": "default"}
                },
                "required": ["query"]
            }
        ),
        
        # get_context, graph_slice는 기존 유지
        # ...
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> str:
    # Tier 0
    if name == "search":
        return await search(search_service, arguments)
    # ...
```

---

### 1.2 `get_context` 최적화

#### 목표
Budget 제어 강화 + 기본 facets 최적화

**파일**: `server/mcp_server/handlers/context.py`

```python
async def get_context(arguments: dict) -> str:
    """
    통합 컨텍스트 조회.
    
    최적화:
    - 기본 facets: ["definition", "usages", "callers"]
    - budget: max_chars=8000, max_items=20
    - timeout: 3초
    """
    target = arguments["target"]
    facets = arguments.get("facets", ["definition", "usages", "callers"])
    budget = arguments.get("budget", {
        "max_chars": 8000,
        "max_items": 20
    })
    
    # 기존 로직 + budget 추적
    result = {
        "target": target,
        "budget_used": {
            "chars": 0,
            "items": 0
        }
    }
    
    # facet별 조회 (budget 초과 시 중단)
    for facet in facets:
        if result["budget_used"]["chars"] >= budget["max_chars"]:
            break
        # ... facet 처리
    
    return json.dumps(result, indent=2)
```

---

### 1.3 `graph_slice` 메타데이터 추가

**파일**: `server/mcp_server/handlers/analysis.py`

```python
async def graph_slice(arguments: dict) -> str:
    """Semantic Slicing"""
    # 기존 로직
    result = {
        # ... slice 결과
        "meta": {
            "timeout_seconds": 5,
            "cost_hint": "medium",
            "took_ms": took_ms
        }
    }
    return json.dumps(result, indent=2)
```

---

### 1.4 테스트

**파일**: `tests/integration/test_tier0_tools.py`

```python
import pytest
from server.mcp_server.handlers import search, get_context

@pytest.mark.asyncio
async def test_search_hybrid():
    """search 하이브리드 동작 확인"""
    result = await search(search_service, {
        "query": "UserService",
        "types": ["all"],
        "limit": 5
    })
    
    data = json.loads(result)
    assert "results" in data
    assert "mixed_ranking" in data
    assert data["took_ms"] < 2000  # 2초 이내

@pytest.mark.asyncio
async def test_get_context_budget():
    """get_context budget 제어 확인"""
    result = await get_context({
        "target": "UserService",
        "budget": {"max_chars": 1000, "max_items": 5}
    })
    
    data = json.loads(result)
    assert data["budget_used"]["chars"] <= 1000
    assert data["budget_used"]["items"] <= 5
```

---

## 2. Phase 2: Tier 1 통합 (1주)

### 2.1 `get_symbol` 필드 통합

#### 목표
~~`get_definition`~~ → `get_symbol(fields=["definition"])`

**파일**: `server/mcp_server/handlers/symbols.py`

```python
async def get_symbol(
    service: MCPSearchService,
    arguments: dict
) -> str:
    """
    심볼 조회 (fields 옵션).
    
    Args:
        symbol: 심볼 ID/FQN
        fields: ["definition", "body", "signature", "docstring"]
                default: ["definition", "signature"]
    """
    symbol = arguments["symbol"]
    fields = arguments.get("fields", ["definition", "signature"])
    
    # 기존 get_symbol + get_definition 통합
    result = {
        "symbol": symbol,
        "fields": {}
    }
    
    if "definition" in fields:
        result["fields"]["definition"] = await _get_definition(symbol)
    if "body" in fields:
        result["fields"]["body"] = await _get_body(symbol)
    # ...
    
    return json.dumps(result, indent=2)
```

**main.py 업데이트**:
```python
Tool(
    name="get_symbol",
    description="심볼 ID/FQN으로 조회 (fields 선택 가능)",
    inputSchema={
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "fields": {
                "type": "array",
                "items": {"enum": ["definition", "body", "signature", "docstring"]},
                "default": ["definition", "signature"]
            }
        },
        "required": ["symbol"]
    }
),
# ❌ get_definition 제거
```

---

### 2.2 `get_callers` mode 통합

#### 목표
~~`preview_callers`~~ → `get_callers(mode="preview")`

**파일**: `server/mcp_server/handlers/graph.py`

```python
async def get_callers(
    service: MCPGraphService,
    arguments: dict
) -> str:
    """
    호출자 조회.
    
    Args:
        symbol: 심볼 ID/FQN
        depth: 탐색 깊이 (default: 1)
        limit: 결과 수 (default: 100)
        mode: "preview" (top 50 + 2초) | "full" (전체 + depth)
    """
    symbol = arguments["symbol"]
    depth = arguments.get("depth", 1)
    limit = arguments.get("limit", 100)
    mode = arguments.get("mode", "preview")
    
    if mode == "preview":
        # 빠른 프리뷰: limit=50, depth=2, timeout=2초
        result = await service.get_callers(
            symbol, 
            depth=min(depth, 2), 
            limit=min(limit, 50),
            timeout=2
        )
    else:  # mode == "full"
        # 전체 조회: depth/limit 그대로
        result = await service.get_callers(
            symbol, 
            depth=depth, 
            limit=limit,
            timeout=10
        )
    
    result["meta"] = {
        "mode": mode,
        "timeout_seconds": 2 if mode == "preview" else 10,
        "cost_hint": "low" if mode == "preview" else "medium"
    }
    
    return json.dumps(result, indent=2)
```

**main.py 업데이트**:
```python
Tool(
    name="get_callers",
    description="호출자 조회 (mode: preview=빠른요약, full=전체)",
    inputSchema={
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "depth": {"type": "integer", "default": 1},
            "limit": {"type": "integer", "default": 100},
            "mode": {
                "type": "string",
                "enum": ["preview", "full"],
                "default": "preview"
            }
        },
        "required": ["symbol"]
    }
),
# ❌ preview_callers 제거
```

---

### 2.3 메타데이터 추가

모든 Tier 1 툴에 다음 추가:

```python
"meta": {
    "timeout_seconds": int,
    "cost_hint": "low" | "medium" | "high",
    "typical_duration_ms": int
}
```

---

## 3. Phase 3: Tier 2 통합 (1주)

### 3.1 Heavy 분석 옵트인

**파일**: `server/mcp_server/handlers/analysis.py`

```python
async def analyze_race(arguments: dict) -> str:
    """
    Race condition 분석 (Heavy).
    
    ⚠️ 비용/시간 높음: 명시적 승인 필요
    """
    # 비용 경고 포함
    result = {
        "warning": "This is a heavy operation (60s+, high cost)",
        "meta": {
            "timeout_seconds": 60,
            "cost_hint": "very_high",
            "requires_approval": True
        },
        # ... 분석 결과
    }
    return json.dumps(result, indent=2)
```

**main.py Tool 정의**:
```python
Tool(
    name="analyze_race",
    description="⚠️ [HEAVY] Race condition 분석 (60s+, 명시적 승인 필요)",
    # ...
)
```

---

### 3.2 Job 시스템 안정화

- [ ] Job Queue 우선순위 처리
- [ ] Timeout 강제 종료
- [ ] 결과 페이지네이션 최적화

---

## 4. Phase 4: 레거시 제거

### 4.1 제거 대상

```bash
# 제거할 핸들러
apps/mcp_server/handlers/
├── search_chunks.py      # → search
├── search_symbols.py     # → search
├── get_definition.py     # → get_symbol(fields=...)
└── preview_callers.py    # → get_callers(mode=...)
```

### 4.2 마이그레이션 체크리스트

- [ ] 모든 Tier 0-2 핸들러 구현 완료
- [ ] 통합 테스트 100% 통과
- [ ] 성능 벤치마크 달성 (Tier 0 < 2s)
- [ ] 문서 업데이트 (`_docs/api/mcp-tools.md`)
- [ ] 레거시 import 제거
- [ ] 사용되지 않는 코드 정리

---

## 5. 테스트 전략

### 5.1 단위 테스트

```python
# tests/unit/handlers/test_search.py
@pytest.mark.asyncio
async def test_search_chunks_only():
    result = await search(service, {
        "query": "test",
        "types": ["chunks"]
    })
    data = json.loads(result)
    assert "chunks" in data["results"]
    assert "symbols" not in data["results"]

@pytest.mark.asyncio
async def test_search_timeout():
    """2초 timeout 확인"""
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            search(service, {"query": "..."}, timeout=2.0)
        )
```

### 5.2 통합 테스트

```python
# tests/integration/test_tier_escalation.py
@pytest.mark.asyncio
async def test_escalation_tier0_to_tier1():
    """Tier 0 → Tier 1 escalation"""
    # 1. Tier 0: search
    result = await call_tool("search", {"query": "UserService"})
    
    # 2. Tier 0: get_context
    result = await call_tool("get_context", {"target": "UserService"})
    
    # 3. Tier 1: get_callers (더 상세)
    result = await call_tool("get_callers", {
        "symbol": "UserService",
        "mode": "full",
        "depth": 3
    })
```

### 5.3 성능 테스트

```python
# tests/performance/test_tier_latency.py
@pytest.mark.benchmark
def test_tier0_latency(benchmark):
    """Tier 0 < 2s 확인"""
    result = benchmark(lambda: asyncio.run(
        call_tool("search", {"query": "test"})
    ))
    assert result["took_ms"] < 2000

@pytest.mark.benchmark
def test_tier1_latency(benchmark):
    """Tier 1 < 10s 확인"""
    result = benchmark(lambda: asyncio.run(
        call_tool("get_callers", {
            "symbol": "UserService",
            "mode": "full",
            "depth": 5
        })
    ))
    assert result["took_ms"] < 10000
```

---

## 6. 롤아웃 계획

### Week 1: Tier 0
- [ ] Mon-Tue: `search` 통합 구현
- [ ] Wed-Thu: `get_context` 최적화
- [ ] Fri: 통합 테스트 + 성능 검증

### Week 2: Tier 1
- [ ] Mon-Tue: `get_symbol` 필드 통합
- [ ] Wed-Thu: `get_callers` mode 통합
- [ ] Fri: 메타데이터 추가 + 테스트

### Week 3: Tier 2
- [ ] Mon-Tue: Job 시스템 안정화
- [ ] Wed-Thu: Heavy 분석 옵트인
- [ ] Fri: 전체 통합 테스트

### Week 4: 레거시 제거
- [ ] Mon-Tue: 레거시 핸들러 제거
- [ ] Wed: 문서 업데이트
- [ ] Thu-Fri: 최종 검증 + 배포

---

## 7. 체크리스트

### Phase 1 완료 조건
- [ ] `search` 도구 구현 (chunks + symbols)
- [ ] `get_context` budget 제어
- [ ] `graph_slice` 메타데이터
- [ ] Tier 0 테스트 100% 통과
- [ ] 성능: Tier 0 < 2s (p95)

### Phase 2 완료 조건
- [ ] `get_symbol(fields=...)` 통합
- [ ] `get_callers(mode=...)` 통합
- [ ] Tier 1 메타데이터 추가
- [ ] Tier 1 테스트 100% 통과
- [ ] 성능: Tier 1 < 10s (p95)

### Phase 3 완료 조건
- [ ] Job 시스템 안정화
- [ ] Heavy 분석 경고 추가
- [ ] Tier 2 테스트 100% 통과

### Phase 4 완료 조건
- [ ] 레거시 핸들러 제거
- [ ] 문서 업데이트
- [ ] 최종 통합 테스트
- [ ] 프로덕션 배포

---

**End of Implementation Guide**

