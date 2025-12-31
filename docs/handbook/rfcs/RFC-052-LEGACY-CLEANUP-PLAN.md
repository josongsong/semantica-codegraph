# RFC-052: Legacy Cleanup Plan

## Status: Deprecation
## Target: Next Major Version
## Risk Level: Low (Backward compatible)

---

## Executive Summary

RFC-052 구현 후 발견된 **중복/레거시 코드 정리 계획**.

### Identified Legacy Components

```
1. CodeFoundationContainer RFC-052 부분 (중복)
2. graph_semantics_tools.py (V1 Handler)
3. UnifiedQueryAPI 일부 메서드 (중복)
```

---

## 1. CodeFoundationContainer RFC-052 중복

### 현재 상태

```python
# src/contexts/code_foundation/di.py (518 lines)
class CodeFoundationContainer:
    # RFC-052 컴포넌트 (L254-442) ← ⚠️ 중복!
    def evidence_repository(self): ...
    def snapshot_session_service(self): ...
    def create_slice_usecase(self): ...
    def create_dataflow_usecase(self): ...

# src/contexts/code_foundation/infrastructure/di.py (590 lines)
class FoundationContainer:
    # RFC-052 컴포넌트 (L431-590) ← ✅ 정식!
    def evidence_repository(self): ...
    def snapshot_session_service(self): ...
    def create_slice_usecase(self): ...
    def create_dataflow_usecase(self): ...
```

### 영향 분석

```bash
$ grep -r "CodeFoundationContainer" --include="*.py" | grep -v test | grep -v ".pyc"

src/contexts/code_foundation/di.py:15:class CodeFoundationContainer:
src/contexts/code_foundation/di.py:66:    >>> container = CodeFoundationContainer()
src/contexts/code_foundation/di.py:446:code_foundation_container = CodeFoundationContainer()
src/contexts/llm_arbitration/application/execute_executor.py:...
src/contexts/llm_arbitration/application/executors/analyze_executor.py:...
```

**사용처: 2곳 (llm_arbitration context)**

### Cleanup Plan

#### Phase 1: Deprecation Warning (즉시)

```python
# di.py L254-442에 경고 추가 ✅ 완료
# DEPRECATED: Use FoundationContainer instead
```

#### Phase 2: Redirect to FoundationContainer (1주 후)

```python
@cached_property
def evidence_repository(self):
    """DEPRECATED: Use container._foundation.evidence_repository"""
    warnings.warn("...", DeprecationWarning)
    
    from src.container import container
    return container._foundation.evidence_repository
```

#### Phase 3: Remove (다음 Major Version)

```python
# 완전 제거:
# - L254-442 (RFC-052 section)
# - 190 lines 제거
```

#### Phase 4: Migrate llm_arbitration (선택)

```python
# llm_arbitration에서 CodeFoundationContainer 사용 중지
# FoundationContainer로 전환
```

---

## 2. V1 Handler (graph_semantics_tools.py)

### 현재 상태

```python
# V1 (Legacy) - 239 lines
server/mcp_server/handlers/graph_semantics_tools.py
- Direct Infrastructure access
- No VerificationSnapshot
- No Evidence
- No recovery hints

# V2 (RFC-052) - 235 lines
server/mcp_server/handlers/graph_semantics_tools_v2.py
- UseCase orchestration
- VerificationSnapshot ✅
- Evidence references ✅
- Recovery hints ✅
- V1 fallback included
```

### Deprecation Status

```python
# server/mcp_server/handlers/__init__.py
_use_v2 = os.getenv("MCP_USE_V2", "false").lower() == "true"

if _use_v2:
    from .graph_semantics_tools_v2 import ...  # V2
else:
    from .graph_semantics_tools import ...     # V1 (default)
```

### Cleanup Plan

#### Phase 1: Deprecation Warning (✅ 완료)

```python
# graph_semantics_tools.py 상단에 경고 추가
"""
⚠️ DEPRECATED: V1 for backward compatibility.
Use V2 with MCP_USE_V2=true
"""
```

#### Phase 2: Gradual Rollout (1-2개월)

```
Week 1-2: V2 canary (10% traffic)
Week 3-4: V2 rollout (50% traffic)
Week 5-6: V2 default (90% traffic)
Week 7-8: V2 100%, V1 deprecated
```

#### Phase 3: Remove V1 (다음 Major Version)

```bash
# 제거 대상
rm server/mcp_server/handlers/graph_semantics_tools.py

# 수정 대상
server/mcp_server/handlers/__init__.py
- 버전 선택 로직 제거
- V2를 기본으로
```

---

## 3. UnifiedQueryAPI 일부 메서드

### 중복 가능성

```python
# src/agent/api/unified_query_api.py
class UnifiedQueryAPI:
    def find_taint_flows(...)  # ← DataflowUseCase와 중복?
    def find_call_chains(...)  # ← 추가 UseCase 필요?
    def find_data_dependencies(...)  # ← 추가 UseCase 필요?
```

### 분석 필요

```bash
$ grep -r "UnifiedQueryAPI" --include="*.py" | wc -l
```

**TODO**: 사용처 확인 후 통합 여부 결정

---

## 4. 정리 우선순위

| 항목 | 중복/레거시 | 영향 범위 | 우선순위 | 조치 |
|------|-------------|-----------|----------|------|
| **CodeFoundationContainer RFC-052** | 중복 | llm_arbitration (2곳) | P2 | ✅ Deprecation 마킹 |
| **graph_semantics_tools.py (V1)** | 레거시 | MCP clients | P1 | ✅ Deprecation 마킹 |
| **UnifiedQueryAPI 메서드** | 중복? | Agent tools | P3 | 분석 필요 |
| **CodeFoundationContainer 전체** | 중복? | 4곳 | P3 | 사용처 마이그레이션 |

---

## 5. Migration Timeline

### Immediate (완료)

- [x] Deprecation warnings 추가
- [x] V2 version selection 구현
- [x] Backward compatibility 보장

### Short-term (1-2개월)

- [ ] V2 canary deployment
- [ ] Monitor error rates
- [ ] Gradual rollout

### Mid-term (다음 Major Version)

- [ ] Remove V1 handler
- [ ] Remove CodeFoundationContainer RFC-052
- [ ] Consolidate UnifiedQueryAPI

### Long-term (선택)

- [ ] Merge CodeFoundationContainer into FoundationContainer
- [ ] Single DI container for code_foundation

---

## 6. Backward Compatibility Strategy

### Version Selection

```python
# Environment variable controls version
export MCP_USE_V2=true   # Use V2 (RFC-052)
export MCP_USE_V2=false  # Use V1 (default)
```

### Fallback Chain

```python
# V2 with V1 fallback
try:
    # V2 implementation
    usecase = foundation.create_slice_usecase(ir_doc)
    response = await usecase.execute(request)
except Exception:
    # Fallback to V1
    from server.mcp_server.handlers.graph_semantics_tools import graph_slice as v1
    return await v1(arguments)
```

### API Versioning

```
V1: /api/v1/graph/slice        ← Existing
V2: /api/v1/graph/v2/slice     ← New (RFC-052)

Both active for transition period
```

---

## 7. Testing During Transition

### Dual Testing

```bash
# Test V1
MCP_USE_V2=false pytest tests/unit/server/test_mcp_graph_tools.py

# Test V2
MCP_USE_V2=true pytest tests/integration/code_foundation/test_rfc052_complete_workflow.py

# Both
pytest tests/ -k "graph_slice or graph_dataflow"
```

### Canary Monitoring

```python
# Metrics to monitor
- V1 request count
- V2 request count
- V1 error rate
- V2 error rate
- V2 performance (vs V1)
```

---

## 8. Rollback Plan

If V2 has critical issues:

```bash
# Immediate rollback
export MCP_USE_V2=false

# Or code-level
# server/mcp_server/handlers/__init__.py
_use_v2 = False  # Force V1
```

---

## 9. Documentation Updates

### Update Required

- [ ] README: V1 vs V2 migration guide
- [ ] API Docs: V2 endpoints
- [ ] Deprecation notices
- [ ] Migration examples

---

## 10. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| V2 has bugs | Low | High | Dual testing, Gradual rollout |
| Performance regression | Low | Medium | Benchmarks, Monitoring |
| Breaking changes | Low | High | Backward compat, Version selection |
| Container confusion | Medium | Low | Deprecation warnings |

**Overall Risk: LOW** ✅

---

## Recommendation

### Immediate Actions (완료)

- [x] Deprecation warnings 추가
- [x] V2 version selection
- [x] Documentation

### Next Steps (1-2주)

1. V2 canary deployment (10% traffic)
2. Monitor metrics
3. Collect feedback

### Future (다음 Major Version)

1. Remove V1 handler
2. Remove CodeFoundationContainer RFC-052 duplicate
3. Single DI container

---

**Status: 레거시 정리 계획 수립 완료**
**Next: Gradual migration with monitoring**

