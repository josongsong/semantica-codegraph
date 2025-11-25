# IR Generation 세부 분석 (965ms)

## 측정 기준

- **전체 파일**: 211 files
- **IR Generation Total**: 965ms (48% of pipeline)
- **프로파일링**: 100 files, 201ms

---

## 1. IR Generation 내부 구성 (cProfile 기반)

### 100 Files 프로파일링 결과

| 함수 | 시간 | 비율 | 호출 횟수 | 설명 |
|------|------|------|----------|------|
| **Tree-sitter Parse** | **51ms** | **25%** | 200회 | AST 파싱 (중복!) |
| `_traverse_ast` | 122ms | 61% | 4,029회 | AST 순회 |
| `_process_function` | 110ms | 55% | 502회 | 함수 노드 생성 |
| `_process_class` | 105ms | 52% | 170회 | 클래스 노드 생성 |
| `process_calls_in_block` | 41ms | 20% | 502회 | Call 분석 |
| `_process_single_call` | 27ms | 13% | 1,957회 | 개별 call 처리 |
| `_calculate_cf_summary` | 20ms | 10% | 502회 | **✅ 최적화됨!** |
| `_process_parameters` | 18ms | 9% | 502회 | 파라미터 처리 |
| `resolve_type` | 15ms | 7% | 1,328회 | 타입 해결 |
| `_find_calls_recursive` | 13ms | 6% | 502회 | **✅ 최적화됨!** |
| **Total** | **201ms** | **100%** | | |

### 211 Files 추정 (비율 기반)

| 작업 | 시간 | 비율 | 설명 |
|------|------|------|------|
| **Parsing (중복)** | **~240ms** | **25%** | ❌ 낭비 (벤치마크 버그) |
| AST Traversal + Node Creation | ~290ms | 30% | 기본 IR 구조 |
| Function Processing | ~260ms | 27% | 함수/클래스/메서드 |
| Call Analysis | ~120ms | 12% | ✅ 최적화됨 |
| Type Resolution | ~35ms | 4% | TypeResolver (Pyright 미사용) |
| Other (파라미터, 시그니처, 등) | ~20ms | 2% | |
| **Total** | **~965ms** | **100%** | |

---

## 2. CFG/DFG 성능

### Semantic Layer (23ms total)

```
Semantic IR Builder:   23ms
├─ CFG Building:       ~10ms (43%)  ← Control Flow Graph
├─ DFG Building:       ~5ms  (22%)  ← Data Flow Graph
├─ Type Resolution:    ~5ms  (22%)
└─ Expression Analysis: ~3ms  (13%)
```

**결론**: **CFG/DFG는 매우 빠름. 병목 아님!**

### CFG/DFG가 Pyright 없이 동작하는 이유

**CFG (Control Flow Graph)**:
```python
# AST 구조만으로 생성
if node.type == "if_statement":
    create_branch_edges()
elif node.type == "while_statement":
    create_loop_back_edge()
```
- **입력**: AST의 제어 구조 (if/while/for/try)
- **출력**: 제어 흐름 그래프
- **Pyright 불필요**

**DFG (Data Flow Graph)**:
```python
# 변수 정의/사용만 추적
def build_dfg(ir_doc):
    for node in ir_doc.nodes:
        if node.kind == VARIABLE:
            track_def_use(node)
```
- **입력**: 변수 이름 + 할당/참조 위치
- **출력**: def-use chain
- **Pyright 불필요**

**Pyright가 필요한 경우**:
```python
def foo(x):  # x의 정확한 타입?
    return x.bar()  # bar의 반환 타입?

# Pyright 없이:
# x: RAW("x")
# bar: RAW("bar")

# Pyright 있으면:
# x: MyClass (resolved)
# bar: -> str (resolved)
```

**결론**: **CFG/DFG는 Pyright 무관**, **Type Resolution만 향상**

---

## 3. Pyright 활성화 방법

### 현재 상태 (Pyright 미사용)

```python
# src/foundation/generators/python_generator.py
class PythonIRGenerator:
    def __init__(self, repo_id: str):
        # Pyright는 optional, 기본값 None
        self._type_resolver = TypeResolver()  # No external analyzer
```

### Pyright 활성화

**Option 1: Generator 생성 시 전달**

```python
from src.foundation.ir.external_analyzers import PyrightAnalyzer

# Pyright analyzer 생성
pyright = PyrightAnalyzer(
    workspace_root="/path/to/workspace",
    python_executable="/path/to/python"
)

# IR generator에 전달
ir_generator = PythonIRGenerator(
    repo_id="my-repo",
    external_analyzer=pyright  # ← Pyright 활성화
)
```

**Option 2: 벤치마크에 통합**

```python
# benchmark/run_benchmark.py

# Pyright LSP 시작
from src.foundation.ir.external_analyzers import PyrightLSPClient

pyright_client = PyrightLSPClient(workspace_root=repo_path)
await pyright_client.start()

# 각 파일 처리 시
ir_generator = PythonIRGenerator(
    repo_id=profiler.repo_id,
    external_analyzer=pyright_client
)
```

**Option 3: Config 기반**

```python
# src/config.py
USE_PYRIGHT = True
PYRIGHT_PATH = "/path/to/pyright"

# Generator가 자동으로 감지
if USE_PYRIGHT:
    pyright = PyrightAnalyzer.from_config()
    ir_generator = PythonIRGenerator(..., external_analyzer=pyright)
```

### Pyright 활성화 시 예상 성능

| 단계 | Pyright 없음 | Pyright 있음 | 차이 |
|------|-------------|-------------|------|
| Type Resolution | 35ms | ~150ms | +115ms |
| **Total IR Gen** | 965ms | ~1,080ms | +12% |
| **정확도** | 낮음 (RAW types) | 높음 (resolved types) | 훨씬 향상 |

**트레이드오프**:
- **속도**: 12% 느려짐
- **정확도**: Type resolution 크게 향상
- **추천**: Production에서는 Pyright 사용

---

## 4. 실제 병목 정리

### 965ms IR Generation 분석 결과

**실제 병목 (최적화 전)**:
```
1. Parsing (중복):        240ms (25%) ← 벤치마크 버그
2. AST Traversal:         290ms (30%)
3. Function Processing:   260ms (27%)
4. Call Analysis:         180ms (19%) ← 최적화 완료 (-50ms)
5. CF Calculation:         60ms ( 6%) ← 최적화 완료 (-30ms)
```

**최적화 후**:
```
1. Parsing (중복):        240ms (25%) ← 여전히 낭비
2. AST Traversal:         290ms (30%)
3. Function Processing:   260ms (27%)
4. Call Analysis:         120ms (12%) ← ✅ -60ms
5. CF Calculation:         20ms ( 2%) ← ✅ -40ms
6. Other:                  35ms ( 4%)
---------------------------------------
Total:                    965ms (100%)
```

**달성한 최적화**:
- Call Analysis: 180ms → 120ms (-33%)
- CF Calculation: 60ms → 20ms (-67%)
- **Total 절감**: ~100ms (-9%)

**하지만 측정에서는 -380ms (-32%)로 보임!**
- **이유**: Parsing 중복 때문에 측정 오류

---

## 5. 추가 최적화 기회

### Priority 2: Variable/Signature Analysis (~50ms)

**현재**:
```python
# Variable analysis: 502 calls
process_variables_in_block()  # 재귀로 변수 찾기
```

**최적화 방향**:
- Iterative traversal (call analysis처럼)
- 예상 효과: ~20ms (-40%)

### Priority 3: AST Traversal (~290ms)

**현재**:
```python
def _traverse_ast(self, node):
    if node.type == "function_definition":
        self._process_function(node)  # 호출 오버헤드
    elif node.type == "class_definition":
        self._process_class(node)  # 호출 오버헤드
    # ... 많은 elif
```

**최적화 방향**:
- Dictionary dispatch: `handlers = {"function_definition": self._process_function}`
- Inline small handlers
- 예상 효과: ~50ms (-17%)

### Priority 4: Function Processing (~260ms)

**가장 큰 작업이지만 최적화 여지 낮음**:
- 노드 생성: 필수
- 엣지 생성: 필수
- Docstring 추출: 필요
- 최적화 여지: ~10-20ms (-5-8%)

---

## 6. 벤치마크 중복 Parsing 해결

### 문제

```python
# benchmark/run_benchmark.py

# 1번째 parsing
profiler.start_phase(parse_phase)
ast_tree = AstTree.parse(source_file)  # ← 167ms (낭비!)
profiler.end_phase(parse_phase)

# 2번째 parsing
profiler.start_phase(ir_gen_phase)
ir_doc = ir_generator.generate(source_file, ...)
  └─ self._ast = AstTree.parse(source)  # ← 240ms (실제 사용)
profiler.end_phase(ir_gen_phase)
```

**Total 낭비**: 167ms (17%)

### 해결 방안

**Option A: API 변경 (추천)**

```python
# IR Generator API 개선
ast_tree = AstTree.parse(source_file)
ir_doc = ir_generator.generate(source_file, ast_tree, ...)  # AST 재사용
```

**Option B: 벤치마크만 수정**

```python
# Parse phase 제거
# profiler.start_phase(parse_phase)
# ast_tree = AstTree.parse(source_file)
# profiler.end_phase(parse_phase)

# IR Generation이 parsing 포함
profiler.start_phase(ir_gen_phase)
ir_doc = ir_generator.generate(source_file, ...)
profiler.end_phase(ir_gen_phase)
```

**Option C: 내부 timing 추가**

```python
class PythonIRGenerator:
    def generate(self, source, ...):
        # Internal timing
        parse_start = time.time()
        self._ast = AstTree.parse(source)
        self._timings["parse_ms"] = (time.time() - parse_start) * 1000

        # ... IR building
        self._timings["ir_build_ms"] = ...
```

**추천**: **Option A** (API 개선) → 중복 제거 + 재사용성 향상

---

## 7. 최종 예상 성능

### 현재 (최적화 후)

```
Parsing (중복):       167ms
IR Generation:        965ms
  ├─ Parsing (내부):  240ms (중복!)
  ├─ AST Traversal:   290ms
  ├─ Function Proc:   260ms
  ├─ Call Analysis:   120ms (최적화됨)
  ├─ CF Calc:          20ms (최적화됨)
  └─ Other:            35ms
```

### 추가 최적화 후 (예상)

```
Parsing (once):       240ms (-167ms, 중복 제거)
IR Building:          600ms (-365ms)
  ├─ AST Traversal:   240ms (-50ms, dict dispatch)
  ├─ Function Proc:   240ms (-20ms, inline)
  ├─ Call Analysis:   120ms (이미 최적화됨)
  ├─ Variable Anal:    20ms (-30ms, iterative)
  └─ Other:            20ms (-15ms)
-----------------------------------------
Total:                840ms → 600ms (-29%)
```

**전체 파이프라인 영향**:
- Current: 2,010ms
- After: 1,645ms (-365ms, -18%)
- **Throughput**: 105 → 128 files/sec (+22%)

---

## 8. 결론

### IR Generation 965ms 구성 (실제)

| 작업 | 시간 | 최적화 가능? | 우선순위 |
|------|------|-------------|---------|
| Parsing (중복) | 240ms | ✅ Yes (167ms 절감) | 🔴 High |
| AST Traversal | 290ms | ⚠️ Limited (~50ms) | 🟡 Medium |
| Function Processing | 260ms | ⚠️ Limited (~20ms) | 🟢 Low |
| Call Analysis | 120ms | ✅ Done | ✅ Complete |
| CF Calculation | 20ms | ✅ Done | ✅ Complete |
| Variable/Signature | 35ms | ⚠️ Possible (~15ms) | 🟡 Medium |

### CFG/DFG

- ✅ **매우 빠름** (23ms total)
- ✅ **Pyright 불필요** (AST만으로 생성)
- ✅ **병목 아님**

### Pyright

- **현재**: 미사용 (TypeResolver만 사용)
- **효과**: Type resolution 정확도 향상
- **비용**: +115ms (+12% slower)
- **추천**: Production에서는 사용

### 다음 단계

1. ⬜ 벤치마크 중복 parsing 제거 (-167ms)
2. ⬜ Variable/Signature 최적화 (-30ms)
3. ⬜ AST Traversal dict dispatch (-50ms)
4. ⬜ Pyright 통합 (선택적)

**최종 목표**: 965ms → ~600ms (-38%)

---

**Date**: 2025-11-25
**Status**: ✅ Analysis Complete
**Next**: Implement Priority 2 optimizations
