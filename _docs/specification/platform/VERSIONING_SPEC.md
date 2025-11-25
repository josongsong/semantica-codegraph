# Versioning Specification

본 문서는 API/DTO/Schema 버저닝 규칙을 정의한다.

---

## 목적

- 호환성 유지
- 변경 시 리스크 최소화
- 다중 버전 공존 전략 확립

---

## MUST 규칙

1. API는 `/v1/`, `/v2/` 등 명시적 버저닝을 사용해야 한다.
2. DTO는 필드 추가 시 backward compatible 형태로 유지해야 한다.
3. 필드 제거/타입 변경 등 breaking change 발생 시
   - DTO 신규 버전 생성
   - API 신규 버전 생성
4. Schema version은 metadata(`schema_version`) 필드로 관리한다.
5. 내부 모듈 버전은 semver 기반으로 관리한다.

---

## 금지 규칙

1. API를 암묵적으로 변경
2. 기존 DTO 필드를 의미 변경
3. Graph/Qdrant/Postgres에서 version 없이 구조 변경
4. 버저닝 없이 fallback logic만 추가하는 방식

---

## 문서 간 경계

- API 계약은 API_CONTRACT_SPEC.md
- DTO 스펙은 codegraph/DTO_SPEC.md 참고
