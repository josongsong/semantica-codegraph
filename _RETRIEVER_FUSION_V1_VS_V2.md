# Multi-Strategy Fusion: v1 vs v2 Comparison

**Date**: 2025-11-25
**Status**: v2 Ready for Testing

---

## 🎯 핵심 문제와 해결

### ❌ v1의 문제점

| 문제 | 원인 | 영향 |
|------|------|------|
| **Score Calibration** | 각 인덱스의 스케일이 다름 | BM25가 구조적으로 지배 |
| **Rank Decay 너무 완만** | `1/(1+0.1*rank)` | Tail noise 과다 유입 |
| **Consensus Boost 과함** | 선형 증가 `1+0.2*(k-1)` | 약한 증거도 과대평가 |
| **Single Intent** | Mutually exclusive | 복합 쿼리 처리 불가 |

---

## ✅ v2 개선 사항

### 1. Weighted RRF (가장 큰 개선) ⭐⭐⭐⭐⭐

**v1 (Score-based)**:
```python
# 문제: 각 인덱스의 score 스케일이 다름
weighted_score = 0
for strategy, score, rank in appearances:
    weight = get_weight(strategy)
    rank_decay = 1.0 / (1.0 + rank * 0.1)
    weighted_score += weight * score * rank_decay  # ← score 직접 사용
```

**v2 (Rank-based RRF)**:
```python
# 해결: Rank만 사용, score 스케일 무관
rrf_sum = 0
for strategy, original_score, rank in appearances:
    weight = get_weight(strategy)
    rrf_component = weight / (k + rank)  # ← rank만 사용!
    rrf_sum += rrf_component
```

**효과**:
- Vector (0.6~0.95), Lexical (0~30), Symbol (binary) 모두 **공정하게** 처리
- IR 분야에서 검증된 방법 (RRF)
- 튜닝 안정적

---

### 2. Quality-Aware Consensus Boost

**v1 (무조건 선형)**:
```python
# 문제: 전략 개수만 보고 boost
if len(appearances) > 1:
    consensus_factor = 1.0 + 0.2 * (len(appearances) - 1)
    # 2 strategies: 1.2x
    # 3 strategies: 1.4x
    # 4 strategies: 1.6x  ← 너무 큼
```

**v2 (품질 조건 + sqrt 성장)**:
```python
# 해결: 품질 확인 + 완만한 성장
import math

# 1. sqrt 성장 (더 완만)
effective_strategies = min(num_strategies, 3)  # Cap at 3
base_factor = 1.0 + 0.15 * math.sqrt(effective_strategies - 1)
# 2 strategies: 1.15x
# 3 strategies: 1.21x
# 4 strategies: 1.26x (capped at 3)

# 2. 품질 조건
if max_component_score >= strong_threshold:
    consensus_factor = base_factor  # Full boost
else:
    consensus_factor = 1.0 + (base_factor - 1.0) * 0.5  # 50% boost
```

**효과**:
- 약한 다전략 합의는 과대평가 안 됨
- 강한 단일 증거 vs 약한 다전략 합의 → **강한 단일이 이김** (올바름)

---

### 3. Multi-Label Intent

**v1 (Mutually Exclusive)**:
```python
# 문제: 하나의 intent만 선택
if "symbol" in intent:
    weights = for_symbol_navigation()  # symbol 50%
elif "concept" in intent:
    weights = for_concept_search()  # vector 70%
else:
    weights = for_code_search()
```

**v2 (Multi-Label + Linear Combination)**:
```python
# 해결: 복수 intent 혼합
intent_scores = IntentScore(
    symbol_like=0.6,   # "User class" → symbol
    concept_like=0.4,  # "explain" → concept
)

# Linear combination
weights = (
    0.6 * W_SYMBOL_NAV +  # symbol 50% → 30%
    0.4 * W_CONCEPT       # vector 70% → 28%
).normalize()

# Result: symbol 30%, vector 28%, lexical 20%, ...
```

**효과**:
- "User class definition explain" 같은 **복합 쿼리** 자연스럽게 처리
- 향후 LTR로 확장 용이

---

## 📊 구체적 예시 비교

### 시나리오: "User class definition"

**데이터**:
```python
Vector:  [A(0.75, rank=1), D(0.85, rank=0)]
Lexical: [A(15.0, rank=0), B(25.0, rank=0)]  # BM25 스케일
Symbol:  [A(1.0, rank=0), F(0.9, rank=1)]
```

**Intent**: symbol_nav
- Symbol: 50%
- Vector: 20%
- Lexical: 20%
- Graph: 10%

---

### v1 Score-Based 계산

**Chunk A** (3 strategies):
```python
# Vector: 0.2 * 0.75 * (1/(1+0.1*1)) = 0.2 * 0.75 * 0.91 = 0.136
# Lexical: 0.2 * 15.0 * (1/(1+0.1*0)) = 0.2 * 15.0 * 1.0 = 3.00  ← BM25 지배!
# Symbol: 0.5 * 1.0 * (1/(1+0.1*0)) = 0.5 * 1.0 * 1.0 = 0.50

rrf_sum = 0.136 + 3.00 + 0.50 = 3.636

# Consensus boost (3 strategies)
consensus_factor = 1 + 0.2 * (3-1) = 1.4

final_score_v1 = 3.636 * 1.4 = 5.09  ← Lexical이 지배
```

**Chunk B** (1 strategy, Lexical only):
```python
# Lexical: 0.2 * 25.0 * 1.0 = 5.00

final_score_v1 = 5.00 * 1.0 = 5.00

# 결과: B (5.00) vs A (5.09) → A가 근소하게 이김
# 문제: Symbol perfect match인데도 Lexical에게 거의 밀림!
```

---

### v2 RRF-Based 계산

**Chunk A** (3 strategies):
```python
k = 60

# Vector: 0.2 / (60 + 1) = 0.00328
# Lexical: 0.2 / (60 + 0) = 0.00333  ← BM25 스케일 무관!
# Symbol: 0.5 / (60 + 0) = 0.00833  ← Symbol이 가장 높음

rrf_sum = 0.00328 + 0.00333 + 0.00833 = 0.01494

# Max component: 0.00833 (Symbol)
# Consensus boost (3 strategies, strong component)
consensus_factor = 1 + 0.15 * sqrt(2) = 1.21

final_score_v2 = 0.01494 * 1.21 = 0.0181
```

**Chunk B** (1 strategy, Lexical only):
```python
# Lexical: 0.2 / (60 + 0) = 0.00333

final_score_v2 = 0.00333 * 1.0 = 0.00333

# 결과: A (0.0181) >> B (0.00333) → A가 압도적으로 이김!
# ✅ Symbol perfect match + multi-strategy 합의가 제대로 반영됨
```

---

## 🔥 개선 효과

| Metric | v1 | v2 | 개선 |
|--------|----|----|------|
| **Score Calibration** | ❌ BM25 지배 | ✅ 공정 | +++ |
| **Symbol Match 반영** | 약함 (5.09 vs 5.00) | 강함 (0.0181 vs 0.0033) | **5.4배** |
| **Consensus Boost** | 과함 (1.4x) | 적절 (1.21x) | -14% |
| **Multi-Intent** | ❌ 불가 | ✅ 가능 | +++ |

---

## 🚀 사용 예시

### v1 사용 (기존)

```python
from src.retriever.fusion.smart_interleaving import (
    SmartInterleaver,
    InterleavingWeights,
)

# Single intent
interleaver = SmartInterleaver()
interleaver.set_weights_for_intent("symbol_nav")

results = interleaver.interleave(strategy_results, top_k=50)
```

---

### v2 사용 (권장)

```python
from src.retriever.fusion.smart_interleaving_v2 import (
    SmartInterleaverV2,
    InterleavingWeightsV2,
    IntentScore,
    InterleaverFactoryV2,
)

# Option 1: Simple intent (v1 compat)
interleaver = SmartInterleaverV2()
interleaver.set_weights_for_intent("symbol_nav")
results = interleaver.interleave(strategy_results, top_k=50)

# Option 2: Multi-label intent (recommended)
intent_scores = IntentScore(
    symbol_like=0.6,   # "User class" → symbol
    concept_like=0.4,  # "explain" → concept
)

interleaver = InterleaverFactoryV2.create(
    method="weighted_rrf",
    intent_scores=intent_scores,
    rrf_k=60,  # Tunable
    consensus_boost_base=0.15,  # Tunable
)

results = interleaver.interleave(strategy_results, top_k=50)

# Debugging: Check RRF components
for chunk in results[:5]:
    print(f"Chunk {chunk['chunk_id']}:")
    print(f"  Final score: {chunk['interleaving_score']:.4f}")
    print(f"  Strategies: {chunk['strategies']}")
    for comp in chunk['rrf_components']:
        print(f"    {comp['strategy']}: rank={comp['rank']}, "
              f"rrf={comp['rrf_component']:.4f}")
```

---

## 📋 Migration Guide

### Step 1: 테스트 (A/B 비교)

```python
# v1과 v2를 parallel로 실행해서 비교
v1_results = smart_interleaver_v1.interleave(strategy_results, top_k=50)
v2_results = smart_interleaver_v2.interleave(strategy_results, top_k=50)

# Top-10 비교
print("v1 Top-10:", [c['chunk_id'] for c in v1_results[:10]])
print("v2 Top-10:", [c['chunk_id'] for c in v2_results[:10]])

# Symbol match가 더 높은 순위로 왔는지 확인
```

---

### Step 2: Gradual Rollout

```python
# Canary: 5% traffic to v2
import random

if random.random() < 0.05:
    interleaver = SmartInterleaverV2()  # v2
else:
    interleaver = SmartInterleaver()  # v1 (fallback)
```

---

### Step 3: Full Migration

```python
# service_optimized.py에서 v2로 교체
from src.retriever.fusion.smart_interleaving_v2 import SmartInterleaverV2

self.smart_interleaver = SmartInterleaverV2(
    rrf_k=60,
    consensus_boost_base=0.15,
)
```

---

## 🎯 Tuning Parameters

### RRF k (기본: 60)

```python
# k 작을수록: 상위 rank에 더 집중
# k 클수록: 하위 rank도 고려

# Aggressive (상위 집중)
interleaver = SmartInterleaverV2(rrf_k=30)

# Conservative (전체 고려)
interleaver = SmartInterleaverV2(rrf_k=100)

# Recommended: 60 (검증된 기본값)
```

---

### Consensus Boost Base (기본: 0.15)

```python
# 작을수록: 단일 전략 선호
# 클수록: 다전략 합의 선호

# Weak boost
interleaver = SmartInterleaverV2(consensus_boost_base=0.10)

# Strong boost
interleaver = SmartInterleaverV2(consensus_boost_base=0.20)

# Recommended: 0.15
```

---

## 🧪 Expected Performance

### Benchmark 예상 결과

| Metric | v1 | v2 | Expected |
|--------|----|----|----------|
| **Symbol Nav Hit** | 85% | **95%** | +10%p |
| **Overall Precision** | 85% | **88%** | +3%p |
| **Avg Latency** | 200ms | 200ms | 동일 |
| **Calibration Issue** | 있음 | **없음** | ✅ |

---

## 🔄 Future: Learning-to-Rank

v2의 구조는 **LTR 전환에 최적화**되어 있습니다:

```python
# Features for LTR
features = {
    # Per-strategy features
    "vector_rank": 1,
    "vector_rrf": 0.00328,
    "lexical_rank": 0,
    "lexical_rrf": 0.00333,
    "symbol_rank": 0,
    "symbol_rrf": 0.00833,

    # Consensus features
    "num_strategies": 3,
    "max_rrf_component": 0.00833,

    # Intent features
    "intent_symbol_score": 0.6,
    "intent_concept_score": 0.4,
}

# Label
label = user_clicked  # 1 or 0

# Train LightGBM ranker
model = lgb.LGBMRanker()
model.fit(X_train, y_train)

# 이후 hand-tuned weights를 LTR이 자동 학습
```

---

## ✅ Recommendation

| 상황 | 권장 |
|------|------|
| **Production 신규** | v2 사용 (weighted_rrf) |
| **기존 Production** | v1→v2 canary 테스트 후 전환 |
| **A/B Test** | v1 vs v2 parallel 비교 |
| **LTR 준비 중** | v2 사용 (구조가 LTR-ready) |

---

## 📊 Summary

```
v1 (Score-based)
├── ❌ Score calibration 문제
├── ❌ BM25가 구조적으로 지배
├── ❌ Consensus boost 과함
└── ❌ Single intent만 지원

v2 (Weighted RRF)
├── ✅ Rank-based, 스케일 무관
├── ✅ 모든 전략 공정하게 처리
├── ✅ Quality-aware consensus (sqrt growth)
├── ✅ Multi-label intent 지원
└── ✅ LTR 전환 ready
```

**Status**: v2 구현 완료, 테스트 준비 완료
**Next**: A/B 테스트 → Canary → Full migration
