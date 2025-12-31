"""TRCR Enums - Type-safe Constants.

Central enum definitions for type safety and IDE support.

SOTA: str-based Enums for JSON compatibility.
"""

from enum import Enum


class Tier(str, Enum):
    """Tier classification levels.

    RFC-033: 3-tier classification system.
    """

    TIER1 = "tier1"
    TIER2 = "tier2"
    TIER3 = "tier3"

    def __str__(self) -> str:
        """String representation."""
        return self.value


class EffectKind(str, Enum):
    """Effect kinds for taint rules.

    RFC-033: 4 effect types.
    """

    SOURCE = "source"
    SINK = "sink"
    SANITIZER = "sanitizer"
    PROPAGATOR = "propagator"

    def __str__(self) -> str:
        """String representation."""
        return self.value


class EntityKind(str, Enum):
    """Entity kinds for code entities.

    RFC-033: Entity protocol kinds.
    """

    CALL = "call"
    READ = "read"
    ASSIGN = "assign"

    def __str__(self) -> str:
        """String representation."""
        return self.value


class GeneratorKind(str, Enum):
    """Generator kinds for candidate generation.

    RFC-033: Generator types.
    """

    EXACT_TYPE_CALL = "exact_type_call"
    EXACT_CALL = "exact_call"
    EXACT_TYPE_READ = "exact_type_read"
    TYPE_SUFFIX = "type_suffix"
    CALL_PREFIX = "call_prefix"
    TYPE_TRIGRAM = "type_trigram"
    FALLBACK = "fallback"

    def __str__(self) -> str:
        """String representation."""
        return self.value


class IndexKind(str, Enum):
    """Index kinds for entity lookup.

    RFC-034: Index types.
    """

    EXACT_TYPE_CALL = "exact_type_call"
    EXACT_CALL = "exact_call"
    EXACT_TYPE_READ = "exact_type_read"
    PREFIX_TRIE = "prefix_trie"
    SUFFIX_TRIE = "suffix_trie"
    TRIGRAM = "trigram"
    FUZZY = "fuzzy"
    FALLBACK = "fallback"

    def __str__(self) -> str:
        """String representation."""
        return self.value
