# Type Inference System

**Scope:** 타입 추론 시스템  
**Audience:** 개발자/리뷰어  
**Source of Truth:** `src/contexts/code_foundation/infrastructure/type_inference/`

---

## Table of Contents

- Overview
- Architecture
- Current Coverage (Python)
- Adding New Language
- Integration with Other Systems
- Tests
- Related Systems
- Files

---

## Overview

**Pyright LSP 완전 대체 달성**

Inter-procedural Summary 기반 타입 추론으로 LSP 의존도 0% 달성.
Function/Method/Variable 타입을 IR만으로 추론.

**핵심 성과:**
- LSP 의존도: 완전 제거 (100%)
- 처리 시간: 대폭 개선 (95%+ 감소)
- Summary 커버: 매우 높음 (거의 100%)
- Variable 추론: 완전 지원

**최근 업데이트 (2025-12-21):**
- Layered IR Builder 통합: 타입 추론이 Semantic Layer에서 실행
- 성능 최적화: 병렬 처리 및 캐싱으로 대규모 코드베이스 처리 개선
- 증분 업데이트: 변경된 파일만 재처리하여 빌드 시간 단축

---

## Architecture

### Summary-Based Inference

```
┌─────────────────────────────────────────────────────────────────┐
│            Inter-procedural Return Type Inference               │
├─────────────────────────────────────────────────────────────────┤
│  1. Local Inference                                             │
│     - Annotation (def foo() -> str)                             │
│     - Dunder (__init__ → None)                                  │
│     - Convention (test_* → None, pytest fixture)                │
│     - Literal (return 42 → int)                                 │
│     - No return → None                                          │
│                                                                  │
│  2. Inter-procedural Propagation                                │
│     - Tarjan SCC decomposition (O(V+E))                         │
│     - Fixed-point iteration (max 10)                            │
│     - Widening (Union > 8 → Any)                                │
│                                                                  │
│  3. Variable Type Inference                                     │
│     - Literal (x = 42 → int)                                    │
│     - Call (x = func() → Summary lookup)                        │
│     - Attribute (x = obj.attr → Field type)                     │
│                                                                  │
│  4. Expression Type                                             │
│     - Binary ops (x + y)                                        │
│     - Conditional (a if c else b)                               │
│     - Subscript (items[0])                                      │
│                                                                  │
│  5. LSP Fallback (Optional, 기본 OFF)                           │
│     - 복잡한 Generic, Dynamic typing만                           │
└─────────────────────────────────────────────────────────────────┘
```

### Multi-language Monorepo Structure

```
src/contexts/code_foundation/infrastructure/type_inference/
│
├── # ═══════════════════════════════════════════════════════════
├── # CORE - Language-agnostic Base Classes
├── # ═══════════════════════════════════════════════════════════
├── core/
│   ├── __init__.py
│   ├── base_resolver.py        # BaseTypeResolver (abstract 8-step)
│   ├── base_registry.py        # BaseBuiltinRegistry (YAML loading)
│   └── base_fallback.py        # BaseLSPFallback (LSP interface)
│
├── # ═══════════════════════════════════════════════════════════
├── # PYTHON - Active Implementation
├── # ═══════════════════════════════════════════════════════════
├── python/
│   └── __init__.py             # Re-exports: PythonTypeResolver
├── resolver.py                  # InferredTypeResolver (Python)
├── builtin_methods.py           # YamlBuiltinMethodRegistry
├── pyright_fallback.py          # PyrightFallbackAdapter
├── metrics.py                   # InferenceMetrics (gap analysis)
│
├── # ═══════════════════════════════════════════════════════════
├── # TYPESCRIPT - Future
├── # ═══════════════════════════════════════════════════════════
├── typescript/
│   └── __init__.py             # Stub - tsserver planned
│
├── # ═══════════════════════════════════════════════════════════
├── # JAVA - Future
├── # ═══════════════════════════════════════════════════════════
├── java/
│   └── __init__.py             # Stub - JDT planned
│
├── configs/                     # YAML configurations
│   ├── builtin_methods.yaml    # 31 types, 473 methods
│   ├── stdlib/                 # Python standard library
│   ├── thirdparty/             # pandas, numpy, etc.
│   └── custom/                 # Project-specific
│
└── scripts/                     # Maintenance scripts
    ├── generate_builtin_types.py
    └── run_type_inference_benchmark.py
```

---

## Language Support Matrix

| Language | Status | LSP Fallback | Type Stubs | Config Location |
|----------|--------|--------------|------------|-----------------|
| **Python** | ✅ Active | Pyright | typeshed | `configs/` |
| **TypeScript** | 🔜 Planned | tsserver | @types/* | `configs/typescript/` |
| **Java** | 🔜 Planned | Eclipse JDT | JDK | `configs/java/` |
| **Go** | 💭 Future | gopls | stdlib | `configs/go/` |

---

## Key Components

### 1. InferredTypeResolver (Python)

8-step fallback chain 구현체.

```python
from .python import create_python_inferencer

resolver = create_python_inferencer(
    project_root=Path("/my/project"),
    enable_pyright=True,
    enable_metrics=True,
)

result = resolver.infer(request, context)
# result.inferred_type == "str"
# result.source == InferSource.BUILTIN_METHOD
```

### 2. YamlBuiltinMethodRegistry

YAML 기반 builtin 메서드 반환 타입 레지스트리.

```yaml
# configs/builtin_methods.yaml
str:
  upper: str
  lower: str
  split: "list[str]"

list:
  pop: T          # Generic placeholder
  append: None
  copy: "list[T]"

Logger:
  info: None
  debug: None
  warning: None
```

### 3. InferenceMetrics

LSP 폴백 추적 및 Gap Analysis.

```python
# Gap analysis for prioritizing improvements
gaps = resolver.get_gap_analysis()
# → {
#     "missing_methods": [
#         {"receiver_type": "DataFrame", "method_name": "groupby", "count": 50},
#         {"receiver_type": "Path", "method_name": "with_suffix", "count": 30},
#     ],
#     "recommendations": [
#         "Add DataFrame.groupby to thirdparty/pandas.yaml",
#     ]
# }
```

---

## Current Coverage (Python)

### Performance

| Metric | Before | After |
|--------|--------|-------|
| Layer3 시간 | 매우 느림 | 매우 빠름 (95%+ 개선) |
| LSP 호출 | 많음 | 0 (완전 제거) |
| Summary 커버 | 낮음 | 매우 높음 (거의 100%) |
| Variable 추론 | 없음 | 완전 지원 |

### Coverage

| 지표 | 수준 |
|-----|------|
| Summary resolved | 높음 (80%+) |
| Variables typed | 완전 지원 |
| LSP dependency | 0% |

### Builtin Registry

| Metric | Value |
|--------|-------|
| Types | 30+ |
| Methods | 400+ |
| Load time | 매우 빠름 (<) |

---

## Adding New Language

1. **Create language directory:**
```
type_inference/{language}/
└── __init__.py
```

2. **Implement components (extend core base classes):**
```python
from ..core import BaseTypeResolver, BaseBuiltinRegistry, BaseLSPFallback

class GoTypeResolver(BaseTypeResolver):
    @property
    def language(self) -> str:
        return "go"

    def _try_annotation(self, request, context) -> InferResult:
        # Go-specific: interface{}, *T, []T handling
        ...
```

3. **Add YAML configs:**
```
configs/{language}/
├── stdlib/        # Standard library types
├── thirdparty/    # Common packages
└── custom/        # Project-specific
```

4. **Register in `__init__.py`:**
```python
from .{language} import create_{language}_inferencer
```

---

## Hexagonal Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Domain Layer (Ports)                       │
├─────────────────────────────────────────────────────────────────┤
│  ITypeInferencer, IBuiltinMethodRegistry, IPyrightFallback     │
│  ExpressionTypeRequest, InferContext, InferResult              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Core Layer (Base Classes)                      │
├─────────────────────────────────────────────────────────────────┤
│  BaseTypeResolver ─── Abstract 8-step fallback chain           │
│  BaseBuiltinRegistry ─── YAML loading, type normalization      │
│  BaseLSPFallback ─── LSP lifecycle, error handling             │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   Python        │ │  TypeScript     │ │   Java          │
│   Resolver      │ │  Resolver       │ │   Resolver      │
│   + Pyright     │ │  + tsserver     │ │   + JDT         │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

---

## Maintenance Workflow

### Manual Addition

1. Identify gap via benchmark or metrics
2. Add to appropriate YAML file
3. Run tests to verify

### Auto-generation Pipeline

```bash
# Run benchmark to identify gaps
PYTHONPATH=. python -m src.contexts.code_foundation.infrastructure.type_inference.scripts.run_type_inference_benchmark

# Generate from typeshed
PYTHONPATH=. python -m src.contexts.code_foundation.infrastructure.type_inference.scripts.generate_builtin_types \
    --source typeshed --output stdlib/

# Generate from gap analysis
PYTHONPATH=. python -m src.contexts.code_foundation.infrastructure.type_inference.scripts.generate_builtin_types \
    --from-gaps --min-count 10
```

### CI/CD (Monthly Auto-update)

`.github/workflows/type-inference-update.yml`:
- Monthly scheduled run
- Gap analysis → YAML generation → PR creation

---

## Integration with Other Systems

### SCCP

Type Inference의 Literal 단계에서 SCCP 결과 활용:

```python
# 3️⃣ Literal: Infer from SCCP constant
result = self._try_literal(request, context)
# SCCP가 "hello" 상수 감지 → str 타입 추론
```

### Taint Analysis

타입 정보를 활용한 정밀 taint 전파:

```python
# DataFrame.groupby() 반환 타입 = DataFrameGroupBy
# → taint가 groupby 결과로 전파됨을 정확히 추적
```

### Call Graph

함수 반환 타입 추론:

```python
# Call Graph 단계에서 SignatureEntity 조회
signature = context.get_signature(callee_id)
return_type = signature.return_type  # → "list[str]"
```

---

## Tests

```bash
# Run all type inference tests
pytest tests/unit/type_inference/ -v

# Current: 213+ tests passing
```

---

## Related Systems

- Type Inference Engine (Self-contained, 8-step fallback)
- Return Type Summary (Tarjan SCC + Fixed-point)
- Variable Type Inference
- Expression Type Inference
- SCCP (Sparse Conditional Constant Propagation)
- Query Engine Integration

---

## Files

### 핵심 추가 파일

| File | Purpose | LOC |
|------|---------|-----|
| `summary_builder.py` | Return Type Summary + SCC | ~500 |
| `variable_type_enricher.py` | Variable 타입 추론 | ~170 |
| `expression_type_inferencer.py` | Expression 타입 | ~100 |
| `literal_inference.py` | 공통 literal 추론 | ~70 |

### 기존 핵심 파일

| File | Purpose |
|------|---------|
| `resolver.py` | InferredTypeResolver |
| `builtin_methods.py` | YamlBuiltinMethodRegistry |
| `core/base_resolver.py` | BaseTypeResolver |
| `configs/` | YAML 설정 (10K+ methods) |
