"""
Type Inference Configuration (Domain Layer)

Externalized configuration for type inference components.
Follows SOTA principle: "외부 경계(설정) = string, 내부 로직 = ENUM/typed models"
"""

from dataclasses import dataclass
from enum import Enum


class InferenceMode(Enum):
    """Type inference mode (internal logic)"""

    FULL = "full"  # All strategies including Pyright
    SELF_CONTAINED = "self_contained"  # No Pyright fallback
    QUICK = "quick"  # Annotation + Literal only


@dataclass(frozen=True)
class LocalFlowConfig:
    """
    Configuration for Local Flow Type Inference.

    Controls CFG/SSA-based local type propagation behavior.

    Attributes:
        max_iterations: Maximum fixpoint iterations (default: 5)
                       Higher = more precise, slower
        max_union_size: Maximum union type size before widening to Any (default: 8)
                       Higher = more precise types, larger memory
        enable_call_propagation: Enable inter-procedural call return type propagation
                                 (default: True)
        enable_ternary: Enable ternary expression type inference (default: True)
        enable_binop: Enable binary operation type inference (default: True)

    Example:
        # Default config
        config = LocalFlowConfig()

        # Custom config for large codebase
        config = LocalFlowConfig(
            max_iterations=3,  # Faster convergence
            max_union_size=16,  # More precise unions
        )

        # Minimal config (fast mode)
        config = LocalFlowConfig(
            max_iterations=2,
            enable_call_propagation=False,  # Intra-procedural only
        )
    """

    max_iterations: int = 5
    max_union_size: int = 8
    enable_call_propagation: bool = True
    enable_ternary: bool = True
    enable_binop: bool = True

    def __post_init__(self):
        """Validate configuration"""
        if self.max_iterations < 1:
            raise ValueError(f"max_iterations must be >= 1, got {self.max_iterations}")
        if self.max_union_size < 2:
            raise ValueError(f"max_union_size must be >= 2, got {self.max_union_size}")


@dataclass(frozen=True)
class SpanPoolConfig:
    """
    Configuration for Span interning pool.

    Attributes:
        max_size: Maximum pool size before LRU eviction (default: 10000)
        enable_stats: Enable statistics tracking (default: True)
    """

    max_size: int = 10000
    enable_stats: bool = True

    def __post_init__(self):
        """Validate configuration"""
        if self.max_size < 100:
            raise ValueError(f"max_size must be >= 100, got {self.max_size}")
