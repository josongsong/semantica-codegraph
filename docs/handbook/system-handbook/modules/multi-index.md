# multi_index (vector / lexical / symbol / domain)

**
**Scope:** Chunk를 여러 인덱스로 저장하고, 검색 결과를 `chunk_id`로 통합하는 계층  
**Source of Truth:** `src/contexts/multi_index/`

---

## What it does

- `Chunk`를 검색 친화 문서(`IndexDocument`)로 변환해 **Vector/Symbol/Domain** 인덱싱
- Lexical은 파일 기반(별도 스키마)으로 운영하고 결과를 `chunk_id`로 조인
- 모든 검색 결과를 `SearchHit(chunk_id)`로 표준화하여 fusion 가능하게 함

---

## Inputs / Outputs

- **Input**: `chunks: list[Chunk]`, `repo_id`, `snapshot_id` (+ repomap scores)
- **Output**: `SearchHit[]` (source=lexical/vector/symbol/domain/...)

---

## Key IDs

- **Primary**: `chunk_id`
- **IndexDocument**: `id == chunk_id`

---

## Implementation map

- Document schema: `src/contexts/multi_index/infrastructure/common/documents.py`
- Transformer: `src/contexts/multi_index/infrastructure/common/transformer.py`
- Orchestrator: `src/contexts/multi_index/infrastructure/service/index_orchestrator.py`

---

## Diagram

```mermaid
flowchart LR
  A[ChunkStore: Chunk] --> B[IndexDocumentTransformer]
  B --> C[Vector Index]
  B --> D[Symbol Index]
  B --> E[Domain Index]
  F[Lexical Index (files)] --> G[SearchHit(file,line)]
  C --> H[SearchHit(chunk_id)]
  D --> H
  E --> H
  G --> I[ChunkStore: file+line -> chunk_id]
  I --> H
```


