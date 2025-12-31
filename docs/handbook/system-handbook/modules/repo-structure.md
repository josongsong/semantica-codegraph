# repo_structure (RepoMap / 중요도 / 구조 추출)

**
**Scope:** 레포 구조 요약(RepoMap), 중요도/네비게이션 신호 생성  
**Source of Truth:** `src/contexts/repo_structure/`

---

## What it does

- 파일/심볼 관계로 RepoMap 스냅샷 생성
- chunk 중요도(importance) 등 랭킹 신호 제공 → 인덱싱/리트리벌에 주입

---

## Inputs / Outputs

- **Input**: chunk/graph 정보
- **Output**: RepoMapSnapshot(importance, summaries 등)

---

## Diagram

```mermaid
flowchart LR
  A[Chunks/Graph] --> B[RepoMap Builder]
  B --> C[RepoMapSnapshot]
  C --> D[IndexDocument enrichment]
```


