# CI Pipeline Specification

본 문서는 Semantica 레포의 CI 품질 게이트 규칙을 정의한다.

---

## 목적

- 모든 코드가 자동 품질 검사를 통과하도록 보장
- PR → main merge 시 문제 없는 상태 유지
- 테스트/린트/타입 검증 자동화

---

## MUST 규칙

1. CI job 실행 순서는 다음과 같아야 함
   1) lint
   2) type-check
   3) unit tests
   4) integration tests
   5) scenario tests (main 브랜치에서만 필수)

2. main에 merge되는 모든 변경은 CI를 반드시 통과해야 한다.
3. lint/type-check 실패 시 즉시 실패 처리.
4. scenario 테스트는 병렬 실행을 지원해야 한다.
5. CI 실행 로그는 artifact로 최소 3일간 보존해야 한다.

---

## 금지 규칙

1. 수동 merge
2. 일부 테스트만 임의 실행
3. 환경 변수 미지정으로 인한 flakiness
4. PR에서 scenario 테스트를 완전히 skip

---

## 문서 간 경계

- 테스트 구조 규칙은 TEST_RULES.md
- 보안 스캔은 SECURITY_SPEC.md 참고
