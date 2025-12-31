# Repository Structure v2.1 - Clean Rust-Python Architecture

**Date**: 2025-12-28
**Status**: Final Design

---

## Design Principles

1. **Rust = Engine**: 모든 분석 알고리즘
2. **Python = Consumer + Plugins**: Rust 엔진 사용 + 도메인 룰
3. **Clear Separation**: Rust ↔ Python 경계 명확
4. **Plugin Architecture**: 확장 가능한 플러그인 시스템

---

## Recommended Structure (Option 1: Monorepo with Clear Boundaries)

```
codegraph/                                    # Monorepo root
│
├── packages/                                 # 모든 패키지
│   │
│   ├── codegraph-rust/                      # 🦀 Rust Engine (Core)
│   │   ├── codegraph-ir/                    # IR + Analysis Engine
│   │   │   ├── src/
│   │   │   │   ├── features/
│   │   │   │   │   ├── taint_analysis/     # L24: 12,899 LOC
│   │   │   │   │   ├── smt/                # L27: 9,225 LOC
│   │   │   │   │   ├── cost_analysis/      # L27: 1,347 LOC
│   │   │   │   │   ├── heap_analysis/      # L25
│   │   │   │   │   ├── cross_file/         # L31
│   │   │   │   │   └── ...
│   │   │   │   ├── adapters/
│   │   │   │   │   └── pyo3/               # Python bindings
│   │   │   │   │       ├── api/
│   │   │   │   │       │   ├── mod.rs
│   │   │   │   │       │   ├── taint.rs    # Taint API
│   │   │   │   │       │   ├── complexity.rs
│   │   │   │   │       │   └── plugin.rs   # Plugin interface
│   │   │   │   │       └── lib.rs
│   │   │   │   └── lib.rs
│   │   │   ├── Cargo.toml
│   │   │   └── pyproject.toml               # maturin build
│   │   │
│   │   └── README.md
│   │
│   ├── codegraph-shared/                    # 🔧 Shared Infrastructure
│   │   ├── codegraph_shared/
│   │   │   ├── infra/
│   │   │   │   ├── jobs/                    # Job handlers
│   │   │   │   │   ├── handlers/
│   │   │   │   │   │   ├── ir_handler.py   # L1: IR Build (uses Rust)
│   │   │   │   │   │   ├── chunk_handler.py # L2: Chunking
│   │   │   │   │   │   └── ...
│   │   │   │   ├── storage/                 # DB, Cache
│   │   │   │   └── observability/           # Logging, Metrics
│   │   │   └── ...
│   │   └── pyproject.toml
│   │
│   ├── codegraph-engine/                    # 🐍 Python Engine (Legacy → Deprecated)
│   │   ├── codegraph_engine/
│   │   │   ├── code_foundation/
│   │   │   │   └── infrastructure/
│   │   │   │       ├── ir/
│   │   │   │       │   ├── layered_ir_builder.py  # ⚠️ DEPRECATED (v2.1)
│   │   │   │       │   └── ...                    # ⚠️ Will be removed in v2.2
│   │   │   │       ├── analyzers/
│   │   │   │       │   ├── interprocedural_taint.py  # ⚠️ DEPRECATED
│   │   │   │       │   ├── path_sensitive_taint.py   # ⚠️ DEPRECATED
│   │   │   │       │   └── cost/                     # ⚠️ DEPRECATED
│   │   │   │       │       └── complexity_calculator.py
│   │   │   │       └── parsers/             # ✅ Keep (tree-sitter parsers)
│   │   │   │           ├── __init__.py
│   │   │   │           ├── python.py
│   │   │   │           ├── typescript.py
│   │   │   │           └── ...
│   │   │   └── ...
│   │   └── pyproject.toml
│   │
│   ├── codegraph-analysis/                  # 🔌 Analysis Plugins (NEW!)
│   │   ├── codegraph_analysis/
│   │   │   ├── __init__.py
│   │   │   │   # Plugin registry
│   │   │   │   from .plugin import AnalysisPlugin, PluginRegistry
│   │   │   │   from .security import CryptoPlugin, AuthPlugin
│   │   │   │   from .api_misuse import APIMisusePlugin
│   │   │   │
│   │   │   ├── plugin.py                    # Base plugin interface
│   │   │   │   """
│   │   │   │   from abc import ABC, abstractmethod
│   │   │   │   from codegraph_ir import IRDocument, Finding
│   │   │   │
│   │   │   │   class AnalysisPlugin(ABC):
│   │   │   │       @abstractmethod
│   │   │   │       def analyze(self, ir: IRDocument) -> list[Finding]:
│   │   │   │           pass
│   │   │   │   """
│   │   │   │
│   │   │   ├── security/                    # L22-L23: Security Plugins
│   │   │   │   ├── __init__.py
│   │   │   │   ├── crypto.py                # L22: Crypto patterns
│   │   │   │   │   # WEAK_CRYPTO_PATTERNS = {...}
│   │   │   │   ├── auth.py                  # L23: Auth/AuthZ patterns
│   │   │   │   │   # AUTH_PATTERNS = {...}
│   │   │   │   ├── patterns/                # Pattern databases
│   │   │   │   │   ├── crypto.yaml
│   │   │   │   │   ├── auth.yaml
│   │   │   │   │   └── injection.yaml       # XSS, SQLi patterns
│   │   │   │   └── framework_adapters/      # Framework-specific
│   │   │   │       ├── django.py
│   │   │   │       ├── flask.py
│   │   │   │       └── fastapi.py
│   │   │   │
│   │   │   ├── api_misuse/                  # L29: API Misuse Detection
│   │   │   │   ├── __init__.py
│   │   │   │   ├── stdlib.py                # Python stdlib rules
│   │   │   │   ├── patterns/
│   │   │   │   │   ├── file_ops.yaml        # file.close() missing
│   │   │   │   │   ├── network.yaml         # requests timeout
│   │   │   │   │   └── database.yaml        # session.commit()
│   │   │   │   └── library_rules/
│   │   │   │       ├── requests.py
│   │   │   │       ├── sqlalchemy.py
│   │   │   │       └── asyncio.py
│   │   │   │
│   │   │   ├── patterns/                    # L28: Design Patterns
│   │   │   │   ├── __init__.py
│   │   │   │   ├── design_patterns.py       # Singleton, Factory, etc.
│   │   │   │   └── anti_patterns.py         # God Object, etc.
│   │   │   │
│   │   │   └── coverage/                    # L32: Test Coverage
│   │   │       ├── __init__.py
│   │   │       └── pytest_integration.py
│   │   │
│   │   ├── tests/                           # Plugin tests
│   │   │   ├── test_crypto_plugin.py
│   │   │   ├── test_auth_plugin.py
│   │   │   └── test_api_misuse.py
│   │   │
│   │   ├── pyproject.toml
│   │   └── README.md
│   │
│   ├── codegraph-runtime/                   # 🚀 Runtime (Orchestration)
│   │   ├── codegraph_runtime/
│   │   │   ├── orchestrator.py              # Main orchestrator
│   │   │   │   """
│   │   │   │   # Combines Rust engine + Python plugins
│   │   │   │   from codegraph_ir import IRIndexingOrchestrator
│   │   │   │   from codegraph_analysis import PluginRegistry
│   │   │   │
│   │   │   │   class AnalysisOrchestrator:
│   │   │   │       def __init__(self):
│   │   │   │           self.rust_engine = IRIndexingOrchestrator(...)
│   │   │   │           self.plugins = PluginRegistry()
│   │   │   │
│   │   │   │       def analyze(self, repo_path):
│   │   │   │           # 1. Rust engine
│   │   │   │           result = self.rust_engine.execute(repo_path)
│   │   │   │
│   │   │   │           # 2. Python plugins
│   │   │   │           plugin_findings = self.plugins.run_all(result.ir)
│   │   │   │
│   │   │   │           # 3. Merge results
│   │   │   │           return merge(result, plugin_findings)
│   │   │   │   """
│   │   │   │
│   │   │   ├── config.py                    # Configuration
│   │   │   └── ...
│   │   └── pyproject.toml
│   │
│   └── codegraph-parsers/                   # 📝 Language Parsers (NEW!)
│       ├── codegraph_parsers/               # Tree-sitter parsers
│       │   ├── __init__.py
│       │   ├── python.py                    # From codegraph-engine
│       │   ├── typescript.py
│       │   ├── rust.py
│       │   └── ...
│       └── pyproject.toml
│
├── server/                                   # 🌐 Servers
│   ├── api_server/                          # REST API
│   │   └── main.py
│   └── mcp_server/                          # MCP Server
│       └── main.py
│
├── tests/                                    # 🧪 Integration Tests
│   ├── integration/
│   │   ├── test_rust_python_integration.py  # Rust + Python plugins
│   │   ├── test_taint_analysis.py           # L24
│   │   ├── test_complexity.py               # L27
│   │   └── test_security_plugins.py         # L22-L23
│   └── ...
│
├── docs/                                     # 📚 Documentation
│   ├── adr/
│   │   └── ADR-072-clean-rust-python-architecture.md
│   ├── L22-L32_FINAL_INTEGRATION_PLAN.md
│   ├── RUST_ENGINE_API.md
│   ├── PLUGIN_DEVELOPMENT_GUIDE.md          # NEW!
│   └── MIGRATION_GUIDE_v2.1.md
│
├── pyproject.toml                            # Root (workspace)
├── Cargo.toml                                # Rust workspace
└── README.md
```

---

## Package Dependencies

```
┌─────────────────────────────────────────────────────────┐
│                   codegraph-runtime                     │
│              (Orchestrates Rust + Plugins)              │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
┌──────────────────┐          ┌──────────────────┐
│  codegraph-ir    │          │ codegraph-       │
│  (Rust Engine)   │          │ analysis         │
│                  │          │ (Python Plugins) │
│  • Taint (L24)   │          │                  │
│  • SMT (L27)     │          │  • Crypto (L22)  │
│  • Cost (L27)    │          │  • Auth (L23)    │
│  • Dependency    │          │  • API Misuse    │
│    (L31)         │          │    (L29)         │
└────────┬─────────┘          └────────┬─────────┘
         │                             │
         └──────────┬──────────────────┘
                    ▼
         ┌──────────────────┐
         │ codegraph-shared │
         │ (Infrastructure) │
         │                  │
         │  • Jobs          │
         │  • Storage       │
         │  • Logging       │
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ codegraph-parsers│
         │ (Tree-sitter)    │
         └──────────────────┘
```

---

## Migration Path

### Phase 1: Current State (v2.1.0)

```
✅ codegraph-rust/codegraph-ir          # Rust engine (complete)
✅ codegraph-shared                     # Handlers use Rust
⚠️ codegraph-engine                     # Deprecated (LayeredIRBuilder)
❌ codegraph-analysis                   # Not created yet
```

### Phase 2: Create Plugin Package (Week 3-4)

```bash
# 1. Create new package
mkdir -p packages/codegraph-analysis/codegraph_analysis/{security,api_misuse,patterns,coverage}

# 2. Move patterns from codegraph-engine
mv packages/codegraph-engine/.../deep_security_analyzer.py \
   packages/codegraph-analysis/codegraph_analysis/security/

# 3. Refactor into plugins
# Extract patterns → YAML
# Implement plugin interface
```

### Phase 3: Update Dependencies (Week 5-6)

```toml
# packages/codegraph-runtime/pyproject.toml
[project]
dependencies = [
    "codegraph-ir",        # Rust engine
    "codegraph-analysis",  # Python plugins
    "codegraph-shared",    # Infrastructure
]
```

### Phase 4: Remove Legacy (v2.2.0)

```bash
# Remove deprecated Python analysis
rm -rf packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/analyzers/
rm packages/codegraph-engine/.../layered_ir_builder.py
rm packages/codegraph-engine/.../interprocedural_taint.py

# Keep only parsers
# Move parsers to new package
mkdir packages/codegraph-parsers
mv packages/codegraph-engine/.../parsers/ packages/codegraph-parsers/
```

---

## Alternative: Separate Repos (Option 2)

만약 레포를 분리하고 싶다면:

```
Repo 1: codegraph-engine (Rust)
  └── Rust analysis engine only
      └── PyPI: codegraph-ir

Repo 2: codegraph-plugins (Python)
  └── Analysis plugins
      └── PyPI: codegraph-analysis

Repo 3: codegraph (Main)
  └── Runtime + Infrastructure
      └── Dependencies: codegraph-ir, codegraph-analysis
```

**단점**:
- Version coordination 복잡
- Testing 어려움
- Monorepo가 더 관리 쉬움

**권장**: Option 1 (Monorepo) 유지

---

## pyproject.toml Examples

### Root (Workspace)

```toml
# pyproject.toml (root)
[tool.uv.workspace]
members = [
    "packages/codegraph-rust/codegraph-ir",
    "packages/codegraph-shared",
    "packages/codegraph-analysis",
    "packages/codegraph-runtime",
    "packages/codegraph-parsers",
]
```

### codegraph-ir (Rust)

```toml
# packages/codegraph-rust/codegraph-ir/pyproject.toml
[project]
name = "codegraph-ir"
version = "2.1.0"
description = "Rust-based code analysis engine"
requires-python = ">=3.10"

[build-system]
requires = ["maturin>=1.0,<2.0"]
build-backend = "maturin"

[tool.maturin]
python-source = "python"
module-name = "codegraph_ir"
```

### codegraph-analysis (Plugins)

```toml
# packages/codegraph-analysis/pyproject.toml
[project]
name = "codegraph-analysis"
version = "2.1.0"
description = "Analysis plugins for codegraph"
requires-python = ">=3.10"
dependencies = [
    "codegraph-ir>=2.1.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]
```

### codegraph-runtime

```toml
# packages/codegraph-runtime/pyproject.toml
[project]
name = "codegraph-runtime"
version = "2.1.0"
description = "Runtime orchestration for codegraph"
requires-python = ">=3.10"
dependencies = [
    "codegraph-ir>=2.1.0",
    "codegraph-analysis>=2.1.0",
    "codegraph-shared>=2.1.0",
]
```

---

## Plugin Development Workflow

### 1. Create Plugin

```python
# packages/codegraph-analysis/codegraph_analysis/security/custom_plugin.py

from codegraph_analysis.plugin import AnalysisPlugin
from codegraph_ir import IRDocument, Finding, Severity

class CustomSecurityPlugin(AnalysisPlugin):
    """Custom security checker."""

    def name(self) -> str:
        return "custom-security"

    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ir: IRDocument) -> list[Finding]:
        findings = []

        for node in ir.nodes:
            if node.kind == "Call" and "dangerous_function" in node.name:
                findings.append(Finding(
                    severity=Severity.HIGH,
                    category="dangerous-call",
                    message="Calling dangerous_function",
                    location=node.location,
                ))

        return findings
```

### 2. Register Plugin

```python
# packages/codegraph-runtime/codegraph_runtime/orchestrator.py

from codegraph_analysis import PluginRegistry
from codegraph_analysis.security import CustomSecurityPlugin

registry = PluginRegistry()
registry.register(CustomSecurityPlugin())

# Run all plugins
findings = registry.run_all(ir_document)
```

### 3. Test Plugin

```python
# packages/codegraph-analysis/tests/test_custom_plugin.py

from codegraph_analysis.security import CustomSecurityPlugin
from codegraph_ir import IRDocument, Node

def test_custom_plugin():
    plugin = CustomSecurityPlugin()

    # Create test IR
    ir = IRDocument(
        nodes=[
            Node(kind="Call", name="dangerous_function", ...),
        ]
    )

    findings = plugin.analyze(ir)

    assert len(findings) == 1
    assert findings[0].category == "dangerous-call"
```

---

## Installation

### Development

```bash
# Install all packages in editable mode
uv pip install -e packages/codegraph-rust/codegraph-ir
uv pip install -e packages/codegraph-shared
uv pip install -e packages/codegraph-analysis
uv pip install -e packages/codegraph-runtime

# Or use workspace
uv pip install -e .
```

### Production

```bash
# Install from PyPI (future)
pip install codegraph-runtime  # Includes all dependencies
```

---

## Summary

### ✅ Recommended: Option 1 (Monorepo)

**Structure**:
```
codegraph/
├── packages/
│   ├── codegraph-rust/codegraph-ir/      # Rust engine
│   ├── codegraph-analysis/               # Python plugins (NEW!)
│   ├── codegraph-shared/                 # Infrastructure
│   ├── codegraph-runtime/                # Orchestration
│   ├── codegraph-parsers/                # Tree-sitter parsers
│   └── codegraph-engine/                 # DEPRECATED (remove v2.2)
```

**Benefits**:
- ✅ Clear separation (Rust engine vs Python plugins)
- ✅ Easy to test integration
- ✅ Single version coordination
- ✅ Plugin development workflow
- ✅ Gradual migration path

**Actions**:
1. Create `codegraph-analysis` package (Week 3-4)
2. Refactor patterns into plugins
3. Update `codegraph-runtime` to use plugins
4. Remove `codegraph-engine` analyzers (v2.2.0)

---

**Last Updated**: 2025-12-28
**Status**: Final Design
