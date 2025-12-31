# Agent Code Foundation Tools

Agent-specific wrappers for code foundation domain layer.

## Architecture

```
Agent Layer (this module)
  ↓ uses
Domain Layer (src/contexts/code_foundation/domain)
  ↓ defines
Port Interfaces
  ↓ implemented by
Infrastructure Layer (src/contexts/code_foundation/infrastructure)
```

## Migration Status

### ✅ Completed
- **Parser, IRGenerator**: Delegating to domain adapters
- **IRAnalyzer**: Using TreeSitterParserAdapter + MultiLanguageIRGeneratorAdapter
- **Stub removal**: No more stub/fake adapters

### ⚠️ Pending
- **SecurityAnalyzer**: Requires TaintAnalysisService integration
- **CallGraphBuilder**: Not yet implemented in infrastructure
- **ReferenceAnalyzer**: Not yet implemented
- **ImpactAnalyzer**: Not yet implemented
- **DependencyGraph**: Not yet implemented

## Usage

### Recommended: Use Domain Layer Directly

```python
from src.contexts.code_foundation.infrastructure.adapters import (
    create_parser_adapter,
    create_ir_generator_adapter,
)

parser = create_parser_adapter()
ir_generator = create_ir_generator_adapter()

ast_doc = parser.parse_code(code, Language.PYTHON)
ir_doc = ir_generator.generate(ast_doc)
```

### Backward Compatibility: Agent Adapters

```python
from src.agent.tools.code_foundation.adapters import RealIRAnalyzerAdapter

analyzer = RealIRAnalyzerAdapter()
ir_doc = analyzer.analyze("path/to/file.py")
```

## Port Definitions

Agent-specific ports in `ports.py` are kept for backward compatibility.

For new code, use domain ports:
- `src.contexts.code_foundation.domain.ports`

## Testing

See integration tests:
- `tests/integration/contexts/code_foundation/adapters/`

All tests use production code (NO STUB, NO FAKE).
