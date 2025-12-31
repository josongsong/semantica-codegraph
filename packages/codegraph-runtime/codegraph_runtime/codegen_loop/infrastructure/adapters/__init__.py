"""
Infrastructure Adapters

Hexagonal Architecture: Infrastructure → Application Port 구현
"""

from .unified_shadowfs_adapter import UnifiedShadowFSAdapter

__all__ = [
    "UnifiedShadowFSAdapter",
]
