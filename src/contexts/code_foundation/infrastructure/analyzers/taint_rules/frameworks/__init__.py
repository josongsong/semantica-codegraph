"""Framework-specific Taint Rules"""

from .flask import FLASK_SANITIZERS, FLASK_SINKS, FLASK_SOURCES

__all__ = [
    "FLASK_SOURCES",
    "FLASK_SINKS",
    "FLASK_SANITIZERS",
]
