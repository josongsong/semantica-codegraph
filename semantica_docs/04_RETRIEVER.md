# Retriever 모듈

**SOTA 달성도**: 90% (Late Interaction 완전 구현, Adaptive Weight Learning 완료)

## 개요
의도 기반 하이브리드 검색, 다중 인덱스 융합, 컨텍스트 빌딩.
핵심 구현: [src/contexts/retrieval_search/infrastructure/](src/contexts/retrieval_search/infrastructure/)

## SOTA 비교 (2025-11-29)

| 기능 | Semantica v2 | SOTA (Cursor, DeepSeek) |
|------|--------------|-------------------------|
| Hybrid Search | ✅ 4종 (V/L/S/G) | ✅ Multi-Index |
| Intent Classification | ✅ 3종 Classifier | ✅ ML 기반 |
| Late Interaction | ✅ **완전 구현** (GPU, Cache) | ✅ ColBERT/SlimPLM |
| Fusion | ✅ RRF + Consensus | ✅ LTR |
| Adaptive Weight | ✅ EMA 학습 | ✅ Golden Set |
| Code Embedding | ✅ **CodeBERT/UniXcoder** | ✅ CodeBERT |
| Reranker | ✅ **Learned + Cross-Encoder** | ✅ LTR |

**강점**: 
- Late Interaction (ColBERT) 완전 구현 (GPU 가속, 3-tier 캐싱)
- Code-specific embedding (CodeBERT/UniXcoder) 적용 완료
- Learned Reranker (GradientBoosting, 19 features) + Cross-Encoder

**부족**: 
- Log 기반 Late Interaction 튜닝 (검색 로그 수집 인프라 필요)

## Golden Set Evaluation (NEW)

**구현**: `src/evaluation/`, `tests/evaluation/test_golden_set_regression.py`
**메트릭**: Precision@5 (> 0.6), Recall@10 (> 0.8), MRR
**CI**: `.github/workflows/retrieval-eval.yml` (PR + 주간)
**Justfile**: `just test-retrieval`

## LTR A/B Test (NEW)

**구현**: `src/contexts/retrieval_search/infrastructure/evaluation/ltr_ab_test.py`
**기능**: Baseline vs Candidate weight 비교 (평균 개선 > 2%)
**CI**: `.github/workflows/ltr-ab-test.yml` (주간, GitHub Issue 자동 생성)
**Scripts**: `scripts/run_ltr_ab_test.py`, `scripts/check_ab_test_winner.py`

## BGE Embedding & Reranker (NEW)

**BGE Embedding**: `src/contexts/retrieval_search/infrastructure/hybrid/bge_embedding_model.py`
- LocalLLM BGE-M3 활용, Redis 캐시 통합
- SimpleEmbeddingModel(난수) 대체

**BGE Reranker**: `src/contexts/retrieval_search/infrastructure/hybrid/bge_reranker.py`
- LocalLLM bge-reranker-large 활용

**Query Rewriter**: `src/contexts/retrieval_search/infrastructure/query/ml_rewriter.py`
- 룰 기반 (Intent 템플릿 + 도메인 용어 확장)
- 원본 + 변형 최대 3개 생성

## v2 고도화 완성도

| 항목 | 상태 | 완성도 | 비고 |
|------|------|--------|------|
| **4-1. Query Intent Detection** | ✅ 완료 | 100% | 3종 classifier, 5종 intent, weight preset |
| **4-2. Adaptive max_cost & Budget** | ✅ 완료 | 100% | Cost-aware Dijkstra, graceful degrade |
| **4-3. Fusion 전략 리팩토링** | ✅ 완료 | 100% | 모듈화, config 스키마, per-repo/user 튜닝 |
| **Multi-hop Retrieval** | ✅ 완료 | 100% | QueryDecomposer + MultiHopRetriever 통합 |
| **Reranking Pipeline** | ✅ 완료 | 100% | Cross-encoder 통합, factory 자동 생성 |
| **Scope Selection** | ✅ 완료 | 100% | RepoMap 기반, V3 wrapper 통합 |
| **Adaptive Weight Learning** | ✅ 완료 | 100% | Feedback 메서드, orchestrator 통합 |

**테스트 현황:** 11개 통과 (query_decomposition: 7개, v3_full_integration: 4개)

---

## 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                      RetrieverV3Orchestrator                     │
│                    [v3/orchestrator.py:26]                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Intent     │    │  Multi-Index │    │   Fusion     │       │
│  │  Classifier  │───▶│   Parallel   │───▶│   Engine     │       │
│  │              │    │   Search     │    │     V3       │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│        │                    │                    │               │
│        ▼                    ▼                    ▼               │
│  IntentProbability    SearchHit[]          FusedResultV3[]      │
│                                                  │               │
│                                                  ▼               │
│                                        ┌──────────────────┐     │
│                                        │  Cross-Encoder   │     │
│                                        │   Reranking      │     │
│                                        │  (조건부 P2)      │     │
│                                        └──────────────────┘     │
│                                                  │               │
│  ┌─────────────────────────────────────────────┘               │
│  │                                                               │
│  │  ┌──────────────────────────────────────────┐               │
│  └─▶│     Adaptive Weight Learner (P1)          │               │
│     │  - 사용자 피드백 수집                      │               │
│     │  - EMA 기반 가중치 학습                    │               │
│     └──────────────────────────────────────────┘               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       ContextBuilder                             │
│                  [context_builder/builder.py:101]                │
│                                                                  │
│   Deduplication → Token Packing → Trimming → ContextResult      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 검색 파이프라인

```
Query
  │
  ▼
┌─────────────────────────────────────┐
│ 1. Intent Classification            │
│    IntentClassifierV3               │
│    [v3/intent_classifier.py:13]     │
│    - 규칙 기반 softmax 분류         │
│    - 5종 의도 확률 분포 출력        │
└─────────────────────────────────────┘
  │
  ▼ IntentProbability
┌─────────────────────────────────────┐
│ 2. Async Parallel Search            │
│    RetrieverV3Orchestrator          │
│    [v3/orchestrator.py:178]         │
│    - asyncio.gather로 4개 전략 병렬 │
│    - ~3ms (vs 9ms sequential)       │
└─────────────────────────────────────┘
  │
  ▼ hits_by_strategy: dict[str, list[SearchHit]]
┌─────────────────────────────────────┐
│ 3. RRF Normalization                │
│    RRFNormalizer                    │
│    [v3/rrf_normalizer.py:13]        │
│    - 전략별 k값으로 점수 정규화     │
│    - 의도 가중치 적용               │
└─────────────────────────────────────┘
  │
  ▼ base_scores: dict[str, float]
┌─────────────────────────────────────┐
│ 4. Consensus Boosting               │
│    ConsensusEngine                  │
│    [v3/consensus_engine.py:13]      │
│    - 다중 전략 일치 시 부스팅       │
│    - consensus_factor = 1.0 ~ 1.5x  │
└─────────────────────────────────────┘
  │
  ▼ FusedResultV3[] (~40 results)
┌─────────────────────────────────────┐
│ 4.5 Cross-Encoder Reranking (P2)   │
│     RetrieverV3Orchestrator         │
│     [v3/orchestrator.py]            │
│     - 조건부 활성화 (복잡 쿼리)     │
│     - 40개 → 12-20개로 정제         │
│     - 의미적 관련성 재평가          │
└─────────────────────────────────────┘
  │
  ▼ FusedResultV3[] (~12-20 results)
┌─────────────────────────────────────┐
│ 5. Context Building                 │
│    ContextBuilder                   │
│    [context_builder/builder.py:134] │
│    - 토큰 패킹 (budget 기반)        │
│    - 필요시 트리밍                  │
└─────────────────────────────────────┘
  │
  ▼
ContextResult
```

---

## 의도 분류 (Intent Classification) - v2 고도화 완료 ✅

### 4-1. Query Intent Detection (100% 구현 완료)

**5종 의도 타입 정의:**

| 의도 | 설명 | 가중치 프로파일 | 사용 사례 |
|------|------|----------------|----------|
| `symbol` | 정의/참조 네비게이션 | sym(0.5), lex(0.2), vec(0.2), graph(0.1) | "find login function" |
| `flow` | 실행 흐름 추적 | graph(0.5), sym(0.2), vec(0.2), lex(0.1) | "trace call from A to B" |
| `concept` | 고수준 개념 이해 | vec(0.7), lex(0.2), sym(0.05), graph(0.05) | "how does auth work" |
| `code` | 특정 코드 검색 | vec(0.5), lex(0.3), sym(0.1), graph(0.1) | "error handling code" |
| `balanced` | 균형 검색 | vec(0.4), lex(0.3), sym(0.2), graph(0.1) | 기본값 |

**3종 Classifier 구현:**

```python
# 1. IntentClassifierV3 (규칙 기반 + Softmax)
위치: v3/intent_classifier.py:13
- 패턴 매칭 → raw scores → softmax 정규화
- IntentProbability 출력 (확률 분포)
- 속도: <1ms

# 2. RuleBasedClassifier (빠른 폴백)
위치: intent/rule_classifier.py
- 패턴 점수 → 최고점 선택
- QueryIntent 출력 (단일 intent)
- 속도: <1ms

# 3. MLIntentClassifier (경량 ML)
위치: intent/ml_classifier.py
- 특성 추출 → ML 모델 예측
- 사용자 피드백으로 학습 가능
- 속도: 10-50ms (vs LLM 500-1500ms)
```

### IntentClassifierV3 (메인)
위치: [v3/intent_classifier.py:13](src/contexts/retrieval_search/infrastructure/v3/intent_classifier.py#L13)

**패턴 매칭 규칙:** [v3/intent_classifier.py:21-67](src/contexts/retrieval_search/infrastructure/v3/intent_classifier.py#L21-L67)

```python
SYMBOL_PATTERNS = [
    (r"\b(class|function|method|def)\s+\w+", 0.4),
    (r"^[\w.]+$", 0.5),  # 단일 식별자
    (r"[A-Z][a-z]+(?:[A-Z][a-z]+)+", 0.3),  # CamelCase
    (r"\b(enum|interface|type|protocol|struct)\s+\w+", 0.4),
]

FLOW_PATTERNS = [
    (r"\bwho\s+calls?\b", 0.6),
    (r"\bcall\s+(chain|graph|path)\b", 0.5),
    (r"\bfrom\s+\w+\s+to\s+\w+", 0.5),
    (r"\bused\s+by\b", 0.4),
    (r"\bdepends?\s+on\b", 0.4),
]

CONCEPT_PATTERNS = [
    (r"\bhow\s+(does|do|is)\b", 0.5),
    (r"\bexplain\b", 0.6),
    (r"\barchitecture\b", 0.5),
]
```

**Softmax 정규화:** [v3/intent_classifier.py:166](src/contexts/retrieval_search/infrastructure/v3/intent_classifier.py#L166)

```python
def _softmax(self, scores: dict[str, float], temperature: float = 1.0):
    scaled = {k: v / temperature for k, v in scores.items()}
    exp_scores = {k: math.exp(v) for k, v in scaled.items()}
    total = sum(exp_scores.values())
    return {k: v / total for k, v in exp_scores.items()}
```

**쿼리 확장 추출:** [v3/intent_classifier.py:189](src/contexts/retrieval_search/infrastructure/v3/intent_classifier.py#L189)

```python
def classify_with_expansion(self, query: str):
    intent_prob = self.classify(query)
    expansions = {
        "symbols": self._extract_symbols(query),    # CamelCase, snake_case
        "file_paths": self._extract_file_paths(query),  # *.py, *.ts 등
        "modules": self._extract_modules(query),    # a.b.c 형태
    }
    return intent_prob, expansions
```

---

## RRF (Reciprocal Rank Fusion)

### RRFNormalizer
위치: [v3/rrf_normalizer.py:13](src/contexts/retrieval_search/infrastructure/v3/rrf_normalizer.py#L13)

**RRF 공식:**
```
RRF(d) = 1 / (k + rank)
```

**전략별 k값:** [v3/config.py:16](src/contexts/retrieval_search/infrastructure/v3/config.py#L16)

```python
@dataclass
class RRFConfig:
    k_vec: int = 70    # Vector: 더 넓은 분포
    k_lex: int = 70    # Lexical: 더 넓은 분포
    k_sym: int = 50    # Symbol: 정밀 검색 (상위 강조)
    k_graph: int = 50  # Graph: 정밀 검색
```

**가중치 적용:** [v3/rrf_normalizer.py:54](src/contexts/retrieval_search/infrastructure/v3/rrf_normalizer.py#L54)

```python
def calculate_weighted_scores(self, rrf_scores, weights):
    weighted_scores = {}
    for chunk_id, strategy_scores in rrf_scores.items():
        weighted_score = 0.0
        for strategy, rrf_score in strategy_scores.items():
            weight = weight_map.get(strategy, 0.0)
            weighted_score += weight * rrf_score
        weighted_scores[chunk_id] = weighted_score
    return weighted_scores
```

---

## Consensus Boosting

### ConsensusEngine
위치: [v3/consensus_engine.py:13](src/contexts/retrieval_search/infrastructure/v3/consensus_engine.py#L13)

**합의 점수 계산:** [v3/consensus_engine.py:29](src/contexts/retrieval_search/infrastructure/v3/consensus_engine.py#L29)

```python
def calculate_consensus_stats(self, chunk_id, hits_by_strategy):
    # 통계 계산
    num_strategies = len(ranks)
    best_rank = min(ranks.values())
    avg_rank = sum(ranks.values()) / len(ranks)

    # 품질 계수: 평균 순위 기반
    quality_factor = 1.0 / (1.0 + avg_rank / self.config.quality_q0)

    # 합의 계수: sqrt(전략 수) 기반 (RFC 7-3)
    consensus_raw = 1.0 + self.config.beta * (math.sqrt(num_strategies) - 1.0)
    consensus_capped = min(self.config.max_factor, consensus_raw)
    consensus_factor = consensus_capped * (0.5 + 0.5 * quality_factor)
```

**설정값:** [v3/config.py:26](src/contexts/retrieval_search/infrastructure/v3/config.py#L26)

```python
@dataclass
class ConsensusConfig:
    beta: float = 0.3       # 합의 부스트 계수
    max_factor: float = 1.5 # 최대 합의 승수
    quality_q0: float = 10.0 # 품질 정규화 계수
```

**합의 부스트 예시:**
| 전략 수 | 품질=1.0 시 factor |
|---------|-------------------|
| 1개 | 1.00x |
| 2개 | ~1.13x |
| 3개 | ~1.22x |
| 4개 | ~1.30x (cap 1.5x) |

---

## Fusion Engine V3 - v2 고도화 완료 ✅

### 4-3. Fusion 전략 리팩토링 (100% 구현 완료)

**모듈화된 아키텍처:**

```
FusionEngineV3 (v3/fusion_engine.py)
    ├── RRFNormalizer (v3/rrf_normalizer.py)
    │   └── Strategy별 RRF 정규화
    ├── ConsensusEngine (v3/consensus_engine.py)
    │   └── 다중 전략 합의 부스팅
    └── Intent-based Weighting
        └── 비선형 부스팅 적용
```

**Per-repo/Per-user 튜닝 가능한 Config:**

```python
# v3/config.py:116
@dataclass
class RetrieverV3Config:
    rrf: RRFConfig                    # 전략별 k값 (vec=70, lex=70, sym=50, graph=50)
    consensus: ConsensusConfig        # 합의 파라미터 (beta=0.3, max_factor=1.5)
    intent_weights: IntentWeights     # 의도별 가중치 프로파일
    cutoff: CutoffConfig              # Top-K cutoff
    cross_encoder: CrossEncoderConfig # Reranker 설정
    
    # Per-repo 커스터마이징 예시
    @staticmethod
    def for_large_repo():
        return RetrieverV3Config(
            rrf=RRFConfig(k_vec=100, k_lex=100),
            cutoff=CutoffConfig(concept=100, code=60)
        )
    
    # Per-user 커스터마이징 예시
    @staticmethod
    def for_detailed_user():
        return RetrieverV3Config(
            cutoff=CutoffConfig(symbol=30, flow=25),
            cross_encoder=CrossEncoderConfig(enabled=True, final_k=20)
        )
```

### FusionEngineV3
위치: [v3/fusion_engine.py:19](src/contexts/retrieval_search/infrastructure/v3/fusion_engine.py#L19)

**7단계 파이프라인 (모듈화됨):** [v3/fusion_engine.py:42](src/contexts/retrieval_search/infrastructure/v3/fusion_engine.py#L42)

```python
def fuse(self, hits_by_strategy, intent_prob, metadata_map, query_expansions):
    # Step 1: 의도 기반 가중치 계산 (비선형 부스팅 포함)
    weights = self._calculate_intent_weights(intent_prob)

    # Step 2: RRF 정규화 + 가중치 적용
    base_scores, rrf_scores = self.rrf_normalizer.normalize_and_weight(...)

    # Step 2.5: 쿼리 확장 부스팅 (10% 부스트)
    if query_expansions:
        base_scores = self._apply_expansion_boost(...)

    # Step 3: 합의 부스팅
    final_scores, consensus_stats = self.consensus_engine.apply_consensus_boost(...)

    # Step 4: Feature Vector 생성 (LTR용 18개 특성)
    feature_vectors = self._generate_feature_vectors(...)

    # Step 5: 최종 결과 빌드
    fused_results = self._build_fused_results(...)

    # Step 6: 점수 기준 정렬
    fused_results.sort(key=lambda r: r.final_score, reverse=True)

    # Step 7: Explainability 추가
    if self.config.enable_explainability:
        self._add_explanations(...)
```

**비선형 의도 부스팅:** [v3/fusion_engine.py:157](src/contexts/retrieval_search/infrastructure/v3/fusion_engine.py#L157)

```python
# flow 의도 > 0.2일 때 graph 가중치 1.3x 부스트
if dominant == "flow" and intent_prob.flow > 0.2:
    combined["graph"] *= 1.3

# symbol 의도 > 0.3일 때 sym 가중치 1.2x 부스트
elif dominant == "symbol" and intent_prob.symbol > 0.3:
    combined["sym"] *= 1.2
```

**쿼리 확장 부스팅:** [v3/fusion_engine.py:190](src/contexts/retrieval_search/infrastructure/v3/fusion_engine.py#L190)

```python
def _apply_expansion_boost(self, base_scores, hits_by_strategy, query_expansions):
    expansion_boost_factor = 1.1  # 10% 부스트

    for chunk_id, score in base_scores.items():
        # 심볼 매칭 체크
        if "symbols" in query_expansions:
            for expanded_symbol in query_expansions["symbols"]:
                if expanded_symbol.lower() in symbol_id.lower():
                    has_match = True

        # 파일 경로 매칭 체크
        if "file_paths" in query_expansions:
            for expanded_path in query_expansions["file_paths"]:
                if expanded_path.lower() in file_path.lower():
                    has_match = True

        if has_match:
            base_scores[chunk_id] = score * expansion_boost_factor
```

---

## Feature Vector (LTR용)

### FeatureVector
위치: [v3/models.py:109](src/contexts/retrieval_search/infrastructure/v3/models.py#L109)

**18개 특성 벡터:** [v3/models.py:172](src/contexts/retrieval_search/infrastructure/v3/models.py#L172)

```python
def to_array(self) -> list[float]:
    return [
        # Ranks (4개) - 각 전략에서의 순위
        float(self.rank_vec or 999999),
        float(self.rank_lex or 999999),
        float(self.rank_sym or 999999),
        float(self.rank_graph or 999999),

        # RRF Scores (4개) - 정규화된 RRF 점수
        self.rrf_vec, self.rrf_lex, self.rrf_sym, self.rrf_graph,

        # Weights (4개) - 의도 기반 가중치
        self.weight_vec, self.weight_lex, self.weight_sym, self.weight_graph,

        # Consensus (4개) - 합의 메트릭
        float(self.num_strategies),  # 전략 수
        float(self.best_rank),       # 최고 순위
        float(self.avg_rank),        # 평균 순위
        self.consensus_factor,       # 합의 계수

        # Metadata (2개) - 청크 메타데이터
        float(self.chunk_size),      # 청크 크기
        float(self.file_depth),      # 파일 경로 깊이
    ]
```

---

## Context Builder

### ContextBuilder
위치: [context_builder/builder.py:101](src/contexts/retrieval_search/infrastructure/context_builder/builder.py#L101)

**빌드 프로세스:** [context_builder/builder.py:134](src/contexts/retrieval_search/infrastructure/context_builder/builder.py#L134)

```python
async def build(self, fused_hits, token_budget=4000):
    # Step 1: 중복 제거
    if self.deduplicator:
        deduplicated = self.deduplicator.deduplicate(fused_hits)

    # Step 2: 배치 청크 페칭 (N+1 방지)
    chunk_ids = [hit.chunk_id for hit in deduplicated]
    chunks_dict = await self.chunk_store.get_chunks_batch(chunk_ids)

    # Step 3: 토큰 패킹
    for rank, hit in enumerate(deduplicated, start=1):
        content = chunks_dict.get(hit.chunk_id).get("content", "")
        original_tokens = self.token_counter.count_tokens(content)

        # 트리밍 필요시
        if self.trimmer and original_tokens > self.trimmer.max_trimmed_tokens:
            content, final_tokens, trim_reason = self.trimmer.trim(...)

        # 예산 초과 시 드롭
        if total_tokens + final_tokens > token_budget:
            continue

        context_chunks.append(ContextChunk(...))
        total_tokens += final_tokens

        # 95% 임계값에서 중단
        if total_tokens >= token_budget * 0.95:
            break
```

**토큰 카운터:** [context_builder/builder.py:58](src/contexts/retrieval_search/infrastructure/context_builder/builder.py#L58)

```python
class SimpleTokenCounter:
    def __init__(self, model="gpt-4"):
        # tiktoken 우선 사용
        self.encoding = tiktoken.encoding_for_model(model)

    def count_tokens(self, text: str) -> int:
        if self.encoding:
            return len(self.encoding.encode(text))
        # 폴백: ~0.75 tokens/word
        return max(1, int(len(text.split()) * 0.75))
```

---

## 3-Tier 캐싱

### RetrieverV3Cache
위치: [v3/cache.py](src/contexts/retrieval_search/infrastructure/v3/cache.py)

**캐시 전략:** [v3/service.py:93](src/contexts/retrieval_search/infrastructure/v3/service.py#L93)

```
Tier 1 (L1 query cache):  repo + query + hits → results (maxsize=1000)
Tier 2 (L1 intent cache): repo + query → intent (maxsize=500)
Tier 3 (L1 rrf cache):    repo + hits → rrf_scores (maxsize=250)
Tier 4 (L2 Redis):        분산 캐시 (선택적)
```

**설정값:** [v3/config.py:139](src/contexts/retrieval_search/infrastructure/v3/config.py#L139)

```python
cache_ttl: int = 300        # 5분
l1_cache_size: int = 1000   # 쿼리 결과 캐시
intent_cache_size: int = 500 # 의도 분류 캐시
```

---

## Async 병렬 검색

### RetrieverV3Orchestrator
위치: [v3/orchestrator.py:26](src/contexts/retrieval_search/infrastructure/v3/orchestrator.py#L26)

**성능 최적화:** [v3/orchestrator.py:178](src/contexts/retrieval_search/infrastructure/v3/orchestrator.py#L178)

```python
async def _search_parallel(self, repo_id, snapshot_id, query, limit, symbol_limit):
    tasks = []
    strategy_names = []

    if self.symbol_index:
        tasks.append(self._search_symbol(repo_id, snapshot_id, query, symbol_limit))
        strategy_names.append("symbol")
    if self.vector_index:
        tasks.append(self._search_vector(repo_id, snapshot_id, query, limit))
        strategy_names.append("vector")
    if self.lexical_index:
        tasks.append(self._search_lexical(repo_id, snapshot_id, query, limit))
        strategy_names.append("lexical")
    if self.graph_index:
        tasks.append(self._search_graph(repo_id, snapshot_id, query, limit))
        strategy_names.append("graph")

    # asyncio.gather로 병렬 실행
    # return_exceptions=True: 단일 전략 실패 시에도 전체 검색 계속
    results = await asyncio.gather(*tasks, return_exceptions=True)
```

**성능 비교:**
| 모드 | 시간 | 설명 |
|------|------|------|
| Sequential | ~9ms | symbol 2ms + vector 3ms + lexical 2ms + graph 2ms |
| Parallel | ~3ms | max(all strategies) |
| **절감** | **67%** | ~6ms 감소 |

---

## 고급 기능

### Query Decomposition
위치: [query/decomposer.py:133](src/contexts/retrieval_search/infrastructure/query/decomposer.py#L133)

복잡한 쿼리를 단계별 서브쿼리로 분해:

```python
class QueryDecomposer:
    async def decompose(self, query: str) -> DecomposedQuery:
        prompt = DECOMPOSITION_PROMPT.format(query=query)
        response = await self.llm_client.generate(prompt, max_tokens=800)
        return self._parse_response(response_json, query)
```

**쿼리 타입:**
| 타입 | 설명 | 예시 |
|------|------|------|
| `single_hop` | 단일 검색 | "find authenticate function" |
| `multi_hop` | 순차 검색 | "auth → DB calls → error handling" |
| `comparative` | 비교 검색 | "REST vs GraphQL auth" |
| `causal` | 인과 검색 | "why does X cause Y" |

### Multi-Hop Retrieval
위치: [query/multi_hop.py:18](src/contexts/retrieval_search/infrastructure/query/multi_hop.py#L18)

**아키텍처:**

```
Query
  ↓
QueryDecomposer (LLM 기반 분해)
  ↓
DecomposedQuery {type, steps[], reasoning}
  ↓
┌─ single_hop → base_retriever.retrieve()
│
└─ multi_hop → MultiHopRetriever.retrieve_multi_hop()
     ↓
   Step 1: retrieve() → StepResult
     ↓
   Step 2: retrieve(context from Step 1) → StepResult
     ↓
   Step 3: retrieve(context from Step 1,2) → StepResult
     ↓
   MultiHopResult (final_chunks, reasoning_chain)
```

**구현:**

```python
class MultiHopRetriever:
    def __init__(self, retriever_service: RetrieverService):
        self.retriever_service = retriever_service

    async def retrieve_multi_hop(self, repo_id, snapshot_id, decomposed):
        execution_order = decomposed.get_execution_order()

        for step in execution_order:
            # 이전 단계 컨텍스트 빌드
            prior_context = self._build_prior_context(step, context_accumulator)

            # 쿼리 강화: "search X (related to: Y, in files: Z)"
            enhanced_query = self._enhance_query_with_context(step.query, prior_context)

            # 단계별 검색 실행
            result = await self.retriever_service.retrieve(...)

            # 핵심 정보 추출
            chunks = self._extract_chunks(result)  # UnifiedRetrievalResult/RetrievalResult 호환
            
            # 컨텍스트 누적
            context_accumulator[step.step_id] = {
                "chunks": chunks,
                "symbols": self._extract_key_symbols(result, chunks),
                "summary": self._summarize_step_results(result, chunks),
            }
            
        # 최종 결과 통합
        return self._build_final_result(decomposed, step_results)
```

**Factory 통합:**

```python
# factory.py - _create_multi_hop()
def _create_multi_hop(self, config: RetrieverConfig):
    # 1. 기본 retriever 생성
    base_retriever = self._create_basic(config)
    
    # 2. QueryDecomposer 생성
    decomposer = QueryDecomposer(llm_client=self.container.llm_port)
    
    # 3. MultiHopRetriever 생성
    multi_hop_retriever = MultiHopRetriever(retriever_service=base_retriever)
    
    # 4. Wrapper로 통합
    return _MultiHopRetrieverWrapper(
        multi_hop_retriever=multi_hop_retriever,
        decomposer=decomposer,
        config=config,
    )

# Wrapper - 자동 분해 및 실행
async def retrieve(self, repo_id, snapshot_id, query):
    # 1. 쿼리 분해
    decomposed = await self._decomposer.decompose(query)
    
    # 2. Multi-hop 여부 확인
    if decomposed.is_multi_hop() and len(decomposed.steps) > 1:
        # Multi-hop 실행
        result = await self._multi_hop_retriever.retrieve_multi_hop(...)
    else:
        # Single-hop fallback
        result = await base_retriever.retrieve(...)
    
    return self._to_unified(result, query)
```

**테스트:** 7개 통과 (tests/retriever/test_query_decomposition.py)

### Graph Flow Expansion

#### 레거시: 단순 BFS
위치: [graph_runtime_expansion/flow_expander.py:49](src/contexts/retrieval_search/infrastructure/graph_runtime_expansion/flow_expander.py#L49)

```python
class GraphExpansionClient:
    async def expand_flow(self, start_symbol_ids, direction="forward"):
        # 단순 BFS - 모든 edge 동등 취급
        while queue and len(expansion_nodes) < self.config.max_nodes:
            current = queue.popleft()  # FIFO
            ...
```

#### **NEW: Cost-Aware Graph Expander (Dijkstra 기반)**
위치: [graph/cost_aware_expander.py](src/contexts/retrieval_search/infrastructure/graph/cost_aware_expander.py)

**핵심 개선점:**
1. **Edge Cost Model**: 엣지 유형별 차등 비용
2. **Dijkstra 알고리즘**: 비용 기반 우선순위 탐색
3. **Intent-aware 비용 조정**: 쿼리 의도에 따른 동적 비용

```python
class CostAwareGraphExpander:
    """Dijkstra 기반 cost-aware 그래프 확장"""

    async def expand_flow(
        self,
        start_symbol_ids: list[str],
        direction: str = "forward",
        scope: ScopeResult | None = None,
        intent: str = "balanced",  # 의도 기반 비용 조정
    ) -> list[SearchHit]:
        # Priority Queue로 최소 비용 경로 우선
        pq: list[ExpansionPath] = []
        heapq.heappush(pq, ExpansionPath(symbol_id=seed, total_cost=0.0, depth=0))

        while pq and len(results) < self.config.max_nodes:
            current = heapq.heappop(pq)  # 최소 비용 경로

            # 비용 임계값 기반 종료 (depth 대신)
            if current.total_cost > self.config.max_total_cost:
                break

            for neighbor in await self._get_neighbors(current.symbol_id, direction):
                # Edge 비용 계산 (유형 + 컨텍스트)
                edge_cost = self.cost_calculator.calculate_cost(
                    edge_kind=neighbor.get("edge_kind"),
                    target_attrs=neighbor,
                )
                new_total_cost = current.total_cost + edge_cost
                heapq.heappush(pq, ExpansionPath(..., total_cost=new_total_cost))
```

**Edge Cost 모델:** [graph/edge_cost.py](src/contexts/retrieval_search/infrastructure/graph/edge_cost.py)

```python
# 엣지 유형별 기본 비용 (낮을수록 우선)
DEFAULT_EDGE_COSTS = {
    "CALLS": 1.0,           # 직접 호출 - 최우선
    "ROUTE_HANDLER": 1.0,   # API 라우트
    "CONTAINS": 0.5,        # 구조적 포함 - 매우 저렴
    "INHERITS": 1.5,        # 상속
    "IMPORTS": 2.0,         # 임포트
    "REFERENCES_TYPE": 2.5, # 타입 참조
    "READS": 3.0,           # 데이터 읽기
    "WRITES": 3.0,          # 데이터 쓰기
    "CFG_NEXT": 4.0,        # 제어 흐름
}

# 컨텍스트 승수
class EdgeCostCalculator:
    config = EdgeCostConfig(
        test_path_multiplier=5.0,     # 테스트 코드 5x 페널티
        mock_path_multiplier=8.0,     # Mock 코드 8x 페널티
        cross_module_multiplier=1.5,  # 모듈 경계 1.5x
        external_module_multiplier=3.0,  # 외부 의존성 3x
    )
```

**Intent별 비용 조정:**

```python
def get_intent_adjusted_costs(self, intent: str) -> dict[str, float]:
    base = self.config.base_costs.copy()

    if intent == "flow":
        # Call edges 부스트 (0.7x)
        base["CALLS"] *= 0.7
        base["ROUTE_HANDLER"] *= 0.7
        # Data flow 감소 (1.5x)
        base["READS"] *= 1.5
        base["WRITES"] *= 1.5

    elif intent == "symbol":
        # 구조적 엣지 부스트
        base["CONTAINS"] *= 0.5
        base["INHERITS"] *= 0.7
```

**양방향 탐색:** [graph/cost_aware_expander.py:180](src/contexts/retrieval_search/infrastructure/graph/cost_aware_expander.py#L180)

```python
async def expand_bidirectional(
    self,
    symbol_id: str,
    intent: str = "flow",
    forward_weight: float = 0.6,  # forward:backward = 6:4
) -> list[SearchHit]:
    forward_hits = await self.expand_flow([symbol_id], direction="forward", intent=intent)
    backward_hits = await self.expand_flow([symbol_id], direction="backward", intent=intent)
    # 가중 합성으로 허브 노드 발견
```

**v2 고도화: 4-2. Adaptive max_cost & Budget (100% 구현 완료) ✅**

**쿼리별 탐색 정책:**

```python
# cost_aware_expander.py:30
@dataclass
class CostAwareExpansionConfig:
    max_total_cost: float = 30.0  # Budget 기반 종료
    max_nodes: int = 40            # 노드 수 제한
    max_depth: int = 5             # 깊이 안전 제한
    test_path_multiplier: 5.0      # 테스트 경로 페널티
    mock_path_multiplier: 8.0      # Mock 경로 페널티
```

**Intent별 Cost 조정:**

```python
# edge_cost.py:213
def get_intent_adjusted_costs(self, intent: str):
    if intent == "flow":
        costs["CALLS"] *= 0.7       # Call edge 부스트 (빠른 탐색)
        costs["READS"] *= 1.5        # Data flow 감소
    elif intent == "symbol":
        costs["CONTAINS"] *= 0.5     # 구조 edge 부스트
        costs["INHERITS"] *= 0.7
```

**Graceful Degradation:**

```python
# cost_aware_expander.py:146-173
while pq and len(results) < max_nodes:
    current = heapq.heappop(pq)
    
    # Budget 초과 시 graceful stop
    if current.total_cost > max_total_cost:
        logger.debug("Budget exceeded, stopping expansion")
        break  # ✅ Timeout 대신 정상 종료
    
    # 깊이 제한
    if current.depth >= max_depth:
        continue  # ✅ Skip, not fail
```

**현재 vs 레거시 비교:**

| 항목 | 레거시 BFS | Cost-Aware Dijkstra (v2 구현) |
|------|-----------|------------------------------|
| 알고리즘 | BFS (FIFO) | Dijkstra (Priority Queue) ✅ |
| 종료 조건 | depth=3 | cost 기반 (max_cost=30) ✅ |
| Edge 취급 | 모두 동등 | 유형별 차등 비용 ✅ |
| 점수 계산 | 깊이 감소 | exp(-cost) ✅ |
| 컨텍스트 | mock만 필터 | test/mock/cross-module 페널티 ✅ |
| Intent 적응 | 없음 | 의도별 비용 조정 ✅ |
| Budget | 없음 | max_cost budget ✅ |

---

## Graph Traversal SOTA 설계 (Reference)

### 핵심 개념: Query-Conditioned Personalized Graph Score

```
S_total(n|Q) = α·S_prior(n) + β·S_proximity(n|Q) + γ·S_semantic(n|Q)
                   ↑                ↑                    ↑
              PageRank        Weighted Dijkstra      Embedding
              (오프라인)      (쿼리 조건부)          (선택적)
```

SOTA 그래프 탐색의 3대 요소:
1. **정적 prior**: PageRank/centrality - "이 노드는 원래 중요"
2. **Edge-aware**: edge_type별 가중치 - "call ≠ import ≠ test"
3. **Query-conditioned**: seed 기준 proximity - "이 쿼리에서 가까운 노드"

### Edge Cost 설계

```python
# 관계 유형별 cost (낮을수록 가까움)
EDGE_COST = {
    "CALLS":     1.0,   # call은 가장 가까움
    "OVERRIDES": 1.1,   # override ≈ call
    "INHERITS":  1.25,
    "REFERENCES": 1.4,
    "CONTAINS":  1.7,   # file → symbol
    "IMPORTS":   2.0,   # import는 멀게
    "TESTS":     2.5,   # test는 더 멀게
}
```

**핵심**: Edge cost 튜닝이 그래프 검색 품질의 핵심. Golden set으로 실험 필수.

### Weighted Best-First (Dijkstra 변형)

```python
import heapq
import math

def weighted_bfs(seeds: list[str], max_nodes=300, max_cost=5.0):
    """Multi-source Dijkstra 기반 query-conditioned 탐색"""
    pq = []  # (total_cost, node_id)
    best_cost = {}  # node_id → best cost so far

    # seed 초기화
    for node_id in seeds:
        heapq.heappush(pq, (0.0, node_id))
        best_cost[node_id] = 0.0

    visited = set()
    results = {}

    while pq and len(results) < max_nodes:
        cost, node = heapq.heappop(pq)

        # 비용 기반 종료 (depth 대신)
        if cost > max_cost:
            break

        if node in visited:
            continue
        visited.add(node)
        results[node] = cost

        for edge in get_neighbors(node):
            edge_cost = EDGE_COST.get(edge.type, 2.0)
            new_cost = cost + edge_cost

            if new_cost < best_cost.get(edge.to, float("inf")):
                best_cost[edge.to] = new_cost
                heapq.heappush(pq, (new_cost, edge.to))

    return results  # node → shortest_cost
```

### Proximity Score 계산

```python
def calculate_proximity_score(best_cost: dict[str, float]) -> dict[str, float]:
    """cost → [0,1] proximity score 변환"""
    return {node: math.exp(-cost) for node, cost in best_cost.items()}
```

### Prior와 합성

```python
def calculate_total_score(
    proximity: dict[str, float],
    pagerank: dict[str, float],
    alpha=0.3, beta=0.7
) -> dict[str, float]:
    """
    S_total = α·S_prior + β·S_proximity

    - alpha=0.3: PageRank prior (원래 중요한 노드)
    - beta=0.7: Query proximity (쿼리에서 가까운 노드)
    """
    total = {}
    for node in proximity:
        s_prior = pagerank.get(node, 0.0)
        s_prox = proximity[node]
        total[node] = alpha * s_prior + beta * s_prox
    return total
```

### Adaptive max_cost (의도별)

```python
INTENT_GRAPH_CONFIG = {
    "flow": {
        "max_cost": 6.0,    # 깊게 탐색
        "max_nodes": 400,
        "bidirectional": True,  # 허브 탐색
    },
    "symbol": {
        "max_cost": 3.0,    # 얕게 탐색
        "max_nodes": 150,
        "bidirectional": False,
    },
    "debug": {
        "max_cost": 7.0,    # error propagation까지
        "max_nodes": 500,
        "bidirectional": True,
    },
    "concept": {
        "max_cost": 2.5,    # 모듈 단위만
        "max_nodes": 100,
        "bidirectional": False,
    },
}
```

### Bidirectional 탐색 (flow 의도)

```python
async def bidirectional_search(seeds, config):
    """양방향 탐색으로 중간 허브 발견"""
    # Forward: callees
    forward_costs = weighted_bfs(seeds, direction="forward", **config)

    # Backward: callers
    backward_costs = weighted_bfs(seeds, direction="backward", **config)

    # 합성: 양쪽 모두 cost 낮은 노드 = 허브
    all_nodes = set(forward_costs) | set(backward_costs)
    hub_scores = {}
    for node in all_nodes:
        cf = forward_costs.get(node, config["max_cost"])
        cb = backward_costs.get(node, config["max_cost"])
        hub_scores[node] = math.exp(-(cf + cb))  # 양방향 proximity

    return hub_scores
```

### Memgraph 영역 자르기

```cypher
-- 대략적인 neighborhood 추출 (2000개 후보)
MATCH (s:GraphNode)-[:CALLS|REFERENCES|INHERITS*1..4]->(n:GraphNode)
WHERE s.id IN $seed_ids
  AND s.repo_id = $repo_id
  AND s.snapshot_id = $snapshot_id
RETURN DISTINCT n.id
LIMIT 2000
```

→ Memgraph는 "대략 어디 근처"만 추출, 세밀한 scoring은 Python에서 처리

### Golden Set 기반 튜닝

**세 종류 golden set:**

| 쿼리 유형 | 주요 edge | 튜닝 목표 |
|----------|----------|----------|
| "핵심 흐름 보여줘" | CALLS, OVERRIDES, INHERITS | call chain 정확도 |
| "타입 관련 코드" | INHERITS, CONTAINS, REFERENCES | 타입 hierarchy |
| "버그 원인 찾기" | CALLS + error propagation | root cause 도달률 |

**메트릭**: `Recall@K = (정답 노드 ∩ Top-K) / 정답 노드`

**튜닝 파라미터**:
- `EDGE_COST[type]` 각 값
- `max_cost`, `max_nodes` 조합
- `alpha`, `beta` 합성 비율

### 구현 로드맵

| Phase | 내용 | 목표 |
|-------|------|------|
| **v1** | 단방향 Weighted BFS + Adaptive max_cost | 기본 edge-aware 탐색 |
| **v2** | Bidirectional 추가 (flow 의도) | 허브 노드 발견 |
| **v3** | Golden set 기반 자동 튜닝 | Edge cost 최적화 |

### 현재 vs SOTA 비교

| 항목 | 현재 | SOTA |
|------|------|------|
| 탐색 알고리즘 | BFS (FIFO) | Weighted Dijkstra |
| 종료 조건 | depth=3 | cost 기반 (max_cost) |
| Edge 취급 | 모두 동등 | type별 cost 차등 |
| 점수 계산 | 깊이 감소 | exp(-cost) + PageRank |
| 방향 | 단방향 | 의도별 양방향 옵션 |
| 튜닝 | 하드코딩 | Golden set 기반 |

---

## Adaptive Weight Learning (v2 통합 완료)

### AdaptiveWeightLearner
위치: [adaptive/weight_learner.py](src/contexts/retrieval_search/infrastructure/adaptive/weight_learner.py)

**통합 상태:** ✅ V3 Orchestrator에 통합, 피드백 메서드 제공

**기존 한계:**
- Intent 기반 가중치가 정적 (수동 튜닝 필요)
- 사용자 피드백 반영 불가
- 도메인별 최적화 불가

**피드백 기반 온라인 학습 (구현 완료)**

```python
class AdaptiveWeightLearner:
    """
    사용자 피드백으로 fusion 가중치를 학습.

    - EMA(Exponential Moving Average)로 점진적 업데이트
    - Intent별 독립 학습
    - Confidence 기반 정적/학습 가중치 혼합
    """

    def record_feedback(self, feedback: FeedbackSignal) -> None:
        """피드백 기록 및 가중치 업데이트"""
        # 1. 전략별 성공률 계산
        for strategy, chunk_ids in feedback.strategy_contributions.items():
            hits = len(selected_set.intersection(chunk_ids))
            success_rate = hits / len(chunk_ids)

            # 2. EMA 업데이트 (learning_rate=0.1)
            current = self._strategy_success_rate[intent][strategy]
            updated = current * 0.9 + success_rate * 0.1
            self._strategy_success_rate[intent][strategy] = updated

        # 3. 가중치 재계산
        self._recompute_weights(intent)
```

**피드백 시그널:**

```python
@dataclass
class FeedbackSignal:
    query: str
    intent: str
    selected_chunk_ids: list[str]  # 사용자가 선택한 청크
    strategy_contributions: dict[str, list[str]]  # 전략별 기여 청크
    is_positive: bool = True  # 긍정/부정 피드백
```

**Confidence 기반 가중치 혼합:**

```python
def get_adaptive_weights(
    self,
    intent_prob: IntentProbability,
    base_weights: dict[str, WeightProfile],
) -> WeightProfile:
    """정적 가중치와 학습 가중치를 confidence 기반 혼합"""

    for intent_name, probability in intent_dict.items():
        learned = self._learned_weights.get(intent_name)
        base = base_weights.get(intent_name)

        # Confidence 기반 보간 (0~1)
        # confidence = min(1.0, sample_count / 50)
        if learned and learned.confidence > 0:
            alpha = learned.confidence
            effective = {
                "vec": alpha * learned.vec + (1 - alpha) * base.vec,
                ...
            }
        else:
            effective = base  # 학습 데이터 없으면 정적 사용

        # Intent 확률로 가중 합
        combined["vec"] += probability * effective["vec"]
```

**학습 상태 통계:**

```python
learner.get_stats()
# {
#   "feedback_counts": {"symbol": 42, "flow": 28, ...},
#   "success_rates": {"symbol": {"vector": 0.65, "lexical": 0.72, ...}},
#   "learned_weights": {
#     "symbol": {"weights": {...}, "confidence": 0.84, "sample_count": 42}
#   }
# }
```

**피드백 수집 구현:**

위치: [server/api_server/routes/feedback.py](server/api_server/routes/feedback.py)

```python
# API 엔드포인트
POST /api/v1/feedback/weight-learning
{
  "query": "Find User authentication logic",
  "intent": "symbol",
  "selected_chunk_ids": ["chunk_123", "chunk_456"],
  "hits_by_strategy": {
    "vector": ["chunk_123", "chunk_789"],
    "lexical": ["chunk_456"],
    "symbol": ["chunk_123", "chunk_456"],
    "graph": []
  },
  "is_positive": true
}

# 즉시 가중치 업데이트 및 통계 반환
{
  "success": true,
  "intent": "symbol",
  "learned_weights": {
    "vec": 0.25, "lex": 0.20, "sym": 0.40, "graph": 0.15,
    "confidence": 0.84,
    "sample_count": 42
  }
}
```

**배치 프로세서:**

위치: [adaptive/feedback_processor.py](src/contexts/retrieval_search/infrastructure/adaptive/feedback_processor.py)

```python
# DB에 저장된 피드백을 주기적으로 읽어서 학습
processor = FeedbackProcessor(feedback_service, weight_learner)
stats = await processor.process_batch(mark_processed=True)

# 독립 실행 가능
python -m src.retriever.adaptive.feedback_processor
```

**통합 흐름:**

```
1. 검색 실행 → hits_by_strategy 메타데이터 포함
2. 사용자 클릭/선택 → selected_chunk_ids 기록  
3. 피드백 전송 → WeightLearner 즉시 업데이트
4. 다음 검색 → 학습된 가중치 자동 적용
```

**설정:**

```python
@dataclass
class WeightLearnerConfig:
    learning_rate: float = 0.1      # EMA 학습률
    min_weight: float = 0.05        # 최소 가중치 (0이 되지 않도록)
    max_weight: float = 0.8         # 최대 가중치
    feedback_decay: float = 0.95    # 오래된 피드백 감쇠
    weights_path: Path | None       # 학습 가중치 저장 경로 (선택)
    max_feedback_history: int = 100 # Intent별 피드백 히스토리
    weights_path: Path | None       # 가중치 영속화 경로
```

---

## Cross-Encoder Reranking (P2)

### 개요

**목적:** Fusion 후 상위 결과의 의미적 관련성을 재평가하여 정밀도 향상

**위치:** [v3/orchestrator.py](src/contexts/retrieval_search/infrastructure/v3/orchestrator.py)

**적용 시점:**
- Consensus Boosting 직후 (~40개 결과)
- Context Building 직전 (~12-20개로 정제)

### 조건부 활성화 로직

```python
def _should_use_cross_encoder(
    self,
    query: str,
    intent_prob: IntentProbability,
) -> bool:
    """
    Cross-encoder 적용 여부 결정.
    
    활성화 조건:
    1. Cross-encoder 활성화 설정
    2. 쿼리 길이 > min_query_length
    3. 특정 Intent (flow, concept)
    4. 복잡 쿼리 패턴 (why/how/explain/debug/refactor/trace)
    """
    config = self.v3_service.config.cross_encoder
    
    # 기본 조건
    if not config.enabled or not self.cross_encoder:
        return False
    
    if len(query) < config.min_query_length:
        return False
    
    # Intent 기반 트리거
    dominant_intent = intent_prob.dominant_intent()
    if dominant_intent in config.intent_triggers:  # ["flow", "concept"]
        return True
    
    # 복잡 쿼리 패턴 검출
    complex_keywords = ["why", "how", "explain", "debug", "refactor", "trace"]
    if any(keyword in query.lower() for keyword in complex_keywords):
        return True
    
    return False
```

### Reranking 프로세스

```python
async def _apply_cross_encoder_reranking(
    self,
    query: str,
    fused_results: list[FusedResultV3],
    intent_prob: IntentProbability,
) -> list[FusedResultV3]:
    """
    Cross-encoder로 상위 결과 재평가.
    
    과정:
    1. FusedResultV3[] → candidates (dict)
    2. Cross-encoder.rerank(query, candidates, top_k)
    3. 재정렬된 결과 반환 (12-20개)
    """
    target_k = self.config.cross_encoder.final_k  # 12-20
    
    # Candidate 변환
    candidates = [
        {
            "chunk_id": r.chunk_id,
            "file_path": r.file_path,
            "content": r.metadata.get("content", ""),
            "score": r.final_score,
            "metadata": r.metadata,
        }
        for r in fused_results
    ]
    
    # Cross-encoder 적용
    reranked = await self.cross_encoder.rerank(
        query=query,
        candidates=candidates,
        top_k=target_k,
    )
    
    # 결과 매핑 및 스코어 업데이트
    reranked_results = []
    for candidate in reranked:
        for result in fused_results:
            if result.chunk_id == candidate["chunk_id"]:
                result.metadata["cross_encoder_score"] = candidate.get(
                    "cross_encoder_score", result.final_score
                )
                reranked_results.append(result)
                break
    
    return reranked_results
```

### 설정

```python
@dataclass
class CrossEncoderConfig:
    enabled: bool = True
    min_query_length: int = 10          # 최소 쿼리 길이
    intent_triggers: list[str] = ["flow", "concept"]  # 트리거 Intent
    final_k: int = 15                   # 최종 결과 개수 (12-20)
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    batch_size: int = 32
    max_length: int = 512
```

### 성능 특성

| 항목 | Before (Fusion만) | After (+ Cross-Encoder) |
|------|------------------|------------------------|
| 결과 개수 | ~40개 | ~12-20개 |
| 정밀도 | 중간 | 높음 |
| Latency | ~3ms | +20-50ms |
| 활성화율 | 100% | ~30-40% (조건부) |

### 통합 예시

```python
# Orchestrator에서
fused_results, intent, metrics = await orchestrator.search(
    repo_id="codegraph",
    snapshot_id="HEAD",
    query="How does authentication flow work?",
    limit=40,
)

# metrics에 cross-encoder 정보 포함
{
    "total_ms": 45.2,
    "fusion_ms": 3.1,
    "cross_encoder_ms": 28.4,
    "cross_encoder_used": True,
    "result_count": 15,
}
```

### 트레이드오프

**장점:**
- 의미적 관련성 향상 (특히 복잡 쿼리)
- 불필요한 결과 제거
- Context budget 효율 향상

**단점:**
- Latency 증가 (20-50ms)
- GPU 필요 (선택)
- 모든 쿼리에 적용 시 오버헤드

**해결책:**
- 조건부 활성화로 트레이드오프 균형
- 간단한 쿼리는 Fusion만 사용
- 복잡한 쿼리만 Cross-encoder 적용

---

## Strategy Path Router (Intent → Path Selection)

### StrategyRouter
위치: [routing/strategy_router.py](src/contexts/retrieval_search/infrastructure/routing/strategy_router.py)

**기존 한계:**
- 모든 전략 항상 실행 (비용 낭비)
- Early stopping 없음
- Intent별 최적 경로 정의 없음

**NEW: 명시적 전략 경로 라우팅**

```python
class StrategyRouter:
    """
    Intent 기반 전략 경로 라우팅.

    - Primary → Fallback → Enrichment 3단계 실행
    - Early stopping으로 불필요한 전략 스킵
    - 전략별 latency 추적
    """

    async def route(
        self,
        query: str,
        intent_prob: IntentProbability,
        confidence_threshold: float = 0.4,
    ) -> RoutingResult:
        # 1. Intent 기반 경로 선택
        dominant = intent_prob.dominant_intent()
        if intent_prob[dominant] >= confidence_threshold:
            path = self.intent_paths[dominant]
        else:
            path = self.intent_paths["balanced"]

        # 2. Primary 전략 실행 (병렬)
        primary_results = await self._execute_strategies(
            path.primary, query, parallel=path.parallel_primary
        )

        # 3. Early stopping 체크
        total_hits = sum(len(r.hits) for r in primary_results)
        if total_hits >= path.early_stop_threshold:
            return RoutingResult(early_stopped=True, ...)

        # 4. Fallback 전략 실행 (필요시)
        if total_hits < path.early_stop_threshold:
            fallback_results = await self._execute_strategies(path.fallback, query)

        # 5. Enrichment 전략 (항상 실행)
        enrichment_results = await self._execute_strategies(path.enrichment, query)
```

**Intent별 전략 경로:**

```python
INTENT_STRATEGY_PATHS = {
    "symbol": StrategyPath(
        primary=[SYMBOL, LEXICAL],      # 심볼 우선
        fallback=[VECTOR],
        enrichment=[],
        early_stop_threshold=15,
        parallel_primary=True,
    ),
    "flow": StrategyPath(
        primary=[GRAPH, SYMBOL],        # 그래프 우선
        fallback=[LEXICAL, VECTOR],
        enrichment=[],
        early_stop_threshold=10,
    ),
    "concept": StrategyPath(
        primary=[VECTOR],               # 벡터만 (의미 검색)
        fallback=[LEXICAL],
        enrichment=[SYMBOL],            # 심볼로 보강
        early_stop_threshold=30,
        parallel_primary=False,         # 순차 실행
    ),
    "code": StrategyPath(
        primary=[LEXICAL, VECTOR],      # 키워드 + 의미
        fallback=[SYMBOL],
        enrichment=[GRAPH],
        early_stop_threshold=25,
    ),
    "balanced": StrategyPath(
        primary=[VECTOR, LEXICAL, SYMBOL],  # 모든 전략
        fallback=[GRAPH],
        early_stop_threshold=20,
    ),
}
```

**실행 결과:**

```python
@dataclass
class RoutingResult:
    hits_by_strategy: dict[str, list[RankedHit]]
    strategy_results: list[StrategyResult]  # 개별 전략 결과
    total_latency_ms: float
    strategies_executed: list[str]          # 실제 실행된 전략
    early_stopped: bool                     # Early stop 여부
    path_used: StrategyPath                 # 사용된 경로

@dataclass
class StrategyResult:
    strategy: StrategyType
    hits: list[RankedHit]
    latency_ms: float
    success: bool
    error: str | None
```

**Latency 추적 및 통계:**

```python
router.get_routing_stats()
# {
#   "average_latencies": {
#     "vector": 45.2,   # ms
#     "lexical": 12.8,
#     "symbol": 8.3,
#     "graph": 23.1
#   },
#   "sample_counts": {"vector": 156, ...}
# }
```

**커스텀 경로 설정:**

```python
# 특정 도메인에 최적화된 경로 추가
custom_path = StrategyPath(
    primary=[StrategyType.SYMBOL],
    fallback=[StrategyType.GRAPH, StrategyType.VECTOR],
    early_stop_threshold=10,
)
router.set_custom_path("debug", custom_path)
```

---

## Reranking Pipeline

### **2단계 리랭킹 구조 (프로덕션)**

```
Raw Candidates (~200)
  │
  ▼
┌────────────────────────────────────────────────────────────┐
│ STAGE 1: Retriever (필수)                                  │
│ [v3/orchestrator.py, v3/fusion_engine.py]                  │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │ 1. Multi-Index   │  │ 2. V3 Fusion     │               │
│  │    Search        │→ │    (RRF+Consensus)│              │
│  │  (200 candidates)│  │    Top ~40       │               │
│  └──────────────────┘  └──────────────────┘               │
│           │                      │                         │
│           ▼                      ▼                         │
│  ┌─────────────────────────────────────┐                  │
│  │ 3. Conditional Cross-Encoder        │                  │
│  │    (선택적, query complexity 기반)  │                  │
│  │    Top 40 → Top 12-20               │                  │
│  │    - Query length > 20              │                  │
│  │    - Intent: flow/concept           │                  │
│  │    - Keywords: why/how/explain      │                  │
│  └─────────────────────────────────────┘                  │
│                                                            │
└────────────────────────────────────────────────────────────┘
  │
  ▼ 12-20 candidates
┌────────────────────────────────────────────────────────────┐
│ STAGE 2: Agent Final Selection (선택적)                    │
│ [agent/tools/context_selector.py]                          │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │ 1. Noise Filter  │  │ 2. Test Filter   │               │
│  │  vendor/         │→ │  test_*.py       │              │
│  │  migrations/     │  │  *_test.py       │               │
│  └──────────────────┘  └──────────────────┘               │
│           │                      │                         │
│           ▼                      ▼                         │
│  ┌─────────────────────────────────────┐                  │
│  │ 3. Top-K Selection by Score         │                  │
│  │    12-20 → 6-12 (final context)     │                  │
│  │    - Semantic relevance             │                  │
│  │    - Dependency chain               │                  │
│  │    - LLM context budget             │                  │
│  └─────────────────────────────────────┘                  │
│                                                            │
└────────────────────────────────────────────────────────────┘
  │
  ▼ 6-12 final chunks (LLM Context)
```

### 리랭킹 설계 원칙

**1. 분리 책임:**
- **Retriever**: 검색 품질 + 비용 안정성 (deterministic, cheap)
- **Agent**: 의미·맥락 기반 최종 판단 (semantic, context-aware)

**2. Latency 상한 보장:**
- 대부분의 리랭킹은 Retriever 내부에서 처리
- Agent는 빠른 규칙 기반 필터링만

**3. Reproducibility:**
- Retriever 단계는 deterministic scoring
- Agent는 context-aware selection (optional)

### Conditional Cross-Encoder (Retriever Stage)

**설정:** [v3/config.py:99](src/contexts/retrieval_search/infrastructure/v3/config.py#L99)

```python
@dataclass
class CrossEncoderConfig:
    enabled: bool = False               # 기본 비활성화
    final_k: int = 15                   # 목표 결과 수 (12-20 범위)
    min_query_length: int = 20          # 최소 쿼리 길이
    complexity_threshold: float = 0.5   # 복잡도 임계값
    intent_triggers: set[str] = {"flow", "concept"}  # 트리거 의도
```

**트리거 조건:** [v3/orchestrator.py:254](src/contexts/retrieval_search/infrastructure/v3/orchestrator.py#L254)

```python
def _should_use_cross_encoder(self, query: str, intent_prob: IntentProbability):
    # 1. 기능 활성화 및 컴포넌트 존재
    if not config.enabled or not self.cross_encoder:
        return False

    # 2. 쿼리 길이 체크
    if len(query) < config.min_query_length:
        return False

    # 3. Intent 트리거 (flow, concept)
    if intent_prob.dominant_intent() in config.intent_triggers:
        return True

    # 4. 복잡 쿼리 패턴
    complex_keywords = ["why", "how", "explain", "debug", "refactor", "trace"]
    if any(keyword in query.lower() for keyword in complex_keywords):
        return True

    return False
```

**리랭킹 실행:** [v3/orchestrator.py:294](src/contexts/retrieval_search/infrastructure/v3/orchestrator.py#L294)

```python
async def _apply_cross_encoder_reranking(
    self,
    query: str,
    fused_results: list[FusedResultV3],  # ~40개
    intent_prob: IntentProbability,
) -> list[FusedResultV3]:  # 12-20개
    target_k = self.v3_service.config.cross_encoder.final_k

    # Cross-encoder 호출
    reranked_candidates = await self.cross_encoder.rerank(
        query=query,
        candidates=candidates,
        top_k=target_k,  # 15개
    )

    # 결과 업데이트
    for candidate in reranked_candidates:
        result.metadata["cross_encoder_score"] = candidate["cross_encoder_score"]

    return reranked_results  # 12-20개
```

### Agent Final Selection (Stage 2)

**도구:** [agent/tools/context_selector.py](src/contexts/agent_automation/infrastructure/tools/context_selector.py)

```python
class ContextSelectorTool:
    """
    Retriever 후보(12-20)를 최종 컨텍스트(6-12)로 필터링.

    필터링 기준:
    1. Noise 제거: vendor/, migrations/, legacy/
    2. Test 제거: test_*.py, *_test.py (선택적)
    3. Score 기반 Top-K
    4. Dependency chain 유지
    """

    NOISE_PATTERNS = [
        "vendor/", "node_modules/", "migrations/",
        "legacy/", "__pycache__/", ".git/",
    ]

    TEST_PATTERNS = [
        "test_", "_test.", "tests/",
        "spec.", "fixture", "mock",
    ]

    async def _execute(self, input_data: ContextSelectionInput):
        # 1. Noise 필터링
        filtered = self._filter_noise(candidates)

        # 2. Test 필터링 (keep_tests=False 시)
        if not input_data.keep_tests:
            filtered = self._filter_tests(filtered)

        # 3. Top-K by score
        filtered = self._select_top_k(filtered, target_count)

        # 4. Dependency chain 유지
        if input_data.keep_dependencies:
            filtered = self._ensure_dependencies(filtered)

        return ContextSelectionOutput(selected_chunks=filtered)
```

**사용 예시:**

```python
# Agent에서 호출
selector = ContextSelectorTool()

result = await selector.execute(
    ContextSelectionInput(
        candidates=retriever_results,  # 12-20개
        task_description="Implement user authentication",
        target_count=10,               # 6-12 범위
        keep_tests=False,              # 테스트 제외
        keep_dependencies=True,        # 의존성 유지
    )
)

# 최종 6-12개 청크를 LLM context에 전달
final_chunks = result.selected_chunks
```

**필터링 통계:**

```python
result.removal_reasons
# {
#   "test_files": 2,
#   "noise_files": 1,
#   "low_score": 3,
# }
```

### 3단계 Cascading Reranker (실험용)

**위치:** [service_optimized.py](src/contexts/retrieval_search/infrastructure/service_optimized.py)

```
Fusion Results (Top-100)
  │
  ▼
┌─────────────────────────────┐
│ Stage 1: Learned Reranker   │  ← 1-5ms, 90-95% LLM quality
│ [hybrid/learned_reranker.py]│
│ Top-100 → Top-50            │
└─────────────────────────────┘
  │
  ▼
┌─────────────────────────────┐
│ Stage 2: Late Interaction   │  ← ColBERT-style MaxSim
│ [hybrid/late_interaction.py]│
│ Top-50 → Top-20             │
└─────────────────────────────┘
  │
  ▼
┌─────────────────────────────┐
│ Stage 3: Cross-Encoder      │  ← 100ms, NDCG@10 +15%
│ [hybrid/cross_encoder_*.py] │
│ Top-20 → Top-10 (final)     │
└─────────────────────────────┘
```

**참고:** 실험용 파이프라인으로, V3 메인 파이프라인에는 미연동

### Cross-Encoder Reranker (v2 통합 완료)
위치: [hybrid/cross_encoder_reranker.py:46](src/contexts/retrieval_search/infrastructure/hybrid/cross_encoder_reranker.py#L46)

**통합 상태:** ✅ V3 Orchestrator에 완전 통합

**Cross-encoder vs Bi-encoder:**
- Bi-encoder: 쿼리/문서 각각 인코딩, 빠름, 낮은 품질
- Cross-encoder: 쿼리+문서 함께 인코딩, 느림, 높은 품질

```python
class CrossEncoderReranker:
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: str = "cpu",
        batch_size: int = 10,
        max_length: int = 512,
    ):
        self.model = CrossEncoder(model_name, max_length=max_length, device=device)

    async def rerank(self, query: str, candidates: list[dict], top_k: int = 10):
        pairs = [[query, c.get("content", "")[:2000]] for c in candidates[:top_k]]
        scores = self.model.predict(pairs, batch_size=self.batch_size)

        for i, candidate in enumerate(candidates[:top_k]):
            cross_score = self._normalize_score(scores[i])  # sigmoid
            original_score = candidate.get("score", 0.0)
            # 80% cross-encoder + 20% original
            candidate["final_score"] = 0.8 * cross_score + 0.2 * original_score
```

**V3 통합:**

```python
# config.py - 기본 활성화
@dataclass
class CrossEncoderConfig:
    enabled: bool = True  # ✅ 활성화됨
    final_k: int = 15
    min_query_length: int = 20
    intent_triggers: set[str] = {"flow", "concept"}

# factory.py - 자동 인스턴스 생성
def _create_v3(self, config):
    cross_encoder = self._create_cross_encoder_if_available()
    orchestrator = RetrieverV3Orchestrator(
        cross_encoder=cross_encoder,  # ✅ 주입됨
        ...
    )

# orchestrator.py - 조건부 적용
async def retrieve(...):
    if self._should_use_cross_encoder(query, intent_prob):
        fused_results = await self._apply_cross_encoder_reranking(...)
```

**성능:**
- 예상 개선: NDCG@10 +15%, MRR +20%
- 지연: Top-10 기준 ~100ms

### LLM Reranker
위치: [hybrid/llm_reranker.py:48](src/contexts/retrieval_search/infrastructure/hybrid/llm_reranker.py#L48)

**3차원 점수 평가:**

```python
@dataclass
class LLMScore:
    match_quality: float       # 리터럴 매칭 (0-1)
    semantic_relevance: float  # 의미적 관련성 (0-1)
    structural_fit: float      # 구조적 적합성 (0-1)
    overall: float             # 가중 평균
    reasoning: str             # LLM 설명

class LLMReranker:
    def __init__(
        self,
        llm_client: "LLMPort",
        top_k: int = 20,
        llm_weight: float = 0.3,  # 30% LLM, 70% original
        timeout_seconds: float = 5.0,
    ):
        ...

    async def rerank(self, query: str, candidates: list[dict]):
        # 배치 처리로 LLM 호출 최소화
        for batch in batched(candidates[:self.top_k], batch_size=5):
            batch_results = await self._score_batch(query, batch)
```

**전체 점수 공식:**
```
overall = 0.4 * match_quality + 0.4 * semantic_relevance + 0.2 * structural_fit
final = 0.7 * original_score + 0.3 * llm_score
```

### Learned Reranker (Student Model)
위치: [hybrid/learned_reranker.py:191](src/contexts/retrieval_search/infrastructure/hybrid/learned_reranker.py#L191)

**LLM 출력을 학습한 경량 모델:**

```python
class LearnedReranker:
    """
    LLM reranker 출력을 학습한 gradient boosted trees.
    - 지연: 500ms → 2ms (99.6% 감소)
    - 비용: $100/월 → $5/월 (95% 감소)
    - 품질: LLM의 90-95% 유지
    """

    def train(self, training_data: list[dict]):
        # LLM 출력으로 학습
        X = [self.feature_extractor.extract(ex["query"], ex["chunk"]).to_array()
             for ex in training_data]
        y = [1 if ex["llm_score"] > 0.7 else 0 for ex in training_data]

        self.model = GradientBoostingClassifier(n_estimators=100, max_depth=6)
        self.model.fit(X_train, y_train)
```

**19개 특성:**
```python
@dataclass
class RerankerFeatures:
    # Query features (4개)
    query_length: int
    query_has_code_identifiers: bool
    query_has_file_path: bool
    query_has_natural_language: bool

    # Chunk features (5개)
    chunk_length: int
    chunk_is_definition: bool
    chunk_is_class: bool
    chunk_is_function: bool
    chunk_is_import: bool

    # Matching features (4개)
    exact_token_matches: int
    fuzzy_token_matches: int
    keyword_overlap: float
    code_identifier_overlap: float

    # Score features (4개)
    vector_score: float
    lexical_score: float
    symbol_score: float
    combined_score: float

    # Context features (2개)
    is_test_file: bool
    is_config_file: bool
```

### HybridReranker (Student + LLM 폴백)
위치: [hybrid/learned_reranker.py:441](src/contexts/retrieval_search/infrastructure/hybrid/learned_reranker.py#L441)

```python
class HybridReranker:
    """
    - 대부분 쿼리: Learned model (빠름, 저렴)
    - 낮은 confidence 시: LLM 폴백
    - LLM 결과로 지속적 학습 데이터 수집
    """

    async def rerank(self, query: str, candidates: list[dict]):
        learned_results = self.learned_reranker.rerank(query, candidates)
        max_score = max(c.get("learned_reranker_score", 0) for c in learned_results)

        # 낮은 confidence 또는 랜덤 샘플링 시 LLM 사용
        use_llm = max_score < self.confidence_threshold or random.random() < 0.05

        if use_llm and self.llm_reranker:
            llm_results = await self.llm_reranker.rerank(query, candidates)
            # 학습 데이터 수집
            for c in llm_results:
                self.learned_reranker.collect_training_example(query, c, c.llm_score.overall)
            return llm_results

        return learned_results
```

---

## Late Interaction (ColBERT-style) - ✅ 완전 구현

**구현 상태**: 3개 파일에 완전 구현 (GPU 가속, 3-tier 캐싱 지원)

**파일**:
- `src/contexts/retrieval_search/infrastructure/hybrid/late_interaction.py`: 기본 MaxSim 구현
- `src/contexts/retrieval_search/infrastructure/hybrid/late_interaction_optimized.py`: GPU 가속, 양자화
- `src/contexts/retrieval_search/infrastructure/hybrid/late_interaction_cache.py`: 3-tier 캐싱

### MaxSim 알고리즘
위치: [hybrid/late_interaction.py:126](src/contexts/retrieval_search/infrastructure/hybrid/late_interaction.py#L126)

**ColBERT-style 토큰 레벨 매칭:**

```python
class LateInteractionSearch:
    """
    Query token과 document token 간 fine-grained matching.

    Pipeline 위치:
    Fast Retrieval (1000) → Fusion (100) → Late Interaction (50) → Cross-encoder (20)
    """

    def _compute_maxsim(self, query_emb: np.ndarray, doc_emb: np.ndarray):
        """
        MaxSim = sum of max similarities for each query token.

        For each query token q_i:
          max_sim_i = max(cos_sim(q_i, d_j) for all doc tokens d_j)

        total_score = sum(max_sim_i for all query tokens)
        """
        # (num_query_tokens, num_doc_tokens)
        similarities = np.dot(query_emb, doc_emb.T)

        # 각 쿼리 토큰에 대해 최대 유사도
        max_sims = np.max(similarities, axis=1)

        return float(np.sum(max_sims)), max_sims.tolist()
```

### Optimized Late Interaction
위치: [hybrid/late_interaction_optimized.py:247](src/contexts/retrieval_search/infrastructure/hybrid/late_interaction_optimized.py#L247)

**최적화 기법:**

```python
class OptimizedLateInteractionSearch:
    """
    성능 최적화:
    1. Pre-computed embeddings (인덱싱 시 캐시)
    2. GPU 가속 MaxSim (torch.matmul)
    3. Quantization (50% 메모리 절감)
    4. Batch processing

    예상 개선:
    - 캐시 히트: 0ms (vs 50-100ms)
    - GPU 가속: 10x speedup
    - 총 지연: 100ms → 10ms (90% 감소)
    """

    def __init__(
        self,
        embedding_model,
        cache: EmbeddingCache = None,
        use_gpu: bool = True,
        quantize: bool = False,  # int8 양자화
    ):
        ...

    def _maxsim_gpu_batch(self, query_embs, doc_embs_list):
        query_tensor = torch.from_numpy(query_embs).float().cuda()

        for chunk_id, doc_embs in doc_embs_list:
            doc_tensor = torch.from_numpy(doc_embs).float().cuda()
            similarities = torch.matmul(query_tensor, doc_tensor.T)
            max_sims = torch.max(similarities, dim=1).values
            score = float(torch.sum(max_sims).cpu().item())
```

### Embedding Cache
위치: [hybrid/late_interaction_optimized.py:47](src/contexts/retrieval_search/infrastructure/hybrid/late_interaction_optimized.py#L47)

```python
class EmbeddingCache:
    """
    3-tier 임베딩 캐시:
    1. In-memory LRU (maxsize=10000)
    2. Redis (선택, TTL=24h)
    3. Disk (sharded by hash prefix)
    """

    def get(self, chunk_id: str) -> np.ndarray | None:
        # L1: Memory
        if chunk_id in self.memory_cache:
            return self.memory_cache[chunk_id].embeddings

        # L2: Redis
        if self.redis_client:
            data = self.redis_client.get(f"emb:{chunk_id}")
            if data:
                return pickle.loads(data).embeddings

        # L3: Disk
        cache_file = self._get_cache_file(chunk_id)
        if cache_file.exists():
            return pickle.load(cache_file).embeddings

        return None
```

---

## Scope Selection (v2 통합 완료)

### ScopeSelector
위치: [scope/selector.py:21](src/contexts/retrieval_search/infrastructure/scope/selector.py#L21)

**통합 상태:** ✅ V3 Orchestrator Wrapper에 통합

**RepoMap 기반 검색 범위 제한:**

```python
class ScopeSelector:
    """
    쿼리 의도와 RepoMap을 기반으로 검색 범위를 좁힘.

    Scope types:
    - full_repo: 전체 레포 검색 (RepoMap 없거나 stale 시)
    - focused: 특정 노드/청크에 집중 (RepoMap 활용)
    - symbol_only: 심볼 검색만 (특정 쿼리)
    """

    def select_scope(self, repo_id: str, snapshot_id: str, intent: QueryIntent) -> ScopeResult:
        # RepoMap 유효성 검사
        status, can_use = self.validator.validate_or_warn(repo_id, snapshot_id)

        if not can_use:
            return ScopeResult(scope_type="full_repo", reason=f"repomap_{status.value}")

        # 의도 기반 포커스 노드 선택
        focus_nodes = self._select_focus_nodes(repomap, intent)

        # 청크 스코프 계산
        chunk_ids = self._calculate_chunk_scope(repomap, focus_nodes)

        return ScopeResult(
            scope_type="focused",
            focus_nodes=focus_nodes,
            chunk_ids=chunk_ids,  # 이 청크들만 검색
        )
```

**V3 통합:**

```python
# factory.py - 자동 생성
def _create_scope_selector_if_available(self):
    repomap_port = getattr(self.container, "repomap_port", None)
    if repomap_port:
        return ScopeSelector(repomap_port=repomap_port)
    return None

# _V3OrchestratorWrapper - retrieve 시작 시 적용
async def retrieve(self, repo_id, snapshot_id, query):
    # 1. Scope selection
    scope = None
    if self._scope_selector:
        intent = QueryIntent(query=query, intent_kind="symbol")
        scope = self._scope_selector.select_scope(repo_id, snapshot_id, intent)
    
    # 2. Orchestrator에 scope 전달
    result = await self._orchestrator.retrieve(
        repo_id, snapshot_id, query,
        scope=scope,  # ✅ 전달됨
    )
```

### 의도별 포커스 노드 전략

```python
def _select_by_intent_kind(self, repomap, intent_kind: IntentKind):
    if intent_kind == IntentKind.REPO_OVERVIEW:
        # 진입점, 최상위 모듈
        nodes = [n for n in repomap.nodes if n.is_entrypoint or n.depth <= 2]

    elif intent_kind == IntentKind.CONCEPT_SEARCH:
        # 고중요도 노드, 테스트 제외
        nodes = [n for n in repomap.nodes if not n.is_test and n.metrics.importance > 0]

    elif intent_kind == IntentKind.CODE_SEARCH:
        # 구현 코드: 함수/클래스 + LOC > 10
        nodes = [n for n in repomap.nodes
                 if n.kind in ["function", "class"] and n.metrics.loc > 10]

    elif intent_kind == IntentKind.SYMBOL_NAV:
        # 높은 연결성 노드 (PageRank 기준)
        nodes = [n for n in repomap.nodes if n.metrics.edge_degree > 0]
        nodes.sort(key=lambda n: n.metrics.pagerank or 0, reverse=True)

    elif intent_kind == IntentKind.FLOW_TRACE:
        # 고차수 노드 (흐름 추적용)
        nodes = [n for n in repomap.nodes if n.metrics.edge_degree > 2]

    return nodes[:self.default_top_k]  # 기본 20개
```

### RepoMap Validator
위치: [scope/validator.py:101](src/contexts/retrieval_search/infrastructure/scope/validator.py#L101)

```python
class RepoMapStatus(str, Enum):
    FRESH = "fresh"       # 스냅샷 일치 + 최신
    STALE = "stale"       # 스냅샷 불일치
    OUTDATED = "outdated" # 스냅샷 일치 + 오래됨
    MISSING = "missing"   # RepoMap 없음

class RepoMapValidator:
    def __init__(
        self,
        repomap_port: "RepoMapPort",
        stale_threshold_hours: float = 1.0,    # 1시간
        outdated_threshold_hours: float = 24.0, # 24시간
    ):
        ...

    def validate_or_warn(self, repo_id, snapshot_id) -> tuple[RepoMapStatus, bool]:
        status = self.validate_freshness(repo_id, snapshot_id)

        if status == RepoMapStatus.MISSING or status == RepoMapStatus.STALE:
            return status, False  # full_repo 검색으로 폴백

        # OUTDATED도 사용 가능 (suboptimal이지만)
        return status, True
```

---

## Top-K Cutoff

### 의도별 Cutoff
위치: [v3/config.py:88](src/contexts/retrieval_search/infrastructure/v3/config.py#L88)

```python
@dataclass
class CutoffConfig:
    symbol: int = 20    # 정밀 검색 → 적은 결과
    flow: int = 15      # 흐름 추적 → 적은 결과
    concept: int = 60   # 개념 이해 → 많은 결과
    code: int = 40      # 코드 검색 → 중간
    balanced: int = 40  # 균형 → 중간
```

**적용:** [v3/fusion_engine.py:446](src/contexts/retrieval_search/infrastructure/v3/fusion_engine.py#L446)

```python
def apply_cutoff(self, results, intent_prob):
    dominant = intent_prob.dominant_intent()
    k = getattr(self.config.cutoff, dominant, self.config.cutoff.balanced)
    return results[:k]
```

---

## 설정

### RetrieverV3Config
위치: [v3/config.py:99](src/contexts/retrieval_search/infrastructure/v3/config.py#L99)

```python
@dataclass
class RetrieverV3Config:
    rrf: RRFConfig                    # RRF k값
    consensus: ConsensusConfig        # 합의 파라미터
    intent_weights: IntentWeights     # 의도별 가중치
    cutoff: CutoffConfig              # Top-K cutoff

    # 기능 토글
    enable_query_expansion: bool = True
    enable_explainability: bool = True
    enable_cache: bool = True

    # 캐시 설정
    cache_ttl: int = 300
    l1_cache_size: int = 1000
    intent_cache_size: int = 500
```

**환경변수 로드:** [v3/config.py:154](src/contexts/retrieval_search/infrastructure/v3/config.py#L154)

```python
# SEMANTICA_RETRIEVER_* 환경변수 사용
config = RetrieverV3Config.from_settings()
```

---

## 에러 처리

위치: [exceptions.py](src/contexts/retrieval_search/infrastructure/exceptions.py)

| 예외 | 설명 |
|------|------|
| `QueryValidationError` | 입력 검증 실패 |
| `RetrievalTimeoutError` | 30초 초과 |
| `SnapshotNotFoundError` | 스냅샷 없음 |
| `FusionError` | 융합 오류 |

---

## 디렉토리 구조

```
src/contexts/retrieval_search/infrastructure/
├── v3/                          # V3 핵심 구현
│   ├── service.py              # 메인 서비스
│   ├── orchestrator.py         # Async 오케스트레이터
│   ├── fusion_engine.py        # 융합 엔진
│   ├── intent_classifier.py    # 의도 분류기
│   ├── rrf_normalizer.py       # RRF 정규화
│   ├── consensus_engine.py     # 합의 부스팅
│   ├── config.py               # 설정
│   ├── models.py               # 데이터 모델
│   └── cache.py                # L1 캐시
├── hybrid/                      # 리랭킹 파이프라인
│   ├── reranker.py             # 리랭커 프로토콜
│   ├── cross_encoder_reranker.py # Cross-encoder (Top-10)
│   ├── llm_reranker.py         # LLM 리랭커 (Top-20)
│   ├── learned_reranker.py     # Student model (Top-50)
│   ├── late_interaction.py     # ColBERT-style MaxSim
│   ├── late_interaction_optimized.py # GPU 가속 버전
│   └── late_interaction_cache.py # 임베딩 캐시
├── scope/                       # 검색 범위 선택
│   ├── selector.py             # RepoMap 기반 스코프 선택
│   ├── validator.py            # RepoMap 유효성 검증
│   └── models.py               # ScopeResult 모델
├── context_builder/            # 컨텍스트 빌더
│   ├── builder.py              # 메인 빌더
│   ├── dedup.py                # 중복 제거
│   ├── trimming.py             # 트리밍
│   ├── ordering.py             # 청크 순서
│   └── models.py               # 모델
├── query/                       # 쿼리 처리
│   ├── decomposer.py           # 쿼리 분해
│   ├── multi_hop.py            # 멀티홉 검색
│   ├── rewriter.py             # 쿼리 재작성
│   └── models.py               # 모델
├── graph_runtime_expansion/    # 그래프 확장 (레거시)
│   └── flow_expander.py        # BFS 확장
├── graph/                       # **NEW** Cost-aware 그래프 탐색
│   ├── edge_cost.py            # Edge cost 모델
│   └── cost_aware_expander.py  # Dijkstra 기반 확장
├── adaptive/                    # **NEW** 적응형 가중치 학습
│   └── weight_learner.py       # 피드백 기반 가중치 학습
├── routing/                     # **NEW** 전략 경로 라우팅
│   └── strategy_router.py      # Intent → Path selection
├── intent/                      # 의도 분석
│   ├── service.py              # 의도 서비스
│   ├── rule_classifier.py      # 규칙 기반 분류
│   └── ml_classifier.py        # ML 기반 분류
├── fusion/                      # 융합 엔진
│   ├── engine.py               # 융합 로직
│   └── normalizer.py           # 점수 정규화
├── evaluation/                  # 평가 프레임워크
│   ├── metrics.py              # Recall, NDCG 등
│   ├── evaluator.py            # 평가기
│   └── golden_set_service.py   # Golden set 관리
└── models.py                    # 공통 모델
```

---

## 주요 데이터 흐름

```
Query: "who calls authenticate"
  │
  ▼
IntentClassifierV3.classify()
  → IntentProbability(symbol=0.2, flow=0.6, concept=0.1, code=0.05, balanced=0.05)
  │
  ▼
RetrieverV3Orchestrator._search_parallel()
  → {
      "symbol": [SearchHit(chunk_id="c1", rank=0), ...],
      "vector": [SearchHit(chunk_id="c2", rank=0), ...],
      "lexical": [SearchHit(chunk_id="c1", rank=2), ...],
      "graph": [SearchHit(chunk_id="c3", rank=0), ...]
    }
  │
  ▼
FusionEngineV3.fuse()
  1. weights = {vec: 0.15, lex: 0.08, sym: 0.15, graph: 0.62}  # flow 부스트 적용
  2. rrf_scores["c1"]["symbol"] = 1/(50+0) = 0.02
  3. base_scores["c1"] = 0.15*0.02 + 0.62*0.01 = ...
  4. consensus_factor["c1"] = 1.13  # 2개 전략
  5. final_score["c1"] = base * consensus
  │
  ▼
FusedResultV3[]
  → [FusedResultV3(chunk_id="c1", final_score=0.85, ...), ...]
  │
  ▼
ContextBuilder.build()
  → ContextResult(chunks=[...], total_tokens=3800, token_budget=4000)
```
