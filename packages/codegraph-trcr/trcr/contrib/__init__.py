"""Community Contribution - RFC-039.

Rule contribution workflow and quality management.

Exports:
    - RuleValidator: Validate contributed rules
    - QualityScorer: Score rule quality
    - PromotionManager: Manage rule promotion
    - ValidationResult: Validation result
"""

from trcr.contrib.promotion import PromotionManager, PromotionStatus, RuleStage
from trcr.contrib.scorer import QualityScorer
from trcr.contrib.validator import (
    RuleValidator,
    ValidationError,
    ValidationResult,
    ValidationWarning,
)

__all__ = [
    # Validator
    "RuleValidator",
    "ValidationResult",
    "ValidationError",
    "ValidationWarning",
    # Scorer
    "QualityScorer",
    # Promotion
    "PromotionManager",
    "PromotionStatus",
    "RuleStage",
]
