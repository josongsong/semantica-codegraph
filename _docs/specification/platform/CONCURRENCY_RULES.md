# Concurrency Rules Specification

본 문서는 thread/process/async 기반 동시성 사용 규칙을 정의함.

---

## 목적

- 동시성 모델 선택 기준 명확화
- 데이터 레이스/교착 상태를 예방
- 복잡한 동시성 패턴 도입을 통제

---

## MUST 규칙

1. 기본 동시성 모델은 **async IO** 를 우선 사용함.
2. CPU-bound 작업이 필요한 경우에만 process pool 또는 별도 worker를 사용함.
3. thread 사용은 제한적으로 허용되며, 공유 상태를 최소화해야 함.
4. 동시성 사용 시 아래 사항을 반드시 명시해야 함.
   - 목적 (throughput 향상, latency 감소 등)
   - 사용 모델 (async/thread/process/queue)
5. Lock/Mutex를 사용하는 경우, 획득·해제 범위를 코드 상에서 명확히 드러내야 함.
6. 공유 상태를 다루는 객체에는 명시적인 동시성 안전성 전략을 적용해야 함.
   - 예: immutable 데이터, message passing, queue 기반 설계 등.

---

## 금지 규칙 (MUST NOT)

1. 임의의 thread 생성 후 join 없이 방치.
2. 전역 mutable 상태를 여러 thread/process에서 직접 조작.
3. async 코드와 threading을 혼합하여 사용하는 복잡한 패턴.
4. DB 커넥션을 여러 thread/async task에서 직접 공유.
5. 동시성 버그를 테스트 없이 추론만으로 해결했다고 간주.

---

## 문서 간 경계

- async 사용 범위·제한은 `ASYNC_RULES.md` 참고.
- 리소스(커넥션/세션) 라이프사이클은 `RESOURCE_MANAGEMENT_SPEC.md` 참고.
