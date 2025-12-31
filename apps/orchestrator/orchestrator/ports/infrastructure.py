"""
Infrastructure Abstraction Ports (Hexagonal Architecture 완벽 준수)

Domain/Application Layer가 Infrastructure 라이브러리에 직접 의존하지 않도록
모든 외부 시스템 접근을 Port로 추상화
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


@dataclass
class CommandResult:
    """명령 실행 결과"""

    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: float
    status: CommandStatus

    def is_success(self) -> bool:
        return self.exit_code == 0 and self.status == CommandStatus.SUCCESS


@dataclass
class SystemProcess:
    """시스템 프로세스 정보"""

    pid: int
    name: str
    status: str
    cpu_percent: float
    memory_mb: float
    ports: list[int]
    environment: dict[str, str]

    def is_zombie(self) -> bool:
        return self.status == "zombie"

    def is_high_resource(self, cpu_threshold: float = 90.0) -> bool:
        return self.cpu_percent > cpu_threshold


@dataclass
class FileSystemEntry:
    """파일 시스템 엔트리"""

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


class ICommandExecutor(Protocol):
    """
    명령 실행 Port (subprocess, Docker exec 등 추상화)

    Hexagonal 원칙: Adapter는 이 Port를 구현하여 실제 subprocess를 호출
    """

    async def execute(
        self,
        command: list[str],
        cwd: str | None = None,
        timeout: float = 30.0,
        capture_output: bool = True,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """
        명령 실행

        Args:
            command: 실행할 명령 (리스트 형태)
            cwd: 작업 디렉토리
            timeout: 타임아웃 (초)
            capture_output: stdout/stderr 캡처 여부
            env: 환경 변수

        Returns:
            CommandResult: 실행 결과
        """
        ...


class IProcessMonitor(Protocol):
    """
    프로세스 모니터링 Port (psutil 추상화)

    Hexagonal 원칙: 시스템 프로세스 접근을 추상화하여 테스트 가능하게
    """

    async def list_processes(self, filter_fn: callable | None = None) -> list[SystemProcess]:
        """
        프로세스 목록 조회

        Args:
            filter_fn: 필터 함수 (Optional)

        Returns:
            List[SystemProcess]: 프로세스 목록
        """
        ...

    async def kill_process(self, pid: int, force: bool = False) -> bool:
        """
        프로세스 종료

        Args:
            pid: 프로세스 ID
            force: SIGKILL 사용 여부

        Returns:
            bool: 성공 여부
        """
        ...

    async def get_processes_by_port(self, port_range: tuple[int, int]) -> list[SystemProcess]:
        """
        포트 점유 프로세스 조회

        Args:
            port_range: (start, end) 포트 범위

        Returns:
            List[SystemProcess]: 프로세스 목록
        """
        ...


class IFileSystem(Protocol):
    """
    파일 시스템 Port (pathlib, os 추상화)

    Hexagonal 원칙: 파일 시스템 접근을 추상화하여 테스트에서 Mock 가능
    """

    async def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """파일 읽기"""
        ...

    async def write_text(self, path: str, content: str, encoding: str = "utf-8") -> None:
        """파일 쓰기"""
        ...

    async def exists(self, path: str) -> bool:
        """파일/디렉토리 존재 여부"""
        ...

    async def get_info(self, path: str) -> FileSystemEntry:
        """파일 정보 조회"""
        ...

    async def create_temp_file(self, suffix: str = "", prefix: str = "tmp", content: str | None = None) -> str:
        """임시 파일 생성"""
        ...

    async def delete(self, path: str) -> None:
        """파일/디렉토리 삭제"""
        ...
