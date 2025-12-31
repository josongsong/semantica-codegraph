# Repository Migration Plan - 현재 구조 기반

**Date**: 2025-12-28
**Status**: Practical Migration Plan

---

## 현재 상황 (As-Is)

```
packages/
├── codegraph-rust/              # 🦀 Rust 신버전 (23,471 LOC)
│   ├── codegraph-ir/            # Taint, SMT, Cost
│   ├── codegraph-orchestration/
│   └── codegraph-storage/
│
├── codegraph-engine/            # 🐍 Python IR 구버전 (DEPRECATED)
│   └── code_foundation/
│       └── infrastructure/
│           ├── ir/              # LayeredIRBuilder (deprecated)
│           ├── analyzers/       # interprocedural_taint.py (deprecated)
│           └── parsers/         # ✅ Keep (tree-sitter)
│
├── codegraph-taint/             # 🐍 Python Taint 구버전 (중복!)
│   └── codegraph_taint/         # Python taint implementation
│
├── codegraph-analysis/          # 🐍 Analysis (이미 존재!)
│   └── codegraph_analysis/
│       ├── security_analysis/   # 일부 보안 분석
│       └── verification/
│
├── codegraph-security/          # 🐍 Security (중복!)
│   └── codegraph_security/      # Security analysis
│
├── codegraph-parsers/           # 📝 Parsers (이미 존재!)
│   └── tree-sitter parsers
│
├── codegraph-shared/            # 🔧 Infrastructure ✅
├── codegraph-runtime/           # 🚀 Runtime ✅
├── codegraph-agent/             # 🤖 Agent ✅
├── codegraph-ml/                # 🧠 ML ✅
├── codegraph-search/            # 🔍 Search ✅
└── security-rules/              # 📋 Rules (중복?)
```

**문제점**:
1. ❌ **중복**: `codegraph-taint`, `codegraph-security`, `codegraph-analysis`, `security-rules` 기능 중복
2. ❌ **혼재**: Rust (신) + Python (구) taint analysis 공존
3. ❌ **불명확**: 어떤 패키지를 써야 할지 혼란

---

## 목표 (To-Be)

```
packages/
├── codegraph-rust/              # 🦀 Rust Engine (Core Algorithms)
│   ├── codegraph-ir/            # ✅ L24 Taint, L27 SMT+Cost, L31 Dependency
│   ├── codegraph-orchestration/ # ✅ Pipeline orchestration
│   └── codegraph-storage/       # ✅ Storage layer
│
├── codegraph-analysis/          # 🔌 Python Plugins (Domain Rules)
│   └── codegraph_analysis/
│       ├── security/            # L22-L23 (통합)
│       │   ├── crypto.py
│       │   ├── auth.py
│       │   └── framework_adapters/
│       ├── api_misuse/          # L29
│       ├── patterns/            # L28
│       └── coverage/            # L32
│
├── codegraph-parsers/           # 📝 Tree-sitter parsers ✅
│
├── codegraph-shared/            # 🔧 Infrastructure ✅
├── codegraph-runtime/           # 🚀 Runtime ✅
├── codegraph-agent/             # 🤖 Agent ✅
├── codegraph-ml/                # 🧠 ML ✅
└── codegraph-search/            # 🔍 Search ✅

# Deprecated/Remove:
├── codegraph-engine/            # ⚠️ REMOVE (IR, analyzers)
├── codegraph-taint/             # ⚠️ REMOVE (Rust로 대체)
├── codegraph-security/          # ⚠️ MERGE → codegraph-analysis/security/
└── security-rules/              # ⚠️ MERGE → codegraph-analysis/security/patterns/
```

**원칙**:
1. ✅ **Rust = Engine**: 알고리즘만
2. ✅ **Python = Plugins**: 도메인 룰만
3. ✅ **No Duplication**: 중복 제거

---

## Migration Steps

### Phase 1: Consolidate Python Plugins (Week 1-2)

**Goal**: Python 분산된 패키지 통합 → `codegraph-analysis`

#### Step 1.1: Merge Security Packages

```bash
# codegraph-security → codegraph-analysis/security/
mkdir -p packages/codegraph-analysis/codegraph_analysis/security/{crypto,auth,patterns}

# Move crypto patterns
mv packages/codegraph-security/codegraph_security/crypto_* \
   packages/codegraph-analysis/codegraph_analysis/security/crypto/

# Move auth patterns
mv packages/codegraph-security/codegraph_security/auth_* \
   packages/codegraph-analysis/codegraph_analysis/security/auth/

# Move security-rules → patterns
mv packages/security-rules/* \
   packages/codegraph-analysis/codegraph_analysis/security/patterns/
```

#### Step 1.2: Extract Framework Adapters

```bash
# From codegraph-engine (if any Django/Flask specific code)
mkdir -p packages/codegraph-analysis/codegraph_analysis/security/framework_adapters

# Extract Django taint sources/sinks
# packages/codegraph-analysis/codegraph_analysis/security/framework_adapters/django.py
cat > packages/codegraph-analysis/codegraph_analysis/security/framework_adapters/django.py << 'EOF'
"""Django-specific security patterns."""

DJANGO_TAINT_SOURCES = [
    "request.GET",
    "request.POST",
    "request.FILES",
    "request.COOKIES",
]

DJANGO_TAINT_SINKS = [
    "cursor.execute",
    "cursor.executemany",
    "QuerySet.raw",
    "QuerySet.extra",
    "render_to_response",  # XSS if not escaped
]

DJANGO_SANITIZERS = [
    "django.utils.html.escape",
    "django.utils.html.escapejs",
    "django.db.models.Q",  # ORM sanitizes
]
EOF
```

#### Step 1.3: Update codegraph-analysis Structure

```bash
# Final structure
packages/codegraph-analysis/
├── codegraph_analysis/
│   ├── __init__.py
│   ├── plugin.py                    # Base plugin interface
│   ├── registry.py                  # Plugin registry
│   │
│   ├── security/                    # L22-L23 (merged)
│   │   ├── __init__.py
│   │   ├── crypto.py                # From codegraph-security
│   │   ├── auth.py                  # From codegraph-security
│   │   ├── patterns/                # From security-rules
│   │   │   ├── crypto.yaml
│   │   │   ├── auth.yaml
│   │   │   └── injection.yaml
│   │   └── framework_adapters/
│   │       ├── django.py
│   │       ├── flask.py
│   │       └── fastapi.py
│   │
│   ├── api_misuse/                  # L29 (new)
│   │   ├── __init__.py
│   │   ├── stdlib.py
│   │   └── patterns/
│   │       ├── file_ops.yaml
│   │       ├── network.yaml
│   │       └── database.yaml
│   │
│   ├── patterns/                    # L28 (new)
│   │   ├── __init__.py
│   │   ├── design_patterns.py
│   │   └── anti_patterns.py
│   │
│   └── coverage/                    # L32 (new)
│       ├── __init__.py
│       └── pytest_integration.py
│
├── tests/
└── pyproject.toml
```

---

### Phase 2: Remove Deprecated Python Analysis (Week 3-4)

**Goal**: Python taint/complexity 제거 (Rust로 대체됨)

#### Step 2.1: Remove codegraph-taint

```bash
# Verify no dependencies
rg "from codegraph_taint" packages/ tests/ server/

# If clear, remove
rm -rf packages/codegraph-taint/

# Update pyproject.toml dependencies
# Remove codegraph-taint from all packages
```

#### Step 2.2: Deprecate codegraph-engine Analyzers

```bash
# Remove analyzers (taint, complexity)
rm -rf packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/analyzers/

# Keep only parsers
ls packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/
# Should have: parsers/ only

# Move parsers if needed (already in codegraph-parsers?)
# Check if duplicate
diff -r packages/codegraph-engine/.../parsers/ \
        packages/codegraph-parsers/codegraph_parsers/
```

#### Step 2.3: Remove security-rules (merged to codegraph-analysis)

```bash
# Already merged in Step 1.2
rm -rf packages/security-rules/
```

---

### Phase 3: Update Dependencies (Week 5-6)

**Goal**: 모든 패키지가 Rust engine + Python plugins 사용

#### Step 3.1: Update codegraph-runtime

```python
# packages/codegraph-runtime/codegraph_runtime/orchestrator.py

from codegraph_ir import IRIndexingOrchestrator, TaintConfig
from codegraph_analysis.registry import PluginRegistry
from codegraph_analysis.security import CryptoPlugin, AuthPlugin
from codegraph_analysis.api_misuse import APIMisusePlugin

class AnalysisOrchestrator:
    def __init__(self):
        # Rust engine
        self.rust_engine = IRIndexingOrchestrator(
            enable_taint=True,      # L24: Rust IFDS/IDE
            enable_complexity=True, # L27: Rust SMT+Cost
            enable_cross_file=True, # L31: Rust
        )

        # Python plugins
        self.plugins = PluginRegistry()
        self.plugins.register(CryptoPlugin())      # L22
        self.plugins.register(AuthPlugin())        # L23
        self.plugins.register(APIMisusePlugin())   # L29

    def analyze(self, repo_path: str):
        # 1. Rust engine
        rust_result = self.rust_engine.execute(repo_path)

        # 2. Python plugins
        plugin_findings = self.plugins.run_all(rust_result.ir_documents)

        # 3. Merge
        return {
            "taint": rust_result.taint_findings,      # From Rust
            "complexity": rust_result.complexity,     # From Rust
            "security": plugin_findings["security"],  # From Python
            "api_misuse": plugin_findings["api_misuse"],
        }
```

#### Step 3.2: Update pyproject.toml

```toml
# packages/codegraph-runtime/pyproject.toml
[project]
dependencies = [
    "codegraph-ir>=2.1.0",          # Rust engine
    "codegraph-analysis>=2.1.0",    # Python plugins
    "codegraph-shared>=2.1.0",
]

# Remove old dependencies
# - codegraph-taint  (removed)
# - codegraph-security  (merged to codegraph-analysis)
```

---

### Phase 4: Testing & Validation (Week 7-8)

#### Step 4.1: Update Tests

```bash
# Update imports in tests
find tests/ -name "*.py" -exec sed -i '' \
  's/from codegraph_taint/from codegraph_ir/g' {} \;

find tests/ -name "*.py" -exec sed -i '' \
  's/from codegraph_security/from codegraph_analysis.security/g' {} \;
```

#### Step 4.2: Integration Tests

```python
# tests/integration/test_rust_python_integration.py

import codegraph_ir
from codegraph_analysis.registry import PluginRegistry
from codegraph_analysis.security import CryptoPlugin

def test_rust_taint_analysis():
    """Test Rust taint analysis (L24)."""
    config = codegraph_ir.TaintConfig(
        enable_interprocedural=True,
        enable_path_sensitive=True,
    )

    result = codegraph_ir.taint_analysis(
        repo_path="/repo",
        config=config,
        sources=["request.GET"],
        sinks=["eval"],
    )

    assert len(result.paths) > 0

def test_python_crypto_plugin():
    """Test Python crypto plugin (L22)."""
    plugin = CryptoPlugin()

    # Mock IR with MD5 usage
    ir = create_test_ir_with_md5()

    findings = plugin.analyze(ir)

    assert len(findings) > 0
    assert findings[0].category == "weak-crypto"
```

#### Step 4.3: Benchmark

```python
# benchmark/compare_rust_vs_python.py

import time
import codegraph_ir

def benchmark_taint_rust():
    start = time.time()

    result = codegraph_ir.taint_analysis(
        repo_path="/large_repo",
        config=codegraph_ir.TaintConfig(enable_interprocedural=True),
    )

    duration = time.time() - start
    print(f"Rust Taint: {duration:.2f}s")
    return duration

# Expected: Rust 10-50x faster than old Python
```

---

## Deletion Checklist

### Remove These Packages

- [ ] **codegraph-taint** (완전 삭제)
  ```bash
  rm -rf packages/codegraph-taint/
  ```

- [ ] **codegraph-security** (merge 후 삭제)
  ```bash
  # After merging to codegraph-analysis
  rm -rf packages/codegraph-security/
  ```

- [ ] **security-rules** (merge 후 삭제)
  ```bash
  # After merging to codegraph-analysis
  rm -rf packages/security-rules/
  ```

- [ ] **codegraph-engine analyzers** (일부 삭제)
  ```bash
  # Keep parsers, remove analyzers
  rm -rf packages/codegraph-engine/.../analyzers/interprocedural_taint.py
  rm -rf packages/codegraph-engine/.../analyzers/path_sensitive_taint.py
  rm -rf packages/codegraph-engine/.../analyzers/cost/
  rm packages/codegraph-engine/.../ir/layered_ir_builder.py
  ```

### Keep These (Refactor)

- [ ] **codegraph-parsers** ✅
  - Tree-sitter parsers
  - Check if duplicate with codegraph-engine/parsers

- [ ] **codegraph-engine/parsers** → **codegraph-parsers**
  ```bash
  # If duplicate, remove from codegraph-engine
  # Keep only in codegraph-parsers
  ```

---

## Final Structure (v2.2.0)

```
packages/
├── codegraph-rust/              # 🦀 Rust Engine
│   ├── codegraph-ir/            # Taint, SMT, Cost
│   ├── codegraph-orchestration/
│   └── codegraph-storage/
│
├── codegraph-analysis/          # 🔌 Python Plugins (consolidated)
│   └── codegraph_analysis/
│       ├── security/            # L22-L23 (merged from 3 packages)
│       ├── api_misuse/          # L29
│       ├── patterns/            # L28
│       └── coverage/            # L32
│
├── codegraph-parsers/           # 📝 Parsers (tree-sitter)
│
├── codegraph-shared/            # 🔧 Infrastructure
├── codegraph-runtime/           # 🚀 Runtime (uses Rust + Plugins)
├── codegraph-agent/             # 🤖 Agent
├── codegraph-ml/                # 🧠 ML
└── codegraph-search/            # 🔍 Search

# Removed:
# - codegraph-taint (→ Rust)
# - codegraph-security (→ codegraph-analysis/security)
# - security-rules (→ codegraph-analysis/security/patterns)
# - codegraph-engine/analyzers (→ Rust)
```

---

## Dependencies Graph (After Migration)

```
codegraph-runtime
    ├── codegraph-ir (Rust)          # Taint, SMT, Cost
    ├── codegraph-analysis (Python)  # Security, API Misuse
    ├── codegraph-shared
    └── codegraph-parsers

codegraph-agent
    └── codegraph-runtime

codegraph-ml
    └── codegraph-runtime

codegraph-search
    └── codegraph-runtime
```

---

## Migration Commands

```bash
# Phase 1: Merge Python packages
cd packages/
mkdir -p codegraph-analysis/codegraph_analysis/security/{crypto,auth,patterns,framework_adapters}
mkdir -p codegraph-analysis/codegraph_analysis/api_misuse/patterns
mkdir -p codegraph-analysis/codegraph_analysis/{patterns,coverage}

# Move security code
cp -r codegraph-security/codegraph_security/* \
      codegraph-analysis/codegraph_analysis/security/

# Move security rules
cp -r security-rules/* \
      codegraph-analysis/codegraph_analysis/security/patterns/

# Phase 2: Remove deprecated
rm -rf codegraph-taint/
rm -rf codegraph-security/
rm -rf security-rules/
rm -rf codegraph-engine/codegraph_engine/code_foundation/infrastructure/analyzers/

# Phase 3: Update imports (grep & replace)
find . -name "*.py" -exec sed -i '' \
  's/from codegraph_taint/from codegraph_ir/g' {} \;

find . -name "*.py" -exec sed -i '' \
  's/from codegraph_security/from codegraph_analysis.security/g' {} \;

# Phase 4: Test
pytest tests/ -v
```

---

## Rollback Plan

만약 문제가 생기면:

```bash
# Git revert
git revert <commit>

# Or restore from backup
git checkout v2.1.0 -- packages/codegraph-taint
git checkout v2.1.0 -- packages/codegraph-security
```

---

## Summary

**현재 문제**:
- ❌ 4개 패키지 중복 (taint, security, security-rules, analysis)
- ❌ Rust + Python 혼재

**해결책**:
1. **통합**: `codegraph-analysis`로 Python 플러그인 통합
2. **제거**: `codegraph-taint`, `codegraph-security`, `security-rules`
3. **정리**: `codegraph-engine` analyzers 삭제

**결과**:
- ✅ Rust = 엔진 (23,471 LOC)
- ✅ Python = 플러그인 (5,800 LOC, consolidated)
- ✅ 명확한 경계

**타임라인**: 8주
- Week 1-2: Python 패키지 통합
- Week 3-4: 구버전 제거
- Week 5-6: 의존성 업데이트
- Week 7-8: 테스트 & 검증

---

**Last Updated**: 2025-12-28
**Status**: Practical Migration Plan (Based on Current Structure)
