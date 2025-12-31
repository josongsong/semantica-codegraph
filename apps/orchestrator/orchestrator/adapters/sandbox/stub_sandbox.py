"""
Stub Sandbox Executor

LocalSandboxAdapter (subprocess 기반 stub).
Phase 2+에서 E2B로 교체 예정.

CASCADE 통합:
- Process Manager cleanup (실행 전후)
"""

import logging
import subprocess
import sys
import time
from dataclasses import dataclass

from apps.orchestrator.orchestrator.domain.models import ExecutionResult
from codegraph_shared.ports import ISandboxExecutor

logger = logging.getLogger(__name__)


@dataclass
class SandboxInstance:
    """Sandbox 인스턴스"""

    sandbox_id: str
    config: dict
    created_at: float


@dataclass
class SandboxConfig:
    """Sandbox 설정"""

    template: str  # "python", "node", etc.
    timeout: int = 60
    working_dir: str | None = None


class LocalSandboxAdapter(ISandboxExecutor):
    """
    Local Sandbox Adapter (Stub).

    subprocess로 로컬에서 코드 실행.
    Phase 2+에서 E2B로 교체.

    CASCADE 통합:
    - Process Manager cleanup (실행 전후)
    """

    def __init__(self, process_manager=None):
        """
        Args:
            process_manager: IProcessManager (Optional, CASCADE 통합)
        """
        self.sandboxes: dict[str, SandboxInstance] = {}
        self.process_manager = process_manager  # CASCADE Process Manager (Optional)

    async def create_sandbox(self, config: dict | None = None, env_vars: dict[str, str] | None = None) -> str:
        """
        Sandbox 생성 (stub).

        Args:
            config: Sandbox 설정 (optional)
            env_vars: 환경 변수 (optional)

        Returns:
            sandbox_id
        """
        import uuid

        sandbox_id = f"local-{uuid.uuid4().hex[:8]}"

        instance = SandboxInstance(
            sandbox_id=sandbox_id,
            config=config or {},
            created_at=time.time(),
        )

        self.sandboxes[sandbox_id] = instance

        return sandbox_id

    async def execute_code(self, sandbox_id: str, code: str, language: str) -> ExecutionResult:
        """
        코드 실행 (subprocess) with CASCADE Process Manager.

        Flow:
        1. [CASCADE] Process cleanup (실행 전)
        2. 코드 실행
        3. [CASCADE] Process cleanup (실행 후)

        Args:
            sandbox_id: Sandbox ID
            code: 실행할 코드
            language: 언어 ("python", "node", etc.)

        Returns:
            ExecutionResult
        """
        if sandbox_id not in self.sandboxes:
            raise ValueError(f"Sandbox not found: {sandbox_id}")

        # ================================================================
        # CASCADE Phase 1: Pre-execution cleanup
        # ================================================================
        if self.process_manager:
            try:
                logger.debug(f"CASCADE: Cleaning up processes before execution (sandbox={sandbox_id})")
                killed_pids = await self.process_manager.kill_zombies(
                    sandbox_id=sandbox_id,
                    force=False,  # SIGTERM 먼저 시도
                )
                if killed_pids:
                    logger.info(f"CASCADE: Killed {len(killed_pids)} zombie processes before execution")
            except Exception as cleanup_error:
                logger.warning(f"CASCADE: Pre-execution cleanup failed: {cleanup_error}")

        # ================================================================
        # Step 2: 코드 실행 (기존 로직)
        # ================================================================
        start = time.time()

        try:
            if language == "python":
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            else:
                raise ValueError(f"Unsupported language: {language}")

            elapsed = int((time.time() - start) * 1000)

            execution_result = ExecutionResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time_ms=elapsed,
            )

        except subprocess.TimeoutExpired:
            execution_result = ExecutionResult(
                stdout="",
                stderr="Execution timeout",
                exit_code=124,
                execution_time_ms=60000,
            )
        except Exception as e:
            execution_result = ExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
                execution_time_ms=0,
            )

        # ================================================================
        # CASCADE Phase 3: Post-execution cleanup
        # ================================================================
        if self.process_manager:
            try:
                logger.debug(f"CASCADE: Cleaning up processes after execution (sandbox={sandbox_id})")

                # Zombie 프로세스 정리
                killed_pids = await self.process_manager.kill_zombies(sandbox_id=sandbox_id, force=False)
                if killed_pids:
                    logger.info(f"CASCADE: Killed {len(killed_pids)} zombie processes after execution")

                # Port 정리 (8000-9000 범위)
                cleaned_ports = await self.process_manager.cleanup_ports(sandbox_id=sandbox_id, port_range=(8000, 9000))
                if cleaned_ports:
                    logger.info(f"CASCADE: Cleaned up {len(cleaned_ports)} ports after execution")

            except Exception as cleanup_error:
                logger.warning(f"CASCADE: Post-execution cleanup failed: {cleanup_error}")

        return execution_result

    async def inject_secrets(self, sandbox_id: str, secrets: dict[str, str]) -> None:
        """
        Secrets 주입 (stub - 환경변수).

        Args:
            sandbox_id: Sandbox ID
            secrets: Secrets dict
        """
        # Stub: 환경변수로 주입 (실제로는 안전하지 않음)
        import os

        for key, value in secrets.items():
            os.environ[key] = value

    async def destroy_sandbox(self, sandbox_id: str) -> None:
        """
        Sandbox 삭제.

        Args:
            sandbox_id: Sandbox ID
        """
        if sandbox_id in self.sandboxes:
            del self.sandboxes[sandbox_id]
