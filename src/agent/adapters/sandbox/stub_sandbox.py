"""
Stub Sandbox Executor

LocalSandboxAdapter (subprocess 기반 stub).
Phase 2+에서 E2B로 교체 예정.
"""

import subprocess
import sys
import time
from dataclasses import dataclass

from src.agent.domain.models import ExecutionResult
from src.ports import ISandboxExecutor


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
    """

    def __init__(self):
        self.sandboxes: dict[str, SandboxInstance] = {}

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
        코드 실행 (subprocess).

        Args:
            sandbox_id: Sandbox ID
            code: 실행할 코드
            language: 언어 ("python", "node", etc.)

        Returns:
            ExecutionResult
        """
        if sandbox_id not in self.sandboxes:
            raise ValueError(f"Sandbox not found: {sandbox_id}")

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

            return ExecutionResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time_ms=elapsed,
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                stdout="",
                stderr="Execution timeout",
                exit_code=124,
                execution_time_ms=60000,
            )
        except Exception as e:
            return ExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
                execution_time_ms=0,
            )

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
