"""
Local Command Adapter

RFC-060 Section 4.1: LocalCommandAdapter
- 로컬 터미널에서 명령 실행
- Safety: 위험 명령 차단 / 승인 요청
"""

import asyncio
import logging
import re
import time
from typing import Callable

from codegraph_agent.ports.command import (
    CommandResult,
    ICommandExecutor,
)

logger = logging.getLogger(__name__)


class DangerousCommandError(Exception):
    """위험한 명령 실행 시도"""

    pass


class LocalCommandAdapter(ICommandExecutor):
    """
    Local Command Adapter

    Safety 기능:
    - BLACKLIST: 절대 실행 불가
    - APPROVAL_REQUIRED: 사용자 승인 필요

    Dependency Injection:
    - approval_callback: 승인 요청 콜백 (Optional)
    """

    # 절대 실행 불가 명령 패턴
    BLACKLIST = [
        r"rm\s+-rf\s+/\s*$",  # rm -rf /
        r"rm\s+-rf\s+~\s*$",  # rm -rf ~
        r"dd\s+if=.*of=/dev/",  # dd to device
        r"mkfs\.",  # format filesystem
        r">\s*/dev/sd",  # write to device
        r":\(\)\s*{\s*:\|:\s*&\s*}\s*;:",  # fork bomb
    ]

    # 승인 필요 명령 패턴
    APPROVAL_REQUIRED = [
        r"rm\s+-rf",  # rm -rf (not root)
        r"git\s+push\s+.*--force",  # force push
        r"git\s+reset\s+--hard",  # hard reset
        r"DROP\s+TABLE",  # SQL drop
        r"DELETE\s+FROM.*WHERE\s+1\s*=\s*1",  # delete all
        r"truncate\s+",  # truncate
        r"chmod\s+777",  # insecure permissions
    ]

    def __init__(
        self,
        approval_callback: Callable[[str], bool] | None = None,
        default_timeout: float = 60.0,
    ):
        """
        Args:
            approval_callback: 승인 요청 콜백
                - None이면 APPROVAL_REQUIRED 명령 자동 거부
                - 함수(command) -> bool 형태
            default_timeout: 기본 타임아웃 (초)
        """
        self._approval_callback = approval_callback
        self._default_timeout = default_timeout

        # Compile patterns
        self._blacklist_patterns = [re.compile(p, re.IGNORECASE) for p in self.BLACKLIST]
        self._approval_patterns = [re.compile(p, re.IGNORECASE) for p in self.APPROVAL_REQUIRED]

    async def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float | None = None,
        require_approval: bool | None = None,
    ) -> CommandResult:
        """
        명령 실행

        Safety:
        1. BLACKLIST 체크 → DangerousCommandError
        2. APPROVAL_REQUIRED 체크 → 콜백 호출 또는 거부
        """
        timeout = timeout or self._default_timeout

        # 1. Blacklist 체크
        if self.is_blacklisted(command):
            raise DangerousCommandError(f"Blocked command: {command}")

        # 2. Approval 체크
        if require_approval is None:
            require_approval = self.needs_approval(command)

        if require_approval:
            approved = await self._request_approval(command)
            if not approved:
                return CommandResult(
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    timed_out=False,
                    rejected=True,
                    rejection_reason="User rejected the command",
                )

        # 3. 실행
        start_time = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )

            return CommandResult(
                exit_code=proc.returncode or 0,
                stdout=stdout_bytes.decode(errors="replace"),
                stderr=stderr_bytes.decode(errors="replace"),
                timed_out=False,
                rejected=False,
            )

        except asyncio.TimeoutError:
            logger.warning(f"Command timed out after {timeout}s: {command}")
            # 프로세스 종료 시도
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass

            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                timed_out=True,
                rejected=False,
            )

        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                timed_out=False,
                rejected=False,
            )

    def is_blacklisted(self, command: str) -> bool:
        """블랙리스트에 해당하는 명령인지 확인"""
        for pattern in self._blacklist_patterns:
            if pattern.search(command):
                return True
        return False

    def needs_approval(self, command: str) -> bool:
        """승인이 필요한 명령인지 확인"""
        for pattern in self._approval_patterns:
            if pattern.search(command):
                return True
        return False

    async def _request_approval(self, command: str) -> bool:
        """승인 요청"""
        if self._approval_callback is None:
            logger.warning(f"No approval callback, rejecting: {command}")
            return False

        logger.info(f"Requesting approval for: {command}")

        # 콜백이 async인지 확인
        if asyncio.iscoroutinefunction(self._approval_callback):
            return await self._approval_callback(command)
        else:
            # Sync callback → loop에서 실행
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self._approval_callback,
                command,
            )


# ============================================================================
# Console Approval Helper (CLI 환경용)
# ============================================================================


def console_approval_callback(command: str) -> bool:
    """
    터미널에서 사용자 승인 요청

    Usage:
        adapter = LocalCommandAdapter(approval_callback=console_approval_callback)
    """
    print(f"\n⚠️  Dangerous command detected:")
    print(f"   {command}")
    response = input("Execute? [y/N]: ")
    return response.lower() == "y"
