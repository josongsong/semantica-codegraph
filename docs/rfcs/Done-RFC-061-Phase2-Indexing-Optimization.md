# RFC-061: Phase 2 인덱싱 파이프라인 SOTA 최적화

> **Status**: Draft (Revised)
> **Created**: 2025-12-26
> **Revised**: 2025-12-26
> **Author**: Claude Opus 4.5
> **Reviewer**: Human Expert
> **Target**: Phase 2 처리 시간 62초 → 10초 (84% 개선)
> **Related**: DAG Pipeline, L2 Occurrence, L4 Cross-file

---

## Executive Summary

현재 인덱싱 파이프라인의 **Phase 2 (L2 Occurrence + L4 Cross-file)**가 전체 시간의 **70.3%**를 차지하는 심각한 병목입니다. 본 RFC는 SOTA급 최적화를 통해 62초 → 10초로 **84% 개선**을 목표로 합니다.

### 핵심 수치

| 지표 | 현재 | 목표 | 개선율 |
|-----|------|------|--------|
| Phase 2 시간 | 62.26초 | 10초 | **84%↓** |
| 전체 시간 | 88.62초 | 36초 | **59%↓** |
| 메모리 피크 | 6.8GB | 2GB | **70%↓** |
| 처리량 | 21K LOC/s | 54K LOC/s | **2.5x** |

### ⚠️ 선행 조건: 정확도 검증 필요

벤치마크에서 **"413,274 심볼, 0 deps"**가 관측되었습니다. deps가 0이면:
- Resolution이 실패하고 있을 가능성 (정확도 문제)
- Import edge 생성 로직 오류
- 언어/스키마 mismatch

**최적화 전에 반드시 정확도 경로부터 점검해야 합니다.**

---

## 1. 현재 문제점 상세 분석

### 1.1 벤치마크 데이터 (2025-12-26)

**테스트 환경:**
- Repository: codegraph (13,183 파일, 1,954,513 LOC)
- CPU: 16코어, 메모리: 48GB
- Platform: Darwin 24.6.0, Python 3.12.11

**Phase별 소요 시간:**

```
Phase 1 (L1 ∥ L5): 22.71초 (25.6%)  ← Rust 병렬화로 빠름
Phase 2 (L2 + L4): 62.26초 (70.3%)  ← 🔴 병목
Phase 3 (L3):       3.64초 (4.1%)   ← 양호
Phase 4 (L6):       0.00초 (0.0%)   ← 스킵됨
────────────────────────────────────
Total:             88.62초 (100%)
```

**Phase 2 세부 분석:**

| Layer | 작업 | 예상 시간 | 비율 |
|-------|------|----------|------|
| L2 Occurrence | 26,366개 생성 | ~7초 | 11% |
| L4 Cross-file | 413,274 심볼, 0 deps | ~55초 | **89%** |

### 1.2 L4 Cross-file 병목 원인

**파일 위치**: `packages/codegraph-engine/.../cross_file_resolver.py`

#### 문제 1: 이중 순회 (O(2M) → O(M) 가능)

```python
# 현재 코드 (Lines 247-262)

# Step 1: Symbol Table 빌드 - O(M)
for file_path, ir_doc in ir_docs_dict.items():
    for node in ir_doc.nodes:
        if node.fqn:
            global_ctx.register_symbol(node.fqn, node, file_path)

# Step 2: Node Index 빌드 - O(M) ← 불필요한 중복!
node_by_id: dict[str, "Node"] = {}
for ir_doc in ir_docs_dict.values():
    for node in ir_doc.nodes:
        node_by_id[node.id] = node
```

**영향**: 413,274 노드 × 2 = 826,548 iterations
**예상 절감**: ~10초

#### 🔴 문제 2: Node 객체 전역 저장 (메모리 폭탄)

```python
# 현재 코드 - 치명적 문제
symbol_table[fqn] = (node, file_path)  # Node 객체 중복 저장!
```

**문제점**:
- Node 객체가 전역 테이블에 중복 보관됨
- 413,274개 Node 객체 × 평균 크기 → 메모리 폭발
- 6.8GB 피크의 주요 원인

**해결책**:
```python
# 수정 - 정수 ID만 저장
symbol_table[fqn_id] = (file_id, node_id)  # 경량 정수만
```

#### 문제 3: List Comprehension 오버헤드

```python
# 현재 코드 (Line 266)
for file_path, ir_doc in ir_docs_dict.items():
    import_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.IMPORTS]  # ❌
```

**정정**: 3,215,056 edges는 **전체 합계**이며, 파일마다 전체를 다시 도는 것은 아닙니다.
단, 매번 새 리스트 생성으로 인한 메모리 할당/GC 비용은 여전히 유효한 문제입니다.

**개선**:
- Generator 사용 또는
- edges를 kind별로 사전 분리/인덱싱 (더 근본적)

#### 문제 4: Partial Resolve 비효율

```python
# 현재 코드 (Lines 340-351)
def _try_partial_resolve(self, imported_name, ...):
    parts = imported_name.split(".")

    # O(K) iterations where K = parts count
    for i in range(len(parts) - 1, 0, -1):
        partial_name = ".".join(parts[:i])
        resolved = global_ctx.resolve_symbol(partial_name)  # O(1) lookup
```

**문제**: 매번 `split` + `join` 수행
**개선**: split된 토큰 캐시, 또는 join 없이 prefix 생성

### 1.3 L2 Occurrence 병목 원인

**파일 위치**: `packages/codegraph-engine/.../occurrence_generator.py`

#### 문제 1: 비효율적인 노드 조회

```python
# 현재 코드 (Lines 205-209)
def _create_reference_occurrence(self, edge, ir_doc):
    source_node = ir_doc.get_node(edge.source_id)  # O(N) 탐색!
```

**문제**: `get_node()`가 선형 탐색이면 O(E×N) 복잡도

**개선**:
- 각 IRDocument에 `node_by_id` dict 빌드
- 또는 nodes를 `id → offset` 구조로 저장

### 1.4 메모리 문제

**현재 상태**:
- 시작: 26.1 MB
- 피크: 6,820.2 MB (+6,794 MB)

**원인**:
1. Node 객체를 전역 symbol_table에 중복 저장 (🔴 주요 원인)
2. 모든 IR 문서를 메모리에 유지
3. 중간 결과 캐싱 (ir_cache, occurrence_cache, global_ctx_cache)

---

## 2. SOTA 최적화 전략 (수정됨)

### 2.1 전략 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                    SOTA 최적화 3단계 (수정)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Level 1: 알고리즘 + 메모리 최적화 (Python) - P0                  │
│  ├── 🔴 Node 객체 전역 저장 제거 → 정수 ID만 저장                 │
│  ├── 단일 순회로 fqn_index + node_by_id 빌드                     │
│  ├── split/join 제거 (토큰 캐시)                                 │
│  └── Generator 또는 edge 사전 분류                               │
│                                                                  │
│  Level 2: 병렬화 (⚠️ 조건부) - P1                                │
│  ├── ❌ ProcessPoolExecutor + ir_docs 전달 금지                  │
│  ├── ✅ 옵션 A: 단일 프로세스 + Rust (GIL-free)                  │
│  └── ✅ 옵션 B: mmap/바이너리 포맷 + 경로만 전달                  │
│                                                                  │
│  Level 3: Rust 마이그레이션 (GIL-free) - P2                      │
│  ├── ID 인터닝 (문자열 → 정수)                                   │
│  ├── Arena/flat vector 기반 레이아웃                             │
│  ├── Fst (Finite State Transducer) 심볼 검색                    │
│  └── Python↔Rust: msgpack bytes / mmap (리스트 전달 X)          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Level 1: 알고리즘 + 메모리 최적화 (P0)

#### 🔴 2.2.1 Node 객체 전역 저장 제거 (최우선)

**Before (현재 - 메모리 폭탄):**
```python
# symbol_table에 Node 객체 저장 → 중복 메모리
symbol_table: dict[str, tuple[Node, str]] = {}
symbol_table[node.fqn] = (node, file_path)
```

**After (수정 - 정수 ID만):**
```python
# 인터닝: 문자열 → 정수 ID
class StringInterner:
    def __init__(self):
        self._str_to_id: dict[str, int] = {}
        self._id_to_str: list[str] = []

    def intern(self, s: str) -> int:
        if s not in self._str_to_id:
            self._str_to_id[s] = len(self._id_to_str)
            self._id_to_str.append(s)
        return self._str_to_id[s]

    def get(self, id: int) -> str:
        return self._id_to_str[id]

# 전역 테이블은 정수만 저장
fqn_interner = StringInterner()
file_interner = StringInterner()

# symbol_table[fqn_id] = (file_id, node_id)
symbol_table: dict[int, tuple[int, str]] = {}

for file_path, ir_doc in ir_docs_dict.items():
    file_id = file_interner.intern(file_path)
    for node in ir_doc.nodes:
        if node.fqn:
            fqn_id = fqn_interner.intern(node.fqn)
            symbol_table[fqn_id] = (file_id, node.id)
```

**예상 효과**:
- 메모리: 1.5GB+ 절감
- 근거: Node 객체 (평균 ~4KB) × 413K = ~1.6GB → 정수 (8bytes) × 413K = ~3MB

#### 2.2.2 단일 순회 + Per-doc Node Index

**After (최적화):**
```python
# O(M) 단일 순회
symbol_table: dict[int, tuple[int, str]] = {}
fqn_to_file: dict[int, int] = {}

for file_path, ir_doc in ir_docs_dict.items():
    file_id = file_interner.intern(file_path)

    # Per-doc node index (전역 아님)
    ir_doc._node_by_id = {node.id: node for node in ir_doc.nodes}

    for node in ir_doc.nodes:
        if node.fqn:
            fqn_id = fqn_interner.intern(node.fqn)
            symbol_table[fqn_id] = (file_id, node.id)
            fqn_to_file[fqn_id] = file_id
```

**예상 효과**:
- 시간: 10초 절감
- 근거: 이중 순회 → 단일 순회

#### 2.2.3 split/join 제거

**Before:**
```python
def _try_partial_resolve(self, name: str):
    parts = name.split(".")  # 매번 split
    for i in range(len(parts) - 1, 0, -1):
        partial = ".".join(parts[:i])  # 매번 join
        if partial in self.symbol_table:
            return self.symbol_table[partial]
```

**After:**
```python
# 미리 split된 토큰으로 작업
def _try_partial_resolve(self, name_parts: tuple[str, ...]):
    # join 없이 prefix 생성
    for i in range(len(name_parts) - 1, 0, -1):
        # intern된 prefix 사용
        prefix_id = self._get_prefix_id(name_parts[:i])
        if prefix_id in self.symbol_table:
            return self.symbol_table[prefix_id]

# 또는 Trie 사용 (O(K) 순차 탐색, 상수항 절감)
```

**복잡도 정정**: Trie는 O(1)이 아니라 **O(K)** (K = 토큰 수)입니다.
단, split/join/해시를 제거하여 **상수항을 크게 절감**합니다.

#### 2.2.4 Edge 사전 분류

**Before:**
```python
# 매번 필터링
import_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.IMPORTS]
```

**After:**
```python
# IR 빌드 시점에 분류
class IRDocument:
    edges: list[Edge]
    edges_by_kind: dict[EdgeKind, list[Edge]]  # 사전 분류

    def __post_init__(self):
        self.edges_by_kind = defaultdict(list)
        for e in self.edges:
            self.edges_by_kind[e.kind].append(e)

# 사용 시
import_edges = ir_doc.edges_by_kind[EdgeKind.IMPORTS]  # O(1)
```

### 2.3 Level 2: 병렬화 (조건부)

#### ❌ 2.3.1 금지: ProcessPoolExecutor + 거대 객체 전달

```python
# ❌ 절대 금지 - 성능 악화 유발
with ProcessPoolExecutor(max_workers=8) as pool:
    # ir_documents (6.8GB)를 pickle → IPC → 메모리 복제
    pool.map(resolve_fn, ir_documents)  # 💥 터짐
```

**문제점**:
- 6.8GB 객체를 pickle하는 비용 >> 처리 비용
- 프로세스당 메모리 복제 → OOM
- "병렬화"가 아니라 "성능 악화"

#### ✅ 2.3.2 옵션 A: Rust 단일 프로세스 병렬 (권장)

```python
# Level 3으로 직행하는 것이 실제로 더 빠름
from codegraph_rust import CrossFileResolver

resolver = CrossFileResolver()
# Rust 내부에서 Rayon으로 GIL-free 병렬 처리
results = resolver.resolve_all(ir_data_bytes)
```

#### ✅ 2.3.3 옵션 B: mmap/바이너리 포맷 + 경로 전달

**전제 조건**: IR을 바이너리 포맷으로 저장

```python
import mmap
from concurrent.futures import ProcessPoolExecutor

# 1. IR을 파일 단위 바이너리로 저장 (msgpack/arrow)
for file_path, ir_doc in ir_docs_dict.items():
    binary_path = f"/tmp/ir_cache/{hash(file_path)}.msgpack"
    with open(binary_path, "wb") as f:
        f.write(msgpack.packb(ir_doc.to_dict()))

# 2. 워커는 경로만 받아서 mmap으로 읽음
def resolve_batch(binary_paths: list[str]) -> list[dict]:
    results = []
    for path in binary_paths:
        with open(path, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            ir_data = msgpack.unpackb(mm)
            # process...
    return results

# 3. 병렬 실행 (경로만 전달)
with ProcessPoolExecutor(max_workers=8) as pool:
    path_batches = [paths[i:i+100] for i in range(0, len(paths), 100)]
    results = pool.map(resolve_batch, path_batches)
```

### 2.4 Level 3: Rust 마이그레이션 (P2)

#### 2.4.1 핵심: ID 인터닝 + Flat Table

```rust
use pyo3::prelude::*;
use fxhash::FxHashMap;

/// 문자열 인터닝
pub struct StringInterner {
    str_to_id: FxHashMap<String, u32>,
    id_to_str: Vec<String>,
}

impl StringInterner {
    pub fn intern(&mut self, s: &str) -> u32 {
        if let Some(&id) = self.str_to_id.get(s) {
            return id;
        }
        let id = self.id_to_str.len() as u32;
        self.id_to_str.push(s.to_string());
        self.str_to_id.insert(s.to_string(), id);
        id
    }
}

/// 압축된 심볼 테이블
#[pyclass]
pub struct SymbolTable {
    /// fqn_id → (file_id, node_id)
    table: FxHashMap<u32, (u32, u32)>,
    fqn_interner: StringInterner,
    file_interner: StringInterner,
}
```

**효과**:
- 메모리: String 중복 제거, 정수 기반 테이블
- 속도: FxHash (빠른 해시), 캐시 친화적 레이아웃

#### 2.4.2 Fst (Finite State Transducer) 심볼 검색

```rust
use fst::{Map, MapBuilder};

/// Fst 기반 심볼 검색 (Trie보다 메모리 효율적)
pub struct FstSymbolIndex {
    /// immutable Fst (빌드 후 변경 불가)
    main_fst: Map<Vec<u8>>,
    /// delta for incremental updates
    delta: FxHashMap<u32, (u32, u32)>,
}

impl FstSymbolIndex {
    pub fn build(entries: &[(String, u64)]) -> Self {
        let mut builder = MapBuilder::memory();
        // entries must be sorted
        for (key, value) in entries {
            builder.insert(key, *value).unwrap();
        }
        let fst = builder.into_map();
        Self { main_fst: fst, delta: FxHashMap::default() }
    }

    pub fn resolve(&self, fqn: &str) -> Option<u64> {
        // delta 먼저 확인 (incremental)
        // 없으면 main_fst 조회
        self.main_fst.get(fqn)
    }
}
```

**Fst 장점**:
- Trie보다 메모리 효율적 (압축된 automaton)
- 범위 쿼리, prefix 검색 지원
- Rust 생태계 `fst` crate 성숙

**Fst 제약**:
- 빌드 후 immutable → 2-tier 구조로 해결 (main Fst + delta HashMap)

#### 2.4.3 Python ↔ Rust 경계 최적화

```rust
use pyo3::types::PyBytes;

#[pymethods]
impl CrossFileResolver {
    /// ❌ 금지: Python list를 받아서 Rust Vec으로 변환
    pub fn bulk_insert_bad(&self, entries: Vec<(String, String, String)>) {
        // Python list → Rust Vec 변환 비용이 큼
    }

    /// ✅ 권장: msgpack bytes를 받아서 zero-copy 처리
    pub fn bulk_insert(&self, py: Python, data: &PyBytes) -> PyResult<()> {
        let bytes = data.as_bytes();
        let entries: Vec<(String, String, String)> = rmp_serde::decode::from_slice(bytes)?;
        // Rust 내부에서 병렬 처리
        self.table.par_extend(entries);
        Ok(())
    }

    /// ✅ 권장: 결과도 bytes로 반환
    pub fn resolve_all(&self, py: Python, fqns_bytes: &PyBytes) -> PyResult<Py<PyBytes>> {
        let fqns: Vec<String> = rmp_serde::decode::from_slice(fqns_bytes.as_bytes())?;
        let results: Vec<Option<(u32, u32)>> = fqns.par_iter()
            .map(|fqn| self.resolve(fqn))
            .collect();
        let result_bytes = rmp_serde::to_vec(&results)?;
        Ok(PyBytes::new(py, &result_bytes).into())
    }
}
```

---

## 3. 측정 계획 (SOTA 문서 필수)

### 3.1 측정 도구

| 도구 | 측정 대상 | 용도 |
|-----|----------|------|
| `time.perf_counter()` | Wall time | 전체 소요 시간 |
| `py-spy` | CPU time per function | 병목 함수 식별 |
| `tracemalloc` | Memory allocations | 메모리 할당 추적 |
| `gc.get_stats()` | GC time | GC 오버헤드 측정 |
| `scalene` | CPU + Memory + GPU | 종합 프로파일링 |

### 3.2 각 최적화별 Before/After 측정

```python
# 측정 템플릿
import tracemalloc
import gc
import time

def measure_optimization(name: str, func: Callable):
    # GC 정리
    gc.collect()
    gc.disable()

    # Memory 시작
    tracemalloc.start()

    # Time 시작
    start = time.perf_counter()

    # 실행
    result = func()

    # Time 종료
    elapsed = time.perf_counter() - start

    # Memory 종료
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    gc.enable()

    print(f"[{name}] time={elapsed:.2f}s, peak_mem={peak/1024/1024:.1f}MB")
    return result
```

### 3.3 목표 측정 결과

| 최적화 | 측정 항목 | Before | Target |
|--------|----------|--------|--------|
| Node 객체 제거 | peak_mem | 6.8GB | 4.5GB |
| ID 인터닝 | peak_mem | 4.5GB | 2.5GB |
| 단일 순회 | wall_time | 20s | 10s |
| split/join 제거 | cpu_time | 5s | 2s |
| Fst 도입 | resolve_batch | 3s | 0.5s |

---

## 4. 구현 우선순위 (수정됨)

### P0: 즉시 실행 (정확도 + 메모리)

1. **"0 deps" 원인 파악**
   - Resolution이 실패하는지 확인
   - Import edge 생성 로직 검증
   - 정확도 문제 해결 후 성능 최적화 진행

2. **Node 객체 전역 저장 제거**
   - `symbol_table[fqn] = (node, file_path)` → `symbol_table[fqn_id] = (file_id, node_id)`
   - 예상 효과: 메모리 1.5GB+ 절감

3. **단일 순회 + Per-doc node_by_id**
   - 이중 순회 제거
   - 예상 효과: 시간 10초 절감

### P1: 그 다음 (알고리즘)

4. **split/join 제거**
   - 토큰 캐시 또는 Trie 도입
   - 예상 효과: 시간 2-3초 절감

5. **Edge 사전 분류**
   - IR 빌드 시점에 kind별 분류
   - 예상 효과: 시간 2-3초 절감

### P2: Rust 마이그레이션

6. **ID 인터닝 + Flat Table**
   - DashMap 아닌 인터닝 우선
   - 예상 효과: 메모리 50% 추가 절감

7. **Fst 심볼 검색**
   - 2-tier 구조 (main Fst + delta)
   - 예상 효과: resolve 10x 가속

8. **msgpack bytes 경계**
   - Python list 전달 금지
   - 예상 효과: FFI 오버헤드 최소화

---

## 5. 목표치 근거 (수정됨)

### 5.1 Level 1 (P0 + P1) 효과 추정

| 최적화 | 현재 | 예상 | 근거 |
|--------|------|------|------|
| Node 객체 제거 | - | 메모리 1.5GB↓ | 413K × 4KB → 413K × 8B |
| 단일 순회 | 20초 | 10초 | iterations 50% 감소 |
| split/join 제거 | 5초 | 2초 | 문자열 연산 제거 |
| Edge 사전 분류 | 5초 | 3초 | 필터링 오버헤드 제거 |
| **L1 합계** | 30초 | 15초 | **50% 개선** |

### 5.2 Level 3 (Rust) 효과 추정

| 최적화 | Level 1 후 | 예상 | 근거 |
|--------|------------|------|------|
| ID 인터닝 | 2.5GB | 1GB | 문자열 중복 제거 |
| Fst 심볼 | 10초 | 2초 | 압축 automaton |
| Rayon 병렬 | 2초 | 0.5초 | GIL-free 16코어 |
| **L3 합계** | 15초 | 3초 | **80% 추가 개선** |

### 5.3 종합 목표 (보수적)

| 단계 | Phase 2 시간 | 메모리 피크 | 누적 개선 |
|------|-------------|------------|----------|
| 현재 | 62초 | 6.8GB | - |
| P0 완료 | 40초 | 4.5GB | 35% |
| P1 완료 | 25초 | 3.5GB | 60% |
| **P2 완료** | **10초** | **2GB** | **84%** |

---

## 6. 리스크 및 완화 (수정됨)

| 리스크 | 영향 | 완화 방안 |
|--------|------|----------|
| "0 deps" 정확도 문제 | 높음 | P0에서 먼저 해결 |
| Fst immutable 제약 | 중간 | 2-tier 구조 (main + delta) |
| Rust 빌드 복잡성 | 중간 | maturin + CI 자동화 |
| ~~ProcessPoolExecutor 오버헤드~~ | ~~낮음~~ | **사용 금지** |
| msgpack 직렬화 비용 | 낮음 | 배치 크기 튜닝 |

---

## 7. 성공 지표

### 7.1 성능 지표

| 지표 | 현재 | P0 | P1 | P2 (목표) |
|-----|------|-----|-----|----------|
| Phase 2 시간 | 62초 | 40초 | 25초 | **10초** |
| 메모리 피크 | 6.8GB | 4.5GB | 3.5GB | **2GB** |
| 처리량 (LOC/s) | 21K | 31K | 49K | **54K** |

### 7.2 품질 지표

| 지표 | 기준 |
|-----|------|
| 테스트 통과율 | 100% |
| Symbol resolution 정확도 | 99%+ (현재 0% → 수정 필요) |
| 기존 API 호환성 | 100% |

---

## 8. 결론 (수정됨)

### 핵심 메시지

1. **Phase 2가 70% 병목** - L4 Cross-file이 주범
2. **"0 deps"가 정확도 문제일 수 있음** - 최적화 전에 확인 필요
3. **Node 객체 전역 저장이 메모리 주범** - P0에서 즉시 제거
4. **ProcessPoolExecutor + 거대 객체는 금지** - 성능 악화 유발
5. **Rust는 DashMap보다 ID 인터닝 + Fst가 핵심**

### 다음 단계

1. **즉시 (P0)**: "0 deps" 원인 파악 + Node 객체 제거
2. **P1**: 알고리즘 최적화 (split/join 제거, edge 분류)
3. **P2**: Rust 마이그레이션 (인터닝 + Fst)

---

## Appendix A: 벤치마크 명령어

```bash
# 현재 성능 측정
python tools/benchmark/bench_indexing_dag.py /path/to/repo --skip-vector

# 프로파일링
py-spy record -o profile.svg -- python tools/benchmark/bench_indexing_dag.py /path/to/repo

# 메모리 프로파일링
python -m scalene tools/benchmark/bench_indexing_dag.py /path/to/repo
```

## Appendix B: 관련 파일

| 파일 | 역할 |
|-----|------|
| `packages/codegraph-engine/.../cross_file_resolver.py` | L4 Cross-file |
| `packages/codegraph-engine/.../occurrence_generator.py` | L2 Occurrence |
| `packages/codegraph-shared/.../cross_file_handler.py` | L4 Handler |
| `packages/codegraph-shared/.../occurrence_handler.py` | L2 Handler |
| `tools/benchmark/bench_indexing_dag.py` | DAG 벤치마크 |
| `packages/codegraph-rust/codegraph-ir/` | Rust 확장 |

## Appendix C: 참고 자료

- [fst crate](https://docs.rs/fst) - Finite State Transducer for Rust
- [DashMap](https://docs.rs/dashmap) - Concurrent HashMap (샤딩 락 기반)
- [Rayon](https://docs.rs/rayon) - Data parallelism library
- [FxHash](https://docs.rs/fxhash) - Fast non-cryptographic hash
- [PyO3](https://pyo3.rs) - Rust bindings for Python
