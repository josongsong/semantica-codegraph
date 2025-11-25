# Security Specification

본 문서는 코드/문서/운영 전반의 보안 규칙을 정의한다.
MUST 수준의 플랫폼 보안 기준이다.

---

## 목적

- 민감 정보 보호
- 외부 노출 위험 방지
- 인덱싱/검색 과정에서 발생 가능한 보안 문제 차단

---

## MUST 규칙

1. 로그에 credential/token/password/쿠키 정보를 포함하면 안 된다.
2. secrets는 반드시 별도의 secret manager 또는 환경 변수를 통해 주입해야 한다.
3. 테스트용 mock credential은 실제 credential 패턴을 사용하면 안 된다.
4. 외부 API 호출 시 TLS를 반드시 사용해야 한다.
5. 파일 시스템 접근은 whitelisted path로 제한해야 한다.
6. AI 프롬프트 입력 시 민감 정보 제공 금지.

---

## 금지 규칙

1. 소스 코드에 키/토큰 하드코딩
2. GitHub Actions secrets를 로그 또는 에러 출력에 노출
3. 외부 API 클라이언트에서 SSL 검증 비활성화
4. 사용자가 입력한 raw 파일 내용을 그대로 로그에 저장

---

## 문서 간 경계

- 로깅 필드·구조는 LOGGING_SPEC.md
- 권한/Scope/ACL은 PERMISSION_GUIDE.md 참고
