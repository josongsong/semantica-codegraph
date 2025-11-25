# Retriever 구조 분석 & 개선 계획

## 현재 구조 분석 (2025-11-25)

### 📦 기존 컴포넌트

#### 1. **Service Layer** (3 versions)
```
service.py              # Base service (Phase 1)
service_optimized.py    # P0+P1 optimizations
v3/service.py          # RFC v3 (SOTA, 방금 구현) ✅
```

#### 2. **Sub-modules** (17 directories)
```
adaptive/              # Adaptive top-k selection
adaptive_embeddings/   # LoRA-based embedding adaptation
code_reranking/        # AST + CallGraph reranking
context_builder/       # Token packing, ordering, trimming
experimentation/       # A/B testing, shadow mode
feedback/              # Hard negative mining, contrastive learning
fusion/                # Score fusion (v1, v2)
graph_runtime_expansion/ # Graph traversal
hybrid/                # Late interaction, cross-encoder
intent/                # Intent analysis (LLM + Rule)
multi_index/           # Multi-index orchestration
observability/         # Tracing, explainability
query/                 # Query decomposition, multi-hop, rewriting
reasoning/             # Test-time reasoning (o1-style)
scope/                 # Scope selection (RepoMap)
v3/                    # RFC v3 implementation ✅
```

---

## 🚨 구조적 문제점

### 1. **Version Fragmentation**
- **문제**: 3개의 service 버전이 독립적으로 존재
  - `service.py`: 기본 파이프라인
  - `service_optimized.py`: P0+P1 최적화
  - `v3/service.py`: RFC v3 구현
- **영향**: 어떤 버전을 사용해야 하는지 불명확, 유지보수 비용 증가

### 2. **Fusion 중복**
- **문제**: 3개의 fusion 구현
  - `fusion/engine.py`: Base fusion
  - `fusion/smart_interleaving_v2.py`: Weighted RRF
  - `v3/fusion_engine.py`: RFC v3 fusion (consensus-aware)
- **영향**: 중복 코드, 일관성 부족

### 3. **Intent Classification 중복**
- **문제**: 3개의 intent classifier
  - `intent/service.py`: LLM + Rule fallback
  - `intent/ml_classifier.py`: ML-based
  - `v3/intent_classifier.py`: Multi-label softmax
- **영향**: 어떤 classifier가 최신인지 불명확

### 4. **통합 부족**
- **문제**: v3가 기존 파이프라인과 통합되지 않음
  - Multi-index orchestrator와 연동 안 됨
  - Context builder와 연동 안 됨
  - Observability/tracing과 연동 안 됨
- **영향**: v3의 SOTA 기능을 실제 파이프라인에서 사용 불가

### 5. **테스트 커버리지 불균형**
- **완료**: v3 (39 tests, 100% pass)
- **불명확**: service.py, service_optimized.py의 통합 테스트 상태
- **문제**: 전체 파이프라인의 e2e 테스트 부족

### 6. **문서화 부족**
- **존재**: v3 가이드 (`_docs/retriever/RETRIEVER_V3_GUIDE.md`)
- **부족**:
  - 전체 아키텍처 문서
  - 버전 선택 가이드
  - Migration 가이드

---

## 🎯 개선 필요 사항

### Phase 1: 구조 정리 (High Priority)

#### 1.1 **Version Consolidation**
**목표**: 단일 진입점으로 통합

```python
# Proposed: src/retriever/service_v4.py
class RetrieverServiceV4:
    """
    Unified retriever service integrating best practices from all versions.

    Features:
    - Multi-label intent classification (from v3)
    - Weighted RRF + Consensus (from v3)
    - Late interaction + Reranking (from optimized)
    - Observability + Tracing (from Phase 3)
    - Context building with dependencies (from optimized)
    """

    def __init__(self, config: RetrieverConfig):
        # V3 components
        self.intent_classifier = IntentClassifierV3()
        self.fusion_engine = FusionEngineV3(config.fusion)

        # Existing components
        self.multi_index = MultiIndexOrchestrator(...)
        self.context_builder = ContextBuilder(...)

        # Optional advanced features
        if config.enable_reranking:
            self.reranker = CrossEncoderReranker(...)
        if config.enable_observability:
            self.tracer = RetrievalTracer(...)
```

**Action Items**:
- [ ] v3 fusion을 main pipeline에 통합
- [ ] v3 intent classifier를 default로 설정
- [ ] service_optimized의 best practices 통합
- [ ] 통일된 configuration 시스템

#### 1.2 **Fusion Layer Unification**
**목표**: 단일 fusion 인터페이스

```python
# Proposed: src/retriever/fusion/unified.py
class UnifiedFusionEngine:
    """
    Unified fusion engine with pluggable strategies.

    Strategies:
    - weighted_rrf: v3 weighted RRF (default)
    - correlation_aware: Phase 2 correlation-aware
    - ensemble: Combine multiple strategies
    """

    def __init__(self, strategy: str = "weighted_rrf"):
        if strategy == "weighted_rrf":
            self.engine = FusionEngineV3()  # Use v3 as default
        elif strategy == "correlation_aware":
            self.engine = CorrelationAwareFusion()
```

**Action Items**:
- [ ] v3/fusion_engine을 fusion/unified.py로 이동
- [ ] 기존 fusion/engine.py를 deprecated 처리
- [ ] Migration 가이드 작성

#### 1.3 **Intent Classification Unification**
**목표**: Multi-backend intent classifier

```python
# Proposed: src/retriever/intent/unified.py
class UnifiedIntentClassifier:
    """
    Unified intent classifier with multiple backends.

    Backends:
    - rule_based: Fast pattern matching (v3) [default]
    - ml_based: Trained model
    - llm_based: LLM API call
    """

    def __init__(self, backend: str = "rule_based"):
        if backend == "rule_based":
            self.classifier = IntentClassifierV3()  # Use v3 as default
        elif backend == "ml_based":
            self.classifier = MLIntentClassifier()
        elif backend == "llm_based":
            self.classifier = LLMIntentClassifier()
```

**Action Items**:
- [ ] v3/intent_classifier를 intent/classifiers/rule_based_v3.py로 이동
- [ ] Unified interface 구현
- [ ] Benchmark 각 backend 성능

---

### Phase 2: 통합 & 연동 (Medium Priority)

#### 2.1 **V3 ↔ Multi-Index Integration**
**문제**: v3가 SearchHit를 받지만, multi_index orchestrator와 직접 연동 안 됨

**Action Items**:
- [ ] MultiIndexOrchestrator에서 v3 service 호출하도록 수정
- [ ] SearchHit → RankedHit 변환 자동화
- [ ] Metadata 전달 파이프라인 구축

#### 2.2 **V3 ↔ Context Builder Integration**
**문제**: v3 fusion 결과를 context builder로 전달하는 로직 부재

**Action Items**:
- [ ] FusedResultV3 → ContextChunk 변환 adapter
- [ ] Dependency ordering과 consensus 결합
- [ ] Token packing에 consensus_factor 활용

#### 2.3 **Observability Integration**
**문제**: v3의 explainability와 기존 observability 모듈 연동 부재

**Action Items**:
- [ ] v3 explanation을 RetrievalTrace에 추가
- [ ] Feature vector logging
- [ ] Intent probability tracking

---

### Phase 3: 성능 최적화 (Low Priority)

#### 3.1 **Caching**
**현재**: service_optimized에 일부 캐싱 구현됨
**개선**:
- [ ] v3 service에 Redis 캐싱 완전 구현
- [ ] Query → Intent 캐싱
- [ ] RRF score 캐싱

#### 3.2 **Async Optimization**
**현재**: Multi-index search는 async
**개선**:
- [ ] v3 fusion도 async로 변환 (대용량 처리용)
- [ ] Parallel consensus calculation

#### 3.3 **Batch Processing**
**현재**: 단일 쿼리 처리만 지원
**개선**:
- [ ] Batch intent classification
- [ ] Batch fusion

---

## 📋 우선순위별 작업 목록

### 🔥 P0: Critical (이번 주)

1. **V3 Integration Test**
   - [ ] Multi-index orchestrator → v3 service e2e test
   - [ ] Context builder 연동 test
   - [ ] 실제 index adapter (Zoekt, Qdrant, Kuzu) 연동 test

2. **Documentation**
   - [ ] 전체 아키텍처 다이어그램
   - [ ] Version selection guide (v1 vs optimized vs v3)
   - [ ] Migration guide (기존 → v3)

3. **Configuration Unification**
   - [ ] 통일된 RetrieverConfig 클래스
   - [ ] v3 config를 main config에 통합
   - [ ] Feature flags (enable_v3_fusion, enable_v3_intent, etc.)

### ⚡ P1: High (다음 주)

1. **Fusion Layer Consolidation**
   - [ ] v3 fusion을 default로 설정
   - [ ] 기존 fusion 코드 deprecated 처리
   - [ ] Backward compatibility 테스트

2. **Intent Classifier Consolidation**
   - [ ] v3 intent classifier를 default로 설정
   - [ ] Multi-backend 인터페이스 구현
   - [ ] Benchmark 비교 (rule vs ML vs LLM)

3. **Service V4 구현**
   - [ ] Best practices 통합
   - [ ] Feature flag 기반 동적 구성
   - [ ] Production-ready 테스트

### 📌 P2: Medium (이번 달)

1. **Observability Integration**
   - [ ] v3 explanation → tracing
   - [ ] Feature vector logging
   - [ ] Performance metrics

2. **Context Builder Enhancement**
   - [ ] Consensus-aware ordering
   - [ ] Dependency + consensus 결합
   - [ ] Token budget optimization

3. **Caching Implementation**
   - [ ] Redis 캐싱 완전 구현
   - [ ] Cache invalidation 전략
   - [ ] Performance benchmark

### 🔮 P3: Low (필요시)

1. **Batch Processing**
2. **Async Optimization**
3. **Advanced Reranking Integration**
4. **Adaptive Top-K with V3**

---

## 🏗️ 제안: 새로운 구조

### Proposed Architecture

```
src/retriever/
├── service.py                    # [KEEP] Base service (legacy)
├── service_optimized.py          # [KEEP] Optimized service (legacy)
├── service_v4.py                 # [NEW] Unified service (v3 + best practices)
├── config.py                     # [NEW] Unified configuration
│
├── intent/
│   ├── unified.py                # [NEW] Multi-backend interface
│   ├── classifiers/
│   │   ├── rule_based_v3.py      # [MOVE from v3/]
│   │   ├── ml_based.py           # [KEEP]
│   │   └── llm_based.py          # [KEEP]
│
├── fusion/
│   ├── unified.py                # [NEW] Multi-strategy interface
│   ├── engines/
│   │   ├── weighted_rrf.py       # [MOVE from v3/fusion_engine.py]
│   │   ├── correlation_aware.py  # [KEEP]
│   │   └── ensemble.py           # [NEW]
│   ├── consensus.py              # [MOVE from v3/consensus_engine.py]
│   └── rrf_normalizer.py         # [MOVE from v3/rrf_normalizer.py]
│
├── multi_index/                  # [KEEP]
├── context_builder/              # [KEEP + ENHANCE]
├── observability/                # [KEEP + ENHANCE]
│
├── v3/                           # [DEPRECATED after migration]
│   ├── __init__.py               # [Redirect to new locations]
│   └── models.py                 # [KEEP, used by new modules]
│
└── [other modules...]            # [KEEP]
```

---

## 🎯 Success Metrics

### Phase 1 완료 기준
- [ ] v3가 main pipeline에 통합됨
- [ ] 통일된 configuration 시스템
- [ ] E2E integration test 통과
- [ ] Architecture documentation 완성

### Phase 2 완료 기준
- [ ] Single service interface (v4)
- [ ] Fusion/Intent 중복 제거
- [ ] Observability 완전 통합
- [ ] Migration guide 완성

### Phase 3 완료 기준
- [ ] Production deployment
- [ ] Performance benchmark (latency, accuracy)
- [ ] User feedback collection

---

## 💡 즉시 실행 가능한 Quick Wins

### 1. **V3 Exports 추가** (5분)
```python
# src/retriever/__init__.py
from .v3 import (
    RetrieverV3Service,
    RetrieverV3Config,
    IntentProbability,
    FusedResultV3,
)

__all__.extend([
    "RetrieverV3Service",
    "RetrieverV3Config",
    "IntentProbability",
    "FusedResultV3",
])
```

### 2. **Integration Example** (10분)
```python
# examples/retriever_integration_example.py
# V3 service와 기존 multi-index orchestrator 연동 예제
```

### 3. **Config Migration** (15분)
```python
# src/retriever/config.py
# RetrieverConfig에 v3_config 추가
```

---

## 📊 현재 상태 요약

| Component | Status | Test Coverage | Production Ready |
|-----------|--------|---------------|------------------|
| V3 Service | ✅ Complete | 39 tests, 100% | ⚠️ Needs integration |
| Base Service | ✅ Stable | ⚠️ Unknown | ✅ Yes |
| Optimized Service | ✅ Stable | ⚠️ Unknown | ✅ Yes |
| Multi-Index | ✅ Stable | ⚠️ Unknown | ✅ Yes |
| Context Builder | ✅ Stable | ⚠️ Unknown | ✅ Yes |
| Fusion (base) | ⚠️ Deprecated? | ⚠️ Unknown | ⚠️ Use v3 instead |
| Intent (base) | ⚠️ Deprecated? | ⚠️ Unknown | ⚠️ Use v3 instead |

---

## 🚀 Next Steps

### Immediate (Today)
1. V3를 retriever/__init__.py에 export 추가
2. Integration example 작성
3. E2E integration test 작성

### This Week
1. Service V4 설계 문서
2. Configuration consolidation
3. Architecture documentation

### Next Week
1. Service V4 구현
2. Migration guide
3. Deprecation plan

---

**Generated**: 2025-11-25
**Author**: Analysis based on current codebase structure
**Status**: 🔴 Action Required
