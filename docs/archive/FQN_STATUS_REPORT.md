# FQN (Fully Qualified Name) 구현 상태 보고서

**작성일**: 2025-12-27
**조사 대상**: Rust IR Builder, Python Taint Analysis, Pattern Matching

---

## 📋 요약

**질문**: "Option 3: FQN 매칭이 이미 구현되어 있지 않나?"

**답변**: **❌ 아니요, 현재 구현되어 있지 않습니다.**

현재 Rust IR Builder는 built-in 함수 호출 시 **단순 이름만 사용**합니다:
- ✅ 생성됨: `"input"`, `"eval"`, `"exec"`
- ❌ 생성 안 됨: `"builtins.input"`, `"builtins.eval"`

---

## 🔍 조사 결과

### 1. IR Builder 현황 (ir_builder.rs)

**FQN 생성 로직:**
```rust
// packages/codegraph-rust/codegraph-ir/src/features/ir_generation/infrastructure/ir_builder.rs

/// Build FQN from scope stack
fn build_fqn(&self, name: &str) -> String {
    let mut parts: Vec<&str> = self.scope_stack.iter()
        .map(|f| f.name.as_str())
        .collect();
    parts.push(name);
    parts.join(".")
}
```

**FQN이 생성되는 곳:**
1. **함수 정의**: `test.vulnerable_function` ✅
2. **클래스 정의**: `test.MyClass` ✅
3. **메서드 정의**: `test.MyClass.method1` ✅
4. **변수 정의**: `vulnerable_function.user_input` ✅

**FQN이 생성되지 않는 곳:**
1. **Built-in 함수 호출**: `"input"` ❌ (Should be `"builtins.input"`)
2. **외부 모듈 함수 호출**: `"os.system"` ❌ (Import 해석 필요)

---

### 2. CALLS 엣지 생성 위치 (processor.rs)

**현재 코드:**
```rust
// packages/codegraph-rust/codegraph-ir/src/pipeline/processor.rs:909

// Extract calls
let calls = extract_calls_in_block(&body_node, source);
for call in calls {
    // Add CALLS edge
    builder.add_calls_edge(node_id.clone(), call.callee_name, call.span);
}
```

**문제점:**
- `call.callee_name`은 단순 문자열: `"input"`, `"eval"`
- 모듈 정보가 없음 (builtins, os, sys 등)

---

### 3. Call Extractor 현황 (call.rs)

**현재 코드:**
```rust
// packages/codegraph-rust/codegraph-ir/src/features/parsing/infrastructure/extractors/call.rs

pub struct CallInfo {
    pub callee_name: String,  // ← 단순 이름만 저장
    pub span: Span,
}

pub fn extract_calls_in_block(node: &TSNode, source: &str) -> Vec<CallInfo> {
    // ...
    let callee_name = get_node_text(&callee, source).to_string();
    calls.push(CallInfo {
        callee_name,  // "input", "eval" 등 단순 이름만
        span,
    });
}
```

---

### 4. 테스트 결과

**테스트 코드:**
```python
def vulnerable_function():
    user_input = input("Enter command: ")
    eval(user_input)
```

**IR 결과:**
```python
# Nodes (정의)
{
    "id": "3db6d0cc...",
    "kind": "Function",
    "name": "vulnerable_function",
    "fqn": "test.vulnerable_function"  # ✅ 모듈 포함
}

# Edges (호출)
{
    "source_id": "3db6d0cc...",
    "target_id": "input",  # ❌ 모듈 없음 (should be "builtins.input")
    "kind": "CALLS"
}
```

---

## 💡 구현 방안

### Option A: IR Builder에서 Built-in FQN 추가 (추천)

**장점:**
- ✅ 한 번만 수정하면 모든 분석에 적용됨
- ✅ Python 규칙과 완벽하게 매칭됨
- ✅ 다른 언어 확장 시에도 동일한 패턴 사용 가능

**구현 위치:**
```rust
// packages/codegraph-rust/codegraph-ir/src/pipeline/processor.rs

// Extract calls
let calls = extract_calls_in_block(&body_node, source);
for call in calls {
    // Resolve FQN for built-in functions
    let callee_fqn = resolve_callee_fqn(&call.callee_name);

    builder.add_calls_edge(node_id.clone(), callee_fqn, call.span);
}

fn resolve_callee_fqn(name: &str) -> String {
    // Python built-ins
    const PYTHON_BUILTINS: &[&str] = &[
        "input", "eval", "exec", "compile", "open",
        "print", "len", "range", "str", "int", "float"
    ];

    if PYTHON_BUILTINS.contains(&name) {
        format!("builtins.{}", name)
    } else {
        name.to_string()
    }
}
```

**예상 결과:**
```python
# 변경 전
{"target_id": "input"}  # ❌

# 변경 후
{"target_id": "builtins.input"}  # ✅
```

---

### Option B: Python 규칙을 단순 패턴으로 변경 (임시 방편)

**장점:**
- ✅ Rust 코드 수정 없이 즉시 적용 가능

**단점:**
- ❌ False positive 위험 (예: 사용자 정의 `input()` 함수도 매칭됨)
- ❌ 다른 언어로 확장 불가

**구현 예시:**
```python
# packages/codegraph-security/codegraph_security/domain/rules/sources.py

# 변경 전 (Regex on source text)
SourceRule(
    pattern=r"\binput\s*\(",  # ❌ IR에서는 동작 안 함
    description="User input"
)

# 변경 후 (Simple match on callee name)
SourceRule(
    pattern="input",  # ✅ IR target_id와 매칭됨
    description="User input",
    is_regex=False
)
```

---

## 🎯 추천 로드맵

### Phase 1: 긴급 패치 (1-2시간)
1. **Option B 구현**: Python 규칙을 단순 패턴으로 변경
2. **테스트**: `analyze_from_source()` 재실행하여 검증
3. **배포**: 즉시 사용 가능

### Phase 2: 장기 솔루션 (1-2일)
1. **Option A 구현**: Rust IR Builder에 FQN 해석 추가
2. **Import 해석**: `from os import system` → `"os.system"` 매칭
3. **규칙 업데이트**: Python 규칙을 FQN 기반으로 변경
   ```python
   SourceRule(pattern="builtins.input", is_regex=False)
   SinkRule(pattern="os.system", is_regex=False)
   ```

### Phase 3: 고급 기능 (2-3일)
1. **Type Resolution 통합**: 실제 타입 추론으로 정확도 향상
2. **Cross-file Resolution**: `from myapp.utils import validate` 매칭
3. **다국어 지원**: Java, TypeScript 등으로 확장

---

## ✅ 액션 아이템

### 즉시 실행 (P0)
- [ ] Python 규칙을 단순 패턴으로 변경 (`sources.py`, `sinks.py`)
- [ ] `FINAL_TEST_REPORT.md` 업데이트 (패턴 매칭 Gap 섹션)

### 이번 주 (P1)
- [ ] Rust IR Builder에 `resolve_callee_fqn()` 추가
- [ ] Built-in 함수 목록 정의 (Python, JavaScript, etc.)
- [ ] Integration test 추가 (`test_fqn_matching.py`)

### 다음 스프린트 (P2)
- [ ] Import resolver 구현 (cross-file FQN)
- [ ] TypeResolver와 통합
- [ ] Multi-language FQN 표준화

---

## 📊 현재 구현 vs 이상적 구현

| 기능 | 현재 상태 | 이상적 상태 | 구현 난이도 |
|------|----------|-----------|------------|
| Function 정의 FQN | ✅ `test.func` | ✅ `test.func` | - |
| Class 정의 FQN | ✅ `test.MyClass` | ✅ `test.MyClass` | - |
| Method 정의 FQN | ✅ `test.MyClass.method` | ✅ `test.MyClass.method` | - |
| Built-in 호출 | ❌ `"input"` | ✅ `"builtins.input"` | 🟢 쉬움 (4시간) |
| 외부 모듈 호출 | ❌ `"system"` | ✅ `"os.system"` | 🟡 중간 (2일) |
| Import alias | ❌ 지원 안 됨 | ✅ `"np.array"` → `"numpy.array"` | 🔴 어려움 (1주) |

---

## 🔍 코드 위치 참고

### Rust (codegraph-ir)
- **FQN 생성**: `packages/codegraph-rust/codegraph-ir/src/features/ir_generation/infrastructure/ir_builder.rs:122-129`
- **CALLS 엣지**: `packages/codegraph-rust/codegraph-ir/src/pipeline/processor.rs:906-910`
- **Call 추출**: `packages/codegraph-rust/codegraph-ir/src/features/parsing/infrastructure/extractors/call.rs`

### Python (codegraph-security)
- **규칙 정의**: `packages/codegraph-security/codegraph_security/domain/rules/sources.py`
- **분석 서비스**: `packages/codegraph-security/codegraph_security/application/services/analysis_service.py:302-359`

---

## 결론

**FQN 매칭은 현재 구현되어 있지 않지만**, 구현이 어렵지 않습니다:

1. **단기**: Python 규칙 패턴을 단순화하여 즉시 사용 가능 (2시간)
2. **장기**: Rust IR Builder에 FQN 해석 추가하여 정확도 향상 (2일)

**추천**: 먼저 단기 솔루션으로 빠르게 배포하고, 장기 솔루션을 병행 개발하세요.

---

**보고서 생성**: 2025-12-27
**작성자**: Claude (Sonnet 4.5)
**상태**: ✅ 조사 완료
