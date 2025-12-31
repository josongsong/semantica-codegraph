# codegen_loop (ShadowFS + Code/Test Gen)

**
**Scope:** IDE/에이전트 편집을 ShadowFS로 안전하게 관리하고 코드/테스트 생성 루프를 수행  
**Source of Truth:** `src/contexts/codegen_loop/`

---

## What it does

- ShadowFS 트랜잭션으로 파일 변경을 안전하게 적용/롤백
- 생성된 패치의 품질/테스트 적합성 검증 루프 수행

---

## Inputs / Outputs

- **Input**: 목표 작업(이슈/요구사항) + 컨텍스트(HCG/검색 결과)
- **Output**: patch set + (선택) generated tests + verification 결과

---

## Diagram

```mermaid
flowchart LR
  A[Goal] --> B[Context (Search/HCG)]
  B --> C[Patch Proposal]
  C --> D[ShadowFS Transaction]
  D --> E[Verify/Tests]
  E -->|ok| F[Commit]
  E -->|fail| C
```

---

## Links

- 상세: `_docs/modules/codegen-loop/deep-dive.md`


