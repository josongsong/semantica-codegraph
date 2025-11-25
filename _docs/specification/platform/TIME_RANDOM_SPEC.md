# Time & Random Provider Specification

본 문서는 시간/UUID/랜덤 사용을 테스트 가능한 형태로 래핑하는 규칙을 정의한다.

---

## 목적

- 테스트에서 시간/랜덤 값 결정론적(deterministic) 유지
- 글로벌 clock 의존성 제거
- timestamp/uuid 생성 시 일관성 확보

---

## MUST 규칙

1. 시간·UUID·랜덤 생성은 반드시 provider 클래스를 통해 호출한다.
   - 예: `TimeProvider.now()`, `UUIDProvider.new()`
2. provider는 DI 컨테이너에서 단일 인스턴스로 생성한다.
3. 테스트에서는 provider를 mock 가능해야 한다.
4. timestamp를 문자열로 format하는 것은 Interfaces 계층에서만 허용한다.
5. timezone은 반드시 UTC 기준으로 고정한다.

---

## 금지 규칙

1. 코드 곳곳에서 `datetime.utcnow()` 직접 호출
2. uuid4() 직 호출
3. 테스트에서 실제 시간 흐름을 sleep으로 조절
4. 랜덤값을 기반으로 분기하는 로직

---

## 문서 간 경계

- CI 파이프라인 및 deterministic 테스트 규칙은 TEST_RULES.md 참고
