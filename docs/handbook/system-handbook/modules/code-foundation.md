# code_foundation (IR / Graph / HCG)

**
**Scope:** 코드 파운데이션 레이어의 현재 동작/산출물/조인 키  
**Source of Truth:** `src/contexts/code_foundation/`

---

## What it does

- Tree-sitter 기반 파싱 → **IRDocument(Structural IR)** 생성
- CFG/DFG/Type/Signature 등 **Semantic IR** 확장
- GraphDocument(heterogeneous graph) 생성 + HCG/Chunk 연결을 위한 매핑 생성

---

## Inputs / Outputs

- **Input**: repo snapshot + source files
- **Output**
  - `IRDocument` (Structural IR)
  - `semantic_ir` (CFG/DFG/Type/Signature)
  - `GraphDocument`
  - `Chunk` + `ChunkToGraph` / `ChunkToIR` 매핑(ChunkStore에 저장)

---

## Key IDs (조인 키)

- **`chunk_id`**: `chunk:{repo_id}:{kind}:{fqn}` (RAG/검색 통합 조인 키)
- **`snapshot_id`**: 스냅샷/커밋/브랜치 식별자(인덱스 일관성 키)

---

## Implementation map (핵심 경로)

- Parsing: `src/contexts/code_foundation/infrastructure/parsing/`
- IR generators: `src/contexts/code_foundation/infrastructure/generators/`
- IR models: `src/contexts/code_foundation/infrastructure/ir/`
- **Layered IR Builder**: `src/contexts/code_foundation/infrastructure/ir/layered_ir_builder.py`
  - 9-layer 레이어드 아키텍처 (Structural → Semantic → Analysis → Retrieval)
  - 각 레이어별 독립적 빌드 및 캐싱
  - 성능 최적화: 병렬 처리, 증분 업데이트, 메모리 효율
- **IR Cache** (2025-12-21): `src/contexts/code_foundation/infrastructure/ir/cache.py`
  - L12+ SOTA: msgpack + xxhash + struct header + atomic write
  - 성능: 27.7% 개선 (Structural IR)
  - 증분: Content-based invalidation
  - 테스트: 67 unit tests
- DFG/SSA: `src/contexts/code_foundation/infrastructure/dfg/`
- Chunking: `src/contexts/code_foundation/infrastructure/chunk/`

---

## Diagram

```mermaid
flowchart LR
  A[Source Files] --> B[Tree-sitter AST]
  B --> C[IRDocument (Structural IR)]
  C --> D[Semantic IR (CFG/DFG/Type)]
  D --> E[GraphDocument]
  E --> F[Chunk Builder]
  F --> G[ChunkStore: Chunk + mappings]
```

---

## Links

- IR/HCG 상세: `_docs/modules/indexing/pipeline/IR_HCG.md`


