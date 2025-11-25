# API Index

본 문서는 Semantica Platform에서 제공하는 HTTP / MCP / CLI API 계약 문서를 인덱싱하기 위한 상위 목록임.
구체적인 Request/Response 구조는 각 `*_API_CONTRACT.md` 문서를 참조함.

## 목적

- 모든 공개/내부 API 계약 문서의 위치를 한눈에 파악하게 함
- 유즈케이스별로 API 계약 문서를 그룹화함
- 엔진 DTO 스펙, 시나리오 스펙과의 연결 지점을 명시함

## API 그룹

### Search APIs

관련 문서

- `SEARCH_API_CONTRACT.md`

관련 엔진 DTO

- `SEARCH_DTO_SPEC.md` (codegraph/dto/)
- SearchQueryDTO, SearchResultDTO

### Indexing APIs

관련 문서

- `INDEXING_API_CONTRACT.md`

관련 엔진 DTO

- `INDEXING_DTO_SPEC.md`
- IndexingCommandDTO, IndexingStatusDTO

### Graph / Call Graph / RepoMap APIs

관련 문서

- `GRAPH_API_CONTRACT.md`

관련 엔진 DTO

- `GRAPH_DTO_SPEC.md`
- `REPOMAP_DTO_SPEC.md`

### Repository Management APIs

관련 문서

- `REPO_API_CONTRACT.md`

관련 엔진 DTO

- RepoRegistrationDTO, RepoStatusDTO 등 (필요 시 추가 정의)

### Admin / Maintenance APIs

관련 문서

- `ADMIN_API_CONTRACT.md`

관련 엔진 DTO

- AdminTaskDTO, MaintenanceScheduleDTO 등

## 문서 간 경계

- 전역 규칙, 응답 래퍼 구조, 에러 포맷은 `API_CONTRACT_SPEC.md` 에서 정의함
- 엔진 DTO 구조는 `codegraph/DTO_SPEC.md` 및 하위 dto 스펙에서 정의함
- 이 문서는 인덱스용으로만 사용하며, 개별 스키마는 각 계약 문서에만 기록함
