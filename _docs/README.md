# Semantica Documentation

Semantica v2 공식 문서 레이어입니다.

**목적:**
코드와 분리된 공식 문서 레이어로, Semantica 플랫폼 전체의 specification, standards, knowledge를 체계적으로 관리합니다.

**버전:** v2.0
**최종 수정:** 2025-01-23

---

## 문서 구조 개요

_docs/ 디렉터리는 5개 주요 카테고리로 구성됩니다:

1. **overview/** - 프로젝트 개요 (비즈니스 관점)
2. **specification/** - MUST 규칙/계약 스펙
3. **standards/** - SHOULD 권장 가이드
4. **knowledge/** - 연구/실험/레퍼런스
5. **ops/domain/decisions/** - 운영/도메인/ADR

---

## 1. overview/ - 프로젝트 개요

**목적:** Semantica 전체를 5분 안에 이해시키는 비즈니스 문서

| 문서 | 설명 |
|------|------|
| [SEMANTICA_OVERVIEW.md](overview/SEMANTICA_OVERVIEW.md) | Semantica 전체 개요 / 구성요소 / 철학 |
| [VISION_ROADMAP.md](overview/VISION_ROADMAP.md) | 장기 방향성 / 버전별 로드맵 |
| [RELEASE_NOTES.md](overview/RELEASE_NOTES.md) | 릴리즈별 변화 기록 (high-level changelog) |

**규칙:**
- ✅ 비즈니스/제품 관점만 포함
- ❌ 기술 구현 세부사항 금지

---

## 2. specification/ - MUST 규칙/계약 스펙

**목적:** 플랫폼 & Codegraph 엔진 동작을 보장하는 계약 정의

**규칙:**
- ✅ MUST/MUST NOT 규칙만 존재
- ❌ 지식/메모/사례 포함 금지
- ❌ SHOULD 표현 사용 금지

**현재 코드베이스 주요 경로 (혼동 방지):**
- Business Logic: `core/core/` (domain/ports/services)
- Adapters: `core/infra/` (vector/search/git/llm/postgres)
- Apps: `apps/api_server/`, `apps/mcp_server/`
- Ops/DDL: `infra/config`, `infra/db`

### 2.1 specification/platform/ - 플랫폼 공통 스펙

모든 Semantica 기반 레포에 공통 적용되는 규칙:

| 문서 | 설명 |
|------|------|
| [DI_SPEC.md](specification/platform/DI_SPEC.md) | DI 생성 규칙 MUST (container.py 한정) |
| [CONFIG_SPEC.md](specification/platform/CONFIG_SPEC.md) | Settings/RepoConfig/override 규칙 MUST |
| [LAYERING_SPEC.md](specification/platform/LAYERING_SPEC.md) | Core→Ports→Services→Infra 방향 MUST |
| [TEST_RULES.md](specification/platform/TEST_RULES.md) | Unit/Integration/Scenario 3단 테스트 MUST |
| [LINT_FORMAT_SPEC.md](specification/platform/LINT_FORMAT_SPEC.md) | ruff/mypy/biome 규칙 MUST |
| [STYLE_PYTHON.md](specification/platform/STYLE_PYTHON.md) | Python 스타일 MUST |
| [STYLE_TS.md](specification/platform/STYLE_TS.md) | TypeScript/React 스타일 MUST |
| [ERROR_STYLE_SPEC.md](specification/platform/ERROR_STYLE_SPEC.md) | 예외/에러 네이밍 MUST |
| [ASYNC_RULES.md](specification/platform/ASYNC_RULES.md) | async 도입 범위 MUST |
| [CONCURRENCY_RULES.md](specification/platform/CONCURRENCY_RULES.md) | 동시성 패턴 MUST |
| [LOGGING_SPEC.md](specification/platform/LOGGING_SPEC.md) | structured logging MUST |
| [AI_USAGE_SPEC.md](specification/platform/AI_USAGE_SPEC.md) | AI 생성 코드/문서 규칙 MUST |
| [CODE_REVIEW_SPEC.md](specification/platform/CODE_REVIEW_SPEC.md) | PR 승인 기준 MUST |
| [REPO_STRUCTURE_SPEC.md](specification/platform/REPO_STRUCTURE_SPEC.md) | 폴더 표준 구조 MUST |
| [CI_PIPELINE_SPEC.md](specification/platform/CI_PIPELINE_SPEC.md) | CI 품질 게이트 MUST |
| [SECURITY_SPEC.md](specification/platform/SECURITY_SPEC.md) | secrets/log masking MUST |
| [RESOURCE_MANAGEMENT_SPEC.md](specification/platform/RESOURCE_MANAGEMENT_SPEC.md) | DB/HTTP client lifecycle MUST |
| [TIME_RANDOM_SPEC.md](specification/platform/TIME_RANDOM_SPEC.md) | clock/uuid/random 래핑 MUST |
| [VERSIONING_SPEC.md](specification/platform/VERSIONING_SPEC.md) | API/DTO/Schema 버저닝 MUST |
| [API_CONTRACT_SPEC.md](specification/platform/API_CONTRACT_SPEC.md) | 전역 API 계약 원칙 MUST |
| [OBSERVABILITY_SPEC.md](specification/platform/OBSERVABILITY_SPEC.md) | metrics/tracing/logs MUST |

#### specification/platform/api/ - API 계약

| 문서 | 설명 |
|------|------|
| [API_INDEX.md](specification/platform/api/API_INDEX.md) | 전체 API 목록 인덱스 |
| [SEARCH_API_CONTRACT.md](specification/platform/api/SEARCH_API_CONTRACT.md) | /api/search*, MCP code_search 계약 |
| [INDEXING_API_CONTRACT.md](specification/platform/api/INDEXING_API_CONTRACT.md) | /api/indexing/* 계약 |
| [GRAPH_API_CONTRACT.md](specification/platform/api/GRAPH_API_CONTRACT.md) | /api/graph/* 계약 |
| [REPO_API_CONTRACT.md](specification/platform/api/REPO_API_CONTRACT.md) | /api/repos/* 계약 |
| [ADMIN_API_CONTRACT.md](specification/platform/api/ADMIN_API_CONTRACT.md) | 관리용/배치 API 계약 |

### 2.2 specification/codegraph/ - Codegraph 엔진 전용 스펙

Codegraph 엔진 동작/구조를 엄격히 정의:

| 문서 | 설명 |
|------|------|
| [INDEXING_SPEC.md](specification/codegraph/INDEXING_SPEC.md) | 인덱싱 파이프라인 MUST |
| [SEARCH_SPEC.md](specification/codegraph/SEARCH_SPEC.md) | hybrid retrieval MUST |
| [GRAPH_SPEC.md](specification/codegraph/GRAPH_SPEC.md) | 코드 그래프 node/edge taxonomy MUST |
| [SCHEMA_RELATIONAL.md](specification/codegraph/SCHEMA_RELATIONAL.md) | PostgreSQL 스키마 MUST |
| [SCHEMA_VECTOR.md](specification/codegraph/SCHEMA_VECTOR.md) | Qdrant payload 스키마 MUST |
| [SCHEMA_GRAPH.md](specification/codegraph/SCHEMA_GRAPH.md) | Kùzu node/rel 스키마 MUST |
| [SCHEMA_LEXICAL.md](specification/codegraph/SCHEMA_LEXICAL.md) | Meilisearch/Zoekt 스키마 MUST |
| [CHUNK_SPEC.md](specification/codegraph/CHUNK_SPEC.md) | LeafChunk/CanonicalChunk MUST |
| [SUMMARY_SPEC.md](specification/codegraph/SUMMARY_SPEC.md) | symbol summary 템플릿 MUST |
| [DTO_SPEC.md](specification/codegraph/DTO_SPEC.md) | Codegraph DTO 원칙 MUST |
| [MCP_TOOL_SPEC.md](specification/codegraph/MCP_TOOL_SPEC.md) | MCP tool I/O 계약 MUST |
| [FALLBACK_SPEC.md](specification/codegraph/FALLBACK_SPEC.md) | fallback level 0~5 MUST |
| [PROFILING_SPEC.md](specification/codegraph/PROFILING_SPEC.md) | profiling 레코드 MUST |
| [SCENARIO_SPEC.md](specification/codegraph/SCENARIO_SPEC.md) | golden scenario schema MUST |

#### specification/codegraph/dto/ - Engine DTO 스펙

| 문서 | 설명 |
|------|------|
| [DTO_INDEX.md](specification/codegraph/dto/DTO_INDEX.md) | DTO 목록 인덱스 |
| [SEARCH_DTO_SPEC.md](specification/codegraph/dto/SEARCH_DTO_SPEC.md) | SearchService DTO MUST |
| [INDEXING_DTO_SPEC.md](specification/codegraph/dto/INDEXING_DTO_SPEC.md) | IndexingService DTO MUST |
| [GRAPH_DTO_SPEC.md](specification/codegraph/dto/GRAPH_DTO_SPEC.md) | GraphService DTO MUST |
| [REPOMAP_DTO_SPEC.md](specification/codegraph/dto/REPOMAP_DTO_SPEC.md) | RepoMap DTO MUST |
| [PROFILING_DTO_SPEC.md](specification/codegraph/dto/PROFILING_DTO_SPEC.md) | Profiling 이벤트 DTO MUST |

---

## 3. standards/ - SHOULD 권장 가이드

**목적:** 팀이 지향하는 코딩/테스트/아키텍처 스타일 정리

**규칙:**
- ✅ SHOULD/권장/예시 중심
- ❌ MUST 표현 사용 금지

| 문서 | 설명 |
|------|------|
| [house-rules.md](standards/house-rules.md) | 핵심 하우스룰 요약 (상위 10~20개) |

### standards/coding/

| 문서 | 설명 |
|------|------|
| [NAMING_GUIDE.md](standards/coding/NAMING_GUIDE.md) | 네이밍 권장 규칙 |
| [STYLE_GUIDE_PYTHON.md](standards/coding/STYLE_GUIDE_PYTHON.md) | Python 코딩 스타일 SHOULD |
| [STYLE_GUIDE_TS.md](standards/coding/STYLE_GUIDE_TS.md) | TS/React 스타일 SHOULD |
| [PATTERNS.md](standards/coding/PATTERNS.md) | 추천 패턴 모음 |
| [ANTI_PATTERNS.md](standards/coding/ANTI_PATTERNS.md) | 피해야 할 안티패턴 |

### standards/testing/

| 문서 | 설명 |
|------|------|
| [UNIT_TEST_PATTERNS.md](standards/testing/UNIT_TEST_PATTERNS.md) | 테스트 작성 팁 (AAA/fixture) |
| [NAMING_TESTS.md](standards/testing/NAMING_TESTS.md) | 테스트 네이밍 가이드 |
| [MOCKS_FIXTURES.md](standards/testing/MOCKS_FIXTURES.md) | mock/fixture 가이드 |
| [GOLDEN_TESTS.md](standards/testing/GOLDEN_TESTS.md) | snapshot/golden test 팁 |
| [COVERAGE_GUIDELINES.md](standards/testing/COVERAGE_GUIDELINES.md) | 커버리지 가이드 |

### standards/architecture/

| 문서 | 설명 |
|------|------|
| [MODULE_DESIGN_GUIDE.md](standards/architecture/MODULE_DESIGN_GUIDE.md) | 모듈/바운더리 설계 |
| [AGGREGATE_DESIGN_GUIDE.md](standards/architecture/AGGREGATE_DESIGN_GUIDE.md) | aggregate/도메인 모델 |
| [DEPENDENCY_GUIDE.md](standards/architecture/DEPENDENCY_GUIDE.md) | 의존 방향/adapter 패턴 |

### standards/ci/

| 문서 | 설명 |
|------|------|
| [PR_CHECKLIST.md](standards/ci/PR_CHECKLIST.md) | PR 체크리스트 |
| [COMMIT_RULES.md](standards/ci/COMMIT_RULES.md) | 커밋 메시지/단위 |
| [WORKFLOW_BEST_PRACTICES.md](standards/ci/WORKFLOW_BEST_PRACTICES.md) | CI 최적화 팁 |

### standards/security/

| 문서 | 설명 |
|------|------|
| [SECURE_CODING_GUIDE.md](standards/security/SECURE_CODING_GUIDE.md) | 보안 코딩 팁 |
| [SECRETS_HANDLING_GUIDE.md](standards/security/SECRETS_HANDLING_GUIDE.md) | secrets 관리 팁 |
| [PERMISSION_GUIDE.md](standards/security/PERMISSION_GUIDE.md) | 권한/롤 설계 |

---

## 4. knowledge/ - 연구/실험/레퍼런스

**목적:** SPEC 설계 배경, 실험 결과, 레퍼런스 기록

**규칙:**
- ✅ 설명/기록/비교만
- ❌ MUST/SHOULD 규칙 포함 금지

| 문서 | 설명 |
|------|------|
| [knowledge/chunking/CHUNKING_TECHNIQUES.md](knowledge/chunking/CHUNKING_TECHNIQUES.md) | chunking 알고리즘 비교 |
| [knowledge/embedding/EMBEDDING_RESEARCH.md](knowledge/embedding/EMBEDDING_RESEARCH.md) | embedding alignment 실험 |
| [knowledge/search/HYBRID_SEARCH_NOTES.md](knowledge/search/HYBRID_SEARCH_NOTES.md) | hybrid search 튜닝 노트 |
| [knowledge/search/RERANKER_NOTES.md](knowledge/search/RERANKER_NOTES.md) | reranker 실험 |
| [knowledge/graph/GRAPH_RAG_NOTES.md](knowledge/graph/GRAPH_RAG_NOTES.md) | GraphRAG 연구 |
| [knowledge/parsing/TREESITTER_NOTES.md](knowledge/parsing/TREESITTER_NOTES.md) | Tree-sitter 노트 |
| [knowledge/db/DB_OPTIMIZATION_NOTES.md](knowledge/db/DB_OPTIMIZATION_NOTES.md) | DB 튜닝 노트 |
| [knowledge/experiments/EXPERIMENT_LOGS.md](knowledge/experiments/EXPERIMENT_LOGS.md) | 실험 로그 |
| [knowledge/competitors/COMPETITOR_NOTES.md](knowledge/competitors/COMPETITOR_NOTES.md) | 경쟁사 분석 |
| [knowledge/references/REFERENCE_ARCHITECTURES.md](knowledge/references/REFERENCE_ARCHITECTURES.md) | 레퍼런스 아키텍처 |

---

## 5. ops/domain/decisions/ - 운영/도메인/ADR

### ops/ - 운영/런북

| 문서 | 설명 |
|------|------|
| [PORTS_CONFIG.md](ops/PORTS_CONFIG.md) | 서비스 포트 매핑/관리/보안 설정 |
| [DEPLOYMENT_GUIDE.md](ops/DEPLOYMENT_GUIDE.md) | 배포 전략/롤백 절차 |
| [ONCALL_GUIDE.md](ops/ONCALL_GUIDE.md) | 온콜/장애 대응 프로세스 |
| [RUNBOOK_INDEXING_FAILURE.md](ops/RUNBOOK_INDEXING_FAILURE.md) | 인덱싱 실패 대응 |
| [RUNBOOK_VECTOR_DB_DOWN.md](ops/RUNBOOK_VECTOR_DB_DOWN.md) | Qdrant/Graph DB 장애 대응 |

### domain/ - 비즈니스 도메인

| 문서 | 설명 |
|------|------|
| [GLOSSARY_COMMERCE.md](domain/GLOSSARY_COMMERCE.md) | 커머스 도메인 용어 |
| [GLOSSARY_BEAUTY.md](domain/GLOSSARY_BEAUTY.md) | 뷰티 도메인 용어 |
| [RULES_POINTS_MEMBERSHIP.md](domain/RULES_POINTS_MEMBERSHIP.md) | 포인트/멤버십 규칙 |
| [REGULATIONS_US_EU.md](domain/REGULATIONS_US_EU.md) | 컴플라이언스 요약 |

### decisions/ - ADR (아키텍처 결정 기록)

| 문서 | 설명 |
|------|------|
| [index.md](decisions/index.md) | ADR 목록 인덱스 |
| [0001-use-semantica-codegraph.md](decisions/0001-use-semantica-codegraph.md) | Codegraph 채택 배경 |
| [0002-choose-qdrant-over-pgvector.md](decisions/0002-choose-qdrant-over-pgvector.md) | Qdrant 선택 이유 |
| [0003-adopt-python-ts-stack.md](decisions/0003-adopt-python-ts-stack.md) | Python+TS 스택 채택 |
| [0004-use-kuzu-for-graph-store.md](decisions/0004-use-kuzu-for-graph-store.md) | Kùzu 선택 이유 |

---

## 문서 작성 규칙

### 1. specification/ 작성 규칙

**MUST:**
- MUST/MUST NOT 표현만 사용
- 강제 규칙만 포함
- 계약/스키마/구조 정의

**MUST NOT:**
- SHOULD 표현 사용 금지
- 예시/팁/권장사항 포함 금지
- 지식/연구 내용 포함 금지

### 2. standards/ 작성 규칙

**SHOULD:**
- SHOULD/권장/예시 중심
- 좋은 예시 / 나쁜 예시
- 패턴 / 안티패턴

**MUST NOT:**
- MUST 표현 사용 금지

### 3. knowledge/ 작성 규칙

**허용:**
- 배경 설명
- 실험 결과
- 비교 분석
- 레퍼런스

**MUST NOT:**
- MUST/SHOULD 규칙 포함 금지

---

## 문서 네이밍 컨벤션

### 파일명
- 대문자 + 언더스코어: `NAMING_GUIDE.md`
- 명확한 의미: `DI_SPEC.md`, `TEST_RULES.md`

### 문서 제목
- 첫 줄: `# <Title>`
- 명확한 목적 섹션 포함

### 섹션 구조
```markdown
# Title

**문서 목적:** ...
**범위:** ...
**버전:** v1.0

---

## 1. 핵심 원칙 (MUST/SHOULD)
## 2. 금지 규칙 (MUST NOT)
## 3. 예시
## 4. 체크리스트
## 5. 참고 자료
```

---

## 문서 버전 관리

- **v1.0**: 초기 템플릿 생성 (2025-01-23)
- 각 문서 상단에 `**최종 수정:**` 날짜 기록
- 주요 변경 시 버전 증가

---

## 참고 자료

- [프로젝트 루트 README](../README.md)
- [Test Guide](../TEST_GUIDE.md)
- [DI Guide](../DI_GUIDE.md)
- [Docker Setup](../DOCKER_SETUP.md)

---
