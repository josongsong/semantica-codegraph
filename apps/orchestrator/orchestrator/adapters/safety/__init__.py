"""
Safety Adapters

Concrete implementations of Safety ports.
"""

from .action_gate import DangerousActionGateAdapter, RiskClassifier
from .license_checker import LicenseComplianceCheckerAdapter
from .secret_scanner import SecretScrubberAdapter

__all__ = [
    "SecretScrubberAdapter",
    "LicenseComplianceCheckerAdapter",
    "DangerousActionGateAdapter",
    "RiskClassifier",
]
