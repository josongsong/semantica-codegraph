# Modules (Deep Dive)

**
**Scope:** 모듈별 “상세 스펙/운영/테스트” 문서 모음  

---

## 규격 (권장)

각 모듈은 아래 형태를 권장합니다.

```
_docs/modules/<module>/
├── README.md              # 1페이지 요약 + TOC + 링크
├── architecture.md        # 구성요소/다이어그램/흐름
├── runtime.md             # 모드/증분/캐시/성능
├── interfaces.md          # 포트/어댑터/API/계약
├── testing.md             # 테스트 전략/필수 시나리오
└── troubleshooting.md     # 운영/장애 대응 (있으면)
```

---

## Modules

### Indexing (`indexing/`)

- **Reading Order**
  - `indexing/README.md`
  - `indexing/pipeline/pipelines-quick-ref.md`
  - `indexing/pipeline/9-stage-pipeline.md`
- **Key 3**
  - `indexing/pipeline/IR_HCG.md` (IR→Graph→HCG/Chunk 연결)
  - `indexing/ops/configuration.md` (운영 설정)
  - `indexing/verification/VERIFICATION-RESULT.md` (검증 결과/리스크)

### Query DSL (`query-dsl/`)

- **Reading Order**
  - `query-dsl/interfaces.md`
  - `query-dsl/architecture.md`
  - `query-dsl/runtime.md`
- **Key 3**
  - `query-dsl/interfaces.md`
  - `query-dsl/architecture.md`
  - `query-dsl/testing.md`

### Taint (`taint/`)

- **Reading Order**
  - `taint/README.md`
  - `taint/architecture.md`
  - `taint/dfg-requirements.md`
- **Key 3**
  - `taint/architecture.md`
  - `taint/dfg-requirements.md`
  - `taint/testing.md`

### Codegen Loop (`codegen-loop/`)

- **Reading Order**
  - `codegen-loop/README.md`
  - `codegen-loop/architecture.md`
  - `codegen-loop/shadowfs.md`
- **Key 3**
  - `codegen-loop/architecture.md`
  - `codegen-loop/shadowfs.md`
  - `codegen-loop/deep-dive.md`


