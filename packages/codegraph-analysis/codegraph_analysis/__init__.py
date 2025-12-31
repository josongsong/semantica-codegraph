"""CodeGraph Analysis Plugins.

Python plugins for domain-specific analysis rules:
- L22: Cryptographic Analysis
- L23: Auth/AuthZ Analysis
- L29: API Misuse Detection
- L28: Design Pattern Detection
- L32: Test Coverage Analysis
"""

from .plugin import AnalysisPlugin, PluginRegistry

__version__ = "2.1.0"

__all__ = [
    "AnalysisPlugin",
    "PluginRegistry",
]
