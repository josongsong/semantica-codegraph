"""
Runtime Manager

백그라운드 런타임 컴포넌트 통합 관리.

단순 레지스트리 패턴 - 복잡한 추상화 없이 start_all/stop_all만 제공.
"""

import asyncio
from typing import Any, Protocol

from src.common.observability import get_logger

logger = get_logger(__name__)


class Startable(Protocol):
    """Start 가능한 컴포넌트"""

    async def start(self) -> None: ...


class Stoppable(Protocol):
    """Stop 가능한 컴포넌트"""

    async def stop(self) -> None: ...


class RuntimeManager:
    """
    단순 레지스트리 - start/stop 가능한 모든 컴포넌트 관리.

    목적: 한 곳에서 일괄 start_all/stop_all 제공
    """

    def __init__(self):
        # 단순 dict - name -> component
        self.components: dict[str, Any] = {}
        self.running = False

    def register(self, name: str, component: Any) -> None:
        """
        컴포넌트 등록 (start/stop 메서드만 있으면 됨).

        Args:
            name: 컴포넌트 이름
            component: start(), stop() 메서드가 있는 인스턴스
        """
        if name in self.components:
            logger.warning(f"Component '{name}' already registered, overwriting")

        self.components[name] = component
        logger.debug(f"Component registered: {name}")

    async def start_all(self) -> None:
        """모든 등록된 컴포넌트 시작"""
        if self.running:
            logger.warning("RuntimeManager already running")
            return

        self.running = True
        logger.info(f"Starting {len(self.components)} runtime components...")

        for name, component in self.components.items():
            try:
                if hasattr(component, "start"):
                    if asyncio.iscoroutinefunction(component.start):
                        await component.start()
                    else:
                        component.start()
                    logger.info(f"  ✓ {name}")
                else:
                    logger.warning(f"  ⚠ {name} has no start() method")
            except Exception as e:
                logger.error(f"  ✗ {name} failed: {e}")

    async def stop_all(self) -> None:
        """모든 등록된 컴포넌트 정리"""
        if not self.running:
            return

        logger.info(f"Stopping {len(self.components)} runtime components...")

        for name, component in self.components.items():
            try:
                if hasattr(component, "stop"):
                    if asyncio.iscoroutinefunction(component.stop):
                        await component.stop()
                    else:
                        component.stop()
                    logger.info(f"  ✓ {name}")
                else:
                    logger.debug(f"  ⊘ {name} has no stop() method")
            except Exception as e:
                logger.error(f"  ✗ {name} failed: {e}")

        self.running = False

    def get(self, name: str) -> Any | None:
        """컴포넌트 조회"""
        return self.components.get(name)

    def get_status(self) -> dict:
        """전체 상태 조회"""
        return {
            "running": self.running,
            "components": {name: self._get_status(c) for name, c in self.components.items()},
        }

    def _get_status(self, component: Any) -> str:
        """단일 컴포넌트 상태"""
        if hasattr(component, "is_running"):
            return "running" if component.is_running else "stopped"
        if hasattr(component, "running"):
            return "running" if component.running else "stopped"
        return "unknown"
