# Async/Await 구현 가이드

## 개요

SOTA급 async/await IR 생성 시스템.

## 주요 개념

### 1. SUSPEND vs RESUME

```python
# 코드
result = await fetch()

# IR
[SUSPEND Block]  # async call initiated
    ↓ (Event Loop)
[RESUME Block]   # result available
```

### 2. Exception Edges

```python
# 코드
try:
    await fetch()  # 실패 가능
except:
    handle()

# IR
[SUSPEND] ──success──→ [RESUME]
    └──exception──→ [CATCH]
```

## 지원 언어

### Python
```python
# 감지 패턴
await expr
result = await expr
return await expr
```

### JavaScript/TypeScript
```javascript
// 감지 패턴
await expr;
const result = await expr;
return await expr;
```

## 확장 방법

### 새 언어 추가 (Kotlin 예시)

1. **AST 패턴 정의**
```python
KOTLIN_AWAIT_TYPES = {
    "call_expression",  # suspend function call
}
```

2. **Detection 로직**
```python
def _is_await_statement(self, stmt):
    if self._current_language == "kotlin":
        # Kotlin suspend 감지
        return self._is_suspend_call(stmt)
```

3. **Expression 추출**
```python
def _extract_await_details(self, stmt, ast):
    if self._current_language == "kotlin":
        # Kotlin-specific extraction
        return self._extract_kotlin_suspend(stmt, ast)
```

4. **테스트**
```python
def test_kotlin_suspend():
    code = """
    suspend fun test() {
        val result = fetchData()
    }
    """
    # Verify SUSPEND/RESUME generation
```

## 성능 최적화

현재: O(N) - N = statements
향후: Lazy evaluation + caching

## Troubleshooting

### Q: SUSPEND 블록이 생성 안 됨
A: `_is_await_statement` 확인. 언어별 AST 타입 검증.

### Q: Expression이 "unknown"
A: `_extract_await_details` 확인. Deep search 로직 점검.

### Q: Exception edge 누락
A: `_build_try_context_map` 확인. Try 블록 감지 검증.

## 참고

- Tree-sitter 파서 사용
- AST → BFG → CFG 파이프라인
- 언어별 AST 구조: https://tree-sitter.github.io/
