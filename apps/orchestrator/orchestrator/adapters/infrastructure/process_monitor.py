"""
Process Monitor Adapter (psutil 추상화)
"""

import asyncio
import logging
import signal
from collections.abc import Callable

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from codegraph_agent.ports.infrastructure import (
    IProcessMonitor,
    SystemProcess,
)

logger = logging.getLogger(__name__)


class PsutilAdapter(IProcessMonitor):
    """psutil 기반 Process Monitor"""

    def __init__(self):
        if not HAS_PSUTIL:
            raise RuntimeError("psutil not installed. Install with: pip install psutil")

    async def list_processes(self, filter_fn: Callable | None = None) -> list[SystemProcess]:
        """프로세스 목록 조회"""

        processes = []

        for proc in psutil.process_iter(["pid", "name", "status", "cpu_percent", "memory_info"]):
            try:
                info = proc.info

                # 환경 변수
                try:
                    env = proc.environ()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    env = {}

                # 포트 정보
                ports = self._get_listening_ports(proc)

                system_proc = SystemProcess(
                    pid=info["pid"],
                    name=info["name"],
                    status=info["status"],
                    cpu_percent=info["cpu_percent"] or 0.0,
                    memory_mb=info["memory_info"].rss / 1024 / 1024 if info["memory_info"] else 0.0,
                    ports=ports,
                    environment=env,
                )

                # 필터 적용
                if filter_fn is None or filter_fn(system_proc):
                    processes.append(system_proc)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return processes

    async def kill_process(self, pid: int, force: bool = False) -> bool:
        """프로세스 종료"""

        try:
            proc = psutil.Process(pid)

            if force:
                # SIGKILL (강제)
                proc.send_signal(signal.SIGKILL)
                logger.debug(f"Sent SIGKILL to {pid}")
            else:
                # SIGTERM (정상 종료)
                proc.terminate()
                logger.debug(f"Sent SIGTERM to {pid}")

                # 1초 대기
                await asyncio.sleep(1.0)

                # 아직 살아있으면 SIGKILL
                if proc.is_running():
                    proc.kill()
                    logger.debug(f"Sent SIGKILL to {pid} (after SIGTERM)")

            # 종료 확인 (최대 2초)
            for _ in range(20):
                if not proc.is_running():
                    return True
                await asyncio.sleep(0.1)

            logger.warning(f"Process {pid} still alive after kill")
            return False

        except psutil.NoSuchProcess:
            # 이미 종료됨
            return True
        except Exception as e:
            logger.error(f"Failed to kill process {pid}: {e}")
            return False

    async def get_processes_by_port(self, port_range: tuple[int, int]) -> list[SystemProcess]:
        """포트 점유 프로세스 조회"""

        start_port, end_port = port_range

        def port_filter(proc: SystemProcess) -> bool:
            return any(start_port <= port <= end_port for port in proc.ports)

        return await self.list_processes(filter_fn=port_filter)

    def _get_listening_ports(self, proc: psutil.Process) -> list[int]:
        """프로세스가 listening 중인 포트"""

        ports = []

        try:
            connections = proc.connections(kind="inet")
            for conn in connections:
                if conn.status == "LISTEN":
                    ports.append(conn.laddr.port)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        return ports
