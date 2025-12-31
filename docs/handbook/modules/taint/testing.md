# Taint - Testing

**
**Scope:** taint 엔진 회귀 방지 체크리스트  

---

## What to verify

- source/sink 매칭 정확도(타입 기반 매칭 포함)
- DFG 경로 탐색(기본/교차파일) 핵심 케이스
- false positive 방지(정화/배리어/파라미터라이즈드 쿼리 등)

---

## Where tests usually live

- `tests/` 아래 security/taint 관련 통합 테스트

