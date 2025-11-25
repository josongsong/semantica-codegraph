# File I/O Integration Complete

**완료일**: 2025-11-25
**목표**: 모든 모드에 실제 파일 I/O 통합

---

## ✅ 완료 항목

### 1. 공유 파일 읽기 유틸리티 생성

**파일**: [src/agent/utils.py](src/agent/utils.py:1-202) (202 lines)

#### 핵심 기능

**파일 읽기 함수들**:
```python
- read_file(path, max_lines): 전체 파일 또는 제한된 줄 수 읽기
- read_file_lines(path, start, end, context): 특정 라인 범위 + 컨텍스트 읽기
- read_multiple_files(paths, max_lines_per_file): 여러 파일 읽기 & 연결
- safe_read_file(path, fallback): 에러 발생 시 fallback 반환
- get_file_context(path, line_number, context_lines): 특정 라인 주변 컨텍스트
```

**에러 처리**:
```python
- FileReadError: 사용자 정의 예외
- 파일 없음 처리
- 디렉토리 처리
- UTF-8 디코딩 에러 처리
- 권한 에러 처리
```

**특징**:
- 라인 번호 포함 출력 (디버깅용)
- 컨텍스트 라인 지원
- 파일별 구분자 추가
- 여러 파일 실패 시 계속 진행 (logging)

---

### 2. Implementation Mode 업데이트

**파일**: [src/agent/modes/implementation.py](src/agent/modes/implementation.py:18)

**변경사항**:
```python
# Before
def _get_related_code(self, context: ModeContext) -> str:
    return "\n".join([f"# File: {f}" for f in context.current_files[:5]])

# After
def _get_related_code(self, context: ModeContext) -> str:
    files_to_read = context.current_files[:5]
    return read_multiple_files(files_to_read, max_lines_per_file=500)
```

**효과**:
- 최대 5개 파일 읽기
- 파일당 최대 500줄
- 실제 코드를 LLM에 전달
- 코드 생성 시 정확한 컨텍스트 제공

---

### 3. Debug Mode 업데이트

**파일**: [src/agent/modes/debug.py](src/agent/modes/debug.py:25)

**변경사항**:
```python
# Before
async def _get_error_context(self, error_location, context):
    return f"# File: {file_path}\n# Error at line {line_num}"

# After
async def _get_error_context(self, error_location, context):
    if not error_location:
        return read_multiple_files(context.current_files[:3], max_lines_per_file=200)

    file_path = error_location.get("file_path", "")
    line_num = error_location.get("line_number", 0)

    # Get 10 lines of context before/after error
    return get_file_context(file_path, line_num, context_lines=10)
```

**효과**:
- 에러 발생 위치 ±10줄 읽기
- 스택 트레이스 컨텍스트 제공
- 정확한 에러 위치 파악
- 관련 코드를 LLM에 전달하여 fix 생성

---

### 4. Test Mode 업데이트

**파일**: [src/agent/modes/test.py](src/agent/modes/test.py:25)

**변경사항**:
```python
# Before
def _get_code_to_test(self, context: ModeContext) -> str:
    return "\n".join([f"# File: {f}" for f in context.current_files[:3]])

# After
def _get_code_to_test(self, context: ModeContext) -> str:
    return read_multiple_files(context.current_files[:3], max_lines_per_file=300)
```

**효과**:
- 최대 3개 파일 읽기
- 파일당 최대 300줄
- 테스트 대상 코드를 LLM에 전달
- 정확한 테스트 생성

---

### 5. Documentation Mode 업데이트

**파일**: [src/agent/modes/documentation.py](src/agent/modes/documentation.py:25)

**변경사항**:
```python
# Before
def _get_code_to_document(self, context: ModeContext) -> str:
    return "\n".join([f"# File: {f}" for f in context.current_files[:5]])

# After
def _get_code_to_document(self, context: ModeContext) -> str:
    return read_multiple_files(context.current_files[:5], max_lines_per_file=400)
```

**효과**:
- 최대 5개 파일 읽기
- 파일당 최대 400줄
- 문서화 대상 코드를 LLM에 전달
- 정확한 docstring/README 생성

---

### 6. 포괄적 테스트 추가

**파일**: [tests/agent/test_file_io.py](tests/agent/test_file_io.py:1-335) (335 lines)

#### 테스트 커버리지: **16/16 통과**

**TestReadFile** (4 tests):
- ✅ test_read_existing_file
- ✅ test_read_file_with_max_lines
- ✅ test_read_nonexistent_file
- ✅ test_read_directory

**TestReadFileLines** (3 tests):
- ✅ test_read_specific_lines
- ✅ test_read_lines_with_context
- ✅ test_read_lines_until_eof

**TestReadMultipleFiles** (3 tests):
- ✅ test_read_multiple_files
- ✅ test_read_multiple_files_with_limit
- ✅ test_read_multiple_files_with_errors

**TestSafeReadFile** (3 tests):
- ✅ test_safe_read_existing_file
- ✅ test_safe_read_nonexistent_file
- ✅ test_safe_read_default_fallback

**TestGetFileContext** (3 tests):
- ✅ test_get_file_context
- ✅ test_get_file_context_near_start
- ✅ test_get_file_context_error

**테스트 방법**:
- `tempfile.NamedTemporaryFile` 사용하여 임시 파일 생성
- 테스트 후 자동 삭제 (cleanup)
- 에러 케이스 검증 (FileReadError)

---

## 📊 전체 테스트 현황

### 최종 테스트 결과

| 파일 | 테스트 수 | 통과 | 변경 |
|------|----------|------|------|
| test_context_nav.py | 9 | ✅ 9/9 | - |
| test_debug.py | 12 | ✅ 12/12 | - |
| test_documentation.py | 19 | ✅ 19/19 | - |
| test_e2e_flow.py | 8 | ✅ 8/8 | - |
| **test_file_io.py** | **16** | **✅ 16/16** | **✅ NEW** |
| test_fsm.py | 12 | ✅ 12/12 | - |
| test_fsm_week1.py | 3 | ✅ 3/3 | - |
| test_implementation.py | 10 | ✅ 10/10 | - |
| test_orchestrator.py | 22 | ✅ 22/22 | - |
| test_test_mode.py | 17 | ✅ 17/17 | - |
| **총계** | **128** | **✅ 128/128** | **+16** |

**100% 성공률** 🎉

---

## 🔍 주요 설계 결정

### 1. **파일 제한 정책**

각 모드별로 다른 파일 제한:

```python
Implementation Mode: 최대 5개 파일, 500줄/파일 (가장 많은 컨텍스트)
Debug Mode:          최대 3개 파일, 200줄/파일 + 에러 위치 ±10줄
Test Mode:           최대 3개 파일, 300줄/파일 (테스트 생성)
Documentation Mode:  최대 5개 파일, 400줄/파일 (문서화)
```

**이유**:
- LLM 토큰 제한 고려
- 모드별 필요 컨텍스트 크기 다름
- 과도한 컨텍스트는 정확도 저하

### 2. **에러 컨텍스트 전략**

**Debug Mode 전용 기능**:
```python
get_file_context(file_path, line_number, context_lines=10)
```

**특징**:
- 에러 발생 라인 중심으로 컨텍스트 제공
- 라인 번호 포함 (디버깅 용이)
- 에러 위치 정확히 파악

**출력 예시**:
```
  45 | def calculate(x, y):
  46 |     result = x / y  # Error here
  47 |     return result
```

### 3. **라인 번호 포함 출력**

**read_file_lines 출력 형식**:
```python
   1 | import os
   2 | import sys
   3 |
   4 | def main():
   5 |     pass
```

**장점**:
- LLM이 정확한 위치 파악 가능
- 에러 메시지의 라인 번호와 매칭
- 코드 리뷰 시 편리

### 4. **에러 처리 계층**

**3단계 에러 처리**:

1. **read_file**: 예외 발생 (FileReadError)
2. **read_multiple_files**: 로그 + 계속 진행
3. **safe_read_file**: fallback 반환

**예시**:
```python
# 엄격한 처리 (단일 파일)
content = read_file(path)  # Raises FileReadError

# 관대한 처리 (여러 파일)
content = read_multiple_files(paths)  # Logs error, continues

# 안전한 처리 (optional)
content = safe_read_file(path, fallback="# Not found")  # Never raises
```

### 5. **파일 구분자**

**read_multiple_files 출력**:
```python
================================================================================
# File: src/models.py
================================================================================
[file content]

================================================================================
# File: src/utils.py
================================================================================
[file content]
```

**장점**:
- 여러 파일 구분 명확
- LLM이 파일 경계 인식
- 가독성 향상

---

## 📈 개선 효과

### Before (Placeholder)
```python
# File: src/calculator.py
# File: src/utils.py
# File: src/models.py
```

**문제점**:
- 파일 경로만 표시
- 실제 코드 없음
- LLM이 추측으로 코드 생성
- 정확도 낮음

### After (Actual I/O)
```python
================================================================================
# File: src/calculator.py
================================================================================
   1 | class Calculator:
   2 |     def __init__(self):
   3 |         self.result = 0
   4 |
   5 |     def add(self, x, y):
   6 |         return x + y
...
```

**개선점**:
- 실제 코드 내용 표시
- 라인 번호 포함
- LLM이 정확한 컨텍스트 기반 생성
- 정확도 향상
- 에러 위치 정확히 파악

---

## 🚀 실제 사용 시나리오

### Scenario 1: Implementation Mode

**사용자 요청**: "Add a method to calculate average"

**내부 동작**:
```python
# 1. Context에서 파일 목록 가져오기
context.current_files = ["src/calculator.py", "src/utils.py"]

# 2. 실제 파일 읽기
related_code = read_multiple_files(
    ["src/calculator.py", "src/utils.py"],
    max_lines_per_file=500
)

# 3. LLM에 전달
prompt = f"""
Current code:
{related_code}

User request: Add a method to calculate average

Generate the new method.
"""

# 4. LLM이 실제 코드를 보고 정확한 메서드 생성
```

### Scenario 2: Debug Mode

**에러 발생**:
```
File "src/calculator.py", line 15, in divide
    ZeroDivisionError: division by zero
```

**내부 동작**:
```python
# 1. 스택 트레이스에서 위치 추출
error_location = {
    "file_path": "src/calculator.py",
    "line_number": 15
}

# 2. 에러 주변 컨텍스트 읽기
error_context = get_file_context(
    "src/calculator.py",
    line_number=15,
    context_lines=10
)

# Output:
#    5 | class Calculator:
#   ...
#   13 |     def divide(self, x, y):
#   14 |         # No validation!
#   15 |         return x / y  # ERROR HERE
#   16 |
#   17 |     def multiply(self, x, y):

# 3. LLM이 에러 위치와 주변 코드 확인 후 fix 생성
fix = """
def divide(self, x, y):
    if y == 0:
        raise ValueError("Cannot divide by zero")
    return x / y
"""
```

### Scenario 3: Test Mode

**사용자 요청**: "Generate tests for calculator"

**내부 동작**:
```python
# 1. 테스트 대상 코드 읽기
code_to_test = read_multiple_files(
    ["src/calculator.py"],
    max_lines_per_file=300
)

# 2. LLM이 실제 코드를 보고 테스트 생성
# - 모든 메서드 확인
# - 파라미터 타입 확인
# - Edge cases 파악

tests = """
def test_add():
    calc = Calculator()
    assert calc.add(2, 3) == 5
    assert calc.add(-1, 1) == 0

def test_divide():
    calc = Calculator()
    assert calc.divide(10, 2) == 5
    with pytest.raises(ValueError):
        calc.divide(10, 0)
"""
```

---

## 💡 추가 개선 아이디어

### 1. **파일 캐싱**

**현재**: 매번 파일 읽기
**개선**: 파일 캐싱으로 성능 향상

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def read_file_cached(file_path: str, max_lines: Optional[int] = None) -> str:
    return read_file(file_path, max_lines)
```

**장점**:
- 동일 파일 반복 읽기 시 성능 향상
- 메모리 사용량 제어 (LRU)

### 2. **대용량 파일 처리**

**현재**: max_lines로 제한
**개선**: 청킹 + 관련성 기반 선택

```python
def read_relevant_chunks(
    file_path: str,
    query: str,
    chunk_size: int = 100,
    top_k: int = 3
) -> str:
    # 1. 파일을 청크로 분할
    # 2. 각 청크의 관련성 스코어링
    # 3. 상위 k개 청크 반환
    pass
```

**장점**:
- 대용량 파일에서 관련 부분만 추출
- LLM 토큰 제한 회피

### 3. **Binary 파일 처리**

**현재**: UTF-8 텍스트 파일만 지원
**개선**: Binary 파일 감지 & 스킵

```python
def is_binary_file(file_path: str) -> bool:
    with open(file_path, "rb") as f:
        chunk = f.read(1024)
        return b'\0' in chunk

def read_file(file_path: str, ...) -> str:
    if is_binary_file(file_path):
        return f"# Binary file: {file_path}\n"
    # ... normal reading
```

### 4. **파일 변경 감지**

**추가 기능**: 파일 수정 시 캐시 무효화

```python
import os
from datetime import datetime

file_mtimes = {}

def read_file_with_cache_invalidation(file_path: str) -> str:
    mtime = os.path.getmtime(file_path)
    if file_path in file_mtimes and file_mtimes[file_path] != mtime:
        # Invalidate cache
        read_file_cached.cache_clear()

    file_mtimes[file_path] = mtime
    return read_file_cached(file_path)
```

---

## ✅ 결론

### 성과

1. ✅ **공유 유틸리티 생성**
   - 5개 파일 읽기 함수
   - 포괄적 에러 처리
   - 202 lines

2. ✅ **모든 모드 업데이트**
   - Implementation Mode
   - Debug Mode
   - Test Mode
   - Documentation Mode

3. ✅ **16개 테스트 추가**
   - 모든 파일 읽기 함수 커버
   - 임시 파일 사용
   - 에러 케이스 검증

4. ✅ **기존 테스트 100% 통과**
   - 128/128 테스트 통과
   - 하위 호환성 유지
   - 회귀 없음

5. ✅ **실제 파일 I/O 통합**
   - Placeholder → 실제 파일 읽기
   - LLM 컨텍스트 정확도 향상
   - 모든 모드에서 실제 코드 활용

### 주요 변경 사항

**추가된 파일**:
- `src/agent/utils.py` (202 lines) - 파일 I/O 유틸리티
- `tests/agent/test_file_io.py` (335 lines) - 16개 테스트

**수정된 파일**:
- `src/agent/modes/implementation.py` - read_multiple_files 사용
- `src/agent/modes/debug.py` - get_file_context 사용
- `src/agent/modes/test.py` - read_multiple_files 사용
- `src/agent/modes/documentation.py` - read_multiple_files 사용

**영향**:
- 코드: +537 lines
- 테스트: +16 tests
- 테스트 커버리지: src/agent/utils.py 84%

### 다음 단계

**우선순위 1: Graph 통합** (Week 2 Day 5에서 언급됨)
```python
# Debug Mode에서
def _find_error_flow(self, error_location):
    # GraphStore 연결
    # Exception 추적
    # 호출 체인 분석
```

**우선순위 2: Coverage-guided 테스트 생성**
```python
# Test Mode에서
def _generate_tests(self, task, code_to_test, context):
    # Current coverage 분석
    # Low-coverage 함수 우선 테스트 생성
```

**우선순위 3: 파일 캐싱**
- 성능 최적화
- 반복 읽기 회피

---

**작성**: Claude Code
**검토**: -
**다음 리뷰**: Graph 통합 완료 시

---

## 📝 명령어 참고

**테스트 실행**:
```bash
# 파일 I/O 테스트만
pytest tests/agent/test_file_io.py -v

# 모든 agent 테스트
pytest tests/agent/ -v

# 특정 모드 테스트
pytest tests/agent/test_implementation.py tests/agent/test_debug.py -v
```

**사용 예시**:
```python
from src.agent.utils import read_file, get_file_context, read_multiple_files

# 단일 파일 읽기
content = read_file("src/calculator.py")

# 에러 컨텍스트 읽기
context = get_file_context("src/calculator.py", line_number=15, context_lines=5)

# 여러 파일 읽기
content = read_multiple_files(
    ["src/models.py", "src/utils.py"],
    max_lines_per_file=200
)
```
