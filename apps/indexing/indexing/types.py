"""
Application Layer Types

Domain types for Application boundary (external → internal conversion)
"""

from enum import Enum


class SemanticMode(Enum):
    """
    Semantic analysis mode (Application boundary type)

    External (CLI/API): string "quick" or "full"
    Internal (Domain): ENUM SemanticMode.QUICK or FULL

    ✅ SOTA Pattern:
    - External boundary: Accept strings (user-friendly)
    - Internal logic: Use ENUM (type-safe)
    - Conversion at boundary (CLI/API layer)
    """

    QUICK = "quick"
    FULL = "full"

    @classmethod
    def from_string(cls, mode: str) -> "SemanticMode":
        """
        Convert string to ENUM (with validation)

        Args:
            mode: Mode string ("quick" or "full", case-insensitive)

        Returns:
            SemanticMode enum

        Raises:
            ValueError: If mode is invalid
        """
        mode_lower = mode.lower().strip()
        try:
            return cls(mode_lower)
        except ValueError:
            valid_modes = ", ".join([m.value for m in cls])
            raise ValueError(f"Invalid semantic mode: '{mode}'. Expected one of: {valid_modes}")
