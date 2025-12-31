"""
Command Executor Port (Hexagonal Architecture)

RFC-060 Section 4: LocalCommandAdapter
- 로컬 터미널에서 명령 실행
- Safety: 위험 명령 차단 / 승인 요청
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    """명령 실행 결과 (Immutable Value Object)"""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    rejected: bool = False  # 사용자가 거부함
    rejection_reason: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.rejected


class ICommandExecutor(Protocol):
    """Command Executor Port

    책임:
    - 로컬 쉘에서 명령 실행
    - 위험 명령 차단 (블랙리스트)
    - 파괴적 명령 승인 요청

    Safety:
    - BLACKLIST: 절대 실행 불가 (rm -rf /, dd if=)
    - APPROVAL_REQUIRED: 사용자 승인 필요 (rm -rf, git push --force)
    """

    async def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float = 60.0,
        require_approval: bool | None = None,
    ) -> CommandResult:
        """
        명령 실행

        Args:
            command: 실행할 명령
            cwd: 작업 디렉토리 (None이면 현재 디렉토리)
            timeout: 타임아웃 (초)
            require_approval: 승인 필요 여부 (None이면 자동 판단)

        Returns:
            CommandResult: 실행 결과
        """
        ...

    def is_blacklisted(self, command: str) -> bool:
        """블랙리스트에 해당하는 명령인지 확인"""
        ...

    def needs_approval(self, command: str) -> bool:
        """승인이 필요한 명령인지 확인"""
        ...
