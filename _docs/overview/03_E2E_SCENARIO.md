아래 케이스들은 실제 동작이 잘되는지 수행하기 위한 시나리오.


1. 우선순위 1 (엔진 기반 필수)
1-1. 정의 위치 / 코드 블럭 찾기 ([1])

대표 질문

Q1: HybridRetriever 클래스의 retrieve 메서드가 정의된 파일이랑 위치 알려줘.

Q2: create_bootstrap 함수 정의된 소스 코드 블럭 보여줘.

1-2. enum / 인터페이스 정의 찾기 ([2])

대표 질문

Q1: EmbeddingModel enum 이 어디에서 선언돼 있는지 파일 경로랑 코드 보여줘.

Q2: GraphStorePort 인터페이스 정의된 곳 찾아줘.

1-3. 라우트 → 핸들러 매핑 ([7], [61])

대표 질문

Q1: router.post('/hybrid/search') 요청을 처리하는 핸들러 함수 구현부 위치 알려줘.

Q2: POST /hybrid/search 라우트가 어느 파일에서 어떤 함수로 매핑돼 있는지 보여줘.

Q3: GET /hybrid/graph 라우트가 실제로 연결된 핸들러 함수(파일, 함수명)를 알려줘.

Q4: POST /indexing/rebuild 라우트 정의와 해당 요청을 처리하는 핸들러 코드를 함께 보여줘.

1-4. 인터페이스 / 포트 구현체 목록 ([8], [25])

대표 질문

Q1: GraphStorePort 인터페이스를 구현한 클래스들 전체 목록이랑 파일 경로 알려줘.

Q2: EmbeddingStorePort 구현체가 몇 개 있는지, 각각 어떤 이름인지 보여줘.

Q3: EmbeddingModelProvider 인터페이스 구현체 이름과 파일 경로 전부 알려줘.

1-5. import / export 구조 분석 ([17])

대표 질문

Q1: HybridRetriever 를 export 하는 파일과, 거기서 어떤 이름으로 export 하는지 알려줘.

Q2: @/graph/index 경로로 import 될 때 실제로 어떤 파일/심볼들이 export 되는지 정리해줘.

1-6. 특정 함수/메서드 호출하는 모든 곳 ([21])

대표 질문

Q1: PgVectorSemanticSearch.search 를 호출하는 모든 코드를 호출부 파일 경로와 함께 보여줘.

Q2: IndexingPipeline.run 메서드를 사용하는 호출 지점 전체 목록 만들어줘.

1-7. 특정 클래스 / 타입 사용하는 코드 ([22])

대표 질문

Q1: HybridRetriever 인스턴스를 생성해서 쓰는 코드 위치 전체 알려줘.

Q2: PostgresGraphStore 타입을 사용하는 곳(파라미터, 리턴타입, 필드 등) 모두 찾아줘.

1-8. 리팩토링 영향 범위 / rename / 시그니처 변경 ([27], [28], [29])

대표 질문

Q1: IndexingPipeline.run 메서드 시그니처를 바꾸면 영향을 받는 호출부가 어디인지 코드 기준으로 정리해줘.

Q2: HybridRetriever.retrieve 이름을 변경하면 같이 수정해야 하는 코드 위치 목록 만들어줘.

Q3: GraphDependency 클래스를 DependencyGraph 로 rename 할 때 수정해야 하는 import/사용처 전부 보여줘.

Q4: route_hybrid_search 함수 이름을 변경하면 어떤 파일에서 컴파일 에러가 날지 알려줘.

Q5: retrieve(query, limit) 함수에 새로운 파라미터 options 를 추가하면 에러나는 호출부가 어디인지 찾아줘.

Q6: GraphStore.get_edges 리턴 타입을 바꾸면 타입 에러가 나는 코드들 정리해줘.

1-9. IndexingPipeline → Chunker 호출 경로 / 인덱싱 API call chain ([41], [46])

대표 질문

Q1: IndexingPipeline 에서 Chunker 가 실제로 호출되기까지 함수 호출 경로를 순서대로 그려줘.

Q2: 인덱싱 시작 API 기준으로 Chunker.execute 가 호출될 때까지 call chain 을 파일/함수 단위로 나열해줘.

Q3: /api/indexing/start 엔드포인트 호출 시 내부에서 어떤 함수들이 어떤 순서로 실행되는지 call chain 을 만들어줘.

Q4: 인덱싱 시작 API가 트리거되면 어떤 파이프라인 단계들이 실행되는지 코드 기준으로 보여줘.

1-10. retriever → search → reranker 흐름 / hybrid scoring ([42], [45], [48])

대표 질문

Q1: 검색 요청이 들어왔을 때 HybridRetriever → vector search → reranker 까지 호출 흐름을 순서대로 설명해줘.

Q2: retrieve 메서드에서 최종 결과가 re-rank 되기까지 거치는 함수들을 call graph 형태로 보여줘.

Q3: GET /hybrid/search 요청이 들어왔을 때 handler → service → retriever → GraphStore 까지 전체 호출 경로를 그려줘.

Q4: 검색 API 가 어떤 GraphStore 메서드를 마지막에 호출하는지, 중간 계층(service, usecase) 포함해서 설명해줘.

Q5: Hybrid scoring 함수를 호출하는 곳을 전부 찾고, 어떤 검색 경로에서 쓰이는지 정리해줘.

Q6: hybrid_fusion_score 계산 로직이 어느 함수에서 호출되는지 call graph 형태로 보여줘.

1-11. store 초기화 / DB 연결 / GraphStore wiring ([47], [83], [56 일부])

대표 질문

Q1: PostgresGraphStore 인스턴스가 어디에서 생성/초기화되는지 코드 흐름을 정리해줘.

Q2: GraphStore 가 앱 부팅 시점에 어떻게 wiring 되는지 (DI/팩토리/부트스트랩) 순서대로 알려줘.

Q3: PostgreSQL 연결이 어디에서 생성되고, 어떤 레이어(Repository/GraphStore 등)에서 이 커넥션을 사용하는지 흐름을 설명해줘.

Q4: GraphStore 관련 DB 세션/트랜잭션이 시작되고 종료되는 경계를 코드 기준으로 보여줘.

Q5: 벡터 DB gRPC 클라이언트가 어디에서 생성되고, 어떤 서비스/함수가 이 클라이언트를 사용해서 호출하는지 전체 흐름을 정리해줘.

Q6: HybridRetriever 가 gRPC 를 통해 외부 검색 엔진을 호출하는 경로가 있다면 call graph 로 그려줘.

1-12. error 핸들링 전체 흐름 / error code 매핑 ([60], [38], [68])

대표 질문

Q1: 인덱싱 API에서 예외가 발생했을 때, exception → error mapper → API 응답까지 에러 핸들링 흐름을 코드 기준으로 설명해줘.

Q2: 검색 중 에러가 발생했을 때 어떤 공통 error handler 를 거쳐서 HTTP 응답이 만들어지는지 호출 경로를 보여줘.

Q3: IndexingError 예외를 발생시키는 코드와 이 예외를 처리하는 catch/handler 를 매핑해서 정리해줘.

Q4: SearchTimeoutError 를 던지는 함수와, 이 예외를 HTTP 504로 변환하는 코드 흐름을 보여줘.

Q5: 내부 에러 코드(err_*)가 어떻게 HTTP status code / 응답 body 로 변환되는지 mapping 로직을 정리해줘.

Q6: 인덱싱 에러와 검색 에러가 각각 어떤 응답 포맷(JSON 스키마)으로 매핑되는지 코드를 기반으로 설명해줘.

1-13. POST/GET API 목록 ([62])

대표 질문

Q1: 이 코드베이스에서 정의된 GET/POST HTTP 엔드포인트 목록을 메서드/URL/핸들러 함수 기준으로 테이블 형태로 만들어줘.

Q2: /hybrid/* 패턴에 매칭되는 모든 API 라우트와 HTTP 메서드를 정리해줘.

1-14. DTO 정의 위치 ([63])

대표 질문

Q1: IndexingRequest / IndexingResponse DTO 가 각각 어디에서 정의돼 있는지 파일 경로와 코드 보여줘.

Q2: 검색 응답에 쓰이는 SearchResultItem DTO 정의를 찾고 싶어. 위치랑 구조를 보여줘.

1-15. DTO 사용처 / Response 스키마 변화 영향 ([64], [65])

대표 질문

Q1: IndexingRequest DTO 를 사용하는 핸들러/서비스/테스트 코드 위치를 전부 알려줘.

Q2: SearchResultItem 이 리턴 타입/파라미터로 등장하는 함수 목록을 파일 경로와 함께 정리해줘.

Q3: SearchResponse DTO 에 필드 하나를 추가하면 영향을 받는 API 응답 생성 코드들을 모두 찾아줘.

Q4: IndexingStatusResponse 구조를 변경하면 어떤 프런트엔드/클라이언트 코드에서 문제가 생길지 코드 기준으로 정리해줘.

1-16. config override flow / env var ([82], [81])

대표 질문

Q1: 인덱싱 관련 설정(INDEX_BATCH_SIZE)이 기본값 → 환경별 config → runtime override 까지 어떤 순서로 덮어씌워지는지 코드 흐름을 설명해줘.

Q2: config.yml 에서 읽은 설정이 실제로 어디에서 override 되는지(환경변수, CLI 옵션 등) 코드 기준으로 정리해줘.

Q3: SEMANTICA_INDEX_DB_URL 환경 변수를 읽는 코드 위치를 모두 찾아줘.

Q4: 환경 변수로 제어되는 feature flag 들(예: SEMANTICA_EXPERIMENTAL_*)을 어디에서 사용하는지 정리해줘.

1-17. 서비스 간 호출 관계 ([90])

대표 질문

Q1: indexing-service 와 search-service 가 서로 어떤 HTTP/gRPC 호출을 주고받는지, 서비스 간 호출 그래프를 만들어줘.

Q2: 이 코드베이스에서 다른 마이크로서비스로 outbound 호출하는 코드들(예: auth-service, feature-service)을 정리해줘.

1-18. tracing / logging flow ([92])

대표 질문

Q1: 검색 요청에 대해 trace ID 가 어떻게 생성되고, 어떤 레이어(API/서비스/스토어)까지 전달되는지 코드 흐름을 설명해줘.

Q2: 인덱싱 파이프라인에서 로그가 어떤 포맷으로 찍히고, 공통 로깅 유틸을 어디서 사용하는지 정리해줘.

1-19. index rebuild 트리거 / 배치 ([51], [52], [100])

대표 질문

Q1: 인덱스 리빌드 배치 잡이 어디서 스케줄링되고, 실행 시 어떤 함수들을 호출하는지 흐름을 정리해줘.

Q2: 정기적으로 돌아가는 indexing cleanup job 의 실행 엔트리포인트와 내부 로직을 보여줘.

Q3: cron 표현식 '0 3 * * *' 로 등록된 작업이 어떤 코드를 실행하는지 찾아줘.

Q4: 스케줄러 설정 파일/코드 기준으로, indexing 관련 스케줄 잡 목록과 해당 핸들러를 보여줘.

Q5: 전체 인덱스를 재생성(rebuild)하는 트리거가 어디에 정의돼 있고, 어떤 경로로 실제 인덱싱 파이프라인을 호출하는지 보여줘.

Q6: CLI/배치/관리자 API 중 어떤 경로로 index rebuild 가 시작될 수 있는지, 각각의 엔트리포인트를 코드 기준으로 정리해줘.

1-20. 보안 / ACL 필터링 테스트 ([101])

대표 질문

Q1: 내 토큰(security context) 기준으로 접근 불가능한 confidential 태그가 붙은 파일을 검색했을 때, 결과 목록에서 해당 청크들이 필터링되는지 확인해줘.

Q2: /api/search 엔드포인트에서 security_level=SECRET 필터가 적용될 때, 검색 서비스가 GraphStorePort를 호출하기 전에 권한 검증을 하는지 호출 흐름을 보여줘.

2. 우선순위 2 (실무 필수)
2-1. 인터페이스 구현체 찾기 (우선순위1 1-4와 사실상 같은데, 실무 필수 관점) ([25])

대표 질문

Q1: GraphStorePort 를 구현한 adapter 클래스들을 모두 찾아서 목록으로 보여줘.

Q2: EmbeddingModelProvider 인터페이스 구현체 이름과 파일 경로 전부 알려줘.

2-2. deprecated API / 심볼 사용처 ([32], [72])

대표 질문

Q1: deprecated 로 표시된 hybrid_search_v1 함수를 아직 호출하는 코드 위치를 모두 찾아줘.

Q2: @deprecated 주석이 붙어 있는 메서드 사용처를 전부 나열해줘.

Q3: deprecated 로 표시된 /v1/ 검색 API 를 아직 호출하는 클라이언트/테스트 코드를 모두 찾아줘.

Q4: deprecated 된 IndexingPipelineV1 클래스를 new 버전으로 교체하지 않은 사용처 목록을 만들어줘.

2-3. unused 변수/함수 ([33])

대표 질문

Q1: HybridRetriever 모듈에서 선언만 되어 있고 사용되지 않는 함수/변수 목록을 보여줘.

Q2: indexing 관련 코드 중에서 심볼 인덱스에만 있고 호출되지 않는 private 함수들을 찾고 싶어.

2-4. side effect 발생 코드 ([34])

대표 질문

Q1: 검색 호출 시 전역 상태나 캐시를 수정하는 side effect 있는 함수들을 찾아줘.

Q2: PostgresGraphStore 가 호출될 때 DB 가 아닌 다른 리소스를 건드리는 코드(side effect) 있으면 알려줘.

2-5. import cycle 감지 ([36])

대표 질문

Q1: Python 모듈들 사이에 순환 import 가 있는지, 있다면 어떤 모듈 경로들이 cycle을 이루는지 보여줘.

Q2: TS 패키지 간에 dependency cycle 이 생기는 부분이 있는지 검사해줘.

2-6. exception throw/handle mapping (구체 예외) ([38])

대표 질문

Q1: IndexingError 예외를 발생시키는 코드와 이 예외를 처리하는 catch/handler 를 매핑해서 정리해줘.

Q2: SearchTimeoutError 를 던지는 함수와, 이 예외를 HTTP 504로 변환하는 코드 흐름을 보여줘.

2-7. error code 사용처 ([40])

대표 질문

Q1: err_common 코드가 어디서 생성/사용되는지, API 응답/로그까지 포함해서 정리해줘.

Q2: 검색 관련 에러 코드(err_search_*)를 사용하는 핸들러/서비스 위치 모두 보여줘.

2-8. 파싱 파이프라인 전체 흐름 ([43])

대표 질문

Q1: 코드 파싱 파이프라인이 어떻게 시작돼서 AST 생성 → 심볼 추출 → IR 빌드까지 이어지는지 전체 흐름을 함수 호출 순서로 설명해줘.

Q2: 파일 스캔 이후 파싱 pipeline 단계들을 단계별로 어떤 모듈이 처리하는지 call graph 로 보여줘.

2-9. caching layer 흐름 ([49])

대표 질문

Q1: 코드 파싱 결과/임베딩/그래프 등에 대해 각각 어떤 캐시 레이어가 있고, 언제 set/get/clear 되는지 코드 기준으로 정리해줘.

Q2: 검색 결과 캐시가 어디에서 조회되고, miss 시 어떤 경로로 실제 검색이 실행되는지 흐름을 설명해줘.

2-10. event-driven 흐름 ([50])

대표 질문

Q1: repo_indexed 이벤트가 발행되는 코드와 이 이벤트를 구독해서 처리하는 핸들러들을 모두 보여줘.

Q2: indexing_failed 이벤트 흐름(발행 → 소비자) 전체를 call/subscribe 관점에서 설명해줘.

2-11. 배치 job / scheduler 흐름 ([51], [52])

대표 질문

Q1: 인덱스 리빌드 배치 잡이 어디서 스케줄링되고, 실행 시 어떤 함수들을 호출하는지 흐름을 정리해줘.

Q2: 정기적으로 돌아가는 indexing cleanup job 의 실행 엔트리포인트와 내부 로직을 보여줘.

Q3: cron 표현식 '0 3 * * *' 로 등록된 작업이 어떤 코드를 실행하는지 찾아줘.

Q4: 스케줄러 설정 파일/코드 기준으로, indexing 관련 스케줄 잡 목록과 해당 핸들러를 보여줘.

2-12. CLI → internal module 호출 ([53])

대표 질문

Q1: semantica index CLI 명령이 실행됐을 때, 내부적으로 어떤 Python/TS 모듈과 함수들을 호출하는지 순서대로 설명해줘.

Q2: serena init 명령을 실행하면 어떤 코드 경로를 통해 설정 파일이 생성되는지 call chain 을 보여줘.

2-13. gRPC / retry / backoff ([56], [57])

대표 질문

Q1: 벡터 DB gRPC 클라이언트가 어디에서 생성되고, 어떤 서비스/함수가 이 클라이언트를 사용해서 호출하는지 전체 흐름을 정리해줘.

Q2: HybridRetriever 가 gRPC 를 통해 외부 검색 엔진을 호출하는 경로가 있다면 call graph 로 그려줘.

Q3: 검색이나 인덱싱 중 외부 서비스 호출 실패 시 retry/backoff 로직이 어떻게 동작하는지 함수 호출 흐름을 알려줘.

Q4: vector DB 호출에 대해 몇 번까지 재시도하고, backoff 전략은 어떤 함수에서 정의돼 있는지 코드 기준으로 설명해줘.

2-14. DTO / 버전 / 멀티 버전 API ([63], [64], [65], [73])

대표 질문

Q1: IndexingRequest / IndexingResponse DTO 가 각각 어디에서 정의돼 있는지 파일 경로와 코드 보여줘.

Q2: IndexingRequest DTO 를 사용하는 핸들러/서비스/테스트 코드 위치를 전부 알려줘.

Q3: 검색 응답에 쓰이는 SearchResultItem DTO 정의를 찾고 싶어. 위치랑 구조를 보여줘.

Q4: SearchResultItem 이 리턴 타입/파라미터로 등장하는 함수 목록을 파일 경로와 함께 정리해줘.

Q5: SearchResponse DTO 에 필드 하나를 추가하면 영향을 받는 API 응답 생성 코드들을 모두 찾아줘.

Q6: IndexingStatusResponse 구조를 변경하면 어떤 프런트엔드/클라이언트 코드에서 문제가 생길지 코드 기준으로 정리해줘.

Q7: /v1/search 와 /v2/search 가 공존할 때, 어떤 router/handler 구조로 버전을 분기하는지 코드 흐름을 설명해줘.

Q8: 검색 API 여러 버전 간에서 공통 로직과 버전별 분기 로직이 어떻게 나뉘어 있는지 call graph 로 보여줘.

2-15. deprecated API 사용 탐지 ([32], [72])

대표 질문

Q1: deprecated 로 표시된 hybrid_search_v1 함수를 아직 호출하는 코드 위치를 모두 찾아줘.

Q2: @deprecated 주석이 붙어 있는 메서드 사용처를 전부 나열해줘.

Q3: deprecated 로 표시된 /v1/ 검색 API 를 아직 호출하는 클라이언트/테스트 코드를 모두 찾아줘.

Q4: deprecated 된 IndexingPipelineV1 클래스를 new 버전으로 교체하지 않은 사용처 목록을 만들어줘.

2-16. env var 사용처 ([81])

대표 질문

Q1: SEMANTICA_INDEX_DB_URL 환경 변수를 읽는 코드 위치를 모두 찾아줘.

Q2: 환경 변수로 제어되는 feature flag 들(예: SEMANTICA_EXPERIMENTAL_*)을 어디에서 사용하는지 정리해줘.

2-17. 보안 / 입력 검증 누락 패턴 (TS-151, TS-152와 연결)

대표 질문

Q1: /indexing/* API 중에서 인증/인가 미들웨어를 거치지 않고 직접 핸들러가 호출되는 엔드포인트가 있는지 찾아줘.

Q2: admin 전용 flag(SEMANTICA_ADMIN_ONLY)를 검사하지 않고 접근 가능한 관리용 API가 있는지 검사해줘.

Q3: 검색/인덱싱 API에서 body/query 파라미터를 validation 없이 바로 DB/외부 호출에 사용하는 코드가 있는지 찾아줘.

2-18. 크로스-스토리지 무결성 / 멀티 모델 ([104], [105])

대표 질문

Q1: Commit:a1b2c3d에 의해 LeafChunk:X가 삭제된 후, Qdrant와 Kùzu(GraphStore) 양쪽 DB에서 해당 청크가 성공적으로 제거되었는지 확인하는 쿼리를 보여줘.

Q2: 인덱싱 파이프라인에서 CanonicalLeafChunk의 node_id가 Qdrant Point ID 및 Kùzu Node Key로 일치하여 매핑되는 로직을 보여줘.

Q3: EmbeddingModelProvider를 OpenAI v3에서 OpenAI v3-large로 교체했을 때, 기존 벡터와 신규 벡터의 동시 검색 및 버전 분기 처리 로직이 어디에 있는지 설명해줘.

Q4: Zoekt가 응답 불가 상태일 때, HybridRetriever가 Lexical 단계를 건너뛰고 Semantic(Qdrant) 검색만으로 Fallback 동작하는 로직 흐름을 보여줘.

2-19. 디버깅 / 로그 기반 역추적 (추가 TS-101~TS-103)

대표 질문

Q1: SearchTimeoutError: request id=abc123 took longer than 10s 로그가 찍히는 코드 위치와, 이 에러를 던지는 call chain 을 알려줘.

Q2: "failed to fetch hybrid score"라는 로그 메시지가 등장하는 함수와, 그 함수를 호출하는 상위 API 핸들러를 추적해줘.

Q3: “hybrid search에서 rerank 이전 결과가 그대로 내려오는 버그”가 발생할 수 있는 코드 경로를 찾아줘. (feature flag / 조건 분기 포함)

Q4: “/hybrid/search?limit=0일 때 500 에러 나는 버그”와 관련 있을 만한 분기/검증 로직을 찾고 설명해줘.

2-20. 기타 확장 패턴 (테스트, 리팩토링, 성능, 타입 등 TS-111 이후)

대표 질문 예시만 대표로 뽑으면

Q1: HybridRetriever.retrieve에 대한 단위 테스트 / 통합 테스트가 어디 있는지, 테스트 이름과 파일 경로를 정리해줘.

Q2: /api/indexing/start 플로우를 실제로 호출하는 테스트 케이스가 있는지, 있다면 어떤 fixture/환경으로 실행되는지 설명해줘.

Q3: GraphStore 관련 변경을 했을 때, 영향받을 수 있는 테스트 스위트 목록과, 커버되지 않는 영역(테스트 없는 경로)을 구분해서 보여줘.

Q4: indexing-service 모듈이 search-service 내부 인프라 코드(예: DB adapter)에 직접 접근하는 경우가 있는지 찾아줘.

Q5: semantica.codegraph.graph 패키지를 semantica.core.graph로 이동하면 import 경로를 어떻게 일괄 수정해야 하는지, 영향 범위를 정리해줘.

Q6: GraphStore.get_edges 리턴 타입과 실제 사용하는 쪽 타입 선언이 불일치할 수 있는 곳(캐스팅, any/unknown 사용 등)을 찾아서 설명해줘.

Q7: 검색 요청 처리 중 GraphStore.get_edges 를 루프 안에서 여러 번 호출하는 코드가 있는지 찾아줘. 잠재적인 N+1 패턴 예시를 보여줘.

Q8: 검색 결과 캐시를 set 해놓고도 실제로 조회(get)하지 않는 코드 경로가 있는지 찾아줘.

Q9: .github/workflows/indexing.yml에서 사용하는 스크립트/CLI 명령이 내부적으로 어떤 Python/TS 모듈을 호출하는지 call chain을 설명해줘.

Q10: semantica-indexer 컨테이너의 ENTRYPOINT 가 코드베이스의 어느 모듈/함수에 매핑되는지, 그리고 readinessProbe 가 어떤 HTTP 엔드포인트를 체크하는지 알려줘.

Q11: semantica.codegraph.graph_dependency 모듈이 하는 일과 주요 public API를, 코드 구조를 기반으로 요약해서 설명해줘.

Q12: “하이브리드 검색” 기능을 이해하려면 어떤 파일/심볼을 어떤 순서로 읽으면 좋은지 entry → core → infra 순서로 추천해줘.

Q13: /v1/search → /v2/search 로 마이그레이션 중인데, 아직 /v1 을 호출하는 클라이언트/테스트 코드가 남아 있는지 모두 찾아줘.

Q14: SEMANTICA_EXPERIMENTAL_HYBRID feature flag 가 true/false 일 때 각각 어떤 코드 경로가 실행되는지 call graph 를 나눠서 보여줘.