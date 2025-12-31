# Codegraph v3 Architecture Proposal

**Date**: 2025-12-28
**Status**: Proposal for Discussion

---

## Concept

`packages/codegraph-v3/` 아래에 **flat layer**로 모듈별 Rust + Python을 명확히 분리

**핵심 아이디어**:
- ✅ 기존 패키지 건드리지 않음 (backward compatibility)
- ✅ 새로운 clean architecture를 별도로 구축
- ✅ 모듈별로 Rust/Python 명확히 분리
- ✅ 점진적 마이그레이션 가능

---

## Proposed Structure

```
packages/
├── codegraph-v3/                      # 🆕 NEW Clean Architecture
│   ├── taint/                         # L24: Taint Analysis
│   │   ├── rust/                      # Rust implementation
│   │   │   ├── Cargo.toml
│   │   │   └── src/
│   │   │       ├── lib.rs             # PyO3 bindings
│   │   │       ├── ifds.rs            # IFDS/IDE algorithm
│   │   │       ├── interprocedural.rs
│   │   │       └── ...
│   │   ├── python/                    # Python plugins (optional)
│   │   │   ├── __init__.py
│   │   │   └── framework_adapters/
│   │   │       ├── django.py
│   │   │       └── flask.py
│   │   ├── tests/
│   │   └── README.md
│   │
│   ├── smt/                           # L27: SMT Solver
│   │   ├── rust/
│   │   │   ├── Cargo.toml
│   │   │   └── src/
│   │   │       ├── lib.rs
│   │   │       ├── lightweight_checker.rs
│   │   │       ├── solvers/
│   │   │       │   ├── simplex.rs
│   │   │       │   ├── z3_backend.rs
│   │   │       │   └── ...
│   │   │       └── ...
│   │   ├── python/                    # (optional fallback)
│   │   ├── tests/
│   │   └── README.md
│   │
│   ├── complexity/                    # L27: Complexity Analysis
│   │   ├── rust/
│   │   │   ├── Cargo.toml
│   │   │   └── src/
│   │   │       ├── lib.rs
│   │   │       ├── complexity_calculator.rs
│   │   │       └── analyzer.rs
│   │   ├── python/                    # (empty or deprecated)
│   │   ├── tests/
│   │   └── README.md
│   │
│   ├── security/                      # L22-L23: Security Patterns
│   │   ├── rust/                      # (optional, for performance)
│   │   ├── python/                    # Main implementation
│   │   │   ├── __init__.py
│   │   │   ├── crypto.py
│   │   │   ├── auth.py
│   │   │   ├── patterns/
│   │   │   │   ├── crypto.yaml
│   │   │   │   ├── auth.yaml
│   │   │   │   └── injection.yaml
│   │   │   └── framework_adapters/
│   │   ├── tests/
│   │   └── README.md
│   │
│   ├── api-misuse/                    # L29: API Misuse
│   │   ├── rust/                      # (optional)
│   │   ├── python/
│   │   │   ├── __init__.py
│   │   │   ├── stdlib.py
│   │   │   └── patterns/
│   │   ├── tests/
│   │   └── README.md
│   │
│   ├── dependency/                    # L31: Dependency Analysis
│   │   ├── rust/                      # Main implementation
│   │   │   ├── Cargo.toml
│   │   │   └── src/
│   │   │       ├── lib.rs
│   │   │       ├── cross_file.rs
│   │   │       └── dependency_graph.rs
│   │   ├── python/                    # (wrapper only)
│   │   ├── tests/
│   │   └── README.md
│   │
│   ├── patterns/                      # L28: Design Patterns
│   │   ├── rust/                      # (future)
│   │   ├── python/
│   │   │   ├── __init__.py
│   │   │   ├── design_patterns.py
│   │   │   └── anti_patterns.py
│   │   ├── tests/
│   │   └── README.md
│   │
│   ├── coverage/                      # L32: Test Coverage
│   │   ├── rust/                      # (future)
│   │   ├── python/
│   │   │   ├── __init__.py
│   │   │   └── pytest_integration.py
│   │   ├── tests/
│   │   └── README.md
│   │
│   ├── core/                          # Shared infrastructure
│   │   ├── rust/
│   │   │   ├── Cargo.toml
│   │   │   └── src/
│   │   │       ├── lib.rs
│   │   │       ├── models/            # IR models
│   │   │       ├── errors.rs
│   │   │       └── utils.rs
│   │   ├── python/
│   │   │   ├── __init__.py
│   │   │   ├── plugin.py              # Plugin interface
│   │   │   └── registry.py
│   │   └── README.md
│   │
│   ├── orchestrator/                  # Pipeline orchestration
│   │   ├── rust/
│   │   │   ├── Cargo.toml
│   │   │   └── src/
│   │   │       ├── lib.rs
│   │   │       └── pipeline.rs
│   │   ├── python/
│   │   │   ├── __init__.py
│   │   │   └── orchestrator.py        # Python API
│   │   └── README.md
│   │
│   ├── Cargo.toml                     # Rust workspace
│   ├── pyproject.toml                 # Python workspace
│   └── README.md
│
├── codegraph-rust/                    # 🔄 Existing (keep for compatibility)
├── codegraph-engine/                  # 🔄 Existing (deprecated)
├── codegraph-taint/                   # 🔄 Existing (deprecated)
├── codegraph-security/                # 🔄 Existing (deprecated)
├── codegraph-analysis/                # 🔄 Existing (keep)
├── codegraph-parsers/                 # 🔄 Existing (keep)
├── codegraph-shared/                  # 🔄 Existing (keep)
├── codegraph-runtime/                 # 🔄 Existing (migrate to v3)
└── ...
```

---

## Advantages

### 1. Clear Module Boundaries ✅

각 모듈이 독립적:
```
taint/
├── rust/           # Rust implementation (self-contained)
├── python/         # Python wrappers/plugins (self-contained)
├── tests/          # Module-specific tests
└── README.md       # Module documentation
```

**Benefits**:
- 모듈별 독립 개발 가능
- Rust/Python 비율이 한눈에 보임
- 테스트도 모듈별로 분리

### 2. Gradual Migration ✅

기존 패키지 건드리지 않고 새로운 구조 추가:
```python
# Old code (still works)
from codegraph_taint import TaintAnalyzer  # Deprecated

# New code (v3)
from codegraph_v3.taint.rust import taint_analysis
from codegraph_v3.taint.python import DjangoAdapter
```

### 3. Flexible Rust/Python Mix ✅

모듈별로 Rust/Python 비율 다름:
```
taint/
├── rust/           # 99% (IFDS/IDE algorithm)
└── python/         # 1% (framework adapters)

security/
├── rust/           # 0% (not needed)
└── python/         # 100% (pattern rules)

complexity/
├── rust/           # 100% (SMT + Cost)
└── python/         # 0% (deprecated)
```

### 4. Easy to Understand ✅

Flat structure, 계층 없음:
```
codegraph-v3/
├── taint/          # "Taint analysis 보려면 여기"
├── smt/            # "SMT solver 보려면 여기"
├── security/       # "Security patterns 보려면 여기"
└── ...
```

vs 기존:
```
codegraph-rust/codegraph-ir/src/features/taint_analysis/  # 깊음
codegraph-taint/codegraph_taint/                          # 분산
codegraph-security/codegraph_security/                    # 분산
```

---

## Disadvantages

### 1. Duplication During Transition ⚠️

v2와 v3가 공존:
```
packages/
├── codegraph-v3/taint/rust/        # New
├── codegraph-rust/codegraph-ir/    # Old (same code?)
└── codegraph-taint/                # Old (deprecated)
```

**Mitigation**:
- v3 완성되면 old packages 삭제
- symlink 활용? (복잡할 수 있음)

### 2. Workspace Complexity ⚠️

Rust workspace가 복잡해짐:
```toml
# packages/codegraph-v3/Cargo.toml
[workspace]
members = [
    "taint/rust",
    "smt/rust",
    "complexity/rust",
    "dependency/rust",
    "core/rust",
    "orchestrator/rust",
]
```

**Mitigation**:
- Workspace는 관리 용이 (단일 `cargo build`)

### 3. Import Paths ⚠️

Python import가 길어짐:
```python
# v2
from codegraph_ir import taint_analysis

# v3
from codegraph_v3.taint.rust import taint_analysis
```

**Mitigation**:
- Top-level re-export:
```python
# codegraph_v3/__init__.py
from .taint.rust import taint_analysis
from .security.python import CryptoPlugin

# Usage
from codegraph_v3 import taint_analysis, CryptoPlugin
```

---

## Comparison: v3 vs Monolithic

### Option A: codegraph-v3 (Flat Modules)

```
codegraph-v3/
├── taint/rust/
├── taint/python/
├── smt/rust/
├── security/python/
└── ...
```

**Pros**:
- ✅ 모듈별 명확한 경계
- ✅ Rust/Python 비율 한눈에
- ✅ 독립적 개발 가능
- ✅ 기존 코드 건드리지 않음

**Cons**:
- ⚠️ Import path 길어짐
- ⚠️ Transition 중 중복

### Option B: Monolithic (Current codegraph-rust)

```
codegraph-rust/codegraph-ir/
├── src/features/
│   ├── taint_analysis/
│   ├── smt/
│   └── ...
└── src/adapters/pyo3/
```

**Pros**:
- ✅ 단일 Rust crate
- ✅ Import path 짧음

**Cons**:
- ❌ Rust/Python 분리 불명확
- ❌ 모듈별 경계 흐림
- ❌ 기존 코드와 섞임

---

## Recommended Hybrid Approach

**제안**: v3를 **Cargo workspace** + **Python namespace package**로 구성

### Structure

```
packages/codegraph-v3/
├── rust/                          # Rust workspace root
│   ├── taint/                     # Crate: codegraph-taint
│   │   ├── Cargo.toml
│   │   └── src/lib.rs
│   ├── smt/                       # Crate: codegraph-smt
│   │   ├── Cargo.toml
│   │   └── src/lib.rs
│   ├── complexity/                # Crate: codegraph-complexity
│   ├── dependency/                # Crate: codegraph-dependency
│   ├── core/                      # Crate: codegraph-core (shared)
│   └── Cargo.toml                 # Workspace
│
├── python/                        # Python namespace
│   ├── codegraph_v3/
│   │   ├── __init__.py
│   │   ├── taint/
│   │   │   ├── __init__.py        # Re-export Rust
│   │   │   └── adapters/          # Python-only
│   │   │       ├── django.py
│   │   │       └── flask.py
│   │   ├── security/              # Python-only module
│   │   │   ├── __init__.py
│   │   │   ├── crypto.py
│   │   │   └── patterns/
│   │   ├── api_misuse/
│   │   └── ...
│   └── pyproject.toml
│
└── README.md
```

### Rust Workspace

```toml
# packages/codegraph-v3/rust/Cargo.toml
[workspace]
members = [
    "core",
    "taint",
    "smt",
    "complexity",
    "dependency",
]

[workspace.dependencies]
pyo3 = "0.20"
rayon = "1.8"
```

### Python Namespace Package

```python
# packages/codegraph-v3/python/codegraph_v3/__init__.py

# Re-export Rust modules
try:
    from .rust_bindings import (
        taint_analysis,      # From rust/taint
        smt_check,           # From rust/smt
        analyze_complexity,  # From rust/complexity
    )
except ImportError:
    # Fallback or error
    taint_analysis = None

# Python-only modules
from .security import CryptoPlugin, AuthPlugin
from .api_misuse import APIMisusePlugin
```

### Usage

```python
# Simple import
from codegraph_v3 import taint_analysis, CryptoPlugin

# Use Rust engine
paths = taint_analysis(
    ir_documents,
    sources=["request.GET"],
    sinks=["eval"],
)

# Use Python plugin
plugin = CryptoPlugin()
findings = plugin.analyze(ir_documents)
```

---

## Migration Path

### Phase 1: Create v3 Structure (Week 1-2)

```bash
# Create directories
mkdir -p packages/codegraph-v3/{rust,python/codegraph_v3}

# Move Rust code
mkdir packages/codegraph-v3/rust/{taint,smt,complexity,dependency,core}

# Link existing Rust code (temporarily)
ln -s ../../codegraph-rust/codegraph-ir/src/features/taint_analysis \
      packages/codegraph-v3/rust/taint/src

# Create Cargo.toml
cat > packages/codegraph-v3/rust/Cargo.toml << 'EOF'
[workspace]
members = ["core", "taint", "smt", "complexity", "dependency"]
EOF
```

### Phase 2: Python Namespace (Week 3-4)

```bash
# Create Python package
mkdir -p packages/codegraph-v3/python/codegraph_v3/{taint,security,api_misuse}

# Move Python plugins
cp -r packages/codegraph-security/codegraph_security/* \
      packages/codegraph-v3/python/codegraph_v3/security/

# Create __init__.py
cat > packages/codegraph-v3/python/codegraph_v3/__init__.py << 'EOF'
"""Codegraph v3 - Clean Rust-Python Architecture."""

from .rust_bindings import taint_analysis, smt_check, analyze_complexity
from .security import CryptoPlugin, AuthPlugin
from .api_misuse import APIMisusePlugin

__all__ = [
    "taint_analysis",
    "smt_check",
    "analyze_complexity",
    "CryptoPlugin",
    "AuthPlugin",
    "APIMisusePlugin",
]
EOF
```

### Phase 3: Migrate Users (Week 5-8)

```python
# Old code (v2)
from codegraph_ir import taint_analysis
from codegraph_security import CryptoAnalyzer

# New code (v3)
from codegraph_v3 import taint_analysis, CryptoPlugin
```

### Phase 4: Remove Old Packages (v2.3 or v3.0)

```bash
# After v3 is stable
rm -rf packages/codegraph-taint/
rm -rf packages/codegraph-security/
rm -rf packages/codegraph-rust/  # Or keep as legacy
```

---

## Decision Matrix

| Criteria | v3 Flat Modules | v3 Hybrid (Rust/Python) | Keep Current |
|----------|-----------------|------------------------|--------------|
| **Clarity** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| **Modularity** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| **Gradual Migration** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Import Simplicity** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Build Simplicity** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Duplication** | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

**Recommendation**: **v3 Hybrid (Rust workspace + Python namespace)**

---

## Summary

### 제안: codegraph-v3/

**구조**:
```
codegraph-v3/
├── rust/                  # Rust workspace
│   ├── taint/            # Separate crate
│   ├── smt/              # Separate crate
│   └── ...
└── python/               # Python namespace
    └── codegraph_v3/
        ├── taint/        # Re-export Rust + Python adapters
        ├── security/     # Python-only
        └── ...
```

**장점**:
- ✅ 모듈별 명확한 경계
- ✅ Rust/Python 분리 명확
- ✅ 기존 코드 건드리지 않음
- ✅ 점진적 마이그레이션

**단점**:
- ⚠️ Transition 중 중복 (일시적)
- ⚠️ Workspace 관리 필요

**타임라인**: 8주
- Week 1-2: v3 구조 생성
- Week 3-4: Python namespace
- Week 5-8: 사용자 마이그레이션

---

**Last Updated**: 2025-12-28
**Status**: Proposal (Awaiting Decision)
