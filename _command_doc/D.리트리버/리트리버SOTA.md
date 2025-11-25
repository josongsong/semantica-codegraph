RFC: Semantica Hybrid Multi-Index Retriever v3 (S-HMR-v3)

문서 ID: RET-A10-00
버전: v3.0
작성 목적: SOTA 코드 검색·이해·그래프 탐색에 최적화된 하이브리드 리트리버 엔진의 완전한 내부 명세 정의

1. 아키텍처 개요

1-1. 목표

코드베이스를 Vector / Lexical / Symbol / Graph / RepoMap / Metadata 기반으로 동시 융합 검색

Intent-aware / Strategy-aware / Rank-normalized 구조

RRF 기반 late-fusion

Multi-label intent → dynamic weight adaptation

LTR 연동 가능한 feature-first 구조

1-2. 전체 레이어

Query → Intent Classifier

Per-index Retrieval (4 strategies)

Normalization (Strategy-RRF)

Consensus Engine

Fusion Engine

Ranking Layer

Result Formatter

1-3. 핵심 설계 원칙

Score-agnostic: raw score 불사용

Rank-first: 모든 전략에서 rank normalization

Intent-adaptive: soft weight mixing

Consensus-aware: multi-index co-occurrence 강화

Graph-aware: Flow/Trace 전용 weighting

2. 내부 모듈 구조

2-1. Module Map

IntentClassifier

RetrievalLayer

VectorRetriever

LexicalRetriever

SymbolRetriever

GraphRetriever

RankNormalizer

RRFNormalizer

FusionLayer

WeightedRRF

ConsensusBooster

RankingLayer

Formatter

2-2. 호출 관계
IntentClassifier
→ RetrievalLayer (parallel 4 calls)
→ RankNormalizer
→ WeightedRRF
→ ConsensusBooster
→ FinalRanker
→ Formatter

3. Intent Classification

3-1. Multi-label 분류
출력:

p_intent: {
  symbol: float,
  flow: float,
  concept: float,
  code: float,
  balanced: float
} sum = 1


3-2. 규칙 기반 v1

symbol_like: 식별자, 패턴, class/def, ::, ., camelCase

flow_like: call, who calls, where used, trace, flow

concept_like: explain, what is, how works

code_like: example, implement, loop, conditional

balanced: default

3-3. softmax 기반 score → intent 확률

4. Strategy Index Interface

4-1. 공통 인터페이스

retrieve(query, k) -> list[(chunk_id, rank)]


4-2. 전략별 특징

Vector: HNSW 또는 IVF PQ / cosine

Lexical: BM25 / LSH (옵션)

Symbol: FQN index / Inverted Symbol Table

Graph: callers/callees / import graph / DFG slice

5. Weight Profile (Intent → Strategy Weight)

5-1. Base Profiles

W_CODE    = { vec:0.5, lex:0.3, sym:0.1, graph:0.1 }
W_SYMBOL  = { vec:0.2, lex:0.2, sym:0.5, graph:0.1 }
W_FLOW    = { vec:0.2, lex:0.1, sym:0.2, graph:0.5 }
W_CONCEPT = { vec:0.7, lex:0.2, sym:0.05, graph:0.05 }
W_BAL     = { vec:0.4, lex:0.3, sym:0.2, graph:0.1 }


5-2. 선형 조합

W_final = Σ (p_intent[i] * W_i)
normalize(W_final)

6. Rank Normalization (Weighted RRF)

6-1. per-strategy RRF
전략 s에서 청크 d의 rank:

rrf_s(d) = 1 / (k_s + rank_s(d))


symbol, graph: k_s = 50

vector, lexical: k_s = 70

6-2. Weighted RRF

base_score(d) = Σ_s W_final[s] * rrf_s(d)

7. Consensus Engine

7-1. 전략 등장 수

M(d) = |{ s | d in R_s }|


7-2. 품질 요약

avg_rank(d)
best_rank(d)
quality_factor = 1 / (1 + avg_rank/10)


7-3. consensus factor

consensus_raw = 1 + β*(sqrt(M)-1)    # β=0.3
consensus_capped = min(1.5, consensus_raw)
consensus_factor = consensus_capped * (0.5 + 0.5*quality_factor)


7-4. 최종 점수

final_score(d) = base_score(d) * consensus_factor

8. Ranking Layer

8-1. full ranking

score_final(d) 기반 전체 정렬

동일 점수 시 best_rank(d) 우선

graph-hit 우선 옵션 가능

8-2. Top-K cutoff

기본 k=40

intent에 따라 동적 k 조정

concept: k ↑

symbol: k ↓

flow: k 매우 낮음 (정확성 중요)

9. Feature Schema (LTR-ready)

각 청크 d에 대해 feature vector:

F(d) = {
  # 1. 전략별 rank
  rank_vec,
  rank_lex,
  rank_sym,
  rank_graph,

  # 2. RRF
  rrf_vec,
  rrf_lex,
  rrf_sym,
  rrf_graph,

  # 3. intent weight
  W_final_vec,
  W_final_lex,
  W_final_sym,
  W_final_graph,

  # 4. consensus
  M,
  best_rank,
  avg_rank,
  consensus_factor,

  # 5. metadata
  chunk_size,
  file_depth,
  symbol_type,
}


LTR(LambdaMART, LightGBM Ranking, XGBoost Rank) 투입 가능.

10. Retrieval Pipeline 상세

10-1. Flow

classify_intent

retrieve from all strategies

RRF normalize

weight multiply

sum

consensus boost

rerank

return

10-2. pseudo-code

p = classify_intent(query)
W = build_weights(p)
R = parallel_retrieve(query)

scores = {}

for s in strategies:
    for (d, rank) in R[s]:
        scores[d] += W[s] * (1 / (k_s + rank))

for d in scores:
    M = count_strategies(d)
    avg = avg_rank(d)
    qual = 1 / (1 + avg/10)
    factor = min(1.5, 1+0.3*(sqrt(M)-1)) * (0.5 + 0.5*qual)
    scores[d] *= factor

return top_k(sort_by_value(scores))

11. 최적화 포인트

11-1. 병렬성

4전략 retrieval parallel futures

graph traversal batch BFS

11-2. 정규화

per-query rank cutoff

lexical top-n filtering

11-3. 캐싱

Symbol index hot set

Vector ANN cache

Graph slice cache

12. SOTA 구성 요소 요약

12-1. 핵심 기여

Intent multi-label soft mixing

Weighted RRF (score-agnostic)

Graph-aware weighted fusion

Consensus-aware rank booster

LTR-ready feature schema

독립 전략–결과 late fusion 구조

Symbol / Graph priority routing

Universal normalization pipeline

12-2. 검색 품질

LLM 기반 코드 에이전트의 Context Builder로 최적

Graph navigation / flow trace 정확도 극대화

Concept / natural language 검색 recall 강화

Multi-index consensus로 hallucination 감소

symbol-first 작업에 특화

13. Appendix: 모든 파라미터의 기본값

13-1. RRF

k_vec   = 70
k_lex   = 70
k_sym   = 50
k_graph = 50


13-2. consensus

beta = 0.3
max_factor = 1.5
quality_q0 = 10


13-3. base weight
위 Base Profiles 동일

13-4. cutoff
symbol: k=20
flow: k=15
concept: k=60
code/balanced: k=40

14. 결론

S-HMR-v3는 아래 조건을 모두 충족함:

Vector / Symbol / Lexical / Graph 전부를 활용하는 완전한 하이브리드

Intent-aware, Rank-based, Consensus-aware 구조

Graph-first flow trace, Symbol-first navigation 지원

점수 스케일 의존성 제거 → 안정적

LTR로 곧바로 전환 가능한 feature schema

코드 에이전트용 SOTA Retriever 구성