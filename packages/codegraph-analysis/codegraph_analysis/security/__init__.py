"""Security analysis plugins (L22-L23).

Provides domain-specific security analysis:
- L22: Cryptographic Analysis
- L23: Auth/AuthZ Analysis
- L24: Injection Analysis

These plugins consume IR from the Rust engine and apply
framework-specific security rules.
"""

from . import framework_adapters, patterns
from .crypto_plugin import CryptoPlugin

__all__ = [
    "framework_adapters",
    "patterns",
    "CryptoPlugin",
]
