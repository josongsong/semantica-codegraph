1. v5: 정적 분석기 + LSP Name Resolution 확장안 (Semantica Codegraph Precision Engine)
1-1. 목적 개요

Semantica v4는 “빠르고 유연한 코드 검색기” 단계이다.
v5는 **“정교한 타입/스코프/네임 해석이 가능한 정확한 코드 이해 엔진”**으로 발전하는 단계이다.
즉, Cursor·Cody의 정확도, JetBrains IDE 수준의 레퍼런스 추적을 실현한다.

1-2. 정적 분석기 통합 (Static Analyzer Fusion Layer)
1-2-1. 언어별 해석기

Python: Pyright Symbol Table + Type Checking

TypeScript: TSC Compiler API + SWC

Java: javac AST → Symbol Table

Kotlin: K2 Compiler API

Go: go/types, go/ast

Rust: rust-analyzer → HIR

1-2-2. 샘플 데이터 추출

각 언어별 AST + Symbol Table로 아래 정보를 CodeGraph로 변환:

정확한 Definition Resolution

import shadowing / name shadowing

override/overload relations

class → method map

function → closure captured variables

unreachable branches

unused code

nullability flows

v4의 “best-effort graph” → v5의 “precise semantic graph”.

1-3. LSP 기반 Name Resolution Layer
1-3-1. LSP가 제공하는 것

goto-definition

find-references

call hierarchy

type hierarchy

document symbols

semantic tokens

1-3-2. CodeGraph 변환 방식

모든 LSP 결과를 Kùzu Graph로 변환:

LSP-GOTO → RESOLVES_TO

LSP-REFERENCES → REFERENCED_BY

LSP-CALL-HIERARCHY → CALLS

LSP-INHERITANCE → INHERITS

LSP-HOVER TYPEINFO → HAS_TYPE

이 구조는 실제로 Sourcegraph의 SCIP가 하는 역할과 95% 유사하다.
우리는 SCIP 없이 동일한 품질을 재현한다.

1-4. v5가 제공하는 능력

“정확한 Rename Impact Tree”

“타입 기반 검색(Type-aware search)”

“변수/클래스/함수 전체 레퍼런스 정확도 95%+”

“call chain multi-hop 10~20 depth 자동 탐색”

“테스트 코드 ↔ 함수 ↔ API ↔ Config 연관관계 자동 생성”

1-5. 개발자 이점

IDE 수준 refactoring tool

정확한 코드 맥락 제공으로 LLM hallucination 감소

import/export 사이의 누락·오류를 자동 감지

unknown symbol 문제 자동 분석

2. v6: Graph Neural Network 기반 Code Embedding (Semantic Structure Engine)
2-1. 목적 개요

v5가 “정확한 정적분석 그래프”라면
v6는 그 그래프를 GNN 모델로 학습해서 의미적 embedding 공간을 생성한다.

즉, 코드 구조 + 의미 + 타입 + 호출관계를 모두 학습한
“단일 고품질 의미 공간”을 구축한다.

2-2. Graph Neural Network 구조
2-2-1. 입력

노드: Symbol, File, Chunk

엣지: CALLS, INHERITS, USES, TESTS, OVERRIDES, DEPENDS_ON

노드 특성: 요약(summary), raw code embedding, cyclomatic complexity, token size, language type

2-2-2. 모델 타입

GraphSAGE

Graph Attention Network (GATv2)

Graph Transformer (Global attention)

2-2-3. 학습 방식

contrastive learning (CodeBERT류)

next-hop prediction (call graph)

semantic similarity triplet loss

test ↔ function ↔ API linkage alignment

GNN의 핵심은
**“인접한 코드 구조가 의미적으로도 가까워지도록 하는 추론 구조”**를 만든다는 것.

2-3. 결과
2-3-1. 검색 품질 개선

구조적 의미 인식 → 검색 정확도 20~40% 증가

“아 이 함수랑 이 함수가 같은 역할”을 모델이 직접 인식

test → function → API 링크 자동 추론

2-3-2. advanced capability

자동 리팩토링 후보 추천

코드 smell 탐지

문제 발생 시 root-cause 자동 제안

LLM이 “검색”이 아니라 **“연결 추론”**을 수행할 수 있는 기반 구축

2-4. Storage-level 플랫폼 변화

Qdrant 컬렉션: LLM embedding + GNN embedding Dual Index

HybridRetriever:

lexical (Zoekt) +

semantic (LLM) +

structural (GNN)
→ 3-way Hybrid Weighted Fusion

Cursor, Claude Code보다 한 단계 위로 올라가는 지점이 여기에 있음.

3. v7: Multi-Agent Pair Programming (Collaborative AI Developer Team)
3-1. 목적 개요

v7은 “단일 모델 기반 코드 에이전트”를 넘어서
인간 + 복수의 AI가 동시에 협업하는 Pair-Programming 환경을 구축한다.

Cursor / Copilot / Claude Code 중 어느 것도 완전하게 담당하지 못하는 영역이다.

3-2. 에이전트 구성
3-2-1. Planner Agent

유저 intent 분석

필요한 파일/함수/테스트 탐색

tool invocation sequence 작성

diff plan 생성

3-2-2. Coding Agent

diff 생성

함수 구현

리팩토링

파일 생성/삭제

3-2-3. Reviewer Agent

보안/성능/스타일 감리

regression risk 분석

test coverage 평가

3-2-4. Test Runner / Debugger Agent

failing test 분석

call chain 역추적

log/trace 기반 root-cause 도출

failing scenario fix 제안

3-3. Multi-agent Orchestration (LangGraph 기반)
3-3-1. Workflow

Planner가 목표 결정

Context Retriever 호출

Coding Agent diff 작성

Reviewer가 검증

Debugger가 테스트 실행

모든 단계 통과 시 commit/push

3-3-2. Shared Memory

Long-term memory: Kùzu, Qdrant, Zoekt

Short-term memory: session-level context

Decision memory: agent-chain intermediate reasoning (hidden)

3-4. Multi-user Pair Programming

생성 AI pair → 협업 pair로 확장

Host와 Guest가 각각 다른 파일 열어도

Planner Agent가 맥락을 통합

Coding Agent가 양쪽 변경을 병합(Semantic 3-way merge)

Reviewer Agent가 충돌, 위험, 스타일 문제 자동 감지

실제로 “pair-programming with AI & humans simultaneously”를 실현한다.

4. v4 → v5 → v6 → v7 진화 요약
4-1. 기술적 진화

v4: AST + Graph + Hybrid Retrieval

v5: 정적 분석기 + LSP + 정확한 Semantic Graph

v6: Graph Neural Network + 구조적 의미 추론

v7: Multi-Agent Automated Software Engineer

4-2. 난이도/시간

v5: 2~4주

v6: 6~10주 (GNN 학습 포함)

v7: 4~8주 (LangGraph 기반 multi-agent orchestration)

4-3. 결과업무효과

개발자 10명분의 탐색·분석 능력

리팩토링 자동화

버그 자동 수정

로그/trace 기반 해석 자동화

테스트 생성/유지 자동화

대규모 마이그레이션 자동화 (Python→TS 등)
