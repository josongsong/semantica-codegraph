"""
Zombie Process Killer Adapter (SOTA 구현)
Sandbox 내 프로세스 관리 및 정리

Hexagonal Architecture: Infrastructure Port 사용
"""

import asyncio
import logging

from codegraph_agent.ports.cascade import (
    IProcessManager,
    ProcessInfo,
    ProcessStatus,
)
from codegraph_agent.ports.infrastructure import IProcessMonitor, SystemProcess

logger = logging.getLogger(__name__)


class ProcessManagerAdapter(IProcessManager):
    """
    Zombie Process Killer 구현체

    Hexagonal: IProcessMonitor Port 주입
    """

    def __init__(
        self, process_monitor: IProcessMonitor, zombie_threshold_sec: float = 5.0, cpu_threshold: float = 90.0
    ):
        self.process_monitor = process_monitor
        self.zombie_threshold_sec = zombie_threshold_sec
        self.cpu_threshold = cpu_threshold
        self._tracked_pids: set[int] = set()

    async def scan_processes(self, sandbox_id: str) -> list[ProcessInfo]:
        """
        샌드박스 내 프로세스 스캔

        Hexagonal: IProcessMonitor Port 사용
        """

        logger.debug(f"Scanning processes for sandbox: {sandbox_id}")

        # IProcessMonitor로 프로세스 조회
        system_procs = await self.process_monitor.list_processes(
            filter_fn=lambda p: self._is_sandbox_process_from_system(p, sandbox_id)
        )

        # SystemProcess → ProcessInfo 변환
        processes = []
        for sys_proc in system_procs:
            status = self._map_process_status(sys_proc.status)

            processes.append(
                ProcessInfo(
                    pid=sys_proc.pid,
                    name=sys_proc.name,
                    status=status,
                    ports=sys_proc.ports,
                    cpu_percent=sys_proc.cpu_percent,
                    memory_mb=sys_proc.memory_mb,
                )
            )

            self._tracked_pids.add(sys_proc.pid)

        logger.info(f"Found {len(processes)} sandbox processes")
        return processes

    async def kill_zombies(self, sandbox_id: str, force: bool = False) -> list[int]:
        """
        좀비 프로세스 강제 종료

        Hexagonal: IProcessMonitor Port 사용
        """

        logger.info(f"Killing zombies in sandbox: {sandbox_id} (force={force})")

        # 프로세스 스캔
        processes = await self.scan_processes(sandbox_id)

        killed_pids = []

        for proc_info in processes:
            if proc_info.should_kill():
                # IProcessMonitor로 프로세스 종료
                success = await self.process_monitor.kill_process(proc_info.pid, force=force)
                if success:
                    killed_pids.append(proc_info.pid)
                    self._tracked_pids.discard(proc_info.pid)
                    logger.info(f"Killed process: {proc_info.pid} ({proc_info.name})")

        # Cleanup 후 검증
        await asyncio.sleep(0.5)
        remaining = await self.scan_processes(sandbox_id)
        zombie_count = sum(1 for p in remaining if p.is_zombie())

        if zombie_count > 0:
            logger.warning(f"{zombie_count} zombies still remain")

        return killed_pids

    async def cleanup_ports(self, sandbox_id: str, port_range: tuple[int, int] = (8000, 9000)) -> list[int]:
        """
        점유된 포트 정리

        Hexagonal: IProcessMonitor Port 사용
        """

        logger.info(f"Cleaning up ports {port_range[0]}-{port_range[1]} in sandbox: {sandbox_id}")

        # 프로세스 스캔
        processes = await self.scan_processes(sandbox_id)

        cleaned_ports = []

        for proc_info in processes:
            # 포트 범위 내 점유 확인
            occupied_ports = [port for port in proc_info.ports if port_range[0] <= port <= port_range[1]]

            if occupied_ports:
                logger.info(f"Process {proc_info.pid} occupying ports: {occupied_ports}")

                # IProcessMonitor로 프로세스 종료
                success = await self.process_monitor.kill_process(proc_info.pid, force=True)
                if success:
                    cleaned_ports.extend(occupied_ports)
                    self._tracked_pids.discard(proc_info.pid)

        logger.info(f"Cleaned {len(cleaned_ports)} ports")
        return cleaned_ports

    # ========================================================================
    # Private Methods
    # ========================================================================

    def _is_sandbox_process_from_system(self, proc: SystemProcess, sandbox_id: str) -> bool:
        """
        샌드박스 프로세스인지 확인 (SystemProcess 기반)

        Hexagonal: Infrastructure 세부사항에 의존하지 않음
        """

        # 1. 환경변수로 확인
        if proc.environment.get("SANDBOX_ID") == sandbox_id:
            return True

        # 2. 추적 중인 PID인지 확인
        if proc.pid in self._tracked_pids:
            return True

        return False

    def _map_process_status(self, status_str: str) -> ProcessStatus:
        """시스템 프로세스 상태를 ProcessStatus로 매핑"""

        if status_str == "zombie":
            return ProcessStatus.ZOMBIE
        elif status_str in ("running", "sleeping"):
            return ProcessStatus.RUNNING
        else:
            return ProcessStatus.RUNNING
