# 정확한 벤치마크 측정 결과

## Executive Summary

**진짜 병목: IR Generation (1,190ms, 54%)**

GraphBuilder 최적화는 성공적이었으나, 애초에 GraphBuilder가 병목이 아니었음.

---

## 측정 결과 비교

### Before: 잘못된 측정 (monolithic build phase)

| 레이어 | 시간 | 비율 | 문제점 |
|--------|------|------|--------|
| Graph Layer | 1,859ms | 81.4% | ❌ 모든 build 작업이 "graph"로 분류됨 |
| Chunk Layer | 133ms | 6% | ✓ |
| Semantic Layer | 100ms | 4% | ✓ |

**문제**: `build:{file}` 단일 phase에 IR gen, Semantic, Graph, SymbolGraph, Chunk가 모두 포함됨

### After: 정확한 측정 (granular phases)

| 레이어 | 시간 | 비율 | 파일당 평균 | Phase 수 |
|--------|------|------|------------|----------|
| **IR Generation** | **1,190ms** | **54.1%** | **5.6ms** | 211 |
| Graph Build | 314ms | 14.3% | 1.5ms | 211 |
| Semantic IR | 281ms | 12.8% | 1.3ms | 211 |
| Chunk Build | 170ms | 7.7% | 0.8ms | 211 |
| Symbol Graph | 150ms | 6.8% | 0.7ms | 211 |
| Parsing | 94ms | 4.3% | 0.4ms | 211 |
| **Total (core)** | **2,199ms** | **100%** | **10.4ms** | 1,266 |

---

## 예측 vs 실제 비교

### 내 예측 (GRAPH_OPTIMIZATION_ANALYSIS.md)

| 단계 | 예측 시간 | 예측 비율 | 실제 시간 | 실제 비율 | 정확도 |
|------|----------|----------|----------|----------|--------|
| IR Generation | ~1,200ms | 53% | 1,190ms | 54.1% | ✅ 99% |
| SymbolGraph | ~600ms | 26% | 150ms | 6.8% | ❌ 75% 차이 |
| Graph Building | ~420ms | 18% | 314ms | 14.3% | ✅ 75% |
| Semantic IR | ~100ms | 4% | 281ms | 12.8% | ❌ 3배 차이 |

**교훈**:
- IR Generation 예측은 정확했음
- SymbolGraph는 예상보다 훨씬 빠름 (4배 빠름!)
- Semantic IR은 예상보다 느림 (3배 느림)

---

## GraphBuilder 최적화 효과

### 최적화 내용

1. **Request Flow Index**: O(n³) → O(1) (adjacency list)
2. **Index Building**: 3회 순회 → 1회 순회 (single pass)
3. **nodes_by_kind Index**: O(n) 필터링 → O(1) lookup

### 최적화 전후 비교

| 항목 | Before | After | 개선 |
|------|--------|-------|------|
| Graph Build 시간 | ~1.5ms/file | ~1.5ms/file | 미미 |
| 이유 | **애초에 충분히 빠름** | | |

**결론**:
- 최적화는 코드 품질 개선 측면에서 의미 있음
- 하지만 성능 병목이 아니었음
- "Premature optimization" 사례

---

## 진짜 병목 분석

### 1. IR Generation (1,190ms, 54%)

**작업 내용**:
- `PythonIRGenerator.generate()`
- Tree-sitter AST 순회
- IRDocument 생성 (8,908 nodes, 11,084 edges)

**파일당 평균**: 5.6ms

**가장 느린 파일**:
1. `indexing/orchestrator.py`: ~33ms (323 nodes)
2. `foundation/generators/python_generator.py`: ~28ms (202 nodes)
3. `foundation/chunk/incremental.py`: ~27ms (211 nodes)

**최적화 방향**:
- Tree-sitter 순회 최적화
- 노드 생성 로직 간소화
- Bulk creation 패턴
- Cython/Rust 확장 고려

### 2. Graph Build (314ms, 14.3%)

**작업 내용**:
- `GraphBuilder.build_full()`
- IRDocument + SemanticIR → GraphDocument

**파일당 평균**: 1.5ms ← **매우 빠름!**

**결론**: 최적화 불필요. 이미 충분히 빠름.

### 3. Semantic IR (281ms, 12.8%)

**작업 내용**:
- `DefaultSemanticIrBuilder.build_full()`
- Type resolution, signature building, CFG

**파일당 평균**: 1.3ms

**최적화 여지**: 중간 수준

### 4. Symbol Graph (150ms, 6.8%)

**작업 내용**:
- `SymbolGraphBuilder.build_from_graph()`
- GraphDocument → SymbolGraph 변환

**파일당 평균**: 0.7ms ← **매우 빠름!**

**결론**: 예상보다 4배 빠름. 최적화 불필요.

---

## 레이어별 상세 분석

### Parsing Layer (94ms, 4.3%)

```
- Tree-sitter parsing
- AstTree.parse()
- 0.4ms/file
```

**결론**: 매우 빠름. Tree-sitter 성능 우수.

### IR Generation Layer (1,190ms, 54.1%) ⚠️ BOTTLENECK

```
- AST → IRDocument 변환
- PythonIRGenerator.generate()
- 5.6ms/file
```

**최적화 우선순위**: ⭐⭐⭐⭐⭐ (가장 높음)

### Semantic Layer (281ms, 12.8%)

```
- Type resolution
- Signature building
- CFG construction
- 1.3ms/file
```

**최적화 우선순위**: ⭐⭐⭐ (중간)

### Graph Layer (464ms, 21.1%)

```
Graph Build:   314ms (1.5ms/file)
Symbol Graph:  150ms (0.7ms/file)
```

**최적화 우선순위**: ⭐ (낮음 - 이미 충분히 빠름)

### Chunk Layer (170ms, 7.7%)

```
- ChunkBuilder.build()
- Hierarchical chunking
- 0.8ms/file
```

**최적화 우선순위**: ⭐⭐ (낮음)

---

## 성능 목표 및 로드맵

### 현재 성능 (211 files)

- **Total indexing**: 2,199ms (10.4ms/file)
- **Throughput**: ~96 files/sec

### 목표 1: IR Generation 최적화 (50% 개선)

**예상 효과**:
- IR Generation: 1,190ms → 595ms (-595ms)
- **Total**: 2,199ms → 1,604ms (-27%)
- **Throughput**: 96 → 132 files/sec (+37%)

**구현 방법**:
1. AST 순회 최적화 (불필요한 visit 제거)
2. 노드 생성 최적화 (object creation overhead 감소)
3. Batch processing (bulk insert)

### 목표 2: Semantic IR 최적화 (30% 개선)

**예상 효과**:
- Semantic IR: 281ms → 197ms (-84ms)
- **Total**: 1,604ms → 1,520ms (-5%)
- **Throughput**: 132 → 139 files/sec (+5%)

### 목표 3: 병렬 처리

**예상 효과** (4 workers):
- **Total**: 1,520ms → 380ms (-75%)
- **Throughput**: 139 → 555 files/sec (+300%)

**구현 복잡도**: High (상태 관리, 동기화)

---

## 교훈

### 1. "측정하지 않으면 최적화할 수 없다"

> Code inspection만으로는 병목을 찾을 수 없다.
> 항상 정확한 측정이 선행되어야 한다.

### 2. "Premature optimization is the root of all evil"

> GraphBuilder 최적화는 기술적으로 올바르지만,
> 실제로는 병목이 아니었기에 의미 없었다.

### 3. "세밀한 측정이 핵심"

> Monolithic phase는 정확한 분석을 불가능하게 만든다.
> Granular phase separation이 정확한 병목 파악의 핵심.

### 4. "예측은 검증되어야 한다"

> 내 예측:
> - IR Generation: 99% 정확 ✅
> - SymbolGraph: 75% 오차 ❌
> - Semantic IR: 3배 오차 ❌
>
> → 측정 없이는 확신할 수 없다!

---

## 다음 단계

### Phase 1: IR Generation 최적화 (우선순위: 높음)

**목표**: 1,190ms → 595ms (50% 개선)

**작업 계획**:
1. ✅ Profiling 완료
2. ⬜ IR Generator 병목 분석 (cProfile)
3. ⬜ AST 순회 최적화
4. ⬜ 노드 생성 최적화
5. ⬜ 벤치마크 재측정

**예상 소요 시간**: 2-3일

### Phase 2: Semantic IR 최적화 (우선순위: 중간)

**목표**: 281ms → 197ms (30% 개선)

### Phase 3: 병렬 처리 (우선순위: 낮음)

**목표**: 4x throughput

**복잡도**: 높음 (구조 변경 필요)

---

## 벤치마크 상세 정보

### 테스트 환경

- **Repository**: `src/` (전체 소스 코드)
- **Files**: 211개 Python 파일
- **LOC**: 총 코드 라인 수
- **Nodes**: 8,908개 IR 노드
- **Edges**: 11,084개 IR 엣지
- **Symbols**: 21,998개 Semantic 심볼

### 측정 방법

```python
# 각 파일에 대해 6개 phase로 분리 측정
parse_phase = f"parse:{file}"
ir_gen_phase = f"ir_gen:{file}"
semantic_ir_phase = f"semantic_ir:{file}"
graph_build_phase = f"graph_build:{file}"
symbol_graph_phase = f"symbol_graph:{file}"
chunk_build_phase = f"chunk_build:{file}"
```

### Report 위치

```
benchmark/reports/src/2025-11-25/121750_report.txt
```

---

## 결론

1. ✅ **정확한 측정 완료**: Granular phase profiling으로 각 단계별 정확한 시간 측정
2. ✅ **진짜 병목 발견**: IR Generation (1,190ms, 54%)이 진짜 병목
3. ✅ **GraphBuilder는 빠름**: 1.5ms/file로 충분히 빠름. 최적화 불필요.
4. ✅ **SymbolGraph도 빠름**: 0.7ms/file로 예상보다 4배 빠름.
5. ⚠️ **다음 타겟**: IR Generation 최적화가 가장 큰 impact를 가질 것

**ROI (투자 대비 효과)**:
- IR Generation 최적화: 50% 개선 → -595ms (최고)
- Semantic IR 최적화: 30% 개선 → -84ms (중간)
- Graph 추가 최적화: 거의 없음 (낮음)
