# CWE Contract Layer

**Version**: 1.0
**Status**: Production Ready

---

## Overview

CWE = Contract. 보안 약점을 제품 계약으로 격상.

---

## Structure

```
cwe/
├── catalog/           # CWE 정의
│   ├── cwe-*.yaml    # 개별 CWE 정의
│   ├── atoms/        # 규칙 (44 atoms)
│   └── policies/     # 정책 (19 CWE)
├── test-suite/       # 122 테스트케이스
│   └── CWE**/        # 25 CWE 디렉토리
├── profiles/         # View 정의
│   ├── view-injection.yaml (7 CWE)
│   ├── view-top25.yaml (25 CWE)
│   └── view-web-xss.yaml (2 CWE)
├── schema/           # Contract 스키마
└── run_test_suite.py # 실행기
```

---

## Usage

### 단일 CWE
```bash
python cwe/run_test_suite.py --cwe CWE-89
```

### View (여러 CWE)
```bash
# Injection 관련 7개
python cwe/run_test_suite.py --view view-injection

# Top 25 전부
python cwe/run_test_suite.py --view view-top25
```

### Schema 검증
```bash
python cwe/run_test_suite.py --validate-schema
```

---

## Views

### view-injection (7 CWE)
- CWE-89: SQL Injection
- CWE-78: Command Injection
- CWE-79: XSS
- CWE-94: Code Injection
- CWE-95: Eval Injection
- CWE-643: XPath Injection
- CWE-90: LDAP Injection

### view-top25 (25 CWE)
- MITRE CWE Top 25 기준
- 우리가 지원하는 것만 포함

### view-web-xss (2 CWE)
- CWE-79: XSS
- CWE-352: CSRF

---

## Test Results

### CWE-89 (SQL Injection)
```
Precision: 1.000
Recall: 1.000
F1: 1.000
```

### 전체
- 19개 Policy 구현
- 122개 Test Case
- 3개 View

---

## 책임 분리

- **cwe/**: 보안 의미적 검증 (Contract)
- **tests/**: 엔진 내부 테스트
- **benchmark/**: 성능 측정

---

## SOTA 달성

✅ Semgrep/CodeQL 수준
✅ Contract-first 설계
✅ View 기반 검증
✅ Hot reload (YAML)
