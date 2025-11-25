# IR Generation 병목 분석 및 최적화 전략

## 프로파일링 결과 요약

**테스트**: 50개 파일, 총 134ms (평균 2.7ms/file)

### 주요 병목 지점 (Cumulative Time)

| 함수 | 누적 시간 | 호출 횟수 | 파일당 평균 | 비율 |
|------|----------|----------|------------|------|
| `_calculate_cf_summary` | 33ms | 223 | 148μs | 24.6% |
| `process_calls_in_block` | 24ms | 223 | 108μs | 17.9% |
| `_process_single_call` | 15ms | 1,171 | 13μs | 11.2% |
| `has_loop` | 12ms | 22,806 | 0.5μs | 9.0% |
| **Total IR bottlenecks** | **84ms** | | | **62.7%** |

### Self Time 분석 (실제 계산 시간)

| 함수 | Self Time | 호출 횟수 | 문제 |
|------|----------|----------|------|
| `count_branches` | 8ms | 28,729 | 재귀 호출 과다 |
| `_find_calls_recursive` | 7-9ms | 28,729 | 재귀 호출 과다 |
| `has_loop` | 5ms | 22,806 | 재귀 호출 과다 |
| `any()` built-in | 6ms | 38,207 | 불필요한 검사 |

---

## 핵심 병목 3가지

### 1. Cyclomatic Complexity 계산 (33ms, 25%)

**문제**:
```python
def _calculate_cf_summary(self, node):
    """223번 호출, 각각 148μs"""
    cc = self.calculate_cyclomatic_complexity(node)  # 재귀
    has_loop = self.has_loop(node)                   # 재귀 (22,806번 호출!)
    has_try = self.has_try(node)                     # 재귀 (15,512번 호출!)
    # ...
```

**문제점**:
- `has_loop()`: 22,806번 호출 (재귀로 AST 전체 순회)
- `count_branches()`: 28,729번 호출
- `has_try()`: 15,512번 호출
- 각 function마다 AST를 여러 번 재귀적으로 순회

**최적화 방향**:
- ✅ **Single-pass CF calculation**: 한 번의 순회로 모든 CF 메트릭 계산
- ✅ **Iterative 방식**: 재귀 → Stack 기반 iteration
- ✅ **Memoization**: 중복 계산 제거

---

### 2. Call Analysis (39ms, 29%)

**문제**:
```python
def process_calls_in_block(self, node, ...):
    """223번 호출, 각각 108μs"""
    calls = self._find_calls_recursive(node)  # 재귀 (28,729번 호출!)
    for call in calls:
        self._process_single_call(call, ...)  # 1,171번 호출, 각 13μs
```

**문제점**:
- `_find_calls_recursive()`: 재귀로 모든 call expression 찾기
- 28,729번의 재귀 호출
- `collect_parts()`: 1,770번 호출 (nested call handling)

**최적화 방향**:
- ✅ **Iterative call finding**: Stack 기반으로 변경
- ✅ **Early exit**: 불필요한 subtree 탐색 스킵
- ⚠️ **Parallel processing**: 함수별 병렬 처리 (선택적)

---

### 3. 과도한 `any()` 호출 (6ms, 4.5%)

**문제**:
```python
# 38,207번 호출!
if any(keyword in node.type for keyword in ["while", "for", ...]):
    # ...
```

**문제점**:
- Pattern matching에 `any()` + generator 사용
- 매번 새로운 generator 생성
- 38,207번의 불필요한 iteration

**최적화 방향**:
- ✅ **Direct string matching**: `node.type in LOOP_KEYWORDS` (set lookup)
- ✅ **Pre-compiled patterns**: 상수로 정의
- ✅ **Early exit**: 첫 번째 match에서 즉시 return

---

## 최적화 전략

### Phase 1: CF Calculation 최적화 (예상 -20ms, 15%)

#### 1.1 Single-Pass CF Metrics

**Before**:
```python
def _calculate_cf_summary(self, node):
    cc = self.calculate_cyclomatic_complexity(node)  # Pass 1
    has_loop = self.has_loop(node)                   # Pass 2 (22,806 calls)
    has_try = self.has_try(node)                     # Pass 3 (15,512 calls)
    branches = self.count_branches(node)             # Pass 4 (28,729 calls)
    # → 4번의 재귀 순회!
```

**After**:
```python
def _calculate_cf_summary_optimized(self, node):
    """Single pass through AST"""
    metrics = CFMetrics()

    # Single iterative traversal
    stack = [node]
    while stack:
        current = stack.pop()

        # Update all metrics in one pass
        if current.type in BRANCH_KEYWORDS:
            metrics.branches += 1
            metrics.cc += 1
        if current.type in LOOP_KEYWORDS:
            metrics.has_loop = True
            metrics.cc += 1
        if current.type in TRY_KEYWORDS:
            metrics.has_try = True

        # Add children
        stack.extend(current.children)

    return metrics
```

**예상 효과**: 33ms → 10ms (-70%, -23ms)

#### 1.2 Pre-compiled Keyword Sets

**Before**:
```python
if any(kw in node.type for kw in ["while", "for", "if", ...]):
    # 38,207 any() calls, generator overhead
```

**After**:
```python
# Module level constants
BRANCH_KEYWORDS = frozenset(["if_statement", "elif_clause", "else_clause", ...])
LOOP_KEYWORDS = frozenset(["while_statement", "for_statement", ...])
TRY_KEYWORDS = frozenset(["try_statement", "except_clause", ...])

# O(1) lookup instead of O(n) generator
if node.type in BRANCH_KEYWORDS:
    # ...
```

**예상 효과**: 6ms → 1ms (-83%, -5ms)

---

### Phase 2: Call Analysis 최적화 (예상 -15ms, 11%)

#### 2.1 Iterative Call Finding

**Before**:
```python
def _find_calls_recursive(self, node):
    """Recursive - 28,729 calls"""
    calls = []
    if node.type == "call":
        calls.append(node)
    for child in node.children:
        calls.extend(self._find_calls_recursive(child))  # Recursion!
    return calls
```

**After**:
```python
def _find_calls_iterative(self, node):
    """Iterative with stack"""
    calls = []
    stack = [node]

    while stack:
        current = stack.pop()

        if current.type == "call":
            calls.append(current)

        # Add children to stack
        stack.extend(reversed(current.children))  # Maintain order

    return calls
```

**예상 효과**: 24ms → 12ms (-50%, -12ms)

#### 2.2 Early Exit Optimization

**Before**:
```python
def _find_calls_recursive(self, node):
    # Always traverse entire subtree
    for child in node.children:
        calls.extend(self._find_calls_recursive(child))
```

**After**:
```python
# Skip subtrees that can't contain calls
SKIP_TYPES = frozenset(["string", "number", "identifier", "comment"])

def _find_calls_optimized(self, node):
    stack = [node]
    calls = []

    while stack:
        current = stack.pop()

        # Early exit for leaf nodes
        if current.type in SKIP_TYPES:
            continue

        if current.type == "call":
            calls.append(current)

        stack.extend(reversed(current.children))

    return calls
```

**예상 효과**: 추가 -3ms

---

### Phase 3: 기타 최적화 (예상 -5ms, 4%)

#### 3.1 Node Text Extraction 최적화

**현재**: `get_node_text()` - 5,988번 호출

```python
def get_node_text(self, node):
    """Cache frequently accessed text"""
    # Add simple LRU cache
    if node.id not in self._text_cache:
        self._text_cache[node.id] = self._extract_text(node)
    return self._text_cache[node.id]
```

#### 3.2 ID Generation 최적화

**현재**: `generate_edge_id()` - 2,555번 호출

```python
# Pre-compute hash prefix
EDGE_ID_PREFIX = "edge:"

def generate_edge_id_optimized(self, source, target, kind):
    # Use format string instead of concatenation
    return f"{EDGE_ID_PREFIX}{source}:{target}:{kind}"
```

---

## 예상 성능 개선

### 현재 (50 files)

| 레이어 | 시간 | 비율 |
|--------|------|------|
| Tree-sitter parse | 25ms | 18.7% |
| CF calculation | 33ms | 24.6% |
| Call analysis | 39ms | 29.1% |
| Other IR gen | 37ms | 27.6% |
| **Total** | **134ms** | **100%** |

### 최적화 후 (예상)

| 레이어 | Before | After | 개선 |
|--------|--------|-------|------|
| Tree-sitter parse | 25ms | 25ms | - |
| CF calculation | 33ms | 10ms | -70% |
| Call analysis | 39ms | 24ms | -38% |
| Other IR gen | 37ms | 32ms | -14% |
| **Total** | **134ms** | **91ms** | **-32%** |

### 전체 파이프라인 영향 (211 files)

| 단계 | Before | After | 개선 |
|------|--------|-------|------|
| IR Generation | 1,190ms | 809ms | -32% (-381ms) |
| **Total Pipeline** | **2,199ms** | **1,818ms** | **-17%** |

**Throughput**:
- Before: 96 files/sec
- After: 116 files/sec
- **개선: +21%**

---

## 구현 우선순위

### Priority 1 (High Impact, Low Risk)

1. ✅ **Pre-compiled keyword sets** (-5ms, 쉬움)
2. ✅ **Single-pass CF calculation** (-23ms, 중간)
3. ✅ **Iterative call finding** (-12ms, 중간)

**예상 효과**: -40ms (30% 개선)

### Priority 2 (Medium Impact)

4. ⚠️ **Early exit optimization** (-3ms, 쉬움)
5. ⚠️ **Text caching** (-2ms, 쉬움)
6. ⚠️ **ID generation optimization** (-1ms, 쉬움)

**예상 효과**: 추가 -6ms (4% 개선)

### Priority 3 (Future)

7. 🔮 **Parallel processing** (4x throughput, 복잡함)
8. 🔮 **Cython/Rust extension** (2-3x 개선, 매우 복잡함)

---

## 구현 계획

### Week 1: Core Optimizations

**Day 1-2**: Pre-compiled keywords + Single-pass CF
- `src/foundation/generators/base.py` 수정
- 테스트 작성 및 검증

**Day 3-4**: Iterative call finding
- `src/foundation/generators/python/call_analyzer.py` 수정
- 기존 테스트 통과 확인

**Day 5**: Early exit optimization
- Skip types 정의
- 벤치마크 측정

**Day 6**: 통합 테스트 및 벤치마크
- 전체 211 files 벤치마크
- 성능 개선 검증

**Day 7**: 문서화 및 코드 리뷰

### 목표

- ✅ IR Generation: 1,190ms → 809ms (-32%)
- ✅ Total Pipeline: 2,199ms → 1,818ms (-17%)
- ✅ Throughput: 96 → 116 files/sec (+21%)

---

## 위험 요소

### 1. 정확성 유지

**위험**: 최적화로 인한 버그 발생
**완화**:
- 기존 테스트 100% 통과 확인
- 벤치마크 전후 IR 결과 비교 (diff)
- Edge case 테스트 추가

### 2. 유지보수성

**위험**: 최적화된 코드가 복잡해질 수 있음
**완화**:
- 명확한 주석 추가
- Before/After 예시 문서화
- 성능 테스트 자동화

### 3. 측정 오차

**위험**: 예상 개선율과 실제 차이
**완화**:
- 각 최적화마다 개별 벤치마크
- 여러 번 측정 후 평균
- 다양한 코드베이스로 검증

---

## 성공 기준

### Minimum Viable

- ✅ IR Generation 20% 개선 (1,190ms → 952ms)
- ✅ 모든 기존 테스트 통과
- ✅ 코드 품질 유지 (linting, formatting)

### Target

- ✅ IR Generation 30% 개선 (1,190ms → 833ms)
- ✅ Total pipeline 15% 개선
- ✅ Throughput 18% 증가

### Stretch Goal

- 🎯 IR Generation 40% 개선 (1,190ms → 714ms)
- 🎯 병렬 처리 프로토타입
- 🎯 다른 언어(TypeScript, Java)에도 적용

---

## 다음 단계

1. ✅ 프로파일링 완료
2. ⬜ Priority 1 최적화 구현
3. ⬜ 벤치마크로 검증
4. ⬜ Priority 2 최적화 (선택)
5. ⬜ 문서화 및 정리
