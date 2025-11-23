# Semantica Codegraph v4 구현 요구사항 (최종 버전)

## 1. 상위 목표 및 범위

### 1-1. 최종 목표

1. LLM이 레포지토리를 **개발자 수준으로 이해·탐색·수정·생성**할 수 있는 코드 RAG 엔진 구현
2. Cursor / Claude Code 수준 시나리오를 커버
    - 우선순위 1·2 시나리오(1~100)
    - 확장 시나리오(디버깅, 테스트, 성능, 보안, 인프라, 마이그레이션, fallback 등 100+)
3. Git 친화적 구조
    - 증분 인덱싱
    - 브랜치/PR 네임스페이스
    - overlay 워킹트리 반영
    - bottom-up 요약/그래프 갱신
4. CLI / MCP / HTTP API / IDE 플러그인 등 **모든 채널에서 공용으로 쓰는 헤드리스 엔진**
5. 멀티 레포, 문서/설정/인프라 파일, 협업/페어코딩까지 포함하는 **확장 가능 구조**
6. 장애/불완전 인덱스 환경에서도 **fallback 계층**을 통해 항상 best-effort 응답 제공

### 1-2. 기술 스택

1. 코드 파싱: Tree-sitter + Unified AST Schema
2. 코드 그래프/메타: Kùzu (embedded, graph + column store)
3. 벡터 검색: Qdrant (dense + payload filter)
4. Lexical 검색: Zoekt (BM25 + substring + regex)
5. LLM: LLMProvider 추상화 (OpenAI / Claude / 로컬 모델 교체 가능)
6. 세션/협업 메타: Redis/Postgres 등 경량 스토어 (선택)

### 1-3. 인덱싱 상태 및 동작 보장

1. 인덱싱 상태
    - Indexed / Partial / Dirty / Failing
2. 어떤 상태에서도 최소 기능은 유지
    - fallback 레벨(0~5)로 자동 강등
3. 일부 스토어(Qdrant/Kùzu/Zoekt) 장애에도 엔진은 항상 best-effort 응답 생성

## 2. 저장소·데이터 계층 요구사항 (Kùzu / Qdrant / Zoekt)

### 2-1. Kùzu 노드 테이블(엔티티)

1. REPO
    - repo_id, default_branch, languages, last_indexed_commit, attrs
2. PROJECT
    - project_id, repo_id, name, attrs
3. MODULE
    - module_id, project_id, path, attrs
4. FILE
    - file_id, module_id, path, language, hash, summary, category(source/config/doc/infra/resource)
    - attrs:
        - security_level: PUBLIC / INTERNAL / CONFIDENTIAL / SECRET
        - tenant_id / project_scope (멀티 tenant 대비)
        - license: { type, spdx_id, source_url }
5. SYMBOL
    - symbol_id, file_id, kind, name
    - span_start_line, span_start_col, span_end_line, span_end_col
    - import_path, export_name
    - summary
    - attrs:
        - uses_in_loop: bool (루프 안에서 호출되는지)
        - heavy_call_in_loop: bool (중요 store/외부호출이 루프 안에 있는지)
6. CHUNK
    - chunk_id, symbol_id, file_id
    - start_line, end_line
    - raw_code_ref (텍스트 저장 위치 또는 해시)
    - attrs:
        - security_level (FILE 상속 + override 가능)
        - content_hash
7. REPOMAP_NODE
    - map_id
    - type: repo / project / module / file / symbol
    - ref_id: 해당 노드 id
    - summary
    - importance_score
    - attrs
8. DTO_NODE
    - dto_name, file_id, fields_json, attrs
9. CONFIG_NODE
    - config_id, file_id, key, value, source(default/env/config/cli), attrs
10. FEATURE_FLAG
    - flag_key, default_value, attrs
11. JOB_NODE
    - job_id, schedule_expr, handler_symbol_id, kind(index_rebuild / cleanup / consistency_check 등), attrs
12. CLI_COMMAND
    - cmd_name, handler_symbol_id, attrs
13. MIDDLEWARE_NODE
    - middleware_id, kind(auth / validation / logging / rate_limit 등), attrs
14. VALIDATION_NODE
    - validator_id, dto_name, location(symbol_id or file_id), attrs
15. LOG_CALL
    - log_id, symbol_id, log_level, log_message_template, attrs
        
        (정적 문자열 기반 역추적용)
        

### 2-2. Kùzu 엣지(그래프 관계)

1. 코드 구조·호출 관계
    - CALLS(from_symbol → to_symbol)
    - CALLS_REVERSE(to_symbol → from_symbol) // 뷰 또는 별도 엣지
    - IMPORTS(from_file → to_file)
    - EXPORTS(from_symbol → exported_symbol)
    - HAS_SYMBOL(file → symbol)
    - HAS_CHUNK(symbol → chunk)
    - INHERITS(from_symbol → to_symbol)
    - IMPLEMENTS(from_symbol → to_symbol)
    - TESTS(test_symbol → target_symbol)
    - ROUTE(route_id → handler_symbol_id)
2. DTO / 사용 관계
    - DTO_USAGE(symbol_id → dto_name, mode=request|response)
3. 설정·환경·플래그
    - ENV_USAGE(symbol_id → var_name)
    - FLAG_USAGE(symbol_id → flag_key)
4. 에러·이벤트·잡·CLI
    - ERROR_THROW(symbol_id → error_code)
    - ERROR_HANDLE(symbol_id → error_code)
    - EVENT_PUBLISH(symbol_id → event_name)
    - EVENT_HANDLE(symbol_id → event_name)
    - JOB_HANDLER(job_id → handler_symbol_id)
    - CLI_HANDLER(cmd_name → handler_symbol_id)
5. 외부 호출·캐시·재시도·트레이싱
    - OUTBOUND_HTTP(symbol_id → service_hint/url_node)
    - OUTBOUND_GRPC(symbol_id → service_name/method_node)
    - CACHE_SET(symbol_id → cache_name)
    - CACHE_GET(symbol_id → cache_name)
    - CACHE_CLEAR(symbol_id → cache_name)
    - RETRY_CONFIG(symbol_id → retry_node)
    - TRACE_PROPAGATION(symbol_id → span_name)
6. 미들웨어·검증
    - ROUTE_HAS_MIDDLEWARE(route_id → middleware_id)
    - VALIDATION_USAGE(validator_id → route_id or symbol_id)
7. 로그
    - SYMBOL_HAS_LOG(symbol_id → log_id)

### 2-3. Qdrant 스키마

1. 컬렉션: code_chunks
    - point_id: chunk_id (Kùzu CHUNK와 1:1 매핑)
    - vector: embedding_text 임베딩
    - payload:
        - repo_id, file_path, file_id, symbol_id, kind, language, category
        - importance_score
        - security_level, tenant_id
        - content_hash
2. 컬렉션: symbol_summaries
    - point_id: symbol_id
    - summary 임베딩
    - payload: repo_id, file_id, kind, security_level, tenant_id

### 2-4. Zoekt 인덱스

1. 대상: FILE / CHUNK 텍스트
2. 필터: repo_id, path, language, category, security_level, tenant_id
3. 기능: substring, regex, prefix search, symbol name 검색

## 3. 코드 모델·그래프 구축 요구사항

### 3-1. Unified AST Mapper

1. 초기 언어 지원
    - Phase1: Python, TypeScript
    - Phase2: JavaScript, Java, Kotlin
    - Phase3: Go, C#, PHP 등 (우선순위에 따라 확장)
2. 언어 추가 절차
    - Tree-sitter grammar 연결
    - 언어별 AST → Unified Node Model 매퍼 구현
    - CALLS / IMPORTS / INHERITS / IMPLEMENTS / TESTS / ROUTE / DTO / CONFIG / LOG 추출
    - 부분 시나리오 벤치(정의/호출/라우트/DTO/로그)로 품질 검증

### 3-2. 심볼·참조 해석

1. 함수/클래스/메서드/enum/interface/route 핸들러를 SYMBOL로 모델링
2. import/export 구조 해석
    - IMPORTS(from_file → to_file)
    - EXPORTS(from_symbol → exported_symbol)
    - ROUTE(route_id → handler_symbol)
3. IDENT_REF(필요 시)로 rename/impact 분석 기반 제공

### 3-3. 라우트·DTO·에러 매핑

1. router.get/post/put/delete 등에서 ROUTE 노드 생성
2. DTO 정의(class/interface/pydantic model 등)를 DTO_NODE로 저장
3. DTO 사용 위치를 DTO_USAGE로 연결
4. 에러 코드/예외 타입을 ERROR_THROW/ERROR_HANDLE로 연결

### 3-4. 설정/환경/플래그

1. config 파일(yaml/json/toml 등) 파싱 → CONFIG_NODE
2. ENV 변수 사용 코드 → ENV_USAGE
3. feature flag 상수/함수 사용 → FEATURE_FLAG + FLAG_USAGE

### 3-5. 인프라/CI/K8s/Docker/문서

1. 지원 파일 타입
    - 문서: md, rst, txt
    - 설정: yaml, json, xml, toml
    - 인프라: Dockerfile, docker-compose, k8s manifests, helm
    - CI: GitHub Actions, GitLab CI, Jenkinsfile
    - 리소스: svg (텍스트 xml 기반), .env (secret masking)
2. 각 파일은 FILE(category=config/doc/infra/resource)로 편입
3. CI job, k8s probe, Docker ENTRYPOINT 등에서
    - JOB_NODE, CLI_COMMAND, ROUTE와 연결

### 3-6. 로그·제어 흐름 메타데이터

1. LOG_CALL
    - logger.*("...") 형태의 로그 메시지 템플릿을 LOG_CALL로 추출
    - SYMBOL_HAS_LOG 관계로 연결
2. 루프 정보
    - AST 기준으로 loop(for/while/map/filter 등) 내부의 호출을 분석
    - SYMBOL.attrs.uses_in_loop / heavy_call_in_loop 설정
        
        (GraphStore, 외부 서비스 호출 등이 루프 내에 있는지 표시)
        

## 4. 인덱싱 파이프라인 요구사항

### 4-1. 전체 플로우

1. 파일 스캔 (git + 워킹트리)
2. Tree-sitter 파싱 (언어별)
3. Unified AST 매핑 → FILE/SYMBOL/CHUNK/관계 생성
4. REPOMAP_NODE 생성 (bottom-up summary)
5. Kùzu bulk upsert (노드 + 엣지)
6. Zoekt 인덱싱
7. Qdrant 임베딩 생성 및 업서트
8. 인덱싱 상태(State) 업데이트

### 4-2. 증분 인덱싱

1. git diff(last_indexed_commit..current) 기반 변경 파일 목록 확보
2. 변경 파일 관련 FILE/SYMBOL/CHUNK/관계 삭제 후 재생성
3. 상위 REPOMAP_NODE 요약 bottom-up 재계산
4. Qdrant/Zoekt 부분 인덱싱 갱신

### 4-3. Overlay 인덱싱

1. 워킹트리/자동 편집분을 overlay 레이어에 저장
2. 검색 시 base + overlay 조합 결과 제공
3. commit 시 overlay → base 승격

### 4-4. Syntax Error Tolerant 파싱

1. Tree-sitter 파싱 실패 시 MinimalStructuralParser 활성화
2. function/class 키워드/블록 기반으로 근사 심볼/청크 생성
3. 그래프는 불완전해도 최소 SYMBOL/CHUNK는 유지

### 4-5. Cross-Store Consistency Check

1. 인덱싱 후 Kùzu CHUNK.content_hash와 Qdrant payload.content_hash 비교
2. 불일치 시 inconsistency_event 발생 및 해당 chunk 재인덱싱
3. JOB_NODE 기반으로
    - after-indexing consistency job
    - nightly full consistency job (예: 0 3 * * *)

## 5. 검색·RAG 파이프라인 요구사항

### 5-1. 하이브리드 검색 파이프라인

1. 입력: 자연어/코드/에러 메시지/로그 텍스트 등
2. Step 1: Zoekt 후보 (lexical)
3. Step 2: Qdrant 후보 (semantic)
4. Step 3: Kùzu 그래프 확장 (CALLS/IMPORTS/TESTS/OUTBOUND 등)
5. Step 4: Weighted fusion (lexical_score, semantic_score, graph_score)
6. Step 5: Symbol 중심 context 패키징
    - 정의 + 호출부 + 테스트 + 설정/문서 + 로그/에러 흐름

### 5-2. GraphRAG

1. ROUTE/ENTRYPOINT를 시작점으로 multi-hop 탐색
2. API → handler → service → store → DB/외부 서비스 플로우 제공
3. IndexingPipeline → Chunker, retriever → search → reranker 등의 call chain 답변 가능하도록 그래프 추출

### 5-3. RepoMap 기반 요약

1. REPOMAP_NODE를 이용해 repo/project/module/file 레벨 요약 제공
2. 상위 요약 + 대표 심볼을 context로 구성

### 5-4. Context Budget Manager

1. 모델별 토큰 예산 정의
2. 중요도/거리/유형 기반으로 chunk/symbol/file 우선순위화
3. 예산 부족 시 Leaf → Symbol → File → Module → Repo 순으로 요약 fallback

### 5-5. ACL / Security Filter

1. 모든 검색/그래프 쿼리는 security_context(user_id, roles, allowed_levels, tenant_id)를 입력으로 받음
2. Kùzu/Qdrant/Zoekt 쿼리에서
    - security_level ≤ caller_level
    - tenant_id 일치
        
        필터를 적용
        
3. ACL 테스트 시나리오(1-20, 2-17)를 만족할 수 있도록 설계

## 6. Fallback 계층 요구사항

### 6-1. Fallback 레벨 정의

1. Level 0: Full Structure-RAG (Kùzu + Zoekt + Qdrant 정상)
2. Level 1: Graph 누락 → identifier scan / heuristic 보완
3. Level 2: 파싱 오류 → syntax tolerant 구조로 근사
4. Level 3: Kùzu 장애 → Zoekt + Qdrant only
5. Level 4: Zoekt/Qdrant 장애 → RepoMap/파일 요약 기반 reasoning
6. Level 5: 인덱싱 거의 없음 → Pure LLM reasoning

### 6-2. Fallback 동작 규칙

1. 각 검색/그래프 쿼리는 fallback_level과 confidence score(0~1)를 함께 반환
2. 상위 레벨 실패 또는 confidence < threshold(예: 0.6) 시 자동으로 다음 레벨로 강등
3. 에이전트는 fallback_level에 따라 답변의 톤/주의사항을 조정

### 6-3. Confidence Scoring

1. graph_confidence, symbol_match_confidence, lexical_score, semantic_score
2. 시나리오 벤치에서 level별 품질 측정 가능하도록 노출

## 7. Git·증분·브랜치/PR 요구사항

### 7-1. Git 이벤트 처리

1. 브랜치 전환, rebase, checkout, pull/push 감지
2. repo_id + branch별 index namespace 관리

### 7-2. 브랜치/PR 인덱싱

1. main, feature-branch, PR별 독립 네임스페이스 또는 계층형 key 사용
2. PR diff 기반 부분 인덱싱 (변경 파일/심볼/청크만)

### 7-3. 인덱스 상태 일관성

1. last_indexed_commit vs HEAD 비교
2. Dirty 상태일 때 검색 결과에 경고/low confidence 표시

## 8. LLM/Agent 계층 요구사항

### 8-1. LLMProvider 추상화

1. chat/completion, embedding, scoring 인터페이스 통합
2. 모델/벤더 교체 시 core 코드 수정 없이 config로 교체 가능

### 8-2. Intent 분류·Planner

1. intent: search / explain / generate / refactor / debug / test / infra / migrate 등
2. plan: 도구 호출 시퀀스
    - 예: search_code → get_call_chain → open_files → generate_diff → validate → apply_diff

### 8-3. Tool 세트

1. search_code, search_route, get_call_chain, get_tests
2. get_config_flow, get_error_flow, get_job_flow
3. get_outbound_calls, search_logs_by_message
4. apply_diff, run_lint, run_tests 등

### 8-4. Agent Guardrails

1. step 수 상한, tool 호출 수 상한, 시간 제한, 토큰 예산 설정
2. 초과 시 현재까지 수집한 context로 best-effort 요약 응답
3. security_context와 license 정보 기반으로 위험한 코드 제안 차단

### 8-5. Self-Correction 루프

1. 생성된 코드에 대해 lint/syntax/test 실행
2. 실패 시 에러 로그를 다시 LLM에 넘겨 자동 수정 시도

### 8-6. 라이선스/저작권 Guardrail

1. FileNode/ProjectNode에 license 정보 저장
2. 코드 생성/변경 시
    - 참조된 소스의 license_type을 확인
    - GPL/Proprietary 등 정책상 허용되지 않는 라이선스의 코드 조합은 차단 또는 경고
3. attribution_context를 기반으로, 필요 시 출처 정보 제공

## 9. 협업·세션·멀티레포 요구사항

### 9-1. Workspace / Session 모델

1. Workspace: repo 집합 + 인덱스 view 설정
2. Session: workspace, user_id, role(host/guest), agent_state, open_files, search_history

### 9-2. 페어코딩 모드

1. host가 세션 생성, guest는 join
2. 공유 컨텍스트:
    - 열린 파일/탭
    - 최근 검색 결과
    - agent plan 요약
3. 개인 컨텍스트:
    - 개인 메모, 설정, 토큰 사용 내역 등은 분리 저장

### 9-3. 권한·역할

1. host만 apply_diff, index rebuild, 위험한 동작 수행 가능
2. guest는 검색/요약/제안까지만 허용 (정책으로 조정 가능)

### 9-4. Session Replay

1. tool 호출 로그, agent plan, 주요 결과를 세션 단위 저장
2. 디버깅/리뷰/온보딩 용도로 타임라인 재생 가능

### 9-5. 멀티 레포

1. workspace 내 여러 repo 동시 인덱싱 및 검색
2. cross-repo call/import/infra 연결(선택적 기능) 지원

## 10. 문서/설정/인프라 파일 처리 요구사항

### 10-1. 문서·설정·인프라 인덱싱

1. md/rst/txt: 섹션/헤더 기반 chunking
2. yaml/json/xml/toml: 주요 object/section 단위 chunking
3. Docker/K8s/Helm: 리소스별 SYMBOL 노드
    - Deployment, Service, Job, values, probe 등
4. CI: job/step/shell 명령 단위 SYMBOL 생성
    - CLI_COMMAND / ROUTE / JOB과 연결

### 10-2. 코드와의 연결

1. CI job → CLI → 내부 모듈/함수 call chain 구성
2. K8s probe path → ROUTE/handler → service/store와 연결
3. Docker ENTRYPOINT/CMD → main 함수/모듈 매핑

### 10-3. Secret/민감 정보

1. .env, config에서 secret 패턴(API_KEY, TOKEN, PASSWORD 등)을 마스킹 또는 인덱싱 제외
2. LLM context에 secret value가 포함되지 않도록 필터링

### 10-4. 저작권/라이선스 추적

1. 각 FileNode/ProjectNode에 license_type, spdx_id, attribution_context 저장
2. LLM이 생성한 코드가 어떤 파일/프로젝트에서 유도되는지 추적 가능하게 설계
3. 라이선스 정책에 따라
    - 금지 라이선스 코드 조합 차단
    - 필요한 경우 출처/라이선스 표시 지원

## 11. 품질 평가·벤치마크·Observability 요구사항

### 11-1. 시나리오 벤치 프레임워크

1. 우선순위 1·2 코어 시나리오(1~100) 자동 실행
2. 확장 시나리오(101~200: 디버깅, 테스트, 성능, 보안, 인프라, fallback 등) 포함
3. 각 시나리오별로
    - 질의 → 검색 → 그래프 → LLM 응답까지 end-to-end 평가

### 11-2. 검색 품질 메트릭

1. Precision@k, Recall@k, MRR, nDCG 등
2. 인덱스/랭킹 변경 시 regression 체크

### 11-3. Agent 품질 메트릭

1. 성공/실패 비율, step 수, tool 호출 수, 토큰 사용량
2. 핵심 시나리오(예: API 플로우 설명, 테스트 생성, 버그 역추적)에 대한 human eval

### 11-4. Observability 세분화

1. 각 trace/span에 아래 정보 기록
    - fallback_level
    - confidence scores
    - 사용된 도구 목록
    - latency(검색/그래프/LLM 단계별)
    - token_usage:
        - embedding_tokens
        - completion_tokens
        - total_tokens
        - total_cost (모델별 단가 기반 계산)
2. Cost Threshold 기반 Degrade Mode
    - 요청/세션/사용자 단위로 cost budget 지정
    - 초과 시 자동으로
        - 더 단순한 모델
        - 낮은 fallback 레벨 (예: semantic-only)
        - context 축소
            
            로 강등
            

## 12. 비기능 요구사항

### 12-1. 비기능 요구사항

1. 성능
    - IDE 수준 체감 속도 (심볼 검색·call chain 조회: ms~수백 ms)
    - 대형 모노레포에서도 수초 내 인덱싱 단계별 응답
2. 확장성
    - 수백만 LOC / 수천 개 파일 / 수십 서비스 기준으로 안정 동작
3. 안정성
    - 인덱싱 실패 시에도 최소 검색 기능 유지
    - secret/라이선스/ACL 위반 없는 응답 보장
4. 법적·윤리적 안전장치
    - 라이선스/저작권 추적
    - secret/민감 정보 보호
    - 권한/ACL 기반 검색 필터링
5. 비용 관리
    - 토큰/비용 모니터링
    - 임계치 기반 Degrade Mode

### 12-2. 구현 마일스톤(요약)

1. M1: Kùzu/Qdrant/Zoekt 스키마 및 인프라 준비
2. M2: Tree-sitter + Unified AST + 기본 인덱싱 파이프라인
3. M3: Hybrid Search + GraphRAG v1 (코어 시나리오 일부 통과)
4. M4: Git 증분/overlay/branch/PR 지원
5. M5: LLMProvider + Agent(Planner/Intent/Tool Routing) v1
6. M6: Self-correction + 디버깅/리팩토링 시나리오 지원
7. M7: Fallback 계층(0~5레벨) + Cross-store Consistency + 비용/토큰 관측
8. M8: 협업/Session/Replay + 멀티레포/문서/인프라 통합 + 라이선스/ACL 가드레일 강화
