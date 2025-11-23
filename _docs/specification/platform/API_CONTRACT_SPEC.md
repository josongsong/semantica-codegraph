# API Contract Specification

본 문서는 Semantica의 모든 HTTP/MCP/CLI 엔드포인트가 따라야 하는 전역 API 계약 규칙을 정의한다.

---

## 목적

- API 입력/출력 구조 통일
- 엔진 DTO와 wire-format 매핑 명확화
- LLM/도구/외부 서비스가 일관된 방식으로 접근 가능하도록 설계

---

## MUST 규칙

1. 모든 API는 Request/Response JSON 스키마가 있어야 함.
2. 모든 API는 `trace_id`, `repo_id` 를 입력으로 받아야 함.
3. 응답은 반드시 아래 구조를 따라야 함.
{
"success": true/false,
"data": {...},
"error": { "code": "...", "message": "...", "details": {...} }
}

yaml
Copy code
4. error.code는 ERROR_STYLE_SPEC.md 의 규칙을 따라야 함.
5. 각 API는 엔진 DTO와 1:1 매핑되는 Adapter를 구현해야 함.
6. MCP/CLI 툴도 동일한 Contract 구조를 사용해야 함.
7. API 버저닝은 VERSIONING_SPEC.md 의 규칙을 따른다.

---

## 금지 규칙

1. 엔드포인트별 응답 포맷 불일치
2. DTO를 wire-format 없이 내부 구조 그대로 serialize
3. Exceptions를 HTTP error로 직접 변환 없이 노출
4. 메시지 기반(순수 문자열 기반) API 응답

---

## 문서 간 경계

- 엔진 DTO 구조는 codegraph/DTO_SPEC.md
- 라우트/핸들러는 Interfaces 레이어에서 구현
