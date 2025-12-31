# Query DSL - Testing

**
**Scope:** Query DSL 회귀 방지 체크리스트  

---

## What to verify

- 연산자(`>>`, `.via()`) 조합이 기대하는 traversal로 변환되는지
- edge 타입별(DFG/CFG/CallGraph) 기본 케이스가 깨지지 않는지
- 결과 스키마가 상위 계층(SearchHit/chunk_id 조인)과 호환되는지

---

## Where tests usually live

- `tests/` 아래 query 엔진/DSL 관련 테스트

