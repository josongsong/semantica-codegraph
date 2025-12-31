# llm_arbitration (Deterministic Arbitration)

**
**Scope:** 여러 실행기/도구/LLM 경로를 “결정적으로” 조정하는 arbitration 계층  
**Source of Truth:** `src/contexts/llm_arbitration/`

---

## What it does

- 후보 실행 결과를 표준 envelope로 수집/정규화
- 규칙 기반(결정적)으로 선택/집계하여 최종 결과를 만든다

---

## Inputs / Outputs

- **Input**: 후보 결과(여러 실행기/분석기/리트리벌 결과)
- **Output**: 선택된 결과 + 메타(근거/점수/로그)


