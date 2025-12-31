# Taint - Runtime

**
**Scope:** taint 실행 모델(DFG/Query) + 인덱싱/조인 관점  

---

## Execution Model

- IR/Graph에서 source/sink를 매칭하고, DFG 기반 경로를 탐색해 vulnerabilities를 구성
- 상위 계층에서는 결과를 `chunk_id` 기준으로 통합(리포트/컨텍스트 빌드)

---

## Dependencies

- DFG/CFG/CallGraph 등 기본 IR 산출물이 품질에 직접 영향
- DFG 요구사항은 `dfg-requirements.md`를 단일 소스로 둠


