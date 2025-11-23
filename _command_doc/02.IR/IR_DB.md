Kuzu  -> 코드그래프 전체 저장 (노드/엣지/타입/시그니처/CFG)
Postgres → 운영 데이터 + 메타데이터 저장 -> Postgresql 
Qdrant → 벡터 기반 의미 검색


개요

1-1. 목적

Semantica IR v4 JSON 스키마를 Kuzu Graph Database 스키마로 매핑하는 최종 설계임

목표는 다음과 같음

Node / Edge / Type / Signature / CFG 레이어를 명확히 분리

멀티 레포 / 멀티 스냅샷 / 워크스페이스까지 하나의 스키마로 커버

Node 스키마는 한 번 정의하면 바꾸지 않고, 관계/인덱스/캐시만 확장 가능하게 설계

1-2. 핵심 결정사항 요약

모든 코드 구조/심볼은 IRNode 하나의 NODE TABLE로 관리함

모든 관계(호출, 포함, 상속 등)는 IREdge REL TABLE로 관리하고, 필요 시 kind별 전용 REL TABLE로 분리하는 2단계 전략 사용

타입(TypeEntity), 시그니처(SignatureEntity), CFG(ControlFlowGraph)는 각각 독립적인 NODE/REL로 관리

repo_id + snapshot_id를 모든 NODE에 포함시켜, 단일 스키마로 다중 레포/스냅샷을 처리함

cross-snapshot 분석을 위해 stable_symbol_id + content_hash 조합 사용

전체 구조

2-1. 논리 레이어

IRDocument(JSON) → Kuzu 스키마 매핑은 다음과 같음

Node 레이어

IR v4 JSON: nodes[]

Kuzu: NODE TABLE IRNode

Edge 레이어

IR v4 JSON: edges[]

Kuzu: REL TABLE IREdge (추후 Contains / Calls 등 전용 REL 추가 가능)

Type 레이어

IR v4 JSON: types[] (TypeEntity)

Kuzu: NODE TABLE IRType, REL TABLE ResolvesTo (선택)

Signature 레이어

IR v4 JSON: signatures[] (SignatureEntity)

Kuzu: NODE TABLE IRSignature

Control Flow 레이어

IR v4 JSON: control_flow_graphs[] (ControlFlowGraph)

Kuzu: NODE TABLE IRCFGBlock, REL TABLE CFGEdge

선택: CFG_READS / CFG_WRITES REL으로 DFG 기본 관계까지 표현 가능

2-2. 운영 레이어

IRStore(인메모리) + Kuzu(DB) + JSON 스냅샷의 관계는 다음과 같음

JSON 스냅샷: 불변 기록, 재현 가능한 스냅샷 단위

Kuzu: 모든 스냅샷의 통합 그래프 저장소 (repo_id + snapshot_id로 필터링)

IRStore: LLM/툴이 사용하는 “현재 작업 기준” 인메모리 인덱스/캐시 레이어

NODE TABLE 설계

3-1. IRNode

IR v4의 Node 정의를 Kuzu NODE TABLE로 매핑한 결과임.

CREATE NODE TABLE IRNode (
  id               STRING,   -- Node ID (예: method:semantica:src/...:HybridRetriever.plan)
  repo_id          STRING,
  snapshot_id      STRING,

  kind             STRING,   -- File / Module / Class / Interface / Function / Method / ...
  name             STRING,   -- NULL 허용
  fqn              STRING,   -- Fully Qualified Name
  file_path        STRING,   -- repo 루트 기준
  language         STRING,   -- python / typescript / javascript / ...
  module_path      STRING,   -- NULL 가능

  -- span
  span_start_line  INT64,
  span_start_col   INT64,
  span_end_line    INT64,
  span_end_col     INT64,

  -- body_span (없으면 -1 또는 NULL 사용)
  body_start_line  INT64,
  body_start_col   INT64,
  body_end_line    INT64,
  body_end_col     INT64,

  content_hash     STRING,   -- Node 코드 텍스트 hash (sha256:...)
  stable_symbol_id STRING,   -- fqn + signature 기반 논리 ID (파일 이동에도 안정)

  docstring        STRING,
  role             STRING,
  is_test_file     BOOLEAN,

  signature_id     STRING,   -- IRSignature.id 참조 (없으면 NULL)
  declared_type_id STRING,   -- IRType.id (Variable/Field 등만 의미)

  PRIMARY KEY (id)
);


핵심 포인트

Node는 “언어 불문 공통·불변 구조만” 포함함

parent/children, 호출, 참조 등 모든 관계는 REL TABLE에서 표현함

stable_symbol_id + content_hash로 snapshot 간 심볼/코드 추적을 지원함

3-2. IRType (TypeEntity)

CREATE NODE TABLE IRType (
  id                STRING,      -- type:RetrievalPlan, type:List[Candidate]
  repo_id           STRING,
  snapshot_id       STRING,

  raw               STRING,      -- 코드 상 타입 표현
  resolved_target   STRING,      -- IRNode.id (Class/Interface/TypeAlias) 또는 NULL

  flavor            STRING,      -- primitive / builtin / user / external / typevar / generic
  is_nullable       BOOLEAN,
  generic_param_ids STRING[],    -- TypeEntity.id 배열

  PRIMARY KEY (id)
);


타입 해석 Phase 1에서는 raw / flavor / is_nullable 정도만 채워도 동작함

해석이 성공한 경우에만 resolved_target, generic_param_ids를 채우면 됨

3-3. IRSignature (SignatureEntity)

CREATE NODE TABLE IRSignature (
  id                  STRING,      -- sig:HybridRetriever.plan(Query,int)->RetrievalPlan
  repo_id             STRING,
  snapshot_id         STRING,

  owner_node_id       STRING,      -- IRNode.id (Function/Method)
  name                STRING,
  raw                 STRING,      -- 시그니처 문자열

  parameter_type_ids  STRING[],    -- TypeEntity.id 배열
  return_type_id      STRING,      -- TypeEntity.id 또는 NULL

  visibility          STRING,      -- public / protected / private / internal / NULL
  is_async            BOOLEAN,
  is_static           BOOLEAN,
  throws_type_ids     STRING[],    -- TypeEntity.id 배열

  signature_hash      STRING,      -- 시그니처 구조 hash

  PRIMARY KEY (id)
);


IRNode.signature_id가 이 테이블을 참조함

signature_hash로 인터페이스 변경 여부를 빠르게 감지 가능함

3-4. IRCFGBlock (ControlFlowBlock)

CREATE NODE TABLE IRCFGBlock (
  id                   STRING,      -- cfg:HybridRetriever.plan:block:1
  repo_id              STRING,
  snapshot_id          STRING,

  function_node_id     STRING,      -- IRNode.id (Function/Method)
  kind                 STRING,      -- Entry / Exit / Block / Condition / LoopHeader / Try / Catch / Finally

  span_start_line      INT64,
  span_start_col       INT64,
  span_end_line        INT64,
  span_end_col         INT64,

  defined_variable_ids STRING[],    -- IRNode.id 배열 (Variable/Field)
  used_variable_ids    STRING[],    -- IRNode.id 배열

  PRIMARY KEY (id)
);


ControlFlowGraph는 function_node_id + kind=Entry/Exit로 묶어서 논리적으로 정의함

DFG(def/use)는 배열 기반으로 표현하되, 필요 시 CFG_READS / CFG_WRITES REL로 확장 가능함

REL TABLE 설계

4-1. IREdge (일반 IR 관계)

CREATE REL TABLE IREdge (
  FROM IRNode TO IRNode,

  id              STRING,  -- edge:call:plan→_search_vector@1
  kind            STRING,  -- CONTAINS / CALLS / REFERENCES / IMPORTS / INHERITS / IMPLEMENTS / ...

  span_start_line INT64,
  span_start_col  INT64,
  span_end_line   INT64,
  span_end_col    INT64,

  attrs_json      STRING   -- 관계별 메타 (JSON 문자열)
);


Edge.kind는 IR v4 JSON의 enum과 동일하게 유지함

attrs_json은 import_type, argument_count, syntax 등 kind별 확장 메타를 자유롭게 담는 용도임

4-2. CFGEdge (제어 흐름 관계)

CREATE REL TABLE CFGEdge (
  FROM IRCFGBlock TO IRCFGBlock,
  kind STRING      -- NORMAL / TRUE_BRANCH / FALSE_BRANCH / EXCEPTION / LOOP_BACK
);


ControlFlowGraph의 블록 간 제어 흐름을 표현함

4-3. 선택적/추가 REL: Contains, Calls, ResolvesTo, CFG_READS/WRITES

향후 성능/가독성을 위해 다음과 같이 전용 REL TABLE을 추가할 수 있음.
논리 스키마는 IREdge 하나로 충분하고, 아래는 “물리 최적화 / 쿼리 편의용”임.

Contains (구조 계층 전용)

CREATE REL TABLE Contains (
  FROM IRNode TO IRNode,
  id   STRING,
  -- 필요시 span/attrs 추가 가능
);


Calls (호출 그래프 전용)

CREATE REL TABLE Calls (
  FROM IRNode TO IRNode,
  id              STRING,
  span_start_line INT64,
  span_end_line   INT64,
  attrs_json      STRING
);


ResolvesTo (타입 해석 관계)

CREATE REL TABLE ResolvesTo (
  FROM IRType TO IRNode
);


CFG_READS / CFG_WRITES (DFG view)

CREATE REL TABLE CFG_READS (
  FROM IRCFGBlock TO IRNode
);

CREATE REL TABLE CFG_WRITES (
  FROM IRCFGBlock TO IRNode
);


IR → Kuzu 적재 시 아래와 같이 동작함

edges(kind=CONTAINS/CALLS)를 IREdge에 기록하면서, Contains/Calls에도 중복 생성하거나, IREdge를 “나머지 kind용”으로 축소하는 전략 선택 가능

IRType.resolved_target != null 인 경우 ResolvesTo REL 생성

IRCFGBlock.defined_variable_ids / used_variable_ids 배열을 순회해 CFG_WRITES / CFG_READS REL 생성

스냅샷 / 워크스페이스 / IRStore 전략

5-1. 스냅샷 관리 (repo_id + snapshot_id)

모든 NODE TABLE에 repo_id, snapshot_id를 포함했기 때문에,

“하나의 Kuzu 인스턴스”에 여러 레포/스냅샷을 함께 보관할 수 있음

특정 시점의 코드 그래프 조회 예

MATCH (n:IRNode)
WHERE n.repo_id = 'semantica-codegraph'
  AND n.snapshot_id = 'commit:abc123'
RETURN n
LIMIT 100;


snapshot_id 사용 약속 예

commit 기반: commit:<sha>

브랜치 기반: branch:main@<sha>

워크스페이스(로컬 dirty): workspace:<user>@local-<hash>

5-2. IR 변경 시나리오 요약

최초 인덱싱

Tree-sitter → AST

AST → IR(JSON: Node/Edge/Type/Signature/CFG)

JSON → Kuzu(BULK LOAD) + IRStore(인메모리 인덱스)

이 시점의 snapshot_id를 기준으로 “기준 스냅샷” 형성

파일 변경 (실시간 워크스페이스)

변경 파일만 AST → IR 재생성

기존 IR과 diff 계산 (추가/수정/삭제 Node/Edge/Type)

IRStore(메모리) 먼저 업데이트

Kuzu는 비동기 upsert

snapshot_id는 workspace:...로 유지, commit 시점에 다시 commit 기반 snapshot 생성

git checkout/pull/rebase

git HEAD 변경 감지

변경 파일만 diff 기반 재인덱싱

새로운 snapshot_id 생성 (commit 기반)

IRStore를 새 snapshot 기준으로 교체

Kuzu에도 새 snapshot 노드/엣지 upsert

전체 재인덱싱

CI/CD 혹은 main 정식 빌드 시 repo 전체 재인덱싱

새로운 snapshot_id = branch:main@{commit}

이 snapshot을 “공식 스냅샷”으로 취급

5-3. IRStore 계층화

NodeIndex (항상 메모리)

fqn → node_id

file_path → node_ids

kind 기반 목록 등 가벼운 메타 인덱스

GraphIndex (핵심 관계 캐시)

source_id → CALLS/CONTAINS adjacency 일부 캐시

LLM/툴이 자주 쓰는 패턴만 우선 메모리

DetailStore (lazy)

Node/Edge/Type/CFGBlock 풀 데이터는 LRU 캐시

캐시에 없으면 Kuzu에서 로딩 후 메모리 저장

이 구조로 10K+ 파일, 수백만 Node/Edge 규모에서도 Node 스키마 변경 없이 확장 가능함.

인덱스 / 최적화 전략

6-1. 기본 인덱스

IRNode

PRIMARY KEY(id)

index(repo_id, snapshot_id)

index(fqn)

index(file_path)

IREdge

index(kind)

index(source_id, kind)

index(target_id, kind)

필요 시 snapshot_id를 Edge에 중복 보관하고 index(snapshot_id, kind) 추가 가능

6-2. 성능 병목 대응

Edge 폭발 시

가장 빈번한 CONTAINS / CALLS를 전용 REL TABLE로 분리해 스캔 비용 최소화

나머지 kind는 IREdge에 유지

메모리 한계 시

Hot/Cold 분리: 최근 파일/최근 접근 Node/Edge만 메모리 캐시에 유지

LRU eviction으로 IRStore 크기 제한

결론

IR v4 JSON 스키마를 Kuzu로 옮기는 설계는

Node/Edge/Type/Signature/CFG의 역할을 분리하고

repo_id + snapshot_id로 멀티 레포/스냅샷을 단일 스키마로 처리하며

Node 스키마는 불변, 관계/인덱스/캐시만 점진적으로 확장 가능한 구조임

추가로 제안된 Contains / Calls / ResolvesTo / CFG_READS / CFG_WRITES REL은

v1에서는 없어도 되지만,

v2 이후 성능 및 분석 요구에 맞춰 “스키마 변경 없이” 도입 가능한 옵션임