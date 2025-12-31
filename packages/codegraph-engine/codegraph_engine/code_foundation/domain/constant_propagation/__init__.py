"""
Constant Propagation Domain

RFC-024: SCCP (Sparse Conditional Constant Propagation) - Baseline

Hexagonal Architecture:
- Domain Layer: 순수 비즈니스 로직 (외부 의존 없음)
- Infrastructure Layer: 기술 구현 (Domain 의존)
"""

from .models import (
    ConstantPropagationResult,
    ConstantValue,
    LatticeValue,
)
from .ports import IConstantPropagator

__all__ = [
    "LatticeValue",
    "ConstantValue",
    "ConstantPropagationResult",
    "IConstantPropagator",
]
