"""Domain Models"""

from .vulnerability import Vulnerability, Severity, CWE, Location, Evidence, ScanResult
from .security_rule import (
    SecurityRule,
    TaintSource,
    TaintSink,
    TaintSanitizer,
    RuleRegistry,
    register_rule,
    get_registry,
)

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
