"""
Security domain models and configurations
"""

from .semantic_sanitizer_detector import SemanticSanitizerDetector
from .taint_config import TaintConfig

__all__ = [
    "TaintConfig",
    "SemanticSanitizerDetector",
]
