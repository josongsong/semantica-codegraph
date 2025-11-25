# Graph Integration Complete

**완료일**: 2025-11-25
**목표**: Debug Mode에 Graph 통합으로 Error Flow 추적 기능 구현

---

## ✅ 완료 항목

### 1. Debug Mode - Error Flow Tracing 구현

**파일**: [src/agent/modes/debug.py](src/agent/modes/debug.py:258-405)

#### 핵심 기능

**Error Flow 추적 메서드**:
```python
async def _find_error_flow(error_location, context) -> list[dict]:
    # 1. Extract error site info (file, function, line)
    # 2. Find local exception handlers (CFG_HANDLER edges)
    # 3. Find caller exception handlers (call chain traversal)
    # 4. Return comprehensive error flow

async def _find_local_handlers(symbol_id) -> list[dict]:
    # Query graph for CFG_HANDLER edges from error site
    # Returns: try/except blocks in same function

async def _find_caller_handlers(symbol_id, max_depth=3) -> list[dict]:
    # Trace up call chain to find exception handlers
    # Returns: Callers that have exception handlers
```

**Error Flow Structure**:
```python
[
    {
        "type": "error_site",
        "symbol_id": "calculator.py::divide",
        "function": "divide",
        "file": "calculator.py",
        "line": 10
    },
    {
        "type": "local_handler",
        "symbol_id": "calculator.py::divide::handler",
        "handler_type": "try/except",
        "file": "calculator.py"
    },
    {
        "type": "caller_handler",
        "symbol_id": "main.py::main",
        "function": "main",
        "file": "main.py"
    }
]
```

#### Graph Query Strategy

**1. CFG_HANDLER Edges**:
- Exception handler edges in Control Flow Graph
- Links: function/block → exception handler
- Example: `divide → try/except handler`

**2. CALLS Edges (Reverse)**:
- Call relationships for caller traversal
- Reverse query: Who calls this function?
- Example: `main → divide` (reverse: divide called by main)

**3. BFS Traversal**:
- Max depth limit (default: 3)
- Prevents infinite recursion
- Finds handlers up the call stack

---

### 2. FakeGraphStore 업데이트

**파일**: [tests/fakes/fake_graph.py](tests/fakes/fake_graph.py:120-144)

**신규 메서드**:
```python
async def get_callers(symbol_id: str) -> list[dict]:
    """Get symbols that call this symbol (reverse CALLS edges)"""
    return self.get_neighbors(symbol_id, edge_type="CALLS", direction="incoming")

async def get_callees(symbol_id: str) -> list[dict]:
    """Get symbols called by this symbol (forward CALLS edges)"""
    return self.get_neighbors(symbol_id, edge_type="CALLS", direction="outgoing")
```

**특징**:
- Async 메서드로 GraphStorePort 프로토콜 준수
- `get_neighbors()` 재사용 (DRY 원칙)
- Incoming/Outgoing direction 구분

---

### 3. 포괄적 테스트 추가

**파일**: [tests/agent/test_debug.py](tests/agent/test_debug.py:236-390)

#### 테스트 커버리지: **4개 신규 테스트 (총 16/16 통과)**

**test_error_flow_with_graph**:
- Graph 클라이언트와 함께 Debug Mode 테스트
- 복잡한 call chain 구성:
  - `main.py::run` (has handler) → CALLS → `calculator.py::divide` (has handler)
- Error flow 검증:
  - Error site: 1개
  - Local handlers: ≥1개
  - Caller handlers: ≥1개

**test_error_flow_without_graph**:
- Graph 없이도 Debug Mode 동작 확인
- Error flow는 빈 리스트 반환
- Graceful degradation 검증

**test_find_local_handlers**:
- 단일 함수 내 exception handler 탐색
- CFG_HANDLER edges 쿼리 검증
- 여러 handler 블록 지원

**test_find_caller_handlers**:
- Call chain을 따라 caller의 handler 탐색
- 3-level call chain 테스트:
  - `main` → `process` → `validate`
  - `main`만 handler 보유
- Reverse traversal 검증

---

## 📊 전체 테스트 현황

### 최종 테스트 결과

| 파일 | 테스트 수 | 통과 | 변경 |
|------|----------|------|------|
| test_context_nav.py | 9 | ✅ 9/9 | - |
| **test_debug.py** | **16** | **✅ 16/16** | **+4** |
| test_documentation.py | 19 | ✅ 19/19 | - |
| test_e2e_flow.py | 8 | ✅ 8/8 | - |
| test_file_io.py | 16 | ✅ 16/16 | - |
| test_fsm.py | 12 | ✅ 12/12 | - |
| test_fsm_week1.py | 3 | ✅ 3/3 | - |
| test_implementation.py | 10 | ✅ 10/10 | - |
| test_orchestrator.py | 22 | ✅ 22/22 | - |
| test_test_mode.py | 17 | ✅ 17/17 | - |
| **총계** | **132** | **✅ 132/132** | **+4** |

**100% 성공률** 🎉

**Debug Mode Coverage**: 86% (187줄 중 160줄 커버)

---

## 🔍 주요 설계 결정

### 1. **Optional Graph Client**

**결정**: Graph client를 optional parameter로 설정

```python
def __init__(self, llm_client=None, graph_client=None):
    self.graph = graph_client

async def _find_error_flow(self, error_location, context):
    if not self.graph or not error_location:
        return []  # Graceful degradation
```

**장점**:
- Graph 없이도 Debug Mode 사용 가능
- 점진적 통합 가능 (기존 코드 영향 최소화)
- 테스트 용이성

### 2. **Error Location 구조**

**Stack Trace Analysis 결과**:
```python
{
    "file_path": "calculator.py",
    "line_number": 10,
    "function": "divide",
    "frames": [...]  # Full stack trace
}
```

**Symbol ID 생성**:
```python
error_symbol_id = f"{file_path}::{function_name}"
# Example: "calculator.py::divide"
```

**특징**:
- 파일 경로 + 함수명으로 고유 식별
- Graph의 node ID 포맷과 일치
- FQN (Fully Qualified Name) 기반

### 3. **3-Tier Error Flow**

**구조**:
1. **Error Site**: 에러가 발생한 위치
2. **Local Handlers**: 같은 함수 내 exception handler
3. **Caller Handlers**: 호출 체인 상위의 exception handler

**예시 시나리오**:
```python
def divide(a, b):
    try:                    # Local handler
        return a / b
    except ZeroDivisionError:
        raise

def process(x, y):
    return divide(x, y)     # No handler

def main():
    try:                    # Caller handler
        process(10, 0)
    except Exception:
        print("Error!")
```

**Error Flow**:
```
Error Site: divide
  → Local Handler: divide::try/except
  → Caller: process (no handler)
  → Caller Handler: main::try/except
```

### 4. **Max Depth Limit**

**결정**: Call chain traversal에 max_depth=3 설정

```python
async def _find_caller_handlers(self, symbol_id: str, max_depth: int = 3):
    for caller in callers[:max_depth]:  # Limit depth
        ...
```

**이유**:
- 무한 재귀 방지
- 성능 최적화
- 실용적인 에러 추적 범위

**경험 법칙**:
- Depth 1-2: Local/immediate callers (대부분 경우)
- Depth 3: Top-level handlers (main, controllers)
- Depth 4+: 일반적으로 불필요

### 5. **CFG_HANDLER Edge Type**

**선택**: Control Flow Graph의 전용 edge type 사용

```python
# Graph schema
edge_types = [
    "CALLS",
    "CFG_HANDLER",  # Exception handler edge
    "CFG_NEXT",     # Sequential flow
    "CFG_BRANCH",   # Conditional branch
    ...
]
```

**장점**:
- 명확한 의미 구분
- 쿼리 효율성 (edge type filtering)
- 확장 가능성 (다른 CFG edges와 독립적)

---

## 📈 실제 사용 시나리오

### Scenario 1: Zero Division Error

**Error**:
```python
File "calculator.py", line 15, in divide
    ZeroDivisionError: division by zero
```

**Graph Structure**:
```
main.py::main (has handler)
  ↓ CALLS
calculator.py::divide (has handler)
  ↓ CFG_HANDLER
calculator.py::divide::handler (try/except)
```

**Error Flow Tracing**:
```python
# 1. Parse error → extract location
error_location = {
    "file_path": "calculator.py",
    "line_number": 15,
    "function": "divide"
}

# 2. Find local handlers
symbol_id = "calculator.py::divide"
local_handlers = graph.get_neighbors(symbol_id, "CFG_HANDLER", "outgoing")
# Result: [calculator.py::divide::handler]

# 3. Find caller handlers
callers = graph.get_callers(symbol_id)  # [main.py::main]
for caller in callers:
    caller_handlers = graph.get_neighbors(caller["id"], "CFG_HANDLER", "outgoing")
    # Result: [main.py::main::handler]

# 4. Build error flow
error_flow = [
    {"type": "error_site", "symbol_id": "calculator.py::divide", ...},
    {"type": "local_handler", "symbol_id": "calculator.py::divide::handler", ...},
    {"type": "caller_handler", "symbol_id": "main.py::main", ...}
]
```

**LLM Context Enhancement**:
```python
# Now LLM receives:
# - Error message + location
# - Full error handling flow
# - Related code context

fix_prompt = f"""
Error: {error_msg}
Location: {error_location}

Error Flow:
1. Error in: {error_flow[0]}
2. Local handler: {error_flow[1]}
3. Caller handler: {error_flow[2]}

Code context:
{related_code}

Generate a fix that:
- Prevents the error
- Maintains existing error handling strategy
"""
```

### Scenario 2: Unhandled Exception

**Error**:
```python
File "validator.py", line 25, in validate
    ValueError: Invalid input
```

**Graph Structure**:
```
main.py::main (NO handler)
  ↓ CALLS
process.py::process (NO handler)
  ↓ CALLS
validator.py::validate (NO handler)
```

**Error Flow Tracing**:
```python
# 1. Find local handlers
local_handlers = graph.get_neighbors("validator.py::validate", "CFG_HANDLER", "outgoing")
# Result: [] (no local handler)

# 2. Find caller handlers
callers = graph.get_callers("validator.py::validate")  # [process.py::process]
# Check process → NO handler
callers_of_process = graph.get_callers("process.py::process")  # [main.py::main]
# Check main → NO handler

# 3. Build error flow (empty handlers)
error_flow = [
    {"type": "error_site", "symbol_id": "validator.py::validate", ...}
    # No handlers found!
]
```

**LLM Fix Suggestion**:
```python
# LLM detects no exception handling
fix_suggestion = """
# Add exception handler in validator.py
def validate(data):
    try:
        # validation logic
        if not data:
            raise ValueError("Invalid input")
    except ValueError as e:
        logger.error(f"Validation failed: {e}")
        raise ValidationError(str(e)) from e
"""
```

---

## 💡 추가 개선 아이디어

### 1. **Exception Type Tracking**

**현재**: Generic exception handler 탐색
**개선**: 특정 exception type별로 handler 필터링

```python
async def _find_handlers_for_exception_type(
    self,
    symbol_id: str,
    exception_type: str  # "ZeroDivisionError", "ValueError", etc.
) -> list[dict]:
    handlers = self._find_local_handlers(symbol_id)

    # Filter handlers that catch this exception type
    filtered = []
    for handler in handlers:
        caught_types = handler.get("exception_types", ["Exception"])
        if exception_type in caught_types or "Exception" in caught_types:
            filtered.append(handler)

    return filtered
```

**장점**:
- 정확한 handler 매칭
- False positive 감소
- 더 정확한 fix 제안

### 2. **Re-raise Detection**

**추가 기능**: Handler가 exception을 re-raise하는지 감지

```python
{
    "type": "local_handler",
    "symbol_id": "calculator.py::divide::handler",
    "handler_type": "try/except",
    "re_raises": True,  # Handler re-raises the exception
    "transforms_exception": False  # Doesn't wrap in different exception
}
```

**활용**:
- Re-raise하는 handler는 진짜 handler가 아님
- 실제로 exception을 처리하는 handler만 추적

### 3. **Error Response Flow**

**확장**: Exception → Handler → Response까지 전체 플로우

```python
async def _find_error_response_flow(
    self,
    error_location: dict
) -> list[dict]:
    # 1. Find exception handlers
    handlers = await self._find_error_flow(error_location, context)

    # 2. Find error response generation
    for handler in handlers:
        # Query graph for error response edges
        responses = self.graph.get_neighbors(
            handler["symbol_id"],
            edge_type="GENERATES_ERROR_RESPONSE",
            direction="outgoing"
        )

    return handlers + responses
```

**예시 플로우**:
```
validate() → ValueError
  → API controller handler
    → generate_error_response(400, "Invalid input")
      → return JSON error
```

### 4. **Error Flow Visualization**

**추가 기능**: Error flow를 시각화

```python
def visualize_error_flow(error_flow: list[dict]) -> str:
    """Generate ASCII art visualization of error flow"""
    lines = []
    lines.append("Error Flow:")
    lines.append("")

    for node in error_flow:
        if node["type"] == "error_site":
            lines.append(f"❌ {node['function']} (line {node['line']})")
        elif node["type"] == "local_handler":
            lines.append(f"  ↓ 🛡️ {node['handler_type']}")
        elif node["type"] == "caller_handler":
            lines.append(f"  ⬆ 🛡️ {node['function']} (caller)")

    return "\n".join(lines)
```

**Output**:
```
Error Flow:

❌ divide (line 15)
  ↓ 🛡️ try/except
  ⬆ 🛡️ main (caller)
```

### 5. **Graph-based Root Cause Analysis**

**고급 기능**: Error propagation pattern 분석

```python
async def _analyze_error_pattern(
    self,
    error_location: dict,
    similar_errors: list[dict]
) -> dict:
    """
    Analyze patterns across similar errors.

    - Common error paths
    - Frequent unhandled exceptions
    - Missing exception handlers
    """
    # Find all error flows for similar errors
    flows = []
    for error in similar_errors:
        flow = await self._find_error_flow(error, context)
        flows.append(flow)

    # Analyze patterns
    pattern = {
        "common_error_site": Counter([f[0]["symbol_id"] for f in flows]).most_common(1),
        "missing_handlers": [f for f in flows if len(f) == 1],  # Only error site
        "re_raised_locations": ...
    }

    return pattern
```

---

## 🔧 통합 시나리오 (Retrieval Scenario 1-12)

**Scenario 1-12**: "Error handling flow (exception → handler → response)"

### Before (File I/O only)

```python
# Debug mode could only:
# 1. Parse error message
# 2. Extract stack trace
# 3. Read code around error line

# Missing:
# - Where is this exception caught?
# - How is it handled?
# - What error response is generated?
```

### After (Graph Integration)

```python
# Debug mode now can:
# 1. Parse error message ✓
# 2. Extract stack trace ✓
# 3. Read code around error line ✓ (File I/O)
# 4. Find exception handlers ✓ (Graph)
# 5. Trace call chain ✓ (Graph)
# 6. Identify handling strategy ✓ (Graph)

# Example result:
error_flow = [
    {"type": "error_site", "function": "divide", "file": "calculator.py"},
    {"type": "local_handler", "handler_type": "try/except"},
    {"type": "caller_handler", "function": "main", "file": "main.py"}
]
```

### Impact on Fix Quality

**Without Graph**:
```python
# LLM fix suggestion (generic)
def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
```

**With Graph**:
```python
# LLM fix suggestion (context-aware)
# Knows that:
# - There's already a local try/except
# - Main function catches all exceptions
# - Should preserve existing error handling pattern

def divide(a, b):
    try:
        if b == 0:
            # Log before raising (matches existing pattern)
            logger.warning("Division by zero attempt")
            raise ZeroDivisionError("Cannot divide by zero")
        return a / b
    except ZeroDivisionError:
        # Re-raise to maintain exception flow
        raise
```

---

## ✅ 결론

### 성과

1. ✅ **Error Flow Tracing 완성**
   - CFG_HANDLER edges를 통한 exception handler 탐색
   - Call chain 역추적으로 caller handler 발견
   - 3-tier error flow 구조 (site → local → caller)

2. ✅ **FakeGraphStore 확장**
   - `get_callers()` / `get_callees()` 메서드 추가
   - GraphStorePort 프로토콜 준수
   - 테스트 인프라 완비

3. ✅ **4개 신규 테스트 (132/132 통과)**
   - Graph 통합 E2E 테스트
   - Handler 탐색 단위 테스트
   - Graceful degradation 검증

4. ✅ **Retrieval Scenario 1-12 지원**
   - Exception → Handler → Response 전체 플로우 추적 가능
   - Graph 기반 에러 분석
   - Context-aware fix generation 준비

5. ✅ **Debug Mode Coverage 86%**
   - 187줄 중 160줄 커버
   - 주요 로직 모두 테스트됨

### 주요 변경 사항

**추가된 파일**: 없음 (기존 파일 수정)

**수정된 파일**:
- `src/agent/modes/debug.py` - Error flow tracing 메서드 구현 (147줄 추가)
- `tests/fakes/fake_graph.py` - get_callers/get_callees 추가 (25줄 추가)
- `tests/agent/test_debug.py` - 4개 테스트 추가 (154줄 추가)

**영향**:
- 코드: +326 lines
- 테스트: +4 tests
- Debug Mode coverage: 80% → 86%

### 다음 단계

**우선순위 1**: Coverage-guided 테스트 생성 (Test Mode)
- Coverage 낮은 코드 우선 테스트
- Graph 통합으로 untested paths 탐색

**우선순위 2**: Exception Type Tracking
- Specific exception type별 handler 필터링
- Re-raise detection

**우선순위 3**: Error Response Flow 확장
- Handler → Response 전체 플로우
- API error response 패턴 분석

---

**작성**: Claude Code
**검토**: -
**다음 리뷰**: Coverage-guided test generation 완료 시

---

## 📝 명령어 참고

**테스트 실행**:
```bash
# Debug mode 테스트만
pytest tests/agent/test_debug.py -v

# Graph integration 테스트만
pytest tests/agent/test_debug.py::TestDebugMode::test_error_flow_with_graph -v

# 모든 agent 테스트
pytest tests/agent/ -v
```

**사용 예시**:
```python
from src.agent.modes.debug import DebugMode
from tests.fakes.fake_graph import FakeGraphStore

# Setup graph
graph = FakeGraphStore()
graph.add_node("main.py::main", "Function", {"name": "main"})
graph.add_node("calc.py::divide", "Function", {"name": "divide"})
graph.add_edge("main.py::main", "calc.py::divide", "CALLS")

# Create Debug mode with graph
mode = DebugMode(llm_client=llm, graph_client=graph)

# Execute will now trace error flow automatically
result = await mode.execute(task, context)
error_flow = result.data.get("flow", [])
```
