"""TRCR Configuration.

Central configuration for compiler and runtime.

RFC-033: Tier-based confidence and specificity.
RFC-037: Rule IR Optimization.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TierConfig:
    """Tier classification configuration.

    RFC-033 Section 8: Confidence by Tier.

    Tier Definitions:
        - Tier1: Exact matches (base_type + call, both exact)
        - Tier2: Wildcard matches (suffix/prefix patterns)
        - Tier3: Fuzzy matches (trigram, contains, fallback)

    Confidence Semantics:
        - 1.0: Perfect confidence (exact match)
        - 0.9: High confidence (well-defined pattern)
        - 0.7: Medium confidence (needs verification)
        - 0.5: Low confidence (fallback match)
    """

    # Base confidence by tier
    TIER1_CONFIDENCE: float = 1.0  # Exact match: highest confidence
    TIER2_CONFIDENCE: float = 0.85  # Wildcard: slightly lower
    TIER3_CONFIDENCE: float = 0.6  # Trigram/fallback: needs review

    # Specificity scores (for rule ordering)
    TIER1_SPECIFICITY: int = 100
    TIER2_SPECIFICITY: int = 80
    TIER3_SPECIFICITY: int = 50

    # Penalty/bonus for specificity calculation
    WILDCARD_PENALTY: float = 5.0  # Per wildcard (positive = penalty)
    LITERAL_BONUS: float = 0.1  # Per literal character

    # Tier-specific adjustments
    TIER2_SUFFIX_BONUS: float = 0.05  # Suffix patterns are more specific
    TIER2_PREFIX_BONUS: float = 0.03  # Prefix patterns
    TIER3_TRIGRAM_PENALTY: float = -0.1  # Trigram matches less reliable

    def get_confidence(self, tier: Literal["tier1", "tier2", "tier3"]) -> float:
        """Get base confidence for tier."""
        if tier == "tier1":
            return self.TIER1_CONFIDENCE
        elif tier == "tier2":
            return self.TIER2_CONFIDENCE
        elif tier == "tier3":
            return self.TIER3_CONFIDENCE
        else:
            raise ValueError(f"Invalid tier: {tier}")

    def get_specificity_base(self, tier: Literal["tier1", "tier2", "tier3"]) -> int:
        """Get specificity base for tier."""
        if tier == "tier1":
            return self.TIER1_SPECIFICITY
        elif tier == "tier2":
            return self.TIER2_SPECIFICITY
        elif tier == "tier3":
            return self.TIER3_SPECIFICITY
        else:
            raise ValueError(f"Invalid tier: {tier}")

    def get_tier_adjustment(
        self,
        tier: Literal["tier1", "tier2", "tier3"],
        pattern_type: str | None = None,
    ) -> float:
        """Get confidence adjustment for tier and pattern type.

        Args:
            tier: Rule tier
            pattern_type: Optional pattern type ("suffix", "prefix", "trigram", "fallback")

        Returns:
            Confidence adjustment to add to base
        """
        if tier == "tier1":
            return 0.0  # No adjustment for exact

        if tier == "tier2":
            if pattern_type == "suffix":
                return self.TIER2_SUFFIX_BONUS
            elif pattern_type == "prefix":
                return self.TIER2_PREFIX_BONUS
            return 0.0

        if tier == "tier3":
            if pattern_type == "trigram":
                return self.TIER3_TRIGRAM_PENALTY
            elif pattern_type == "fallback":
                return -0.15  # Fallback is least reliable
            return 0.0

        return 0.0


@dataclass(frozen=True)
class ConfidenceConfig:
    """Confidence scoring configuration."""

    MIN_REPORT_THRESHOLD: float = 0.7
    WILDCARD_ADJUSTMENT: float = -0.05
    NOT_CONST_ADJUSTMENT: float = 0.1
    GUARD_MULTIPLIER: float = 0.3

    def validate_confidence(self, confidence: float) -> None:
        """Validate confidence value."""
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0, 1], got: {confidence}")


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime execution configuration."""

    MAX_CANDIDATES_PER_RULE: int = 10000
    MAX_EXECUTION_TIME_MS: float = 1000.0
    PATTERN_CACHE_SIZE: int = 1000
    INDEX_CACHE_TTL_MS: int = 60000


# Default configurations
DEFAULT_TIER_CONFIG = TierConfig()
DEFAULT_CONFIDENCE_CONFIG = ConfidenceConfig()
DEFAULT_RUNTIME_CONFIG = RuntimeConfig()
