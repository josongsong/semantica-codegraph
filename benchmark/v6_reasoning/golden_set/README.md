# v6 Reasoning Engine - Golden Set

v6 추론 엔진의 정확도를 검증하기 위한 Ground Truth 데이터셋.

## 목표

- **Impact Analysis:** Symbol hash가 올바른 영향도를 산출하는지
- **Semantic Diff:** 동작 변화 vs 리팩토링을 올바르게 구분하는지
- **Program Slice:** 올바른 slice를 추출하는지

## 구조

```
golden_set/
├── impact_cases.json       # 30개 impact 시나리오
├── semantic_changes.json   # 50개 semantic change 시나리오
├── slice_cases.json        # 40개 slice 시나리오
└── examples/               # 실제 코드 예제
    ├── impact/
    ├── semantic/
    └── slice/
```

## Impact Cases (30개 목표)

각 케이스는 다음을 포함:

```json
{
  "id": "impact_001",
  "description": "함수 body만 변경 (signature 불변)",
  "before": "def foo(x: int) -> int:\n    return x + 1",
  "after": "def foo(x: int) -> int:\n    return x + 2",
  "expected_impact": {
    "level": "ir_local",
    "affected_symbols": ["foo"],
    "callers_affected": false
  }
}
```

**시나리오 분류:**
- NO_IMPACT (5개): 주석, 포맷팅만 변경
- IR_LOCAL (10개): Body 변경, signature 불변
- SIGNATURE_CHANGE (10개): 파라미터/반환 타입 변경
- STRUCTURAL_CHANGE (5개): import/export 변경

## Semantic Change Cases (50개 목표)

각 케이스는 다음을 포함:

```json
{
  "id": "semantic_001",
  "description": "Side effect 추가 (global mutation)",
  "before": "def foo():\n    x = 1",
  "after": "def foo():\n    global_state.counter += 1\n    x = 1",
  "expected_change": {
    "is_pure_refactoring": false,
    "effect_added": ["global_mutation"],
    "risk_level": "high"
  }
}
```

**시나리오 분류:**
- Pure Refactoring (20개): 변수명 변경, extract function 등
- Effect Added (15개): IO, DB, Network 추가
- Signature Change (10개): 파라미터/반환 타입 변경
- Control Flow Change (5개): 분기 로직 변경

## Slice Cases (40개 목표)

각 케이스는 다음을 포함:

```json
{
  "id": "slice_001",
  "description": "단순 데이터 흐름 (3-hop)",
  "code": "def foo():\n    x = 1\n    y = x + 2\n    z = y * 3\n    return z",
  "target": {
    "variable": "z",
    "line": 5
  },
  "expected_slice": {
    "nodes": ["x", "y", "z"],
    "lines": [2, 3, 4, 5],
    "total_tokens": 50
  }
}
```

**시나리오 분류:**
- Simple Dataflow (10개): 단순 변수 의존성
- Control Dependency (10개): if/loop 조건
- Cross-Function (10개): 함수 호출 추적
- Complex (10개): Closure, side-effect 등

## 수집 방법

### 1. 실제 프로젝트에서 추출
- Django, FastAPI, Flask 등의 실제 커밋
- "Refactor" vs "Feature" 라벨링

### 2. 합성 데이터 생성
- 특정 패턴을 테스트하기 위한 최소 예제

### 3. 사람이 검증
- 각 케이스를 최소 2명이 리뷰
- Expected output 합의

## 현재 상태

- [ ] Impact Cases: 0/30
- [ ] Semantic Change Cases: 0/50
- [ ] Slice Cases: 0/40

**Next Steps:**
1. 템플릿 JSON 파일 생성
2. 실제 프로젝트에서 10개 케이스 추출
3. 합성 데이터 20개 생성
4. 리뷰 및 검증

## 사용 방법

```python
# 벤치마크 실행
from benchmark.v6_reasoning import run_golden_set_benchmark

results = run_golden_set_benchmark(
    golden_set_path="benchmark/v6_reasoning/golden_set",
    engine=reasoning_engine
)

print(f"Impact Accuracy: {results['impact_accuracy']:.2%}")
print(f"Semantic Diff Accuracy: {results['semantic_accuracy']:.2%}")
print(f"Slice Quality: {results['slice_quality']:.2%}")
```

## 품질 기준

### Phase 1 완료 조건
- Impact Accuracy >= 95%
- Semantic Diff Accuracy >= 85%

### Phase 3 완료 조건
- Slice Quality >= 90%
- Token Budget 준수율 100%

