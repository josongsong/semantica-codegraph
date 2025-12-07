"""Framework-specific Taint Rules"""

from .flask import FLASK_SOURCES, FLASK_SINKS, FLASK_SANITIZERS

__all__ = [
    "FLASK_SOURCES",
    "FLASK_SINKS",
    "FLASK_SANITIZERS",
]
