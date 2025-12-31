# External Dependencies

**Updated**: 

---

## 🔗 External Projects

### taint-rule-compiler

**위치**: `/Users/songmin/Documents/code-jo/semantica-v2/taint-rule-compiler/`

**용도**: SRCR (Semantic Rule Compiler & Runtime)

**사용**:
```python
# Development (local)
import sys
sys.path.insert(0, '/Users/songmin/Documents/code-jo/semantica-v2/taint-rule-compiler/src')
from srcr import TaintRuleCompiler, TaintRuleRuntime

# Production (pip)
# pip install -e /Users/songmin/Documents/code-jo/semantica-v2/taint-rule-compiler
from srcr import TaintRuleCompiler, TaintRuleRuntime
```

**설치** (개발 모드):
```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
pip install -e ../taint-rule-compiler
```

---

## 📋 참조 방법

### Option 1: Editable Install (권장)

```bash
pip install -e /Users/songmin/Documents/code-jo/semantica-v2/taint-rule-compiler
```

**장점**: 
- taint-rule-compiler 수정 즉시 반영
- 별도 설치 불필요

---

### Option 2: Path 직접 추가

```python
# src/contexts/code_foundation/application/taint_analysis_service.py
import sys
from pathlib import Path

TAINT_RULE_PATH = Path("/Users/songmin/Documents/code-jo/semantica-v2/taint-rule-compiler/src")
if TAINT_RULE_PATH.exists():
    sys.path.insert(0, str(TAINT_RULE_PATH))

from srcr import TaintRuleCompiler, TaintRuleRuntime
```

---

## 🎯 권장 설정

**pyproject.toml**:
```toml
[tool.poetry.dependencies]
# Development: editable install
srcr = { path = "../taint-rule-compiler", develop = true }

# Production: version
# srcr = "^1.0.0"
```

---

**현재 프로젝트**: codegraph  
**외부 프로젝트**: taint-rule-compiler  
**관계**: codegraph → taint-rule-compiler (의존)

