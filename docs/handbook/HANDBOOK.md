# CodeGraph Handbook

이 문서는 **이 레포의 “현재 상태”를 이해하고, 어디서 무엇을 찾아야 하는지**를 안내하는 최상위 인덱스입니다.

---

## Table of Contents

- **1) System Overview (현재 시스템 요약)**
  - `_docs/system-handbook/`
- **2) Modules (모듈별 상세)**
  - `_docs/modules/`
- **3) Guides (사용/운영 가이드)**
  - `_docs/system-handbook/guides/`
- **4) Design (설계 근거/리뷰/플랜)**
  - `_docs/system-handbook/design/`
- **5) Changelog**
  - `_docs/_changelog/`
- **6) Backlog (비-리빙/역사적 문서, 참고용)**
  - `_docs/_backlog/`
- **7) Roadmap (계획/트래킹, 참고용)**
  - `_docs/_roadmap/`

---

## 1) System Overview (현재 시스템 요약)

> “living doc”의 기준: **현재 시스템의 현재 상태**만 요약합니다.

- `system-handbook/codegraph-full-system-v3.md`: 전체 시스템 한 장 요약(레이어/IR→HCG→Chunk→Indexing 포함)
- `system-handbook/static-analysis-techniques.md`: 정적 분석 기법별 구현 상태 + 테스트 레퍼런스 인덱스
- `system-handbook/static-analysis-coverage.md`: 산업/학계 대비 커버리지 매트릭스
- `system-handbook/type-inference-system.md`: 타입추론 시스템 현황
- `system-handbook/15-multi-repo-structure.md`: 멀티레포/연동 구조

---

## 2) Modules (모듈별 상세)

- **Indexing**: `_docs/modules/indexing/`
  - Pipeline/IR_HCG: `_docs/modules/indexing/pipeline/`
  - Ops: `_docs/modules/indexing/ops/`
  - Verification: `_docs/modules/indexing/verification/`
- **Query DSL**: `_docs/modules/query-dsl/`
- **Taint**: `_docs/modules/taint/`
  - 엔진: `architecture.md`
  - DFG 요구사항: `dfg-requirements.md`
- **Codegen Loop**: `_docs/modules/codegen-loop/` (`deep-dive.md`)

---

## 3) Guides (사용/운영 가이드)

- Quick Start: `_docs/system-handbook/guides/00-QUICK-START.md`
- Tool Catalog: `_docs/system-handbook/guides/tool-catalog.md`

---

## 4) Design (설계 근거/리뷰/플랜)

> “왜 이렇게 설계했는가”가 필요할 때만 봅니다. system-overview에는 넣지 않습니다.

- `_docs/system-handbook/design/indexing-optimization-plan.md`
- `_docs/system-handbook/design/mcp-sota-protocol.md`

---

## 5) Changelog

- `_docs/_changelog/` 디렉토리

---

## 6) Backlog (참고용)

- `_docs/_backlog/` 디렉토리

---

## 7) Roadmap (참고용)

- `_docs/_roadmap/` 디렉토리


