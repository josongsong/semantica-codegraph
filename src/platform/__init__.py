"""
Platform Layer

애플리케이션 런타임 인프라 관리.
도메인 로직(Container)과 분리하여 플랫폼 컴포넌트 관리.
"""

from src.platform.runtime import RuntimeManager

__all__ = ["RuntimeManager"]
