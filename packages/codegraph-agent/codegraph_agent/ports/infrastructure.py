"""
Infrastructure Abstraction Ports (Hexagonal Architecture)

Domain/Application Layer가 Infrastructure에 직접 의존하지 않도록
모든 외부 시스템 접근을 Port로 추상화

SOLID: Dependency Inversion Principle (DIP)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


# ============================================================================
# Domain Models (Infrastructure-agnostic)
# ============================================================================


class CommandStatus(Enum):
    """명령 실행 상태"""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class InfraCommandResult:
    """명령 실행 결과 (Immutable Value Object)"""

    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: float
    status: CommandStatus

    def is_success(self) -> bool:
        return self.exit_code == 0 and self.status == CommandStatus.SUCCESS


@dataclass(frozen=True)
class SystemProcess:
    """시스템 프로세스 정보 (Immutable Value Object)"""

    pid: int
    name: str
    status: str
    cpu_percent: float
    memory_mb: float
    ports: tuple[int, ...]
    environment: tuple[tuple[str, str], ...]  # Immutable

    def is_zombie(self) -> bool:
        return self.status == "zombie"

    def is_high_resource(self, cpu_threshold: float = 90.0) -> bool:
        return self.cpu_percent > cpu_threshold


@dataclass(frozen=True)
class FileSystemEntry:
    """파일 시스템 엔트리 (Immutable Value Object)"""

    path: str
    exists: bool
    is_file: bool
    is_directory: bool
    size_bytes: int

    def is_readable(self) -> bool:
        return self.exists and (self.is_file or self.is_directory)


# ============================================================================
# Infrastructure Ports
# ============================================================================


class IInfraCommandExecutor(Protocol):
    """
    명령 실행 Port (subprocess, Docker exec 등 추상화)

    FuzzyPatcher, GitAdapter 등에서 사용
    """

    async def execute(
        self,
        command: list[str],
        cwd: str | None = None,
        timeout: float = 30.0,
        capture_output: bool = True,
        env: dict[str, str] | None = None,
    ) -> InfraCommandResult:
        """명령 실행"""
        ...


class IProcessMonitor(Protocol):
    """
    프로세스 모니터링 Port (psutil 추상화)

    ProcessManager에서 좀비 프로세스 처리에 사용
    """

    async def list_processes(
        self,
        filter_fn: callable | None = None,
    ) -> list[SystemProcess]:
        """프로세스 목록 조회"""
        ...

    async def kill_process(
        self,
        pid: int,
        force: bool = False,
    ) -> bool:
        """프로세스 종료"""
        ...

    async def get_processes_by_port(
        self,
        port_range: tuple[int, int],
    ) -> list[SystemProcess]:
        """포트 점유 프로세스 조회"""
        ...


# Backward compatibility alias
CommandResult = InfraCommandResult
ICommandExecutor = IInfraCommandExecutor


class IFileSystem(Protocol):
    """
    파일 시스템 Port (pathlib, os 추상화)

    FuzzyPatcher, ShadowFS 등에서 사용
    """

    async def read_text(
        self,
        path: str,
        encoding: str = "utf-8",
    ) -> str:
        """파일 읽기"""
        ...

    async def write_text(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
    ) -> None:
        """파일 쓰기"""
        ...

    async def exists(self, path: str) -> bool:
        """파일/디렉토리 존재 여부"""
        ...

    async def get_info(self, path: str) -> FileSystemEntry:
        """파일 정보 조회"""
        ...

    async def create_temp_file(
        self,
        suffix: str = "",
        prefix: str = "tmp",
        content: str | None = None,
    ) -> str:
        """임시 파일 생성"""
        ...

    async def delete(self, path: str) -> None:
        """파일/디렉토리 삭제"""
        ...
