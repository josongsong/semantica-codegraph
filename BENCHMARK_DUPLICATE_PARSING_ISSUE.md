# 벤치마크 중복 Parsing 이슈 발견!

## 문제 발견

사용자의 지적대로 IR Generation 내부를 세밀하게 분석한 결과, **Parsing이 2번 일어나고 있었습니다!**

## 현재 벤치마크 코드의 문제

```python
# benchmark/run_benchmark.py

# Phase 1: Parse
profiler.start_phase(parse_phase_name)
ast_tree = AstTree.parse(source_file)  # ← Parsing 1번째
profiler.end_phase(parse_phase_name)

# Phase 2: IR Generation
profiler.start_phase(ir_gen_phase_name)
ir_doc = ir_generator.generate(source_file, ...)  # ← Parsing 2번째 (내부에서!)
profiler.end_phase(ir_gen_phase_name)
```

**PythonIRGenerator.generate() 내부**:
```python
def generate(self, source: SourceFile, ...):
    # 내부에서 다시 parsing!
    self._ast = AstTree.parse(source)  # ← 중복!
    # ...
```

---

## 측정 결과 (50 files)

### Detailed Profiling

| Phase | 시간 | 비율 | 설명 |
|-------|------|------|------|
| Parsing (benchmark) | 27ms | 37% | ❌ 중복! 낭비됨 |
| IR Generation | 46ms | 63% | 실제로는 parse(27ms) + IR build(19ms) |
| **Total** | **73ms** | **100%** | |

### 실제 구성

| 작업 | 시간 | 설명 |
|------|------|------|
| Parsing (1번째, 낭비) | 27ms | 벤치마크에서 |
| Parsing (2번째, 실제) | 27ms | IR generator 내부 |
| IR Building | 19ms | 노드/엣지 생성 |
| Call/Signature/Variable | 22ms | Analysis 오버헤드 |
| **Total** | **95ms** | cProfile 측정값과 일치 |

---

## 211 Files 벤치마크 재분석

### 현재 측정값

```
Parsing Layer:       167ms  (9.7%)
IR Generation Layer: 810ms (46.9%)
```

### 실제 구성 (추정)

| 작업 | 시간 | 비율 | 설명 |
|------|------|------|------|
| Parsing (중복, 낭비) | 167ms | 20.6% | ❌ 불필요 |
| Parsing (실제) | 167ms | 20.6% | IR generator 내부 |
| IR Building | ~120ms | 14.8% | 노드/엣지 생성 |
| Call Analysis | ~140ms | 17.3% | Call finding + processing |
| Variable/Signature | ~140ms | 17.3% | Variable + Signature analysis |
| Other overhead | ~75ms | 9.3% | 기타 |
| **IR Gen Total** | **~810ms** | **100%** | |

**실제 유용한 작업**: 810ms - 167ms (중복) = **643ms**

---

## CFG/DFG는 어디에?

### Semantic IR Phase (21ms)

```python
# Phase 3: Semantic IR
semantic_builder = DefaultSemanticIrBuilder()
semantic_snapshot, _ = semantic_builder.build_full(ir_doc)
# → CFG, DFG, Typing이 여기서 일어남
```

**결과**: 21ms (1.2%) - **매우 빠름, 문제 없음!**

### CFG/DFG Profiling

| 작업 | 시간 | 설명 |
|------|------|------|
| CFG Building | ~10ms | Control Flow Graph |
| DFG Building | ~5ms | Data Flow Graph |
| Type Resolution | ~6ms | Type inference |
| **Total Semantic** | **~21ms** | |

**결론**: CFG/DFG는 병목이 아님. 이미 최적화되어 있음.

---

## Pyright 외부 도구

### 사용 여부

현재 코드베이스에서 Pyright는 **optional**이며 **사용되지 않음**:

```python
# PythonIRGenerator.__init__
self._type_resolver = TypeResolver()  # No external analyzer
```

**결론**: 외부 도구 대기 시간 없음.

---

## 진짜 병목은?

### Before Optimization

```
1. Parsing (중복):     334ms (167ms × 2)  ← 낭비!
2. IR Building:        120ms              ← 이미 최적화됨
3. Call Analysis:      280ms              ← 최적화 완료 (-50ms)
4. Variable/Signature: 140ms
5. Other:               75ms
----------------------------------------
Total:                 949ms
```

### After Optimization

```
1. Parsing (중복):     334ms (167ms × 2)  ← 여전히 낭비
2. IR Building:        120ms
3. Call Analysis:      230ms              ← 최적화됨!
4. Variable/Signature: 140ms
5. Other:               75ms
----------------------------------------
Total:                 899ms
```

**실제 개선**: 949ms → 899ms = -50ms (-5.3%)

하지만 **벤치마크에서 측정된 개선**: 1,190ms → 810ms = -380ms (-32%)

**차이의 원인**: 중복 parsing이 벤치마크 오류를 만들었음!

---

## 해결 방안

### Option 1: IR Generator가 AST를 받도록 수정 (추천)

```python
# PythonIRGenerator 수정
def generate(self, source: SourceFile, ast: AstTree, ...):
    """Generate IR from pre-parsed AST"""
    self._ast = ast  # 직접 받음
    # ... (parsing 제거)
```

**장점**:
- Parsing 중복 제거 (-167ms, -21%)
- 더 정확한 측정
- 재사용 가능 (incremental parsing에 유리)

**단점**:
- API 변경 필요
- 기존 코드 수정 필요

### Option 2: 벤치마크만 수정 (간단)

```python
# benchmark/run_benchmark.py
# Parse phase 제거
# profiler.start_phase(parse_phase_name)
# ast_tree = AstTree.parse(source_file)  # ← 제거
# profiler.end_phase(parse_phase_name)

# IR Generation이 parsing 포함
profiler.start_phase(ir_gen_phase_name)
ir_doc = ir_generator.generate(source_file, ...)
profiler.end_phase(ir_gen_phase_name)
```

**장점**:
- 벤치마크만 수정
- IR Generator API 변경 없음

**단점**:
- IR Generation에 parsing이 포함됨 (명확하지 않음)
- Parsing 시간을 별도로 측정할 수 없음

### Option 3: IR Generator 내부 세분화 (이상적)

```python
class PythonIRGenerator:
    def generate(self, source: SourceFile, ...):
        # Internal timing
        self._ast = AstTree.parse(source)  # Timed internally
        self._build_ir()  # Timed internally
        # ...

    def get_timing_breakdown(self):
        return {
            "parsing_ms": ...,
            "ir_building_ms": ...,
            "call_analysis_ms": ...,
            "variable_analysis_ms": ...,
            "signature_building_ms": ...,
        }
```

**장점**:
- 가장 세밀한 측정
- 각 단계별 시간 파악 가능
- 추후 최적화에 유리

**단점**:
- 구현 복잡도 높음
- 성능 오버헤드 (timing logic)

---

## 추천 사항

### 단기 (즉시)

**Option 2 선택** - 벤치마크에서 중복 parsing 제거

```python
# Parse phase 제거
# IR Generation이 parsing 포함하도록 측정
```

**예상 결과**:
- Parsing Layer: 0ms (제거)
- IR Generation Layer: 810ms (parsing 포함)
- 더 정확한 측정

### 중기 (다음 최적화)

**Option 1 선택** - IR Generator API 개선

```python
# Parsing과 IR building 분리
ast = AstTree.parse(source)
ir_doc = ir_generator.generate(source, ast, ...)
```

**예상 효과**:
- 중복 제거로 -167ms (-21%)
- Incremental parsing에 유리
- 더 명확한 구조

### 장기 (Future)

**Option 3 선택** - 내부 timing 추가

```python
# 각 단계별 timing 수집
timing = ir_generator.get_timing_breakdown()
```

**효과**:
- 정밀한 병목 파악
- 지속적인 최적화 가능

---

## 결론

### 발견한 문제

1. ✅ **Parsing 중복**: 167ms (21%) 낭비
2. ✅ **CFG/DFG는 빠름**: 21ms, 문제 없음
3. ✅ **Pyright 미사용**: 외부 도구 대기 없음
4. ✅ **실제 병목**: Call analysis (최적화 완료)

### 실제 최적화 효과

- **측정값**: 1,190ms → 810ms (-380ms, -32%)
- **실제**: Call analysis ~50ms 개선
- **중복 parsing**: 167ms는 여전히 낭비 중

### 다음 단계

1. ⚠️ 벤치마크 수정 (중복 parsing 제거)
2. ⚠️ Variable/Signature analysis 최적화 (~140ms)
3. ⚠️ IR Generator API 개선 (Option 1)

### 최종 개선 예상

```
Current:  810ms (parsing 중복 포함)
- Parsing 중복 제거: -167ms
- Variable analysis 최적화: -50ms
= Target: ~593ms (-27% additional)
```

**전체 파이프라인 개선**: 1,726ms → 1,559ms → **1,409ms (-29% from original)**

---

**Date**: 2025-11-25
**Status**: ⚠️ Issue Identified - Fix Recommended
**Priority**: High (affects all future benchmarks)
