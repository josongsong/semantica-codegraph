
레이어별 큰 모듈 나누기 (foundation + RepoMap 반영 버전)

1-1. foundation 레이어
Parsing / AST / IR / Graph / Chunk
코드레포를 Semantica 내부 공통 표현으로 바꾸는 “엔진 기초 계층”임.

1-2. repomap 레이어
Chunk/Graph/IR를 받아 “프로젝트 구조 요약 + 중요도 기반 트리”를 만드는 계층.
LLM이 한 번에 이해할 수 있는 프로젝트 지도 역할.

1-3. index 레이어
Lexical / Vector / Symbol / Fuzzy / Domain / Runtime
각종 인덱스를 “플러그인”처럼 붙이는 계층.

1-4. retriever 레이어
Query 분석 / Multi-index 조회 / Graph+Runtime Expansion / Fusion / Context builder
LLM/에이전트가 실제로 호출하는 “검색 + 컨텍스트 생성” 계층.

이 네 개 레이어만 지키면, Search 백엔드(Meilisearch→Zoekt, Qdrant→pgvector) 바꿔도 설계는 안 깨짐.

foundation Layer 모듈 (기존 core 2-1 ~ 2-4 대응)

2-1. foundation.parsing (1-1 Parsing & AST)

역할

파일 단위로 Tree-sitter 돌려서 언어별 AST 생성

주요 컴포넌트

ParserRegistry

SourceFile (경로, 언어, raw text)

AstTree (언어별 AST 래퍼)

의존성

최하단. 아무것도 안 봄.

2-2. foundation.ir (1-2 IR)

역할

AST → 언어 중립 IR 노드

FunctionLike / TypeLike / Conditional / Loop / TryCatch 등

scope / FQN / role(Controller, Service, Repo 등) 메타데이터 부여

주요 컴포넌트

IrNode base

IrFunctionLike, IrTypeLike, IrBlock, IrCondition 등

Scope, Fqn, RoleTagger

의존성

foundation.parsing만 참조

이후 모든 축(Graph, Chunk, Symbol, RepoMap 등)이 이 IR만 바라보게 하는 게 핵심.

2-3. foundation.graph (1-3 Graph Construction)

역할

IR 기반 정적 코드 그래프 구성

노드: File / Module / Class / FunctionLike / Route / Service / Repo

엣지: calls / imports / inherits / implements / route_to / uses_repo 등

엔트리포인트(route, CLI, cron 등) 기준 구조화

주요 컴포넌트

GraphNode, GraphEdge

CodeGraphBuilder

EntryPointDetector

의존성

foundation.ir만 참조

index, retriever, repomap은 foundation.graph를 읽기만 함.

2-4. foundation.chunk (1-4 Chunk Hierarchy)

역할

IR/Graph 기반으로 LLM 단위 청크 계층 생성

Leaf: 함수/메서드 단위 chunk

Parent: 클래스/모듈/파일 단위 chunk

주요 컴포넌트

ChunkId, LeafChunk, ParentChunk

ChunkHierarchyBuilder

Chunk ↔ IR/Graph 매핑 정보

의존성

foundation.ir, foundation.graph만 참조

index, repomap, retriever의 기본 단위가 여기 chunk 스키마.

RepoMap Layer 모듈 (foundation과 index 사이에 끼는 1.5 레이어)

3-1. repomap.builder

역할

IR + Graph + Chunk 기반으로 “프로젝트 구조 요약 트리” 생성

LLM-friendly 프로젝트 지도 역할 (module → file → function 구조)

입력

IrNode

GraphNode / GraphEdge

LeafChunk, ParentChunk

출력

RepoMapNode 트리 (노드별 id, 연결 관계, 관련 chunk/graph/ir 레퍼런스)

3-2. repomap.pagerank

역할

RepoMap 트리 위에서 중요도(PageRank / HybridRank) 계산

“어떤 함수/파일/모듈이 더 중요한지” 수치화

출력

각 RepoMapNode에 importance_score 부여

이후 Retriever.fusion, context_builder에서 사용.

3-3. repomap.summarizer

역할

각 RepoMap 노드(모듈/파일/클래스/함수)에 대한 요약 텍스트 생성

LLM 또는 템플릿 기반 요약

출력

RepoMapNode.summary_text

상위 레벨(프로젝트/모듈) 요약도 포함.

3-4. repomap.tree

역할

전체 RepoMap 트리를 직렬화/탐색 가능한 형태로 제공

“이 후보의 상위/하위/형제 노드” 탐색을 Retriever가 쉽게 할 수 있게 함

의존성

foundation.ir, foundation.graph, foundation.chunk만 참조

index, retriever는 repomap을 읽기만 함.

Index Layer 모듈 (Static Index Family, 3-1 ~ 3-6)

각 Index는 “입력 = Chunk / IR / Graph / RepoMap”을 읽어서 자기 저장소에 넣는 플러그인 느낌으로 설계.

4-1. index.lexical

역할

파일/청크 텍스트 전체에 대해 substring, 에러 메시지, SQL, 주석 등 텍스트 기반 고속 검색

입력

LeafChunk / ParentChunk 텍스트

4-2. index.vector

역할

Chunk 텍스트 → 임베딩 → 의미 기반 검색

“장바구니 기능 어디?” 같은 자연어 쿼리 대응

입력

주로 LeafChunk, 필요시 ParentChunk

4-3. index.symbol

역할

IR의 definition / reference / scope 정보 인덱싱

go-to-def / find-refs / 구현체 목록

입력

IrNode 집합, Scope, Fqn

필요시 GraphNode와 cross link

4-4. index.fuzzy

역할

identifier / 토큰 n-gram 기반 오타/깨진 코드 tolerant 검색

입력

chunk에서 추출한 identifier, 토큰 시퀀스

4-5. index.domain_meta

역할

README, ADR, OpenAPI, DB schema, config 등 “코드 외 문서” 인덱싱

IR/Graph/RepoMap과 매핑해서 “문서 → 코드” 링크 구축

입력

문서 텍스트 + 해석된 구조(예: OpenAPI endpoint → Route node, RepoMap node ref)

4-6. index.runtime

역할

실제 실행 시 수집한 로그/트레이스/프로파일 정보를 IR/Graph/RepoMap node에 attach

DI 실제 구현체, feature flag ON/OFF 경로, 핫패스, 에러 위치

입력

tracing/span 로그 + GraphNode 또는 RepoMapNode 매핑 정보

Retriever Layer 모듈 (2-1 ~ 2-5, RepoMap 활용 포함)

5-1. retriever.intent (2-1 Query Routing)

역할

쿼리 분석 → 어떤 축을 얼마나 쓸지 결정

“정의 위치” vs “기능 검색” vs “실행 경로” 분리

출력

RetrievalPlan

사용 index: [lexical, vector, symbol, graph, runtime, domain, fuzzy]

각 축 가중치 초기값

5-2. retriever.multi_index (2-2 Multi-Index Search)

역할

계획에 따라 각 Index를 병렬 조회

축별 후보 chunk/node + score 리스트 생성

출력

CandidateSet (축별 score 포함)

5-3. retriever.graph_runtime_expansion (2-3 Expansion)

역할

Graph를 따라 인접 노드 확장

route → service → repo

caller / callee 확장

Runtime Info를 오버레이

실제 실행 경로, 에러/핫패스 노드에 가중치

출력

확장된 CandidateSet

필요 시 RepoMap 트리를 참고해 상위/하위 노드 확장 전략 결정.

5-4. retriever.fusion (2-4 Weighted Fusion)

역할

lexical_score, vector_score, symbol_score, graph_score, runtime_score, fuzzy_score, domain_meta_score 가중합

최종 ranking 계산

출력

정렬된 RankedResults

5-5. retriever.context_builder (2-5 Context Builder)

역할

상위 N개 후보를 Chunk Hierarchy + RepoMap 기준으로 묶고 토큰 budget 내로 정리

같은 클래스/파일/흐름 단위로 재배치

중요도 높은 RepoMap 노드를 우선 포함

LLM/에이전트에 넘길 ContextPackage 생성

출력

ContextPackage (prompt용 텍스트 + 구조 메타)

실제 코드 레포 구조 예시 (foundation + RepoMap 포함 버전)

semantica/
  foundation/
    parsing/
    ir/
    graph/
    chunk/
  repomap/
    builder/
    pagerank/
    summarizer/
    tree/
  index/
    lexical/
    vector/
    symbol/
    fuzzy/
    domain_meta/
    runtime/
  retriever/
    intent/
    multi_index/
    graph_runtime_expansion/
    fusion/
    context_builder/


의존성 규칙 정리

7-1. 계층 의존 방향

foundation는 누구에게도 의존하지 않는다.

repomap은 foundation만 참조한다.

index는 foundation + repomap만 참조한다.

retriever는 foundation + repomap + index만 참조하고, 반대로 내려가면 안 된다.

7-2. 이 구조의 효과

처음에는 AST/Graph 없이 foundation.parsing 일부만 쓰고
index.lexical + index.vector만으로도 MVP 가능

나중에 Graph/RepoMap/Runtime 붙여도 모듈 경계는 그대로 유지

일부 인덱스(index.vector, index.lexical 등)는 외부 서비스(별도 프로세스/클러스터)로 빼도
index.* 인터페이스만 맞추면 전체 설계는 영향 없음