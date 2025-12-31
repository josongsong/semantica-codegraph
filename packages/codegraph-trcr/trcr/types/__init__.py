"""Shared types - Domain Layer.

Entity Protocol and Match results.
RFC-038: Guard types for guard-aware execution.
"""

from trcr.types.entity import Entity, MockEntity
from trcr.types.enums import EffectKind, EntityKind, GeneratorKind, IndexKind, Tier
from trcr.types.guards import (
    AllowlistGuard,
    EscapeGuard,
    Guard,
    GuardType,
    LengthGuard,
    RegexGuard,
    SanitizerGuard,
    TypeGuard,
    calculate_combined_multiplier,
    has_fail_fast_guard,
    has_strong_guard,
)
from trcr.types.match import Match, MatchContext, TraceInfo

__all__ = [
    # Entity
    "Entity",
    "MockEntity",
    # Match
    "Match",
    "MatchContext",
    "TraceInfo",
    # Enums (Type-safe)
    "Tier",
    "EffectKind",
    "EntityKind",
    "GeneratorKind",
    "IndexKind",
    # Guards (RFC-038)
    "Guard",
    "GuardType",
    "AllowlistGuard",
    "RegexGuard",
    "LengthGuard",
    "TypeGuard",
    "EscapeGuard",
    "SanitizerGuard",
    "calculate_combined_multiplier",
    "has_strong_guard",
    "has_fail_fast_guard",
]
