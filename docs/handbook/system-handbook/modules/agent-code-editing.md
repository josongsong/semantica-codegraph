# agent_code_editing (편집/패치 엔진)

**
**Scope:** 에이전트 코드 편집(atomic edit/FIM/refactoring) 어댑터/실행 계층  
**Source of Truth:** `src/contexts/agent_code_editing/`

---

## What it does

- 에이전트의 코드 변경을 “편집 전략/정밀 패치” 형태로 제공
- refactoring/atomic edit/FIM 류의 편집 어댑터를 모듈로 분리

---

## Inputs / Outputs

- **Input**: 편집 요청(파일/범위/의도) + 컨텍스트
- **Output**: patch/edits + 적용 결과


