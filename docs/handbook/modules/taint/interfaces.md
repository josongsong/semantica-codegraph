# Taint - Interfaces

**
**Scope:** 외부 사용 관점의 taint 분석 인터페이스 요약  

---

## Entry

- `TaintAnalysisService` (애플리케이션 레이어 엔트리)
  - IRDocument/Graph 기반으로 vulnerabilities/findings 생성

---

## Inputs / Outputs

- **Input**: IR/Graph + rules/policies + 실행 모드(fast/deep)
- **Output**: vulnerabilities/findings + 리포트 변환 가능한 구조

---

## Links

- 상세 구조: `architecture.md`

