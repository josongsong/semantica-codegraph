# CodeGraph Reasoning Engine

SOTA (State-of-the-Art) Reasoning Engine for intelligent code analysis and refactoring.

## Features

### RFC-101 Implementation

- **Phase 1: SOTA Boundary Matcher** (46 tests)
  - Multi-stage matching (Pattern → Graph → LLM)
  - Fast-path optimization (95%+ confidence → instant match)
  - Decision path tracking

- **Phase 2: LLM-Guided Refactoring** (38 tests)
  - Multi-layer verification (syntax, type, boundary preservation)
  - Two-phase planning (generate plan → apply with approval)
  - Fail-closed safety guarantees

- **Cross-Language Support** (33 tests)
  - Python (Flask, FastAPI, Django)
  - TypeScript (Express, Nest.js, Next.js)
  - Java (Spring, JAX-RS, Micronaut)
  - Go (Gin, Echo, Fiber, Chi)

### Architecture

- **Hexagonal Architecture** (Ports & Adapters)
- **SOLID Principles** (all 5)
- **Strategy Pattern** (language-specific detectors)
- **Dependency Injection** (testable, modular)

## Installation

```bash
# Install from source
cd packages/codegraph-reasoning
pip install -e .

# With dev dependencies
pip install -e ".[dev]"
```

## Usage

```python
from codegraph_reasoning.infrastructure.boundary import LanguageAwareSOTAMatcher
from codegraph_shared.kernel.contracts import BoundarySpec, BoundaryType, HTTPMethod

# Initialize matcher
matcher = LanguageAwareSOTAMatcher()

# Match boundary
spec = BoundarySpec(
    boundary_type=BoundaryType.HTTP_ENDPOINT,
    endpoint="/api/users/{id}",
    http_method=HTTPMethod.GET,
)

result = matcher.match_boundary(spec, ir_docs=ir_documents)

if result.success:
    print(f"Found: {result.best_match.function_name}")
    print(f"Confidence: {result.confidence:.1%}")
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test suite
pytest tests/test_language_detectors.py -v
pytest tests/test_sota_boundary_matcher.py -v
pytest tests/test_llm_refactoring.py -v
```

## Documentation

- [SOTA Boundary Matcher](codegraph_reasoning/SOTA_BOUNDARY_MATCHER.md)
- [LLM Refactoring Guide](codegraph_reasoning/LLM_REFACTORING_GUIDE.md)
- [Cross-Language Support](codegraph_reasoning/CROSS_LANGUAGE_SUPPORT.md)

## Test Results

```
Total: 117 tests passed
- Phase 1 (SOTA Matcher): 46 passed
- Phase 2 (LLM Refactoring): 38 passed
- Cross-Language: 33 passed
```

## License

Proprietary
