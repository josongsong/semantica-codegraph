"""
Taint Analysis Infrastructure

TRCR-based (taint-rule-compiler integrated).

Legacy removed, using external trcr.
"""

# Canonical types (from IR)
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.base import (
    Location,
    NarrowingContext,
    TypeInfo,
)

# Adapters (trcr integration)
from .adapters.trcr_adapter import TRCRAdapter

# Configuration (codegraph-specific)
from .configuration.toml_control_parser import TOMLControlParser

# Validation (codegraph-specific)
from .validation.constraint_validator import ConstraintValidator

__all__ = [
    # Canonical types
    "Location",
    "TypeInfo",
    "NarrowingContext",
    # TRCR
    "TRCRAdapter",
    # Configuration
    "TOMLControlParser",
    # Validation
    "ConstraintValidator",
]
