# retrieval_search + query-dsl (검색/쿼리 실행)

**
**Scope:** multi-index 결과를 통합(fusion)하고, 그래프/DFG 기반 질의를 실행하는 흐름  
**Source of Truth:** `src/contexts/retrieval_search/`, `_docs/modules/query-dsl/`

---

## What it does

- **Search**: lexical/vector/symbol/domain 결과를 weight/fusion/rerank로 통합
- **Query**: IR/Graph 기반 질의(DSL)를 실행해 dataflow/path를 찾음

---

## Inputs / Outputs

- **Input**: `query string`, `repo_id`, `snapshot_id` (+ weights)
- **Output**: `SearchHit[]` + (필요 시) 컨텍스트 빌드 결과

---

## Diagram

```mermaid
flowchart LR
  A[User Query] --> B[Search Fusion]
  B --> C[Lexical]
  B --> D[Vector]
  B --> E[Symbol]
  C --> F[Fused SearchHit(chunk_id)]
  D --> F
  E --> F
  F --> G[Context Builder / Rerank]
```

---

## Links

- Query DSL 상세: `_docs/modules/query-dsl/architecture.md`


