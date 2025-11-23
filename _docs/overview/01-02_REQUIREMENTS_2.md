기술 축	핵심 이유
AST	구문·스코프 기반 구조 분석 및 안전한 리라이팅
IR (Intermediate Representation)
Graph	호출·의존·흐름 분석 및 영향 범위 추적
Lexical	코드 외 텍스트 포함 전체 문자열 검색
Vector	자연어 기반 의미 매핑
Symbol Index	정확한 심볼 해석(go-to-def·find-refs)
Fuzzy	파싱 실패/오타/불완전 코드 대응
Runtime Info	실제 런타임 실행 흐름 반영
Domain Metadata	코드 외부 지식 결합
Weighted Fusion	모든 신호를 하나의 순위로 결합
Chunk Hierarchy	LLM이 이해할 수 있는 단위로 재구성


순서는 “의존성 기준”으로 쓴 거고, [병렬] 표시는 동시에 돌려도 되는 부분임.

1-1. Parsing & AST

소스코드 → Tree-sitter 파싱 → 언어별 AST 생성

단위: 파일

1-2. IR (Intermediate Representation)

AST → 언어 중립 IR 노드

FunctionLike / TypeLike / Conditional / Loop / TryCatch 등

scope / FQN / role(Controller, Service, Repo 등) 메타데이터 포함

이후 모든 축(Graph, Chunk, Symbol 등)의 “공통 기반”

1-3. Graph Construction

IR 기반 정적 코드 그래프

Node: File / Module / Class / FunctionLike / Route / Service / Repo …

Edge: calls / imports / inherits / implements / route_to / uses_repo …

엔트리포인트(route, CLI, cron 등) 기준으로 구조화

1-4. Chunk Hierarchy

IR/Graph 기반으로 LLM 단위 청크 계층 생성

Leaf: 함수/메서드 단위 chunk

Parent: 클래스/모듈/파일 단위 chunk

이후 모든 인덱스(Lexical/Vector/Runtime 매핑)의 기본 단위

1-5. Static Index Family [병렬]
IR·Graph·Chunk가 나오면 아래는 병렬로 인덱싱 가능함.

Lexical Index

대상: 파일/청크 텍스트 전체

역할: substring, 에러 메시지, SQL, 주석 등 텍스트 기반 고속 검색

Vector Index

대상: Chunk Hierarchy의 leaf/parent 청크 텍스트

역할: 자연어 의미 기반 검색(“장바구니 기능 어디?”)

Symbol Index

대상: IR의 definition / reference / scope 정보

역할: go-to-def / find-refs / 구현체 목록 등 정확한 심볼 단위 검색

Fuzzy Index

대상: identifier / 토큰 n-gram

역할: 오타/깨진 코드/LLM 생성 코드 tolerant 검색

Domain Metadata Index

대상: README, ADR, OpenAPI, DB schema, config 등 코드 외 문서

IR/Graph와 매핑해서 “문서 → 코드” 링크 구축

Runtime Info Index

대상: 실제 실행 시 수집한 로그/트레이스/프로파일 정보

DI로 어떤 구현체가 주입됐는지

feature flag ON/OFF일 때의 실제 경로

핫패스/에러 발생 위치

IR/Graph node(함수, route, repo)에 attach해서
“정적 그래프 + 실제 실행 경로”를 합친 인덱스

여기까지가 Indexing Layer의 전체 구성임.
(Parsing / AST / IR / Graph / Chunk / Lexical / Vector / Symbol / Fuzzy / Domain / Runtime Info, 전부 포함)

─────────────────────
2. Retriever Layer (검색·랭킹·컨텍스트 빌드 단계)
─────────────────────

2-1. Query Routing / Intent 분석

입력 쿼리 → 어떤 축을 얼마나 쓸지 결정

예: “정의 위치” → Symbol + Graph 위주

“이 기능 어디?” → Vector + Lexical + Graph

“실제 실행 경로” → Graph + Runtime Info

2-2. Multi-Index Search (병렬 조회)

Lexical / Vector / Symbol / Fuzzy / Domain / Graph / Runtime Info
전부 병렬로 검색

각 축별로 후보 chunk / node / 문서 + score 얻기

2-3. Graph & Runtime Expansion

초기 후보에서 Graph를 따라 인접 노드 확장

route→service→repo, 호출자/피호출자, 영향 범위

Runtime Info를 오버레이

실제 실행 경로, 에러/핫패스 노드에 가중치

2-4. Weighted Fusion (최종 랭킹)

각 후보에 대해 다음 신호를 가중합

lexical_score

vector_score

symbol_score

graph_score (구조/경로/중심성)

runtime_score (실제 사용 빈도·에러 등)

fuzzy_score

domain_meta_score

하나의 최종 순위 리스트로 정렬

2-5. Context Builder

상위 N개 후보를 Chunk Hierarchy 기준으로 정리

같은 함수/클래스/파일 묶기

호출 경로/흐름 단위로 재배치

토큰 budget 안에 들어오게 자르기

LLM/에이전트에 넘길 최종 context 패키지 생성