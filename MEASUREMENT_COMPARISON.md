# 측정 비교: Before vs After

## 시각적 비교

### ❌ Before: 잘못된 측정 (monolithic phase)

```
전체 파이프라인 (2,283ms)
├── Graph Layer       █████████████████████████████████ 1,859ms (81.4%)  ← 잘못됨!
├── Chunk Layer       ███ 133ms (6%)
├── Semantic Layer    ██ 100ms (4%)
└── 기타              ███ ~200ms (9%)
```

**문제점**:
- `build:{file}` 하나의 phase에 모든 작업 포함
- IR gen + Semantic + Graph + SymbolGraph + Chunk가 모두 "Graph"로 분류됨
- 진짜 병목을 알 수 없음

---

### ✅ After: 정확한 측정 (granular phases)

```
전체 파이프라인 (2,199ms)
├── IR Generation     ████████████████████████████ 1,190ms (54.1%)  ← 진짜 병목!
├── Graph Build       ███████ 314ms (14.3%)
├── Semantic IR       ██████ 281ms (12.8%)
├── Chunk Build       ███ 170ms (7.7%)
├── Symbol Graph      ███ 150ms (6.8%)
└── Parsing           ██ 94ms (4.3%)
```

**개선점**:
- 각 단계를 독립적으로 측정
- 정확한 병목 파악 가능
- 최적화 우선순위 명확

---

## 핵심 발견

### 1. IR Generation이 진짜 병목 (1,190ms, 54%)

```python
# 가장 느린 단계
ir_gen_phase = profiler.measure("ir_gen:file.py")
# → PythonIRGenerator.generate()
# → Tree-sitter AST 순회 + IR 노드 생성
# → 평균 5.6ms/file
```

**왜 느린가?**
- 8,908개 노드 생성
- 11,084개 엣지 생성
- 복잡한 AST 순회 로직
- Python object creation overhead

**최적화 방향**:
- AST 순회 최적화
- 노드 생성 최적화
- Batch processing
- 50% 개선 목표 → -595ms

---

### 2. GraphBuilder는 이미 빠름 (314ms, 14.3%)

```python
# 실제로는 매우 빠름
graph_build_phase = profiler.measure("graph_build:file.py")
# → GraphBuilder.build_full()
# → 평균 1.5ms/file  ← 매우 빠름!
```

**최적화는 성공했지만**:
- O(n³) → O(1) 최적화 완료
- 하지만 애초에 빠른 코드였음
- 추가 최적화 불필요

---

### 3. SymbolGraph는 예상보다 4배 빠름 (150ms, 6.8%)

```python
# 예상보다 훨씬 빠름
symbol_graph_phase = profiler.measure("symbol_graph:file.py")
# → SymbolGraphBuilder.build_from_graph()
# → 평균 0.7ms/file  ← 예상: 2.8ms
```

**내 예측**: ~600ms (26%)
**실제 측정**: 150ms (6.8%)
**오차**: 4배 빠름!

**이유**:
- In-memory 구조가 효율적
- GraphDocument → SymbolGraph 변환이 단순
- 최적화 불필요

---

## 파일별 상세 분석

### 가장 느린 파일 Top 3

#### 1. indexing/orchestrator.py (70ms)
```
├── Parse:         1ms
├── IR Gen:       33ms  ← 병목!
├── Semantic:     10ms
├── Graph:         6ms
├── SymbolGraph:   3ms
└── Chunk:         2ms
```

#### 2. foundation/generators/python_generator.py (60ms)
```
├── Parse:         1ms
├── IR Gen:       28ms  ← 병목!
├── Semantic:      8ms
├── Graph:         5ms
├── SymbolGraph:   2ms
└── Chunk:         2ms
```

#### 3. foundation/chunk/incremental.py (57ms)
```
├── Parse:         1ms
├── IR Gen:       27ms  ← 병목!
├── Semantic:      9ms
├── Graph:         5ms
├── SymbolGraph:   2ms
└── Chunk:         2ms
```

**패턴**: 모든 느린 파일에서 IR Generation이 가장 큰 시간 차지

---

## 최적화 ROI 분석

### Option 1: IR Generation 최적화 (추천 ⭐⭐⭐⭐⭐)

**현재**: 1,190ms (54%)
**목표**: 595ms (50% 개선)
**절감**: -595ms
**효과**: 전체 27% 개선 (2,199ms → 1,604ms)

**구현 난이도**: 중간
**ROI**: 매우 높음

### Option 2: Semantic IR 최적화 (추천 ⭐⭐⭐)

**현재**: 281ms (13%)
**목표**: 197ms (30% 개선)
**절감**: -84ms
**효과**: 전체 4% 개선

**구현 난이도**: 중간
**ROI**: 중간

### Option 3: Graph 추가 최적화 (추천 ⭐)

**현재**: 314ms (14%)
**목표**: 280ms (10% 개선)
**절감**: -34ms
**효과**: 전체 1.5% 개선

**구현 난이도**: 낮음
**ROI**: 낮음 (이미 충분히 빠름)

### Option 4: 병렬 처리 (추천 ⭐⭐⭐⭐)

**현재**: 2,199ms (단일 스레드)
**목표**: 550ms (4 workers)
**절감**: -1,649ms (75%)
**효과**: Throughput 4배 증가

**구현 난이도**: 높음
**ROI**: 매우 높음 (하지만 복잡)

---

## 타임라인

### Week 1: IR Generation 최적화
```
Day 1-2: Profiling 및 병목 분석
Day 3-4: AST 순회 최적화
Day 5:   노드 생성 최적화
Day 6:   벤치마크 및 검증
Day 7:   문서화

예상 효과: -595ms (27% 개선)
```

### Week 2: Semantic IR 최적화
```
Day 1-2: Type resolution 최적화
Day 3-4: CFG 구축 최적화
Day 5:   벤치마크 및 검증

예상 효과: -84ms (4% 개선)
```

### Week 3-4: 병렬 처리 (선택)
```
Week 3: 설계 및 프로토타입
Week 4: 구현 및 테스트

예상 효과: 4배 throughput 증가
```

---

## 측정 방법론 개선

### Before: Monolithic Phase
```python
profiler.start_phase(f"build:{file}")
# ❌ 모든 작업이 하나의 phase
ir_doc = generate_ir(...)
semantic = build_semantic(...)
graph = build_graph(...)
symbol = build_symbol_graph(...)
chunks = build_chunks(...)
profiler.end_phase(f"build:{file}")
```

### After: Granular Phases
```python
# ✅ 각 단계를 독립적으로 측정
profiler.start_phase(f"ir_gen:{file}")
ir_doc = generate_ir(...)
profiler.end_phase(f"ir_gen:{file}")

profiler.start_phase(f"semantic_ir:{file}")
semantic = build_semantic(...)
profiler.end_phase(f"semantic_ir:{file}")

profiler.start_phase(f"graph_build:{file}")
graph = build_graph(...)
profiler.end_phase(f"graph_build:{file}")

profiler.start_phase(f"symbol_graph:{file}")
symbol = build_symbol_graph(...)
profiler.end_phase(f"symbol_graph:{file}")

profiler.start_phase(f"chunk_build:{file}")
chunks = build_chunks(...)
profiler.end_phase(f"chunk_build:{file}")
```

---

## 결론

### ❌ 기존 인식 (잘못됨)
> "Graph Layer가 81.4% (1,859ms) 차지하니까 GraphBuilder가 병목이다!"

### ✅ 정확한 측정 결과
> "IR Generation이 54.1% (1,190ms) 차지하고,
> GraphBuilder는 14.3% (314ms, 1.5ms/file)로 이미 충분히 빠르다!"

### 📊 Data-Driven Decision
1. **IR Generation 최적화**: 가장 큰 impact (27% 개선 가능)
2. **Semantic IR 최적화**: 중간 impact (4% 개선 가능)
3. **Graph 추가 최적화**: 낮은 impact (1.5% 개선)
4. **병렬 처리**: 장기적으로 가장 큰 효과 (4배 throughput)

### 🎯 Next Action
```bash
# Phase 1: IR Generation profiling
python -m cProfile -o profile.stats benchmark/run_benchmark.py src/
python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative').print_stats('PythonIRGenerator', 20)"
```

**목표**: IR Generation 내부 병목 식별 → 50% 개선
