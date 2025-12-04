"""
Type System IR

TypeEntity, TypeFlavor, TypeResolutionLevel

Note: TypeResolver should be imported directly from .resolver to avoid circular imports
"""

from src.contexts.code_foundation.infrastructure.semantic_ir.typing.models import (
    TypeEntity,
    TypeFlavor,
    TypeResolutionLevel,
)

__all__ = [
    "TypeEntity",
    "TypeFlavor",
    "TypeResolutionLevel",
]
