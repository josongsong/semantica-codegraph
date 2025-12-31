# security_analysis (취약점 탐지/리포트)

**
**Scope:** 보안 분석 결과 생성(쿼리/taint 기반)과 리포팅  
**Source of Truth:** `src/contexts/security_analysis/` + taint/query 계층

---

## What it does

- CWE 정책 기반으로 source→sink 경로 탐지(DFG/QueryEngine)
- 결과를 리포트 포맷(JSON/SARIF/Text)으로 변환

---

## Inputs / Outputs

- **Input**: IR/Graph + rules/policies + 실행 모드(fast/deep)
- **Output**: findings(vulnerabilities) + reports

---

## Diagram

```mermaid
flowchart LR
  A[IR/Graph] --> B[Rules/Policies]
  B --> C[Query/Taint Execution]
  C --> D[Findings]
  D --> E[Reports (JSON/SARIF/Text)]
```


