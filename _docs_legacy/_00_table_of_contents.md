docs/
  overview/                                    # [항목] 프로젝트 개요 계층
                                               # [목적] Semantica 전체를 5분 안에 이해하게 하는 상위 문서들
                                               # [필수규칙] MUST provide business-level understanding only (no technical details)

    SEMANTICA_OVERVIEW.md                      # 개요 / 구성요소 / 철학
    VISION_ROADMAP.md                          # 장기 방향성 / 버전 로드맵
    RELEASE_NOTES.md                           # 릴리즈별 변화 기록 (changelog)

  specification/                               # [항목] MUST 규칙/계약 스펙
                                               # [목적] Semantica 플랫폼 & Codegraph 엔진의 동작을 보장하는 계약 정의
                                               # [필수규칙] “~해야 한다(MUST)” 규칙만 존재하고 지식/메모 등은 절대 포함 금지

    platform/                                  # [항목] 플랫폼 공통 스펙
                                               # [목적] 모든 Semantica 기반 프로젝트(코드그래프 외)에서 공통 적용되는 규칙
                                               # [필수규칙] DI/Test/Lint/Style/CI/보안 등 전체 레포의 통일성 보장

      DI_SPEC.md                               # DI 생성 규칙 MUST. container.py에서만 생성, lazy singleton, 계층별 import 제한
      CONFIG_SPEC.md                           # Settings/RepoConfig/override MUST. env prefix, 우선순위 정의
      LAYERING_SPEC.md                         # Core→Ports→Services→Infra 방향 MUST. 순환 금지, import 규칙
      TEST_RULES.md                            # Unit/Integration/Scenario 3단 테스트 모델 MUST. mocking/golden 규칙 포함
      LINT_FORMAT_SPEC.md                      # ruff/mypy/biome/formatter 규칙 MUST. 금지 규칙 지정
      STYLE_PYTHON.md                          # 함수/클래스/import/typing/logging 스타일 MUST
      STYLE_TS.md                              # TS/React 스타일 MUST. strict mode, import rules
      ERROR_STYLE_SPEC.md                      # 예외 네이밍/레이어별 예외 throw 규칙 MUST
      ASYNC_RULES.md                           # async 허용 범위/도입 규칙 MUST. sync/async 혼합 금지
      CONCURRENCY_RULES.md                     # multi-thread/process/async concurrency 규칙 MUST
      LOGGING_SPEC.md                          # structured logging MUST. trace_id/repo_id/fallback_level 필수
      AI_USAGE_SPEC.md                         # AI로 생성한 코드/문서 규칙 MUST. [ai] 태그, 테스트·린트 통과 필수
      CODE_REVIEW_SPEC.md                      # PR 승인 기준 MUST. 테스트/문서 변경 필수 여부
      REPO_STRUCTURE_SPEC.md                   # 폴더 표준 구조 MUST. src/tests/docs 분리
      CI_PIPELINE_SPEC.md                      # CI 품질 게이트 MUST. lint+unit+(integration on main)
      SECURITY_SPEC.md                         # secrets/log masking MUST. credentials 절대 노출 금지
      RESOURCE_MANAGEMENT_SPEC.md              # DB/HTTP client lifecycle 규칙 MUST. 재사용/close 규칙
      TIME_RANDOM_SPEC.md                      # 시간/랜덤 provider 규칙 MUST. 테스트 가능한 clock/uuid 래핑

    codegraph/                                 # [항목] Codegraph 전용 엔진 스펙
                                               # [목적] Codegraph 엔진의 동작/구조를 엄격하게 정의하여 재현성 보장
                                               # [필수규칙] indexing/search/graph/chunk schema 반드시 이 규칙을 따라야 함

      INDEXING_SPEC.md                         # 인덱싱 단계 MUST. parse → chunk → relational/vector/graph/lexical 저장 순서
      SEARCH_SPEC.md                           # hybrid retrieval MUST. lexical+vector+graph+routing+fusion scoring 규칙
      GRAPH_SPEC.md                            # 코드 그래프 node/edge taxonomy MUST. defines/calls/imports/instantiates
      SCHEMA_RELATIONAL.md                     # PostgreSQL 스키마 MUST. PK/FK/unique/constraints 정의
      SCHEMA_VECTOR.md                         # Qdrant payload schema MUST. embedding meta/version 규칙
      SCHEMA_GRAPH.md                          # Graph store(Kùzu) node/edge schema MUST
      SCHEMA_LEXICAL.md                        # Meili/Zoekt 문서 스키마 MUST. searchable/filterable fields
      CHUNK_SPEC.md                            # LeafChunk/CanonicalChunk 스키마 MUST. 규정된 boundary
      SUMMARY_SPEC.md                          # symbol summary 템플릿 MUST. embedding alignment 규칙
      DTO_SPEC.md                              # 내부 전송 객체 DTO MUST. 검색 결과 구조 등
      MCP_TOOL_SPEC.md                         # MCP tool input/output 계약 MUST
      FALLBACK_SPEC.md                         # fallback level 0~5 MUST. degrade semantics
      PROFILING_SPEC.md                        # profiling 구조/필드 MUST. trace logging 일관성
      SCENARIO_SPEC.md                         # golden scenario schema MUST. strict order / identity

  knowledge/                                   # [항목] 내부 지식/연구/노트
                                               # [목적] 스펙을 만들기 위한 배경 지식, 실험 결과, 노트
                                               # [필수규칙] MUST/SHOULD 규칙을 포함하면 안 됨. 참고용 자료만

    chunking/
      CHUNKING_TECHNIQUES.md                   # chunking 전략 비교/연구

    embedding/
      EMBEDDING_RESEARCH.md                    # summary+code embedding alignment 실험

    search/
      HYBRID_SEARCH_NOTES.md                   # hybrid search tuning 노트
      RERANKER_NOTES.md                        # reranker 모델 실험/비교

    graph/
      GRAPH_RAG_NOTES.md                       # graph-based RAG 연구/사례

    parsing/
      TREESITTER_NOTES.md                      # Tree-sitter query 최적화 노트

    db/
      DB_OPTIMIZATION_NOTES.md                 # DB/config/index/IO tuning ノ트

    experiments/
      EXPERIMENT_LOGS.md                       # 실험 로그 기록

    competitors/
      COMPETITOR_NOTES.md                      # Sourcegraph, Cursor 등 비교 분석

    references/
      REFERENCE_ARCHITECTURES.md               # 참고 아키텍처 모음 (논문/사례)
