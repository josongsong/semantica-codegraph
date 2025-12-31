# Query DSL - Runtime

**
**Scope:** DSL → 그래프 실행(Traversal) 관점 요약  

---

## Execution Model

- DSL 식(FlowExpr)을 내부 표현으로 변환
- `via(E.XXX)`로 경로 탐색 시 사용할 그래프 엣지 집합을 고정
- QueryEngine이 그래프/IR 인덱스를 사용해 경로 탐색/필터링 수행

---

## Outputs

- 실행 결과는 보통 “경로/매치” 단위로 반환되며, 상위 계층에서는 `SearchHit`/`chunk_id`로 통합됨

---

## Performance Notes

- 목적: “표현은 고수준, 실행은 저수준(그래프 순회)”  
  - 튜닝 포인트는 주로 edge resolver / traversal pruning / caching

---

## Links

- 상세: `architecture.md`

