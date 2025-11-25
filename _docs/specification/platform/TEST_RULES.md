# Testing Rules Specification

본 문서는 테스트 구조 및 실행 전략에 대한 MUST 규칙을 정의한다.

---

## 목적

- 테스트 일관성 확보
- 유닛/통합/시나리오 테스트의 구분 기준 확립
- 테스트 실행 순서와 구조의 계약 명확화

---

## MUST 규칙

1. 테스트는 **Unit → Integration → Scenario** 3단 구조를 따른다.

### Unit
- Core 서비스, 포트 인터페이스, 순수 함수 테스트
- 외부 자원(mock) 허용

### Integration
- Infra 어댑터 + 실제 외부 리소스(Qdrant/Graph DB 등)
- CI 환경에서는 경량 모드로 실행 가능해야 한다

### Scenario (Golden)
- end-to-end 실행
- 입력/출력/흐름이 고정된 “골든 시나리오” 기반

2. Golden 테스트는 반드시 시나리오 ID 기반으로 관리한다.
3. 테스트 파일명 규칙: `test_*.py`
4. Unit 테스트는 100% deterministic 해야 한다.
5. Scenario 테스트는 snapshot/golden 구조를 따른다.
6. 테스트는 병렬 실행 가능해야 한다.

---

## 금지 규칙

1. Unit 테스트에서 네트워크/DB 호출 금지
2. 통합 테스트에서 DI 컨테이너 우회
3. 시나리오 테스트에서 mocking 사용
4. 테스트 간 순서 의존성 생성

---

## 문서 간 경계

- CI 파이프라인 규칙은 CI_PIPELINE_SPEC.md
- Golden scenario 스키마는 SCENARIO_SPEC.md 참고
