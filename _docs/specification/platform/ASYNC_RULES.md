# Async Usage Specification

본 문서는 async 사용 범위와 sync/async 혼합 금지 규칙을 정의함.

---

## 목적

- 비동기 사용 영역을 명확히 제한
- sync/async 혼합으로 인한 예측 불가능한 동작 방지
- IO 중심 모듈에서만 async를 사용하는 패턴 정착

---

## MUST 규칙

1. async는 **외부 IO가 명확히 존재하는 계층에서만** 사용해야 함.
   - 예: HTTP 클라이언트, DB/Vector Store/Graph Store, 파일 IO 등.
2. Core 도메인 로직은 기본적으로 sync 함수로 유지해야 함.
3. async 함수는 이름에 관용적으로 `async` suffix를 붙이지 않는다. (타입으로 구분)
4. Interfaces 계층(API/CLI/MCP)은 필요 시 async 엔드포인트를 가질 수 있음.
5. async 함수 내부에서는 blocking IO 호출을 사용하면 안 됨.
6. async 컨텍스트에서 sync 코드 호출이 필요할 경우, 별도의 executor 또는 worker를 통해 처리해야 함.

---

## 금지 규칙 (MUST NOT)

1. 동일 기능에 대해 sync/async 두 버전을 중복 유지.
2. 비동기 코드에서 동기 DB 드라이버를 사용하는 행위.
3. Core 서비스에서 직접 async IO를 호출하는 행위.
4. 테스트에서 event loop를 임의로 중복 생성.
5. async function을 단순히 wrapper로만 사용하여 의미 없이 체인 늘리기.

---

## 문서 간 경계

- 동시성(thread/process/async) 패턴 전반은 `CONCURRENCY_RULES.md` 에서 다룸.
- 외부 리소스 라이프사이클 관리는 `RESOURCE_MANAGEMENT_SPEC.md` 참고.
