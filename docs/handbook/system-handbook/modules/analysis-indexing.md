# analysis_indexing (9-stage pipeline)

**
**Scope:** 변경 감지 → 파싱/IR/그래프/청크/RepoMap/인덱싱의 현재 파이프라인  
**Source of Truth:** `src/contexts/analysis_indexing/`

---

## What it does

- repo snapshot 기준으로 **전체/증분 인덱싱** 파이프라인 실행
- Stage 산출물들을 연결해 **Chunk → Multi-Index**까지 일관되게 갱신

---

## Stages (요약)

- Git/Discovery → Parsing → IR → Semantic IR → Graph → **Chunk** → RepoMap → **Indexing**

### Performance Optimization (2025-12-21)

**P0: Structural IR Cache (L12+ SOTA)**
- 성능: 27.7% 개선 (2.74s → 1.98s, 60 files)
- 기술: msgpack + xxhash + struct header + atomic write
- 증분: Content-based invalidation (완전 대응)
- 테스트: 67 unit + integration tests
- 상태: ✅ Production-ready

**구현 위치**:
- `src/contexts/code_foundation/infrastructure/ir/cache.py`
- `src/contexts/code_foundation/infrastructure/ir/layered_ir_builder.py`

---

## Inputs / Outputs

- **Input**: `repo_id`, `snapshot_id`, repo_path (+ change_set for incremental)
- **Output**: `chunk_ids` (StageContext), indexes updated (lexical/vector/symbol/domain/graph)

---

## Key join points

- **ChunkStage**: `ChunkBuilder.build(...)` → `chunk_id` 리스트 생성 + ChunkStore 저장
- **IndexingStage**: `Chunk` → `IndexDocument(id==chunk_id)` 변환 후 vector/symbol/domain 인덱싱
- **Lexical**: 파일 기반 hit → `file_path+line → chunk_id`로 조인

---

## Implementation map (핵심 경로)

- Stages: `src/contexts/analysis_indexing/infrastructure/stages/`
  - `chunk_stage.py`, `repomap_stage.py`, `indexing_stage.py`

---

## Diagram

```mermaid
flowchart LR
  A[ChangeDetector] --> B[Parsing]
  B --> C[IR]
  C --> D[Semantic IR]
  D --> E[Graph]
  E --> F[Chunk]
  F --> G[RepoMap]
  G --> H[Indexing (multi-index)]
```

---

## Links

- 파이프라인 상세: `_docs/modules/indexing/pipeline/9-stage-pipeline.md`
- Quick ref: `_docs/modules/indexing/pipeline/pipelines-quick-ref.md`


