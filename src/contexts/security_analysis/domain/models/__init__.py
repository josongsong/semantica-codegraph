"""Domain Models"""

from .security_rule import (
    RuleRegistry,
    SecurityRule,
    TaintSanitizer,
    TaintSink,
    TaintSource,
    get_registry,
    register_rule,
)
from .vulnerability import CWE, Evidence, Location, ScanResult, Severity, Vulnerability

__all__ = [
    "Vulnerability",
    "Severity",
    "CWE",
    "Location",
    "Evidence",
    "ScanResult",
    "SecurityRule",
    "TaintSource",
    "TaintSink",
    "TaintSanitizer",
    "RuleRegistry",
    "register_rule",
    "get_registry",
]
