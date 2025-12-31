# CodeGraph Quick Start Guide

**Updated**:   
**Level**: All users

---

## 🚀 5분 시작 가이드

### 1. 설치

```bash
pip install codegraph
```

### 2. 기본 사용

```bash
# 프로젝트 스캔
codegraph scan myproject/

# 출력
Found 3 vulnerabilities:
  - CWE-89 (SQL Injection) in views.py:45
  - CWE-79 (XSS) in templates.py:23
  - CWE-78 (Command Injection) in utils.py:67
```

### 3. 상세 분석

```bash
# Cross-file 분석 (정확)
codegraph scan myproject/ --deep

# SARIF 출력 (GitHub Security 연동)
codegraph scan myproject/ --format sarif -o results.sarif
```

---

## 📊 현재 성능

| 지표 | CodeGraph | Semgrep | Bandit |
|------|-----------|---------|--------|
| **F1 Score** | **100%** | 58.8% | 70.6% |
| **속도** | **/파일** |  |  |
| **False Positive** | **0%** | 22% | 11% |

**결과**: 가장 정확하고, 충분히 빠름! ✅

---

## 🎯 지원 기능

### CWE Coverage (5개 완성)
- ✅ CWE-77, 78: Command Injection
- ✅ CWE-79: XSS
- ✅ CWE-89: SQL Injection
- ✅ CWE-95: Eval Injection
- ✅ CWE-502: Deserialization
- ✅ CWE-918: SSRF

### 분석 모드
- **Fast**: Intra-file (빠름)
- **Deep**: Cross-file (정확)

### 출력 형식
- JSON
- SARIF (GitHub Security)
- Text

---

## 🔧 고급 사용

### Python API

```python
from codegraph import CodeGraphAnalyzer

analyzer = CodeGraphAnalyzer(
    cross_file=True,          # Cross-file 분석
    atoms="custom.yaml",      # 커스텀 rules
    confidence_threshold=0.7, # 신뢰도 임계값
)

result = analyzer.analyze("myproject/")

for vuln in result.vulnerabilities:
    print(f"{vuln.cwe}: {vuln.file}:{vuln.line}")
```

---

## 🏗️ 시스템 구조 (간단)

```
1. Python Code → IRDocument (DFG/CFG)
2. atoms.yaml → TaintRuleExecutableIR (SRCR)
3. Matching: Sources/Sinks 감지 (SRCR)
4. Path Finding: Source → Sink (QueryEngine)
5. Guard Filtering: False Positive 제거
6. Report: Vulnerabilities
```

---

## 📚 더 알아보기

- **Taint Analysis**: `../../modules/taint/architecture.md`
- **SRCR 설계**: (legacy) `_docs/_backlog/` 내 관련 문서 참고
- **벤치마크**: `benchmark/artifacts/reports/`
- **변경 이력**: `_docs/_changelog/`

---

**5분 만에 시작 가능!** 🚀

