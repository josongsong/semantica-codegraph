"""Domain Models"""

from .security_rule import (
    RuleRegistry,
    SecurityRule,
    TaintSanitizer,
    TaintSink,
    TaintSource,
    get_registry,
    register_rule,
    reset_registry,
    set_registry,
)
from .vulnerability import CWE, Evidence, Location, ScanResult, Severity, Vulnerability

__all__ = [
    # Vulnerability models
    "Vulnerability",
    "Severity",
    "CWE",
    "Location",
    "Evidence",
    "ScanResult",
    # Security rule models
    "SecurityRule",
    "TaintSource",
    "TaintSink",
    "TaintSanitizer",
    # Registry
    "RuleRegistry",
    "register_rule",
    "get_registry",
    "set_registry",
    "reset_registry",
]
