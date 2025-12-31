# System Handbook (Living Doc)

`_docs/system-handbook/`는 **이 프로젝트의 현재 시스템 상태를 요약하는 “핸드북 홈”** 입니다.

---

## Table of Contents (핸드북 인덱스)

- 최상위 인덱스: `_docs/HANDBOOK.md`
- 이 디렉토리(시스템 핸드북): `_docs/system-handbook/`
- 모듈 상세(Deep Dive): `_docs/modules/`
- 사용/운영 가이드: `_docs/system-handbook/guides/`
- 설계 근거/프로토콜/실측: `_docs/system-handbook/design/`
- 변경 이력: `_docs/_changelog/`
- backlog(참고용): `_docs/_backlog/`
- roadmap(참고용): `_docs/_roadmap/`

---

## Modules (모듈별 요약 바로가기)

- 인덱스: `_docs/system-handbook/modules/README.md`
- `code_foundation`: `_docs/system-handbook/modules/code-foundation.md`
- `analysis_indexing`: `_docs/system-handbook/modules/analysis-indexing.md`
- `multi_index`: `_docs/system-handbook/modules/multi-index.md`
- `retrieval_search`: `_docs/system-handbook/modules/query-and-retrieval.md`
- `query-dsl`: `_docs/system-handbook/modules/query-and-retrieval.md`
- `reasoning_engine`: `_docs/system-handbook/modules/reasoning-engine.md`
- `repo_structure`: `_docs/system-handbook/modules/repo-structure.md`
- `security_analysis`: `_docs/system-handbook/modules/security-analysis.md`
- `session_memory`: `_docs/system-handbook/modules/session-memory.md`
- `codegen_loop`: `_docs/system-handbook/modules/codegen-loop.md`
- `agent`: `_docs/system-handbook/modules/agent.md`
- `agent_code_editing`: `_docs/system-handbook/modules/agent-code-editing.md`
- `llm_arbitration`: `_docs/system-handbook/modules/llm-arbitration.md`
- `replay_audit`: `_docs/system-handbook/modules/replay-audit.md`
- `shared_kernel`: `_docs/system-handbook/modules/shared-kernel.md`
- `verification`: `_docs/system-handbook/modules/verification.md`
- `infra`: `_docs/system-handbook/modules/infra.md`

---

## 읽는 순서 (System Handbook)

1. `codegraph-full-system-v3.md`  
   - 전체 구조/레이어/IR→HCG→Chunk→Indexing “한 장”
2. `static-analysis-techniques.md`  
   - 정적 분석 기법별 구현 상태 + 테스트 레퍼런스 인덱스
3. `static-analysis-coverage.md`  
   - 산업/학계 대비 커버리지 매트릭스
4. `type-inference-system.md`  
   - 타입 추론 시스템 현황
5. `15-multi-repo-structure.md`  
   - 멀티레포/연동 구조

---

## Out of Scope (여기 두지 않음)

- **모듈 상세 스펙(Deep Dive)**: `_docs/modules/`
- **변경 이력**: `_docs/_changelog/`


