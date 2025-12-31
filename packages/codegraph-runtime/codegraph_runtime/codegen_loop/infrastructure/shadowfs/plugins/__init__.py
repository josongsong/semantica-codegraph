"""
ShadowFS Plugins (Infrastructure Layer)

Standard plugins for ShadowFS extension.

Available Plugins:
    - IncrementalUpdatePlugin: Incremental IR updates and indexing
    - LanguageDetector: Language detection by file extension

Note:
    IRSyncPlugin was removed (Phase 2.5) - IncrementalUpdatePlugin handles all IR processing.
"""

from .incremental_plugin import IncrementalUpdatePlugin
from .language_detector import LanguageDetector

__all__ = [
    "IncrementalUpdatePlugin",
    "LanguageDetector",
]
