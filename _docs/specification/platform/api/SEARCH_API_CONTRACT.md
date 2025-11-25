# Search API Contract

본 문서는 Semantica Search/Hybrid Search/MCP code_search 관련 API의 Request/Response 계약을 정의함.

이 문서에서 정의하는 API는 모두 `API_CONTRACT_SPEC.md` 의 전역 규칙을 함께 따라야 함.

## 목적

- 검색 및 하이브리드 검색 API의 입력/출력 구조를 명확히 정의
- 엔진 DTO(SearchQueryDTO, SearchResultDTO)와 wire-format 간 매핑을 고정
- HTTP, MCP, CLI 요청이 동일한 의미 구조를 공유하도록 설계

## 공통 규칙

모든 Search 계열 API는 다음 공통 필드를 포함해야 함.

요청 공통 필드

- `trace_id` 문자열, 필수
- `repo_id` 문자열, 필수
- `source` 문자열, 선택 (예: "api", "mcp", "cli", "ide")

응답 공통 규칙

- `success: boolean`
- `data: object`
- `error: object | null`
  구조는 `API_CONTRACT_SPEC.md` 의 에러 포맷을 따름

## 1) HTTP API: Hybrid Search

엔드포인트

- `POST /api/v1/search/hybrid`

요청 바디

```json
{
  "trace_id": "string",
  "repo_id": "string",
  "query": "string",
  "mode": "symbol|code|doc|auto",
  "limit": 20,
  "offset": 0,
  "filters": {
    "file_path_prefix": "src/",
    "language": "python",
    "kind": "function|class|file|chunk"
  }
}
