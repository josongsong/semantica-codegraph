# Multi-Repo Structure

**
**Scope:** 멀티레포/연동 구조(현재 상태)  
**Audience:** 개발자/운영자  
**Source of Truth:** 레포 구조 + build/runtime 설정

---

## Table of Contents

- 레포 구조
- 연결 방식
- 운영 원칙
- 링크

---

## 🎯 레포 구조

```
semantica-v2/
├── codegraph/                    # 메인 분석 엔진
│   ├── src/
│   │   ├── ir/                   # IRDocument, DFG, CFG
│   │   ├── query/                # QueryEngine (Q.DSL)
│   │   └── taint/
│   │       ├── rules/            → 심볼릭 링크
│   │       └── adapters/         # TRCR 연결
│   │
│   └── cwe/test-suite/           # 통합 테스트
│
└── taint-rule-compiler/          # 규칙 엔진 (독립)
    ├── src/trcr/                 # Compiler, Runtime
    ├── rules/                    # atoms, policies (Source of Truth)
    └── catalog/                  # CWE 메타데이터
```

---

## 🔗 연결 방식

### 심볼릭 링크
```bash
codegraph/src/.../taint/rules
  → taint-rule-compiler/rules
```

**장점**:
- Single source of truth
- 자동 동기화
- 중복 없음

### pip 의존성
```bash
cd codegraph
pip install -e ../taint-rule-compiler
```

---

## 📋 작업별 위치

| 작업 | 레포 | 파일 |
|------|------|------|
| **Atoms 추가** | taint-rule-compiler | rules/atoms/python.atoms.yaml |
| **CWE 테스트** | codegraph | cwe/test-suite/CWE*/ |
| **IR/DFG** | codegraph | src/infrastructure/ir/ |
| **TaintRuleCompiler** | taint-rule-compiler | src/trcr/compiler/ |
| **통합 테스트** | codegraph | cwe/run_test_suite.py |

---

## 🔄 Workflow

**1. Atoms 수정**:
```bash
cd taint-rule-compiler
vim rules/atoms/python.atoms.yaml
pytest tests/
git commit
```

**2. codegraph 확인**:
```bash
cd codegraph
python3 cwe/run_test_suite.py --cwe CWE-89
# 자동으로 새 atoms 사용!
```

**3. 엔진 수정 시**:
```bash
cd taint-rule-compiler
vim src/trcr/runtime/executor.py
cd ../codegraph
pip install -e ../taint-rule-compiler --force-reinstall
```

---

## 🎯 Quick Reference

**Atoms 수정**: taint-rule-compiler  
**테스트 확인**: codegraph  
**자동 동기화**: 심볼릭 링크 ✅

**상세**: `_docs/system-handbook/DEVELOPMENT-WORKFLOW.md`

