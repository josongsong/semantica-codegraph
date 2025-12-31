"""
Taint Analysis Domain

Type-aware taint analysis with 3-layer factorized architecture.
"""

from .atoms import AtomSpec, MatchRule
from .compiled_policy import CompiledPolicy
from .models import (
    DetectedSanitizer,
    DetectedSink,
    DetectedSource,
    SimpleVulnerability,
    TaintFlow,
    Vulnerability,
)

__all__ = [
    "AtomSpec",
    "CompiledPolicy",
    "DetectedSanitizer",
    "DetectedSink",
    "DetectedSource",
    "MatchRule",
    "SimpleVulnerability",
    "TaintFlow",
    "Vulnerability",
]
