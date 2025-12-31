# Development Workflow - Multi-Repo Setup

**Updated**:   
**Setup**: codegraph + taint-rule-compiler 분리

---

## 📦 레포 구조

```
/Users/songmin/Documents/code-jo/semantica-v2/
├── codegraph/                    # 메인 분석 엔진
│   ├── src/                      # IR, DFG, QueryEngine
│   ├── cwe/test-suite/           # 통합 테스트
│   └── src/.../taint/rules/      → 심볼릭 링크
│
└── taint-rule-compiler/          # 규칙 엔진
    ├── src/trcr/                 # TaintRuleCompiler
    ├── rules/                    # atoms, policies (Source of Truth!)
    └── catalog/                  # CWE 메타데이터
```

---

## 🔧 작업 시나리오별 가이드

### Scenario 1: **Atoms/Policies 규칙 수정**

**위치**: `taint-rule-compiler/`

```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/taint-rule-compiler

# 1. atoms 수정
vim rules/atoms/python.atoms.yaml
# 예: sink.sql.new_db 추가

# 2. 테스트 (trcr 자체 테스트)
pytest tests/

# 3. codegraph에 자동 반영 (심볼릭 링크!)
cd ../codegraph
python3 cwe/run_test_suite.py --cwe CWE-89
# 자동으로 새 atoms 사용됨!
```

**핵심**: taint-rule-compiler만 수정, codegraph는 자동 반영

---

### Scenario 2: **CWE 테스트 케이스 추가**

**위치**: `codegraph/cwe/test-suite/`

```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph

# 1. 테스트 케이스 추가
mkdir cwe/test-suite/CWE918_SSRF
vim cwe/test-suite/CWE918_SSRF/bad_01.py
vim cwe/test-suite/CWE918_SSRF/good_01.py

# 2. 실행
python3 cwe/run_test_suite.py --cwe CWE-918

# 3. atoms 부족하면
cd ../taint-rule-compiler
vim rules/atoms/python.atoms.yaml
# sink.ssrf 추가
```

**핵심**: 테스트는 codegraph, 규칙은 taint-rule-compiler

---

### Scenario 3: **IRDocument/DFG 수정**

**위치**: `codegraph/src/`

```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph

# 1. IR 수정
vim src/contexts/code_foundation/infrastructure/ir/layered_ir_builder.py

# 2. 테스트
pytest tests/unit/ir/

# 3. 통합 확인
python3 cwe/run_test_suite.py --cwe CWE-89
```

**핵심**: IR/DFG는 codegraph 전용

---

### Scenario 4: **TaintRuleCompiler 엔진 수정**

**위치**: `taint-rule-compiler/src/trcr/`

```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/taint-rule-compiler

# 1. 엔진 수정
vim src/trcr/compiler/compiler.py
vim src/trcr/runtime/executor.py

# 2. 테스트
pytest tests/

# 3. 재설치
cd ../codegraph
pip install -e ../taint-rule-compiler --force-reinstall

# 4. 통합 확인
python3 cwe/run_test_suite.py --cwe CWE-89
```

**핵심**: 엔진 수정 후 재설치

---

## 🔄 Daily Workflow

### Morning (taint-rule-compiler 작업 시)

```bash
cd taint-rule-compiler

# atoms 추가
vim rules/atoms/python.atoms.yaml

# 테스트
pytest tests/

# Commit
git add rules/atoms/
git commit -m "feat: Add CWE-918 atoms"
```

### Afternoon (codegraph 통합 확인)

```bash
cd codegraph

# 자동 반영 확인 (심볼릭 링크!)
python3 cwe/run_test_suite.py --cwe CWE-918

# 통과하면 commit
git add cwe/test-suite/CWE918_SSRF/
git commit -m "test: Add CWE-918 test cases"
```

---

## 📋 Dependency Flow

```
1. taint-rule-compiler 수정
   ↓
2. codegraph 자동 참조 (symlink)
   ↓
3. codegraph 테스트
   ↓
4. 통과하면 양쪽 commit
```

---

## 🚨 주의사항

### DO
- ✅ atoms/policies는 taint-rule-compiler에서만 수정
- ✅ CWE 테스트는 codegraph에 추가
- ✅ 엔진 수정 후 pip install -e 재실행

### DON'T
- ❌ codegraph에서 rules/ 직접 수정 (심볼릭 링크!)
- ❌ atoms 중복 복사
- ❌ taint-rule-compiler 없이 codegraph 실행

---

## 🎯 Quick Commands

```bash
# atoms 수정
cd taint-rule-compiler && vim rules/atoms/python.atoms.yaml

# 테스트 확인
cd codegraph && python3 cwe/run_test_suite.py --cwe CWE-89

# 엔진 재설치
cd codegraph && pip install -e ../taint-rule-compiler --force-reinstall
```

---

**Clear workflow!** ✅

