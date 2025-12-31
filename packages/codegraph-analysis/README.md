# CodeGraph Analysis Plugins

Python plugins for domain-specific analysis rules.

## Features

This package provides analysis plugins that consume IR from the Rust engine (`codegraph-ir`) and apply domain-specific rules:

- **L22-L23**: Security patterns (crypto, auth/authz)
- **L29**: API misuse detection
- **L28**: Design pattern detection
- **L32**: Test coverage analysis

## Architecture

```
┌─────────────────┐
│  Rust Engine    │  ← codegraph-ir (Taint, SMT, Complexity)
│  (codegraph-ir) │
└────────┬────────┘
         │ IR Documents
         ▼
┌─────────────────┐
│ Python Plugins  │  ← codegraph-analysis
│ (This package)  │
└─────────────────┘
         │
         ▼
   Findings (Security, Patterns, etc.)
```

## Installation

```bash
# Install from local path
uv pip install -e packages/codegraph-analysis

# Or as dependency
pip install codegraph-analysis
```

## Usage

### Basic Plugin Usage

```python
from codegraph_analysis.plugin import PluginRegistry
from codegraph_analysis.security import framework_adapters

# Get IR documents from Rust engine
import codegraph_ir

config = codegraph_ir.E2EPipelineConfig(root_path="/repo")
orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
result = orchestrator.execute()

ir_documents = result.ir_documents

# Create custom plugin
from codegraph_analysis.plugin import AnalysisPlugin

class CryptoPlugin(AnalysisPlugin):
    def name(self) -> str:
        return "crypto"

    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ir_documents):
        findings = []
        # Your analysis logic here
        return findings

# Run plugins
registry = PluginRegistry()
registry.register(CryptoPlugin())

findings = registry.run_all(ir_documents)
```

### Framework Adapters

The package includes pre-defined taint sources and sinks for popular frameworks:

```python
from codegraph_analysis.security.framework_adapters import (
    DJANGO_TAINT_SOURCES,
    DJANGO_TAINT_SINKS,
    FLASK_TAINT_SOURCES,
    FASTAPI_TAINT_SOURCES,
)

# Use in your taint analysis
for source in DJANGO_TAINT_SOURCES:
    print(f"Source: {source}")
```

#### Django Adapter

```python
from codegraph_analysis.security.framework_adapters.django import (
    DJANGO_TAINT_SOURCES,    # request.GET, request.POST, etc.
    DJANGO_TAINT_SINKS,      # cursor.execute, os.system, etc.
    DJANGO_SANITIZERS,       # escape, mark_safe, etc.
    DJANGO_AUTH_DECORATORS,  # @login_required, etc.
)
```

#### Flask Adapter

```python
from codegraph_analysis.security.framework_adapters.flask import (
    FLASK_TAINT_SOURCES,     # request.args, request.form, etc.
    FLASK_TAINT_SINKS,       # render_template_string, etc.
    FLASK_AUTH_DECORATORS,   # @login_required, etc.
)
```

#### FastAPI Adapter

```python
from codegraph_analysis.security.framework_adapters.fastapi import (
    FASTAPI_TAINT_SOURCES,       # Query(...), Body(...), etc.
    FASTAPI_AUTH_DEPENDENCIES,   # Depends(get_current_user), etc.
)
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
        findings = []

        for doc in ir_documents:
            nodes = doc.get("nodes", [])
            for node in nodes:
                # Your analysis logic
                if self._is_vulnerable(node):
                    findings.append({
                        "severity": "HIGH" | "MEDIUM" | "LOW",
                        "category": "my-category",
                        "message": "Description of issue",
                        "location": node.get("location", {}),
                        "remediation": "How to fix",
                    })

        return findings

    def _is_vulnerable(self, node):
        # Your detection logic
        pass
```

## Testing

```bash
# Run tests
pytest tests/integration/test_python_plugins.py -v

# Run with coverage
pytest tests/integration/test_python_plugins.py -v --cov=codegraph_analysis
```

## Migration from v2.0

If you were using the old `codegraph-engine` analyzers:

### Before (v2.0)
```python
from codegraph_engine.code_foundation.infrastructure.analyzers import TaintAnalyzer
analyzer = TaintAnalyzer()
paths = analyzer.analyze(...)
```

### After (v2.1+)
```python
# Use Rust engine for analysis
import codegraph_ir
config = codegraph_ir.E2EPipelineConfig(
    root_path="/repo",
    enable_taint=True,
)
orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
result = orchestrator.execute()

# Use Python plugins for domain rules
from codegraph_analysis.plugin import PluginRegistry
registry = PluginRegistry()
# Register your plugins...
findings = registry.run_all(result.ir_documents)
```

## Dependencies

- `codegraph-ir>=2.1.0` - Rust analysis engine (provides IR)
- `pyyaml>=6.0` - For pattern files

## License

See top-level LICENSE file.
