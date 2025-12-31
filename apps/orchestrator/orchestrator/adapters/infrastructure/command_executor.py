"""
Command Executor Adapter (subprocess 추상화)
"""

import asyncio
import logging
import time

from codegraph_agent.ports.infrastructure import (
    CommandResult,
    CommandStatus,
    ICommandExecutor,
)

logger = logging.getLogger(__name__)


class AsyncSubprocessAdapter(ICommandExecutor):
    """asyncio.subprocess 기반 Command Executor"""

    async def execute(
        self,
        command: list[str],
        cwd: str | None = None,
        timeout: float = 30.0,
        capture_output: bool = True,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """명령 실행"""

        if not command:
            raise ValueError("command cannot be empty")

        start_time = time.time()

        try:
            # asyncio subprocess 실행
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE if capture_output else None,
                stderr=asyncio.subprocess.PIPE if capture_output else None,
                cwd=cwd,
                env=env,
            )

            # timeout과 함께 실행
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            execution_time = (time.time() - start_time) * 1000

            return CommandResult(
                exit_code=proc.returncode or 0,
                stdout=stdout.decode("utf-8", errors="ignore") if stdout else "",
                stderr=stderr.decode("utf-8", errors="ignore") if stderr else "",
                execution_time_ms=execution_time,
                status=CommandStatus.SUCCESS if proc.returncode == 0 else CommandStatus.FAILED,
            )

        except asyncio.TimeoutError:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Command timeout: {' '.join(command)}")

            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timeout after {timeout}s",
                execution_time_ms=execution_time,
                status=CommandStatus.TIMEOUT,
            )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Command execution error: {e}")

            return CommandResult(
                exit_code=-1, stdout="", stderr=str(e), execution_time_ms=execution_time, status=CommandStatus.FAILED
            )


class SyncSubprocessAdapter(ICommandExecutor):
    """subprocess (동기) 기반 Command Executor"""

    async def execute(
        self,
        command: list[str],
        cwd: str | None = None,
        timeout: float = 30.0,
        capture_output: bool = True,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """명령 실행 (sync subprocess를 async로 래핑)"""

        import subprocess

        if not command:
            raise ValueError("command cannot be empty")

        start_time = time.time()

        try:
            result = subprocess.run(
                command, capture_output=capture_output, timeout=timeout, cwd=cwd, env=env, text=True
            )

            execution_time = (time.time() - start_time) * 1000

            return CommandResult(
                exit_code=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                execution_time_ms=execution_time,
                status=CommandStatus.SUCCESS if result.returncode == 0 else CommandStatus.FAILED,
            )

        except subprocess.TimeoutExpired:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Command timeout: {' '.join(command)}")

            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timeout after {timeout}s",
                execution_time_ms=execution_time,
                status=CommandStatus.TIMEOUT,
            )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Command execution error: {e}")

            return CommandResult(
                exit_code=-1, stdout="", stderr=str(e), execution_time_ms=execution_time, status=CommandStatus.FAILED
            )
