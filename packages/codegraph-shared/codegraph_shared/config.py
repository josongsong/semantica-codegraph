"""
Application Configuration (Unified)

이 모듈은 src.infra.config.settings로 통합되었습니다.
하위 호환성을 위해 re-export합니다.

Usage:
    from codegraph_shared.config import settings

    # 또는 직접 import
    from codegraph_shared.infra.config.settings import settings
"""

# Re-export from unified settings
from codegraph_shared.infra.config.settings import Settings, settings

__all__ = ["Settings", "settings"]
