"""
Type Inference Domain

Pyright-independent type inference with fallback chain.

Architecture:
    ┌─────────────────────────────────────────────────────────────────────┐
    │                    Type Inference Fallback Chain                     │
    ├─────────────────────────────────────────────────────────────────────┤
    │  [1] Annotation  ──Yes──►  Done ✅                                  │
    │  [2] Narrowing   ──Yes──►  Done ✅  (isinstance → str)              │
    │  [3] Literal     ──Yes──►  Done ✅  (SCCP: x = 42 → int)           │
    │  [4] Call Graph  ──Yes──►  Done ✅  (foo() → Signature.return)     │
    │  [5] Overload    ──Yes──►  Done ✅  (overload resolution)          │
    │  [6] Builtin     ──Yes──►  Done ✅  (str.upper() → str)            │
    │  [7] Phi-node    ──Yes──►  Done ✅  (SSA Union)                    │
    │  [8] Pyright     ──Yes──►  Done ✅  (fallback)                     │
    └─────────────────────────────────────────────────────────────────────┘

Hexagonal:
    - Ports: ITypeInferencer, IBuiltinMethodRegistry (Domain)
    - Adapters: InferredTypeResolver, YamlBuiltinMethodRegistry (Infrastructure)

SOLID:
    - Single Responsibility: Type inference only
    - Open/Closed: New inference strategies via chain
    - Liskov: All adapters substitutable
    - Interface Segregation: Minimal ports
    - Dependency Inversion: Domain defines contracts
"""

from .models import (
    ExpressionTypeRequest,
    InferContext,
    InferResult,
    InferSource,
    PhiNodeEntry,
    TypeNarrowingEntry,
)
from .ports import IBuiltinMethodRegistry, IPyrightFallback, ITypeInferencer

__all__ = [
    # Ports
    "ITypeInferencer",
    "IBuiltinMethodRegistry",
    "IPyrightFallback",
    # Models
    "ExpressionTypeRequest",
    "InferContext",
    "InferResult",
    "InferSource",
    "TypeNarrowingEntry",
    "PhiNodeEntry",
]
