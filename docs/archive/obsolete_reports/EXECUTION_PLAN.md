# 실행 계획 - 기존 구조 정리

**Date**: 2025-12-28
**Status**: Ready to Execute
**Timeline**: 2-3주

---

## 목표

기존 패키지 구조를 정리하여 Rust-Python 경계를 명확히 하고 중복을 제거합니다.

**핵심 원칙**:
- ✅ **Rust 엔진은 그대로**: `codegraph-rust/codegraph-ir/` 유지 (23,471 LOC)
- ✅ **Parser는 그대로**: `codegraph-parsers/` 유지 (이미 분리됨)
- ✅ **Python 플러그인 통합**: `codegraph-analysis`로 consolidate
- ✅ **중복 제거**: 4개 패키지 → 1개로

---

## 현재 상황

### ✅ 잘 되어 있는 것

```
packages/
├── codegraph-rust/              # ✅ Rust engine (23,471 LOC)
│   └── codegraph-ir/            # Taint, SMT, Cost all done
│
├── codegraph-parsers/           # ✅ Parser package (이미 분리됨!)
│   └── codegraph_parsers/
│       ├── parsing/             # Tree-sitter parsers
│       ├── template/            # Vue, JSX parsers
│       └── document/            # Markdown, Jupyter parsers
│
├── codegraph-shared/            # ✅ Infrastructure
├── codegraph-runtime/           # ✅ Orchestration
└── ...
```

### ❌ 정리 필요한 것

```
packages/
├── codegraph-engine/            # ⚠️ DEPRECATED
│   └── infrastructure/
│       ├── analyzers/           # 🗑️ REMOVE (Rust로 대체됨)
│       │   ├── interprocedural_taint.py
│       │   ├── path_sensitive_taint.py
│       │   └── cost/
│       ├── ir/
│       │   └── layered_ir_builder.py  # 🗑️ REMOVE (Rust로 대체됨)
│       └── parsers/             # 🔄 MOVE to codegraph-parsers (중복)
│           ├── vue_sfc_parser.py
│           └── jsx_template_parser.py
│
├── codegraph-taint/             # 🗑️ REMOVE (Rust 사용)
├── codegraph-security/          # 🔄 MERGE → codegraph-analysis
└── security-rules/              # 🔄 MERGE → codegraph-analysis
```

---

## 목표 구조 (v2.2.0)

```
packages/
├── codegraph-rust/              # 🦀 Rust Engine
│   ├── codegraph-ir/            # ✅ Taint, SMT, Cost, Dependency
│   ├── codegraph-orchestration/
│   └── codegraph-storage/
│
├── codegraph-parsers/           # 📝 Parsers (통합)
│   └── codegraph_parsers/
│       ├── parsing/             # Tree-sitter parsers
│       ├── template/            # Vue, JSX (from codegraph-engine)
│       └── document/            # Markdown, Jupyter
│
├── codegraph-analysis/          # 🔌 Python Plugins (신규)
│   └── codegraph_analysis/
│       ├── plugin.py            # Base plugin interface
│       ├── registry.py          # Plugin registry
│       │
│       ├── security/            # L22-L23 (3개 패키지 통합)
│       │   ├── __init__.py
│       │   ├── crypto.py        # From codegraph-security
│       │   ├── auth.py          # From codegraph-security
│       │   ├── patterns/        # From security-rules
│       │   │   ├── crypto.yaml
│       │   │   ├── auth.yaml
│       │   │   └── injection.yaml
│       │   └── framework_adapters/
│       │       ├── django.py    # Taint sources/sinks
│       │       ├── flask.py
│       │       └── fastapi.py
│       │
│       ├── api_misuse/          # L29
│       │   ├── __init__.py
│       │   ├── stdlib.py
│       │   └── patterns/
│       │       ├── file_ops.yaml
│       │       ├── network.yaml
│       │       └── database.yaml
│       │
│       ├── patterns/            # L28
│       │   ├── __init__.py
│       │   ├── design_patterns.py
│       │   └── anti_patterns.py
│       │
│       └── coverage/            # L32
│           ├── __init__.py
│           └── pytest_integration.py
│
├── codegraph-shared/            # 🔧 Infrastructure
├── codegraph-runtime/           # 🚀 Runtime (Rust + Plugins)
├── codegraph-agent/             # 🤖 Agent
├── codegraph-ml/                # 🧠 ML
└── codegraph-search/            # 🔍 Search
```

---

## Week 1: Python 플러그인 통합

### Day 1-2: codegraph-analysis 패키지 생성

**Step 1: 디렉토리 구조 생성**

```bash
cd packages/

# Create codegraph-analysis package
mkdir -p codegraph-analysis/codegraph_analysis/security/{crypto,auth,patterns,framework_adapters}
mkdir -p codegraph-analysis/codegraph_analysis/api_misuse/patterns
mkdir -p codegraph-analysis/codegraph_analysis/patterns
mkdir -p codegraph-analysis/codegraph_analysis/coverage
mkdir -p codegraph-analysis/tests/security
mkdir -p codegraph-analysis/tests/api_misuse
```

**Step 2: pyproject.toml 생성**

```bash
cat > codegraph-analysis/pyproject.toml << 'EOF'
[project]
name = "codegraph-analysis"
version = "2.1.0"
description = "Analysis plugins for CodeGraph (security, API misuse, patterns)"
authors = [
    {name = "CodeGraph Team"}
]
requires-python = ">=3.10"
dependencies = [
    "codegraph-ir>=2.1.0",      # Rust engine for IR
    "pyyaml>=6.0",              # Pattern files
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["codegraph_analysis"]
EOF
```

### Day 3-4: Plugin 인터페이스 구현

**Step 3: Base plugin interface**

```bash
cat > codegraph-analysis/codegraph_analysis/plugin.py << 'EOF'
"""Base plugin interface for CodeGraph analysis plugins."""

from abc import ABC, abstractmethod
from typing import Any, Protocol


class AnalysisPlugin(ABC):
    """Base class for all analysis plugins."""

    @abstractmethod
    def name(self) -> str:
        """Return plugin name."""
        pass

    @abstractmethod
    def version(self) -> str:
        """Return plugin version."""
        pass

    @abstractmethod
    def analyze(self, ir_documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Analyze IR documents and return findings.

        Args:
            ir_documents: List of IR documents from Rust engine

        Returns:
            List of findings with format:
            {
                "severity": "HIGH" | "MEDIUM" | "LOW",
                "category": str,
                "message": str,
                "location": {"file": str, "line": int, "column": int},
                "remediation": str,
            }
        """
        pass


class PluginRegistry:
    """Registry for managing analysis plugins."""

    def __init__(self):
        self.plugins: dict[str, AnalysisPlugin] = {}

    def register(self, plugin: AnalysisPlugin) -> None:
        """Register a plugin."""
        self.plugins[plugin.name()] = plugin

    def unregister(self, plugin_name: str) -> None:
        """Unregister a plugin."""
        if plugin_name in self.plugins:
            del self.plugins[plugin_name]

    def get(self, plugin_name: str) -> AnalysisPlugin | None:
        """Get a plugin by name."""
        return self.plugins.get(plugin_name)

    def list_plugins(self) -> list[str]:
        """List all registered plugin names."""
        return list(self.plugins.keys())

    def run_all(self, ir_documents: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """
        Run all registered plugins.

        Returns:
            Dictionary mapping plugin names to their findings
        """
        results = {}
        for name, plugin in self.plugins.items():
            try:
                findings = plugin.analyze(ir_documents)
                results[name] = findings
            except Exception as e:
                # Log error but continue with other plugins
                results[name] = [
                    {
                        "severity": "ERROR",
                        "category": "plugin-error",
                        "message": f"Plugin {name} failed: {str(e)}",
                        "location": {},
                    }
                ]
        return results
EOF
```

**Step 4: __init__.py**

```bash
cat > codegraph-analysis/codegraph_analysis/__init__.py << 'EOF'
"""CodeGraph Analysis Plugins."""

from .plugin import AnalysisPlugin, PluginRegistry

__version__ = "2.1.0"

__all__ = [
    "AnalysisPlugin",
    "PluginRegistry",
]
EOF
```

### Day 5: Security 패키지 통합

**Step 5: Security 코드 복사**

```bash
# Copy from codegraph-security
if [ -d "packages/codegraph-security/codegraph_security" ]; then
    cp -r packages/codegraph-security/codegraph_security/* \
          packages/codegraph-analysis/codegraph_analysis/security/
fi

# Copy from security-rules
if [ -d "packages/security-rules" ]; then
    cp -r packages/security-rules/* \
          packages/codegraph-analysis/codegraph_analysis/security/patterns/
fi
```

**Step 6: Framework adapters 생성**

```bash
cat > codegraph-analysis/codegraph_analysis/security/framework_adapters/django.py << 'EOF'
"""Django-specific security patterns."""

# Taint sources (user input)
DJANGO_TAINT_SOURCES = [
    "request.GET",
    "request.POST",
    "request.FILES",
    "request.COOKIES",
    "request.META",
    "request.body",
]

# Taint sinks (dangerous operations)
DJANGO_TAINT_SINKS = [
    "cursor.execute",
    "cursor.executemany",
    "QuerySet.raw",
    "QuerySet.extra",
    "eval",
    "exec",
    "os.system",
    "subprocess.call",
    "subprocess.Popen",
    "render_to_response",  # XSS if not escaped
]

# Sanitizers (safe operations)
DJANGO_SANITIZERS = [
    "django.utils.html.escape",
    "django.utils.html.escapejs",
    "django.utils.safestring.mark_safe",
    "django.db.models.Q",  # ORM sanitizes
    "django.db.models.F",
]

# Auth/AuthZ decorators
DJANGO_AUTH_DECORATORS = [
    "@login_required",
    "@permission_required",
    "@user_passes_test",
]

# Security middleware
DJANGO_SECURITY_MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
EOF

cat > codegraph-analysis/codegraph_analysis/security/framework_adapters/flask.py << 'EOF'
"""Flask-specific security patterns."""

FLASK_TAINT_SOURCES = [
    "request.args",
    "request.form",
    "request.files",
    "request.cookies",
    "request.headers",
    "request.data",
    "request.json",
]

FLASK_TAINT_SINKS = [
    "eval",
    "exec",
    "os.system",
    "subprocess.call",
    "render_template_string",  # XSS if not escaped
]

FLASK_SANITIZERS = [
    "escape",
    "Markup.escape",
]

FLASK_AUTH_DECORATORS = [
    "@login_required",
    "@roles_required",
    "@roles_accepted",
]
EOF

cat > codegraph-analysis/codegraph_analysis/security/framework_adapters/fastapi.py << 'EOF'
"""FastAPI-specific security patterns."""

FASTAPI_TAINT_SOURCES = [
    "Query(...)",
    "Path(...)",
    "Body(...)",
    "Header(...)",
    "Cookie(...)",
    "Form(...)",
]

FASTAPI_TAINT_SINKS = [
    "eval",
    "exec",
    "os.system",
]

FASTAPI_AUTH_DEPENDENCIES = [
    "Depends(get_current_user)",
    "Depends(get_current_active_user)",
    "Security(...)",
]
EOF
```

---

## Week 2: 중복 제거 & Parser 통합

### Day 1-2: Parser 통합

**Step 1: codegraph-engine parsers → codegraph-parsers**

```bash
# Check for duplicates first
echo "Checking for duplicate parsers..."

# Vue parser
if [ -f "packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/parsers/vue_sfc_parser.py" ]; then
    if [ -f "packages/codegraph-parsers/codegraph_parsers/template/vue_sfc_parser.py" ]; then
        echo "⚠️ Vue parser exists in both packages - comparing..."
        diff packages/codegraph-engine/.../vue_sfc_parser.py \
             packages/codegraph-parsers/.../vue_sfc_parser.py || true
    else
        echo "Moving Vue parser to codegraph-parsers..."
        cp packages/codegraph-engine/.../vue_sfc_parser.py \
           packages/codegraph-parsers/codegraph_parsers/template/
    fi
fi

# JSX parser
if [ -f "packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/parsers/jsx_template_parser.py" ]; then
    if [ -f "packages/codegraph-parsers/codegraph_parsers/template/jsx_template_parser.py" ]; then
        echo "⚠️ JSX parser exists in both packages - comparing..."
        diff packages/codegraph-engine/.../jsx_template_parser.py \
             packages/codegraph-parsers/.../jsx_template_parser.py || true
    else
        echo "Moving JSX parser to codegraph-parsers..."
        cp packages/codegraph-engine/.../jsx_template_parser.py \
           packages/codegraph-parsers/codegraph_parsers/template/
    fi
fi
```

**Step 2: Update codegraph-parsers __init__.py**

```python
# packages/codegraph-parsers/codegraph_parsers/__init__.py

from .parsing import *
from .template import *
from .document import *

__all__ = [
    # Parsing
    "ParserRegistry",
    "SourceFile",
    "ASTTree",
    # Template
    "VueSFCParser",
    "JSXTemplateParser",
    # Document
    "MarkdownParser",
    "JupyterParser",
]
```

### Day 3: Import 변경

**Step 3: 모든 import 업데이트**

```bash
# Update imports from deprecated packages
echo "Updating imports..."

# codegraph_taint → codegraph_ir
find packages/ tests/ server/ -name "*.py" -type f -exec sed -i '' \
  's/from codegraph_taint/from codegraph_ir/g' {} \;

# codegraph_security → codegraph_analysis.security
find packages/ tests/ server/ -name "*.py" -type f -exec sed -i '' \
  's/from codegraph_security/from codegraph_analysis.security/g' {} \;

# codegraph_engine.*.parsers → codegraph_parsers
find packages/ tests/ server/ -name "*.py" -type f -exec sed -i '' \
  's/from codegraph_engine\.code_foundation\.infrastructure\.parsers/from codegraph_parsers/g' {} \;
```

### Day 4: pyproject.toml 업데이트

**Step 4: 의존성 업데이트**

```bash
# Update codegraph-runtime
cat > packages/codegraph-runtime/pyproject.toml.new << 'EOF'
[project]
name = "codegraph-runtime"
version = "2.1.0"
requires-python = ">=3.10"
dependencies = [
    "codegraph-ir>=2.1.0",          # Rust engine (NEW: was optional)
    "codegraph-analysis>=2.1.0",    # Python plugins (NEW)
    "codegraph-parsers>=0.1.0",     # Parsers
    "codegraph-shared>=2.1.0",
]

# Remove old dependencies:
# - codegraph-taint
# - codegraph-security
# - codegraph-engine (for analyzers)
EOF

# Update codegraph-shared
cat > packages/codegraph-shared/pyproject.toml.new << 'EOF'
[project]
name = "codegraph-shared"
version = "2.1.0"
requires-python = ">=3.10"
dependencies = [
    "codegraph-ir>=2.1.0",      # Rust engine
    "codegraph-parsers>=0.1.0", # Parsers
    # Remove: codegraph-engine (for LayeredIRBuilder)
]
EOF
```

### Day 5: 중복 패키지 삭제

**Step 5: Verify no dependencies**

```bash
# Check for lingering references
echo "Checking for references to deprecated packages..."

rg "from codegraph_taint" packages/ tests/ server/ || echo "✅ No codegraph_taint imports"
rg "from codegraph_security" packages/ tests/ server/ || echo "✅ No codegraph_security imports"
rg "codegraph.engine.*analyzers" packages/ tests/ server/ || echo "✅ No analyzer imports"
```

**Step 6: Delete deprecated packages**

```bash
# DANGEROUS - only run after verifying no dependencies!
echo "⚠️ Ready to delete deprecated packages"
echo "Press Ctrl+C to abort, or Enter to continue..."
read

# Remove deprecated packages
rm -rf packages/codegraph-taint/
rm -rf packages/codegraph-security/
rm -rf packages/security-rules/

# Remove deprecated code from codegraph-engine
rm -rf packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/analyzers/
rm -f packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/layered_ir_builder.py
rm -rf packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/parsers/

echo "✅ Deprecated packages removed"
```

---

## Week 3: 테스트 & 검증

### Day 1-2: Integration tests

**Step 1: Rust engine test**

```python
# tests/integration/test_rust_engine.py

import codegraph_ir


def test_rust_taint_analysis():
    """Test Rust taint analysis works."""
    config = codegraph_ir.E2EPipelineConfig(
        root_path="/test/repo",
        enable_taint=True,
        parallel_workers=2,
    )

    orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
    result = orchestrator.execute()

    assert result.success
    assert len(result.ir_documents) > 0


def test_rust_complexity_analysis():
    """Test Rust complexity analysis works."""
    config = codegraph_ir.E2EPipelineConfig(
        root_path="/test/repo",
        enable_complexity=True,
    )

    orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
    result = orchestrator.execute()

    assert result.success
```

**Step 2: Python plugin test**

```python
# tests/integration/test_python_plugins.py

from codegraph_analysis.registry import PluginRegistry
from codegraph_analysis.security.crypto import CryptoPlugin


def test_plugin_registry():
    """Test plugin registry works."""
    registry = PluginRegistry()

    # Register plugin
    plugin = CryptoPlugin()
    registry.register(plugin)

    assert "crypto" in registry.list_plugins()


def test_crypto_plugin():
    """Test crypto plugin detects weak crypto."""
    plugin = CryptoPlugin()

    # Mock IR with MD5 usage
    ir_documents = [
        {
            "nodes": [
                {
                    "kind": "Call",
                    "name": "hashlib.md5",
                    "location": {"file": "test.py", "line": 10},
                }
            ]
        }
    ]

    findings = plugin.analyze(ir_documents)

    assert len(findings) > 0
    assert findings[0]["category"] == "weak-crypto"
    assert "md5" in findings[0]["message"].lower()
```

### Day 3: Benchmark

**Step 3: Performance test**

```python
# benchmark/test_rust_vs_python.py

import time
import codegraph_ir


def test_rust_taint_performance(benchmark_repo):
    """Benchmark Rust taint analysis."""
    config = codegraph_ir.E2EPipelineConfig(
        root_path=benchmark_repo,
        enable_taint=True,
        parallel_workers=4,
    )

    start = time.time()
    orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
    result = orchestrator.execute()
    duration = time.time() - start

    print(f"✅ Rust taint: {duration:.2f}s")
    print(f"   Files: {len(result.ir_documents)}")
    print(f"   Findings: {len(result.taint_findings)}")

    # Should be < 1s for 1000 files
    assert duration < 1.0, f"Too slow: {duration:.2f}s"
```

### Day 4-5: Documentation & Cleanup

**Step 4: Update documentation**

```bash
# Update README
cat > packages/codegraph-analysis/README.md << 'EOF'
# CodeGraph Analysis Plugins

Python plugins for domain-specific analysis rules.

## Features

- **L22-L23**: Security patterns (crypto, auth/authz)
- **L29**: API misuse detection
- **L28**: Design pattern detection
- **L32**: Test coverage analysis

## Usage

```python
from codegraph_analysis.registry import PluginRegistry
from codegraph_analysis.security import CryptoPlugin, AuthPlugin

# Setup plugins
registry = PluginRegistry()
registry.register(CryptoPlugin())
registry.register(AuthPlugin())

# Run on IR documents
findings = registry.run_all(ir_documents)
```

## Plugin Development

Create custom plugins by extending `AnalysisPlugin`:

```python
from codegraph_analysis.plugin import AnalysisPlugin

class MyPlugin(AnalysisPlugin):
    def name(self) -> str:
        return "my-plugin"

    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ir_documents):
        # Your analysis logic
        return findings
```
EOF
```

**Step 5: Cleanup deprecation warnings**

Since we're removing the deprecated packages entirely, we can also clean up deprecation warnings:

```bash
# Remove deprecation warnings from files we're keeping
# (since the old code is completely gone now)
```

---

## Summary

### 삭제되는 것

```
packages/
├── codegraph-taint/             # 🗑️ DELETED
├── codegraph-security/          # 🗑️ DELETED
├── security-rules/              # 🗑️ DELETED
└── codegraph-engine/
    └── infrastructure/
        ├── analyzers/           # 🗑️ DELETED
        ├── ir/layered_ir_builder.py  # 🗑️ DELETED
        └── parsers/             # 🗑️ DELETED (moved to codegraph-parsers)
```

### 생성되는 것

```
packages/
└── codegraph-analysis/          # 🆕 NEW
    └── codegraph_analysis/
        ├── plugin.py            # Plugin interface
        ├── registry.py          # Plugin registry
        ├── security/            # From 3 packages
        ├── api_misuse/          # New
        ├── patterns/            # New
        └── coverage/            # New
```

### 통합되는 것

```
packages/
└── codegraph-parsers/           # 🔄 CONSOLIDATED
    └── codegraph_parsers/
        ├── parsing/             # Existing
        ├── template/            # + Vue/JSX from codegraph-engine
        └── document/            # Existing
```

---

## Rollback Plan

만약 문제가 생기면:

```bash
# Git revert all changes
git revert HEAD~10..HEAD

# Or restore specific packages
git checkout v2.1.0 -- packages/codegraph-taint
git checkout v2.1.0 -- packages/codegraph-security
git checkout v2.1.0 -- packages/security-rules
```

---

## Verification Checklist

### Before deletion:
- [ ] All imports updated (no references to deprecated packages)
- [ ] Tests pass with new structure
- [ ] Benchmark shows expected performance
- [ ] Documentation updated

### After deletion:
- [ ] `pytest tests/ -v` passes (모든 테스트 통과)
- [ ] No import errors in runtime
- [ ] Rust engine works (taint + complexity)
- [ ] Python plugins work
- [ ] Parser integration works

---

**Last Updated**: 2025-12-28
**Status**: Ready to Execute
**Timeline**: 2-3 weeks
