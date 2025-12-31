# RFC-073: Repository Cleanup Plan

**Status**: Proposed
**Date**: 2025-12-28
**Author**: Architecture Team
**Type**: Process

---

## Summary

Clean up the codegraph monorepo by consolidating duplicate packages, removing deprecated code, and establishing clear Rust-Python boundaries. This will reduce codebase size by ~50,000 LOC while maintaining all functionality.

**Goal**: 명확한 아키텍처, 중복 제거, Rust-Python 경계 확립

---

## Motivation

### Current Problems

1. **중복된 패키지** (4개):
   - `codegraph-taint` (Python) vs `codegraph-ir` (Rust) - 같은 기능
   - `codegraph-security` + `security-rules` + `codegraph-analysis/security_analysis/` - 3곳에 분산

2. **Deprecated 코드** (~30,000 LOC):
   - `codegraph-engine` analyzers (Rust로 대체됨)
   - LayeredIRBuilder (Rust로 대체됨)
   - Python taint analysis (Rust로 대체됨)

3. **불명확한 경계**:
   - 어떤 패키지를 써야 하는지 혼란
   - Rust vs Python 역할 불명확

4. **의존성 문제**:
   - 많은 패키지가 deprecated `codegraph-engine`에 의존

### Quantified Impact

| Problem | Current | After Cleanup | Improvement |
|---------|---------|---------------|-------------|
| **Total LOC** | ~400,000 | ~350,000 | **-50,000 (-12%)** |
| **Duplicate packages** | 12 | 8 | **-4 packages** |
| **Deprecated code** | ~30,000 LOC | 0 | **-30,000 LOC** |
| **Clear boundaries** | ❌ No | ✅ Yes | Clear |

---

## Detailed Design

### Architecture Principles

1. **Rust = Engine**: All analysis algorithms
2. **Python = Consumer + Plugins**: Uses Rust engine + domain rules
3. **Clear Separation**: No Python→Rust dependencies (except parsers)
4. **No Duplication**: Single source of truth for each feature

### Target Structure (v2.2.0)

```
packages/
├── codegraph-rust/              # 🦀 Rust Engine (23,471 LOC)
│   ├── codegraph-ir/            # Taint, SMT, Cost, Dependency
│   ├── codegraph-orchestration/
│   └── codegraph-storage/
│
├── codegraph-parsers/           # 📝 Parsers (통합)
│   └── codegraph_parsers/
│       ├── parsing/             # Tree-sitter
│       ├── template/            # Vue, JSX (+ from engine)
│       └── document/            # Markdown, Jupyter
│
├── codegraph-analysis/          # 🔌 Python Plugins (통합)
│   └── codegraph_analysis/
│       ├── security_analysis/   # 기존 (keep)
│       ├── security/            # 신규 (merge from 3 packages)
│       │   ├── crypto.py
│       │   ├── auth.py
│       │   ├── patterns/        # From security-rules
│       │   └── framework_adapters/
│       ├── api_misuse/          # 신규
│       ├── patterns/            # 신규
│       └── verification/        # 기존 (keep)
│
├── codegraph-generators/        # 🏗️ Code Generators (rename)
│   └── codegraph_generators/    # From codegraph-engine
│       ├── java.py
│       ├── typescript.py
│       └── ...
│
├── codegraph-shared/            # 🔧 Infrastructure
├── codegraph-runtime/           # 🚀 Runtime
├── codegraph-agent/             # 🤖 Agent
├── codegraph-ml/                # 🧠 ML
└── codegraph-search/            # 🔍 Search
```

### Packages to Delete

```
🗑️ codegraph-taint/              (~5,000 LOC)
🗑️ codegraph-security/           (~3,000 LOC)
🗑️ security-rules/               (~1,000 LOC)
🗑️ codegraph-engine/             (~28,300 LOC from infrastructure/)
   ├── analyzers/                (Rust 대체)
   ├── chunk/                    (Rust 대체)
   ├── heap/                     (Rust 대체)
   ├── ir/                       (Rust 대체)
   ├── parsers/                  (→ codegraph-parsers)
   ├── semantic_ir/              (Rust 대체)
   ├── storage/                  (Rust 대체)
   └── type_inference/           (Rust 대체)

Total: ~37,300 LOC deleted
```

### Packages to Consolidate

```
🔄 codegraph-security + security-rules → codegraph-analysis/security/
🔄 codegraph-engine/parsers/ → codegraph-parsers/
🔄 codegraph-engine/generators/ → codegraph-generators/ (rename)
```

### Packages to Keep (No Change)

```
✅ codegraph-rust/               # Rust engine
✅ codegraph-parsers/            # Parsers (+ merge)
✅ codegraph-analysis/           # Analysis (+ merge)
✅ codegraph-shared/             # Infrastructure
✅ codegraph-runtime/            # Runtime
✅ codegraph-agent/              # Agent
✅ codegraph-ml/                 # ML
✅ codegraph-search/             # Search
```

---

## Feature Analysis

### codegraph-engine Features → Rust Mapping

| Feature | Python LOC | Rust LOC | Verdict |
|---------|------------|----------|---------|
| Analyzers | 2,110 | 12,899 (taint) + 10,572 (SMT) | ✅ Use Rust |
| Chunking | 2,863 | 3,671 | ✅ Use Rust |
| Generators | 8,202 | 0 | ⚠️ Keep Python |
| Heap | 1,169 | 1,536 | ✅ Use Rust |
| IR | 3,786 | full pipeline | ✅ Use Rust |
| Parsers | 46 | n/a | 🔄 Move to parsers |
| Semantic IR | 15,604 | 3,467 | ✅ Use Rust |
| Storage | 1,276 | 2,146 | ✅ Use Rust |
| Type Inference | 1,486 | 3,105 | ✅ Use Rust |

**Summary**: 8/9 features → Rust, 1/9 → Python (generators)

### Rust vs Python: What Goes Where?

#### ✅ Rust Engine (codegraph-ir)

**Core Algorithms**:
- L24: Taint Analysis (IFDS/IDE, 12,899 LOC)
- L27: SMT + Complexity (10,572 LOC)
- L31: Dependency Analysis (cross-file)
- Chunking (3,671 LOC)
- Heap Analysis (1,536 LOC)
- IR Generation (3,467 LOC)
- Storage (2,146 LOC)
- Type Resolution (3,105 LOC)

**Total Rust**: ~40,000 LOC (algorithms only)

#### 🔌 Python Plugins (codegraph-analysis)

**Domain Rules**:
- L22: Crypto Patterns (~1,500 LOC)
- L23: Auth/AuthZ Patterns (~800 LOC)
- L29: API Misuse Rules (~1,500 LOC)
- L28: Design Patterns (~2,000 LOC)
- L32: Coverage Integration (~1,000 LOC)
- Framework Adapters (Django, Flask, FastAPI)

**Total Python**: ~7,000 LOC (rules + patterns)

#### 🏗️ Python Generators (codegraph-generators)

**Code Generation**:
- Java Generator (2,707 LOC)
- TypeScript Generator (1,160 LOC)
- Python Generator (~1,200 LOC)
- Kotlin Generator (~1,000 LOC)
- Rust Generator (~600 LOC)

**Total**: ~8,200 LOC (output only, not analysis)

---

## Implementation Plan

### Timeline: 3 Weeks

**Week 1**: Python 플러그인 통합
**Week 2**: 중복 제거 & Parser 통합
**Week 3**: 테스트 & 검증

### Week 1: Python Plugin Consolidation

#### Day 1-2: Create codegraph-analysis structure

```bash
cd packages/codegraph-analysis

# Create directories
mkdir -p codegraph_analysis/security/{crypto,auth,patterns,framework_adapters}
mkdir -p codegraph_analysis/{api_misuse,patterns,coverage}
mkdir -p tests/security tests/api_misuse
```

#### Day 3: Plugin interface

```python
# codegraph_analysis/plugin.py

from abc import ABC, abstractmethod

class AnalysisPlugin(ABC):
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def analyze(self, ir_documents: list) -> list:
        pass

class PluginRegistry:
    def __init__(self):
        self.plugins = {}

    def register(self, plugin: AnalysisPlugin):
        self.plugins[plugin.name()] = plugin

    def run_all(self, ir_documents: list) -> dict:
        results = {}
        for name, plugin in self.plugins.items():
            results[name] = plugin.analyze(ir_documents)
        return results
```

#### Day 4-5: Merge security packages

```bash
# Merge codegraph-security → codegraph-analysis/security/
cp -r packages/codegraph-security/codegraph_security/* \
      packages/codegraph-analysis/codegraph_analysis/security/

# Merge security-rules → patterns/
cp -r packages/security-rules/* \
      packages/codegraph-analysis/codegraph_analysis/security/patterns/

# Create framework adapters
cat > codegraph_analysis/security/framework_adapters/django.py << 'EOF'
DJANGO_TAINT_SOURCES = ["request.GET", "request.POST", ...]
DJANGO_TAINT_SINKS = ["cursor.execute", "eval", ...]
DJANGO_SANITIZERS = ["django.utils.html.escape", ...]
EOF
```

### Week 2: Deprecation & Consolidation

#### Day 1-2: Parser consolidation

```bash
# Check for duplicates
diff packages/codegraph-engine/.../vue_sfc_parser.py \
     packages/codegraph-parsers/.../vue_sfc_parser.py || true

# Move to codegraph-parsers if not duplicate
cp packages/codegraph-engine/.../parsers/*.py \
   packages/codegraph-parsers/codegraph_parsers/template/
```

#### Day 3: Rename generators (Optional)

```bash
# Option 1: Keep in codegraph-engine (minimal change)
# - Just delete other directories

# Option 2: Rename to codegraph-generators (clearer)
mv packages/codegraph-engine packages/codegraph-generators
# Update pyproject.toml, imports, etc.
```

#### Day 4: Update imports

```bash
# Update all imports
find packages/ tests/ server/ -name "*.py" -exec sed -i '' \
  's/from codegraph_taint/from codegraph_ir/g' {} \;

find packages/ tests/ server/ -name "*.py" -exec sed -i '' \
  's/from codegraph_security/from codegraph_analysis.security/g' {} \;

find packages/ tests/ server/ -name "*.py" -exec sed -i '' \
  's/from codegraph_engine\..*\.parsers/from codegraph_parsers/g' {} \;
```

#### Day 5: Update dependencies

```toml
# codegraph-runtime/pyproject.toml
[project]
dependencies = [
    "codegraph-ir>=2.1.0",          # Rust engine (was optional)
    "codegraph-analysis>=2.1.0",    # Python plugins (NEW)
    "codegraph-parsers>=0.1.0",
    "codegraph-shared>=2.1.0",
]

# Remove:
# - codegraph-taint
# - codegraph-security
# - codegraph-engine (for analyzers)
```

```toml
# codegraph-analysis/pyproject.toml
[project]
dependencies = [
    "codegraph-ir>=2.1.0",      # Rust engine (not codegraph-engine!)
    "pyyaml>=6.0",
]
```

```toml
# codegraph-shared/pyproject.toml
[project]
dependencies = [
    "codegraph-ir>=2.1.0",      # Rust engine
    "codegraph-parsers>=0.1.0",
]
```

### Week 3: Deletion & Testing

#### Day 1: Verify no dependencies

```bash
# Check for lingering references
rg "from codegraph_taint" packages/ tests/ server/
rg "from codegraph_security" packages/ tests/ server/
rg "codegraph.engine.*analyzers" packages/ tests/ server/
rg "LayeredIRBuilder" packages/ tests/ server/

# Should return nothing (or only comments/deprecation warnings)
```

#### Day 2: Delete deprecated packages

```bash
# DANGEROUS - only after verification!
rm -rf packages/codegraph-taint/
rm -rf packages/codegraph-security/
rm -rf packages/security-rules/

# Delete from codegraph-engine
rm -rf packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/analyzers/
rm -rf packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/chunk/
rm -rf packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/heap/
rm -f packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/layered_ir_builder.py
rm -rf packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/parsers/
rm -rf packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/semantic_ir/
rm -rf packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/storage/
rm -rf packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/type_inference/
```

#### Day 3-4: Integration tests

```python
# tests/integration/test_cleanup.py

import codegraph_ir
from codegraph_analysis.registry import PluginRegistry
from codegraph_analysis.security import CryptoPlugin

def test_rust_engine():
    """Test Rust engine works after cleanup."""
    config = codegraph_ir.E2EPipelineConfig(
        root_path="/test/repo",
        enable_taint=True,
        enable_complexity=True,
    )

    orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
    result = orchestrator.execute()

    assert result.success
    assert len(result.ir_documents) > 0

def test_python_plugins():
    """Test Python plugins work after cleanup."""
    registry = PluginRegistry()
    registry.register(CryptoPlugin())

    findings = registry.run_all([mock_ir])

    assert "crypto" in findings
```

#### Day 5: Benchmark & Documentation

```python
# benchmark/test_after_cleanup.py

def test_performance():
    """Verify performance after cleanup."""
    # Rust taint analysis
    start = time.time()
    result = codegraph_ir.taint_analysis(...)
    duration = time.time() - start

    assert duration < 1.0  # < 1s for 1000 files
```

```bash
# Update documentation
# - README.md (remove deprecated packages)
# - ARCHITECTURE.md (new structure)
# - MIGRATION_GUIDE.md (how to upgrade)
```

---

## Migration Guide

### For Users

#### Before (v2.1.0)

```python
# Taint analysis
from codegraph_taint import TaintAnalyzer
analyzer = TaintAnalyzer()
paths = analyzer.analyze(...)

# Security analysis
from codegraph_security import CryptoAnalyzer
analyzer = CryptoAnalyzer()
findings = analyzer.analyze(...)

# IR building
from codegraph_engine.code_foundation.infrastructure.ir import LayeredIRBuilder
builder = LayeredIRBuilder()
ir = builder.build(...)
```

#### After (v2.2.0)

```python
# Taint analysis (Rust)
import codegraph_ir
config = codegraph_ir.TaintConfig(enable_interprocedural=True)
paths = codegraph_ir.taint_analysis(ir_documents, config, ...)

# Security analysis (Python plugin)
from codegraph_analysis.security import CryptoPlugin
plugin = CryptoPlugin()
findings = plugin.analyze(ir_documents)

# IR building (Rust)
import codegraph_ir
config = codegraph_ir.E2EPipelineConfig(root_path="/repo")
orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
result = orchestrator.execute()
```

#### High-Level API (Recommended)

```python
# All-in-one orchestrator
from codegraph_runtime import AnalysisOrchestrator

orchestrator = AnalysisOrchestrator(
    enable_taint=True,
    enable_complexity=True,
    enable_security_plugins=True,
)

result = orchestrator.analyze("/repo")

# All results in one place
print(result.taint_findings)      # From Rust
print(result.complexity)          # From Rust
print(result.crypto_findings)     # From Python plugin
```

### For Developers

#### Dependency Updates

```toml
# Before
[project]
dependencies = [
    "codegraph-engine>=0.1.0",     # ❌ Deprecated
    "codegraph-taint>=0.1.0",      # ❌ Removed
    "codegraph-security>=0.1.0",   # ❌ Removed
]

# After
[project]
dependencies = [
    "codegraph-ir>=2.1.0",         # ✅ Rust engine
    "codegraph-analysis>=2.1.0",   # ✅ Python plugins
    "codegraph-parsers>=0.1.0",    # ✅ Parsers
]
```

---

## Rollback Plan

If issues arise:

```bash
# Git revert all changes
git revert HEAD~20..HEAD

# Or restore specific packages
git checkout v2.1.0 -- packages/codegraph-taint
git checkout v2.1.0 -- packages/codegraph-security
git checkout v2.1.0 -- packages/security-rules
git checkout v2.1.0 -- packages/codegraph-engine
```

---

## Risks & Mitigations

### Risk 1: Breaking Changes

**Risk**: Users depending on deprecated packages

**Mitigation**:
1. Deprecation warnings in v2.1.0 (already done)
2. Clear migration guide
3. Gradual rollout (v2.1 → v2.2 over 2-3 months)
4. Keep v2.1.x branch for critical fixes

### Risk 2: Missing Features

**Risk**: Some Python features not in Rust

**Mitigation**:
1. Feature analysis done (RFC-073)
2. Only generators kept in Python (intentional)
3. All analysis features covered by Rust

### Risk 3: Performance Regression

**Risk**: Rust implementation slower than expected

**Mitigation**:
1. Benchmark before/after
2. Expected: 10-50x faster (based on preliminary tests)
3. Fallback: Keep Python code if Rust is slower (unlikely)

### Risk 4: Integration Issues

**Risk**: Rust-Python integration problems

**Mitigation**:
1. Already tested in v2.1.0
2. Integration tests in Week 3
3. Gradual rollout with monitoring

---

## Success Metrics

### Quantitative

- [ ] **LOC Reduction**: -50,000 LOC (-12%)
- [ ] **Package Reduction**: 12 → 8 packages (-33%)
- [ ] **Build Time**: < 5 minutes (vs 8 minutes now)
- [ ] **Test Coverage**: > 80% (maintain)
- [ ] **Performance**: 10-50x faster analysis

### Qualitative

- [ ] **Clear Architecture**: Rust-Python boundaries well-defined
- [ ] **No Duplication**: Single source of truth for all features
- [ ] **Easy to Understand**: New contributors onboard faster
- [ ] **Maintainable**: Easier to add new features

---

## Alternatives Considered

### Alternative 1: Keep Everything (Status Quo)

**Pros**:
- No migration work
- No risk of breaking changes

**Cons**:
- Continued confusion
- Wasted maintenance effort on duplicate code
- Slower performance

**Verdict**: ❌ Rejected (problems persist)

### Alternative 2: Create codegraph-v3 (Fresh Start)

**Pros**:
- Clean slate
- Perfect architecture

**Cons**:
- Duplicate Rust code (23,471 LOC)
- Massive migration burden for users
- 8 weeks of work vs 3 weeks

**Verdict**: ❌ Rejected (too much work, little benefit)

### Alternative 3: Monolithic Package

**Pros**:
- Single package to install

**Cons**:
- Huge package (all features bundled)
- Can't install selectively (e.g., agent without ML)
- Unclear boundaries

**Verdict**: ❌ Rejected (loses modularity)

### Alternative 4: Proposed Plan (Cleanup Existing)

**Pros**:
- ✅ Minimal changes (3 weeks)
- ✅ Clear boundaries established
- ✅ No code duplication
- ✅ Keeps existing structure

**Cons**:
- Some import changes needed

**Verdict**: ✅ **Selected** (best balance)

---

## Decision

**Approve** this RFC to proceed with repository cleanup:

1. ✅ Consolidate Python plugins → `codegraph-analysis`
2. ✅ Consolidate parsers → `codegraph-parsers`
3. ✅ Delete deprecated code (~37,300 LOC)
4. ✅ Update dependencies (engine → ir)
5. ✅ Optional: Rename `codegraph-engine` → `codegraph-generators`

**Timeline**: 3 weeks (Week 1-3 in January 2025)

**Version**: v2.2.0 (breaking changes, major cleanup)

---

## References

- [FINAL_RECOMMENDATION.md](../FINAL_RECOMMENDATION.md) - Architecture decision
- [CODEGRAPH_ENGINE_FEATURE_ANALYSIS.md](../CODEGRAPH_ENGINE_FEATURE_ANALYSIS.md) - Detailed analysis
- [EXECUTION_PLAN.md](../EXECUTION_PLAN.md) - Implementation guide
- [ADDITIONAL_CONSOLIDATION_REVIEW.md](../ADDITIONAL_CONSOLIDATION_REVIEW.md) - Package review
- [L22-L32_FINAL_INTEGRATION_PLAN.md](../L22-L32_FINAL_INTEGRATION_PLAN.md) - Feature integration
- [ADR-072](../adr/ADR-072-clean-rust-python-architecture.md) - Clean architecture ADR

---

**Last Updated**: 2025-12-28
**Status**: Proposed
**Next Steps**: Team review → Approval → Implementation (Week 1-3, Jan 2025)
