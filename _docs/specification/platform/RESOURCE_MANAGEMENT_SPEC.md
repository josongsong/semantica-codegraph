# Resource Management Specification

본 문서는 DB/HTTP/Vector/Graph 클라이언트의 라이프사이클 규칙을 정의한다.

---

## 목적

- 커넥션/세션 누수 방지
- 재사용 가능한 리소스 모델 확립
- 테스트/운영 환경에서 일관된 동작 보장

---

## MUST 규칙

1. 모든 외부 리소스는 DI 컨테이너에서 단일 인스턴스로 생성한다.
2. DB/Vector/Graph 클라이언트는 lazy initialization 해야 한다.
3. shutdown 시점에 close 또는 graceful shutdown 로직을 반드시 호출해야 한다.
4. 테스트 환경에서는 mock 또는 임시 리소스를 사용해야 한다.
5. 여러 thread/process/async task에서 공유되는 클라이언트는 concurrency-safe 해야 한다.

---

## 금지 규칙

1. 클래스 내부에서 리소스를 직접 생성
2. 사용 후 close하지 않고 방치
3. 매 요청마다 새 클라이언트를 생성하는 패턴
4. test에서 production DB를 직접 사용

---

## 문서 간 경계

- 동시성 규칙은 CONCURRENCY_RULES.md
- async 규칙은 ASYNC_RULES.md 참고
