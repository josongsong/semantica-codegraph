# Error & Exception Style Specification

본 문서는 에러 코드·예외 클래스·레이어별 에러 처리 규칙을 정의함.

---

## 목적

- 에러 표현 방식의 일관성 확보
- 레이어별 에러 책임 범위 명확화
- API/로그/알람에서 해석 가능한 에러 구조 유지

---

## MUST 규칙

1. 에러 코드는 **snake_case** 를 사용해야 하며, prefix는 `err_` 형태여야 함.
   - 예: `err_common_invalid_argument`, `err_search_index_not_found`
2. 예외 클래스는 `SomethingError` 네이밍을 사용해야 함.
3. Core 레이어는 도메인 의미가 있는 예외만 던져야 함.
   - 예: `SearchQueryError`, `IndexingConfigError`
4. Infra 레이어는 외부 시스템 에러를 도메인 예외로 매핑해야 함.
   - 외부 라이브러리 예외를 그대로 노출 금지.
5. Interfaces 레이어(API/CLI/MCP)는 도메인 예외를 HTTP/MCP 에러 응답으로 변환해야 함.
6. 에러 로그에는 반드시 아래 필드를 포함해야 함.
   - `error_code`
   - `layer` (core/infra/interfaces)
   - `operation` (예: search, indexing)
7. 비즈니스 규칙 위반과 시스템 에러를 구분해야 함.
   - 비즈니스 에러: 4xx 계열 응답
   - 시스템 에러: 5xx 계열 응답

---

## 금지 규칙 (MUST NOT)

1. `Exception` 또는 최상위 예외를 그대로 사용.
2. 문자열 상수로만 에러 종류를 구분하는 패턴.
3. 외부 라이브러리 에러 메시지를 그대로 사용자에게 노출.
4. Core에서 HTTP Status Code를 직접 다루는 행위.
5. 에러 코드를 없는 상태로 로그를 남기는 패턴.

---

## 문서 간 경계

- 로깅 필드/구조에 대한 상세 규칙은 `LOGGING_SPEC.md` 에서 정의함.
- API 응답 바디 구조 및 에러 포맷은 `API_CONTRACT_SPEC.md` 에서 정의함.
