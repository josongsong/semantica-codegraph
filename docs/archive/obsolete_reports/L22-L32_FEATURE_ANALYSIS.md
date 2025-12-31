# L22-L32 Advanced Analysis Features: Python vs Rust Implementation Status

**Date**: 2025-12-28
**Status**: Analysis Complete

---

## Executive Summary

현재 **L22-L32 고급 분석 기능**은 주로 Python으로 구현되어 있으며, Rust에는 일부만 이식되었습니다.

**핵심 결론**:
1. **Taint Analysis**: Python (완전), Rust (기본만)
2. **Complexity Analysis**: Python (완전), Rust (Cost Analysis로 부분)
3. **Security Analysis**: Python (완전), Rust (없음)
4. **나머지 L24-L32**: 대부분 Python만 존재

**권장 전략**:
- 🎯 **Python Plugin으로 유지** (당분간)
- 🚀 **점진적 Rust 이식** (성능 critical한 것부터)
- 🔌 **Plugin Architecture** 설계로 공존 가능

---

## Feature Matrix: Python vs Rust

| Layer | Feature | Python Status | Rust Status | Priority | Strategy |
|-------|---------|---------------|-------------|----------|----------|
| **L22** | Cryptographic Analysis | ✅ Full | ❌ None | P2 | Python Plugin |
| **L23** | Auth/AuthZ Analysis | ✅ Full | ❌ None | P2 | Python Plugin |
| **L24** | Injection Analysis | ✅ Full (Taint) | ⚠️ Basic | P1 | Rust Migration |
| **L25** | Memory Leak Detection | ✅ Full | ⚠️ Basic (Heap) | P2 | Rust Enhancement |
| **L27** | Complexity Metrics | ✅ Full | ⚠️ Partial (Cost) | P2 | Rust Enhancement |
| **L28** | Design Pattern Detection | ✅ Full | ❌ None | P3 | Python Plugin |
| **L29** | API Misuse Detection | ✅ Full | ❌ None | P2 | Python Plugin |
| **L31** | Dependency Analysis | ✅ Full | ✅ Full (Cross-File) | ✅ Done | - |
| **L32** | Test Coverage Analysis | ⚠️ Partial | ❌ None | P3 | Python Plugin |

**Legend**:
- ✅ Full: 완전 구현
- ⚠️ Partial/Basic: 부분 구현
- ❌ None: 미구현
- P1: High Priority
- P2: Medium Priority
- P3: Low Priority

---

## Detailed Analysis

### L22: Cryptographic Analysis

#### Python Implementation ✅

**Location**: `packages/codegraph-engine/...analyzers/deep_security_analyzer.py`

**Features**:
- Weak crypto detection (MD5, SHA1, DES)
- Hard-coded key detection
- Insecure random number generation
- Pattern-based + taint flow analysis

**Code Size**: ~1,500 LOC (deep_security_analyzer.py 내 일부)

**Example**:
```python
# Detects:
hashlib.md5(data)  # Weak hash
random.random()  # Insecure random
key = "hardcoded123"  # Hard-coded key
```

#### Rust Implementation ❌

**Status**: Not implemented

**Reason**: Domain-specific patterns require extensive rule database

---

### L23: Auth/AuthZ Analysis

#### Python Implementation ✅

**Location**: `packages/codegraph-engine/...analyzers/deep_security_analyzer.py`

**Features**:
- Missing authentication checks
- Authorization bypass detection
- JWT token misuse
- Session fixation

**Code Size**: ~800 LOC (security patterns)

**Example**:
```python
# Detects:
@app.route("/admin")
def admin():  # Missing @login_required
    ...
```

#### Rust Implementation ❌

**Status**: Not implemented

**Reason**: Framework-specific patterns (Django, Flask, FastAPI)

---

### L24: Injection Analysis (SQL, XSS, Command)

#### Python Implementation ✅ FULL

**Location**:
- `packages/codegraph-engine/...analyzers/interprocedural_taint.py` (78k LOC!)
- `packages/codegraph-engine/...analyzers/path_sensitive_taint.py` (35k LOC)
- `packages/codegraph-engine/...analyzers/deep_security_analyzer.py`

**Features**:
- **Interprocedural taint tracking** (10-hop)
- **Path-sensitive analysis** (symbolic execution)
- **Field-sensitive analysis** (object fields)
- **Context-sensitive** (call-site context)
- SQL, XSS, Command, Path Traversal, SSRF

**Algorithm**:
- Fixpoint iteration (Chaotic iteration)
- Summary-based (function summaries)
- Z3 SMT solver integration

**Performance**: ~3s for medium repo (1000 files)

**Example**:
```python
# Source
user_input = request.GET['query']

# Flow through functions
def process(data):
    return transform(data)

# Sink
cursor.execute(query)  # DETECTED: SQL Injection
```

#### Rust Implementation ⚠️ BASIC

**Location**: `packages/codegraph-rust/.../taint_analysis/`

**Current Status**:
- ✅ Basic taint propagation
- ✅ Intraprocedural (single function)
- ❌ Interprocedural (cross-function) - Missing
- ❌ Path-sensitive - Missing
- ❌ Field-sensitive - Missing

**Code Size**: ~2,000 LOC (vs Python 113k LOC)

**Gap**: Python은 SOTA 수준 구현, Rust는 기본만

**Migration Priority**: **P1** (성능 critical)

---

### L25: Memory Leak Detection

#### Python Implementation ✅

**Location**:
- `packages/codegraph-engine/...heap/audit_null_analyzer.py`
- `packages/codegraph-engine/...heap/realtime_null_analyzer.py`

**Features**:
- Null pointer dereference (sound)
- Resource leak (file, socket)
- Use-after-free detection

**Algorithm**:
- Abstract interpretation
- Separation logic (symbolic heap)
- Fixpoint computation

**Code Size**: ~3,000 LOC

#### Rust Implementation ⚠️ BASIC

**Location**: `packages/codegraph-rust/.../heap_analysis/`

**Current Status**:
- ✅ Basic heap model
- ⚠️ Points-to analysis (Andersen/Steensgaard)
- ❌ Leak detection - Missing
- ❌ Separation logic - Missing

**Gap**: Rust has infrastructure (heap model, points-to) but missing leak detection logic

---

### L27: Complexity Metrics

#### Python Implementation ✅ FULL

**Location**: `packages/codegraph-engine/...analyzers/cost/`

**Features**:
- **Big-O complexity** (O(n), O(n²), O(log n))
- **Loop bound inference** (SMT-based)
- **Recursion analysis**
- **Amortized cost**

**Algorithm**:
- Abstract interpretation
- Loop invariant inference
- Z3 SMT solver

**Code Size**: ~4,000 LOC

**Example**:
```python
# Infers O(n²)
for i in range(n):
    for j in range(n):
        ...
```

#### Rust Implementation ⚠️ PARTIAL

**Location**: `packages/codegraph-rust/.../cost_analysis/`

**Current Status**:
- ✅ Basic cost model
- ✅ Loop detection
- ⚠️ Bound inference (simple cases only)
- ❌ SMT integration - Missing
- ❌ Recursion analysis - Missing

**Code Size**: ~1,500 LOC

**Gap**: Rust는 기본 구조만, Python은 SMT 기반 정확한 분석

---

### L28: Design Pattern Detection

#### Python Implementation ✅

**Location**: Pattern recognition across codebase (scattered)

**Features**:
- Singleton, Factory, Observer, Strategy
- Anti-pattern detection (God Object, Spaghetti Code)

**Code Size**: ~2,000 LOC (추정)

#### Rust Implementation ❌

**Status**: Not implemented

**Reason**: Requires high-level architectural analysis

---

### L29: API Misuse Detection

#### Python Implementation ✅

**Location**: `packages/codegraph-engine/...analyzers/deep_security_analyzer.py`

**Features**:
- Incorrect API usage (e.g., file.close() missing)
- Library-specific rules (requests, sqlalchemy, etc.)
- TypeState analysis (protocol violation)

**Code Size**: ~1,500 LOC

**Example**:
```python
# Detects:
f = open("file.txt")
f.read()
# Missing: f.close()
```

#### Rust Implementation ❌

**Status**: Not implemented

**Reason**: Requires extensive API rule database

---

### L31: Dependency Analysis

#### Python Implementation ✅

**Location**:
- `packages/codegraph-engine/...ir/cross_file_resolver.py`
- Package analyzer

**Features**:
- Import resolution
- Dependency graph
- Circular dependency detection
- Package version analysis

#### Rust Implementation ✅ FULL

**Location**: `packages/codegraph-rust/.../cross_file/`

**Current Status**:
- ✅ Import resolution (DashMap)
- ✅ Dependency graph (petgraph)
- ✅ Circular detection (Tarjan SCC)
- ✅ 12x faster than Python

**Migration**: **✅ Done** (Rust is production)

---

### L32: Test Coverage Analysis

#### Python Implementation ⚠️ PARTIAL

**Location**: Integration with `pytest`, `coverage.py`

**Features**:
- Line coverage
- Branch coverage
- Integration with CI/CD

#### Rust Implementation ❌

**Status**: Not implemented

**Reason**: Requires runtime instrumentation

---

## Implementation Strategies

### Strategy 1: Python Plugin Architecture (Recommended)

**Approach**: Keep Python analyzers as plugins, Rust as engine

```
┌─────────────────────────────────────────┐
│          Rust Analysis Engine           │
│  • IR Building (L1)                     │
│  • Flow Analysis (L4-L6)                │
│  • Basic Taint (L24 basic)              │
│  • Dependency (L31)                     │
└──────────────┬──────────────────────────┘
               │ Plugin Interface
               ▼
┌─────────────────────────────────────────┐
│       Python Analysis Plugins           │
│  • Advanced Taint (L24 full)            │
│  • Security Analysis (L22-L23)          │
│  • Complexity (L27)                     │
│  • API Misuse (L29)                     │
└─────────────────────────────────────────┘
```

**Pros**:
- ✅ Leverage existing Python code (~50k LOC)
- ✅ Rapid development (Python ecosystem)
- ✅ Framework-specific rules easier in Python
- ✅ No performance bottleneck (Rust handles IR)

**Cons**:
- ⚠️ Python dependency for advanced features
- ⚠️ GIL overhead for some analyses

**Implementation**:
```rust
// Rust: Plugin trait
pub trait AnalysisPlugin: Send + Sync {
    fn analyze(&self, ir: &IRDocument) -> Result<AnalysisResult>;
}

// Python: Plugin implementation
#[pyclass]
struct PythonSecurityPlugin {
    analyzer: Py<PyAny>,  // Python analyzer object
}

impl AnalysisPlugin for PythonSecurityPlugin {
    fn analyze(&self, ir: &IRDocument) -> Result<AnalysisResult> {
        Python::with_gil(|py| {
            let result = self.analyzer
                .call_method1(py, "analyze", (ir_to_py(ir),))?;
            Ok(py_to_rust_result(result)?)
        })
    }
}
```

---

### Strategy 2: Gradual Rust Migration

**Approach**: Incrementally port Python → Rust (highest priority first)

**Phase 1** (Q1 2025): Port critical path
- ✅ Dependency Analysis (L31) - **Done**
- 🔄 Interprocedural Taint (L24) - **In Progress**
- 🔄 Complexity Analysis (L27) - **In Progress**

**Phase 2** (Q2 2025): Port security core
- Security patterns (L22-L23)
- Memory leak detection (L25)

**Phase 3** (Q3 2025): Port remaining
- Design patterns (L28)
- API misuse (L29)

**Effort Estimate**:
| Feature | LOC (Python) | Est. Rust LOC | Effort (weeks) |
|---------|--------------|---------------|----------------|
| Taint (L24) | 113,000 | ~30,000 | 12 weeks |
| Complexity (L27) | 4,000 | ~3,000 | 4 weeks |
| Security (L22-L23) | 3,000 | ~2,000 | 4 weeks |
| API Misuse (L29) | 1,500 | ~1,000 | 2 weeks |
| **Total** | **121,500** | **~36,000** | **22 weeks** |

**Pros**:
- ✅ Best performance (Rust native)
- ✅ No Python runtime dependency
- ✅ Type safety, memory safety

**Cons**:
- ❌ High development cost (22 weeks = 5 months)
- ❌ Reimplementing working code
- ❌ Risk of bugs during port

---

### Strategy 3: Hybrid (Best of Both)

**Approach**:
- Rust for performance-critical paths (IR, data flow, taint core)
- Python for domain-specific rules (security patterns, API rules)

```
┌────────────────────────────────────────────────┐
│            Rust Core Engine                    │
│  • IR Building (L1-L8)                         │
│  • Taint Core (propagation, fixpoint)          │
│  • Data Flow (CFG, DFG, PDG)                   │
└─────────────────┬──────────────────────────────┘
                  │
         ┌────────┴─────────┐
         ▼                  ▼
┌─────────────────┐  ┌──────────────────┐
│  Rust Analyzers │  │ Python Analyzers │
│  • Basic Taint  │  │ • Security Rules │
│  • Dependency   │  │ • Framework APIs │
│  • Complexity   │  │ • Design Patterns│
│    (partial)    │  │ • Coverage       │
└─────────────────┘  └──────────────────┘
```

**Division of Labor**:

| Component | Language | Reason |
|-----------|----------|--------|
| **Taint Propagation** | Rust | Performance (fixpoint iteration) |
| **Security Patterns** | Python | Rule flexibility |
| **Complexity Core** | Rust | SMT integration (z3-rs) |
| **Complexity Rules** | Python | Domain knowledge |
| **API Misuse Rules** | Python | Library-specific |
| **Framework Adapters** | Python | Easier to extend |

**Pros**:
- ✅ Best performance for core
- ✅ Best flexibility for rules
- ✅ Incremental migration path

**Cons**:
- ⚠️ Complexity (2 languages)
- ⚠️ Interface maintenance

---

## Repository Structure Options

### Option 1: Monorepo with Python Plugins

```
codegraph/
├── packages/
│   ├── codegraph-rust/          # Rust engine (core)
│   │   ├── codegraph-ir/        # IR + basic analysis
│   │   └── codegraph-plugins/   # Rust plugin interface
│   │
│   ├── codegraph-engine/        # Python core (IR - deprecated)
│   ├── codegraph-analysis/      # Python analysis plugins
│   │   ├── security/            # L22-L23 (crypto, auth)
│   │   ├── taint/               # L24 (advanced taint)
│   │   ├── complexity/          # L27 (complexity)
│   │   ├── patterns/            # L28 (design patterns)
│   │   ├── api_misuse/          # L29 (API rules)
│   │   └── coverage/            # L32 (test coverage)
│   │
│   └── codegraph-shared/        # Shared infrastructure
```

**Benefits**:
- ✅ Clear separation (Rust engine, Python plugins)
- ✅ Easy to develop Python plugins
- ✅ Single version control

---

### Option 2: Separate Repos

```
Repo 1: codegraph-engine (Rust)
  └── Core analysis engine

Repo 2: codegraph-plugins (Python)
  └── Analysis plugins (L22-L32)

Repo 3: codegraph-runtime (Integration)
  └── API Server, MCP Server
```

**Benefits**:
- ✅ Independent release cycles
- ✅ Clear ownership

**Drawbacks**:
- ❌ Coordination overhead
- ❌ Version compatibility issues

---

### Option 3: Feature Flags

```
codegraph/
├── packages/
│   ├── codegraph-rust/
│   │   ├── features/
│   │   │   ├── taint_analysis/   # Rust implementation
│   │   │   ├── complexity/       # Rust implementation
│   │   │   └── ...
│   │
│   ├── codegraph-analysis/       # Python analyzers
│   │   └── (kept as fallback)
│
│   └── codegraph-runtime/
│       └── feature_flags.toml    # Which impl to use
```

**feature_flags.toml**:
```toml
[analysis]
taint_engine = "rust"       # or "python"
complexity = "python"       # or "rust"
security = "python"         # only python
api_misuse = "python"       # only python
```

**Benefits**:
- ✅ A/B testing (Rust vs Python)
- ✅ Gradual migration
- ✅ Rollback capability

---

## Recommendation

### Short-term (v2.1-v2.2, Q1 2025)

**Strategy**: **Hybrid (Strategy 3)** + **Monorepo (Option 1)**

1. ✅ Keep Python analyzers as plugins
2. ✅ Rust handles IR and basic analysis
3. 🔄 Start porting taint core to Rust (P1)

**Why**:
- 50k+ LOC of Python analyzers are production-ready
- Rewriting from scratch = 5+ months
- Plugin architecture allows gradual migration

### Mid-term (v2.3-v2.5, Q2-Q3 2025)

**Strategy**: **Gradual Migration (Strategy 2)**

1. Port interprocedural taint to Rust (L24)
2. Port complexity analysis to Rust (L27)
3. Keep security rules in Python (L22-L23, L29)

### Long-term (v3.0, Q4 2025+)

**Strategy**: **All Rust** (if justified)

1. Port all analyzers to Rust
2. Python only for framework-specific rules
3. Pure Rust engine

**Condition**: Only if performance gains justify 5+ months effort

---

## Plugin Interface Design

### Rust Plugin Trait

```rust
// packages/codegraph-rust/codegraph-plugins/src/lib.rs

pub trait AnalysisPlugin: Send + Sync {
    /// Plugin metadata
    fn name(&self) -> &str;
    fn version(&self) -> &str;
    fn layer(&self) -> AnalysisLayer;  // L22, L23, etc.

    /// Analyze IR document
    fn analyze(&self, ctx: &AnalysisContext) -> Result<Vec<Finding>>;

    /// Supported languages
    fn supported_languages(&self) -> &[Language];
}

pub struct AnalysisContext<'a> {
    pub ir: &'a IRDocument,
    pub call_graph: &'a CallGraph,
    pub type_info: &'a TypeContext,
    pub config: &'a PluginConfig,
}

pub struct Finding {
    pub severity: Severity,  // Critical, High, Medium, Low
    pub category: Category,  // Injection, Crypto, Auth, etc.
    pub message: String,
    pub location: Location,
    pub remediation: Option<String>,
}
```

### Python Plugin Example

```python
# packages/codegraph-analysis/security/crypto_plugin.py

from codegraph_ir import AnalysisPlugin, Finding, Severity

class CryptoAnalysisPlugin(AnalysisPlugin):
    def name(self) -> str:
        return "crypto-analyzer"

    def version(self) -> str:
        return "1.0.0"

    def layer(self) -> str:
        return "L22"  # Cryptographic Analysis

    def analyze(self, ctx) -> list[Finding]:
        findings = []

        # Detect weak crypto
        for node in ctx.ir.nodes:
            if node.kind == "Call":
                if "md5" in node.name.lower():
                    findings.append(Finding(
                        severity=Severity.HIGH,
                        category="weak-crypto",
                        message="MD5 is cryptographically broken",
                        location=node.location,
                        remediation="Use SHA-256 or stronger"
                    ))

        return findings
```

### Registration

```python
# packages/codegraph-runtime/plugin_registry.py

from codegraph_ir import PluginRegistry
from codegraph_analysis.security import CryptoAnalysisPlugin
from codegraph_analysis.taint import AdvancedTaintPlugin

registry = PluginRegistry()
registry.register(CryptoAnalysisPlugin())
registry.register(AdvancedTaintPlugin())

# Run all plugins
findings = registry.run_all(ir_document)
```

---

## Migration Checklist

### Phase 1: Infrastructure (Week 1-2)

- [ ] Design `AnalysisPlugin` trait in Rust
- [ ] Implement PyO3 bindings for plugin interface
- [ ] Create Python `AnalysisPlugin` base class
- [ ] Build plugin registry
- [ ] Write integration tests

### Phase 2: Port Python Plugins (Week 3-4)

- [ ] Refactor existing Python analyzers to use plugin interface
- [ ] Move to `codegraph-analysis/` package
- [ ] Categorize by layer (L22, L23, L24, etc.)
- [ ] Add plugin metadata

### Phase 3: Rust Taint Core (Week 5-16)

- [ ] Port interprocedural taint propagation
- [ ] Port fixpoint solver
- [ ] Port summary-based analysis
- [ ] Port path-sensitive analysis
- [ ] Benchmark Rust vs Python (target: 10x)

### Phase 4: Documentation (Week 17-18)

- [ ] Plugin development guide
- [ ] API reference
- [ ] Migration examples
- [ ] Performance benchmarks

---

## Performance Targets

| Analysis | Current (Python) | Target (Rust) | Speedup |
|----------|------------------|---------------|---------|
| Taint (basic) | 100 ms | 10 ms | 10x |
| Taint (deep) | 3s | 300 ms | 10x |
| Complexity | 500 ms | 50 ms | 10x |
| Security (patterns) | 200 ms | 200 ms | 1x (Python OK) |

**Note**: Pattern-based analysis (L22, L23, L29) doesn't need Rust (fast enough in Python)

---

## Conclusion

**Recommended Approach**: **Hybrid Strategy**

1. **Rust Core** (L1-L8 + basic L24)
   - IR building
   - Data flow analysis
   - Basic taint propagation

2. **Python Plugins** (L22-L23, L27-L29, L32)
   - Security patterns (crypto, auth)
   - Advanced taint rules
   - Complexity analysis
   - API misuse detection
   - Coverage integration

3. **Gradual Migration**
   - Port taint core to Rust (Q1 2025)
   - Port complexity to Rust (Q2 2025)
   - Keep domain-specific rules in Python

**Benefits**:
- ✅ Leverage 50k LOC of existing Python code
- ✅ Get 10-50x Rust performance for core
- ✅ Keep Python flexibility for rules
- ✅ Incremental migration path

**Next Steps**:
1. Implement plugin architecture (2 weeks)
2. Refactor Python analyzers as plugins (2 weeks)
3. Start taint core migration (12 weeks)

---

**Last Updated**: 2025-12-28
**Authors**: Semantica Team
