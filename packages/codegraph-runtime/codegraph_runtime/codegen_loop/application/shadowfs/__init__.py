"""
ShadowFS Application Ports

Abstract interfaces (Ports) for Hexagonal Architecture.
Infrastructure layer provides implementations (Adapters).
"""

from .shadowfs_port import ShadowFSPort
from .transaction_port import TransactionPort

__all__ = [
    "ShadowFSPort",
    "TransactionPort",
]
