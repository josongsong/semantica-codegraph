# Logging Specification

본 문서는 Semantica 전역에서 사용하는 로깅 규칙을 정의함.

---

## 목적

- 모든 로그에 일관된 필드 구조 부여
- 문제 분석·추적이 가능한 수준의 정보 확보
- 개인정보 및 민감 정보 노출 방지

---

## MUST 규칙

1. 로그는 반드시 **structured logging** 형태여야 함 (key-value 기반).
2. 모든 요청 단위 로그에 아래 필드를 포함해야 함.
   - `trace_id`
   - `repo_id` (코드 저장소 식별자)
   - `operation` (예: indexing, search, graph_query)
   - `layer` (core/infra/interfaces)
3. 에러 로그에는 추가로 아래 필드를 포함해야 함.
   - `error_code`
   - `exception_type`
4. 로그 레벨 정의:
   - DEBUG: 상세 내부 상태 (로컬 디버깅 중심)
   - INFO: 정상 흐름, 주요 이벤트
   - WARN: 경고, fallback 사용 등
   - ERROR: 요청 단위 실패
   - FATAL/CRITICAL: 시스템 단위 장애
5. 개인 식별 정보(PII)와 인증 정보는 로그에 저장하지 않아야 함.
6. fallback 사용 시 `fallback_level` 필드를 로그에 포함해야 함.

---

## 금지 규칙 (MUST NOT)

1. `print` 함수로 로깅 처리.
2. 예외 stack trace 전체를 무조건 INFO 레벨에 기록.
3. 액세스 토큰/비밀번호/쿠키 값을 로그에 포함.
4. JSON이 아닌 임의의 문자열 포매팅으로 로그를 남기는 패턴.
5. 로깅 없이 예외를 무시하거나 삼키는 패턴.

---

## 문서 간 경계

- 에러 코드 및 예외 스타일은 `ERROR_STYLE_SPEC.md`.
- Observability(메트릭/트레이싱) 전반 규칙은 `OBSERVABILITY_SPEC.md`.
- 보안 이슈는 `SECURITY_SPEC.md` 에서 별도 다룸.
