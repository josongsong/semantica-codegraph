"""Formatter Chain - 코드 포맷팅 체인."""

import subprocess
from pathlib import Path

from src.infra.observability import get_logger

logger = get_logger(__name__)


class FormatterChain:
    """코드 포맷터 체인.

    적용된 패치를 자동으로 포맷팅합니다.
    - ruff format (Python)
    - ruff check --fix (linting)
    """

    def __init__(
        self,
        enable_ruff_format: bool = True,
        enable_ruff_check: bool = True,
    ):
        """
        Args:
            enable_ruff_format: ruff format 활성화 여부
            enable_ruff_check: ruff check --fix 활성화 여부
        """
        self.enable_ruff_format = enable_ruff_format
        self.enable_ruff_check = enable_ruff_check

    async def format_file(self, file_path: Path) -> bool:
        """파일 포맷팅.

        Args:
            file_path: 포맷팅할 파일 경로

        Returns:
            성공 여부
        """
        success = True

        # Python 파일만 포맷팅
        if file_path.suffix != ".py":
            logger.debug(f"Skipping non-Python file: {file_path}")
            return True

        # ruff format
        if self.enable_ruff_format:
            success = success and await self._run_ruff_format(file_path)

        # ruff check --fix
        if self.enable_ruff_check:
            success = success and await self._run_ruff_check(file_path)

        return success

    async def _run_ruff_format(self, file_path: Path) -> bool:
        """ruff format 실행.

        Args:
            file_path: 파일 경로

        Returns:
            성공 여부
        """
        try:
            result = subprocess.run(
                ["ruff", "format", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                logger.debug(f"ruff format succeeded: {file_path}")
                return True
            else:
                logger.warning(
                    f"ruff format failed: {file_path}\n{result.stderr}",
                    extra={"file_path": str(file_path), "stderr": result.stderr},
                )
                return False

        except FileNotFoundError:
            logger.warning("ruff not found in PATH. Skipping format.")
            return True  # Not a critical error
        except subprocess.TimeoutExpired:
            logger.error(f"ruff format timeout: {file_path}")
            return False
        except Exception as e:
            logger.error(f"ruff format error: {file_path}, {e}")
            return False

    async def _run_ruff_check(self, file_path: Path) -> bool:
        """ruff check --fix 실행.

        Args:
            file_path: 파일 경로

        Returns:
            성공 여부
        """
        try:
            result = subprocess.run(
                ["ruff", "check", "--fix", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # ruff check는 linting 이슈가 있어도 returncode=1일 수 있음
            # --fix로 자동 수정되면 문제 없음
            if result.returncode in (0, 1):
                logger.debug(f"ruff check succeeded: {file_path}")
                return True
            else:
                logger.warning(
                    f"ruff check failed: {file_path}\n{result.stderr}",
                    extra={"file_path": str(file_path), "stderr": result.stderr},
                )
                return False

        except FileNotFoundError:
            logger.warning("ruff not found in PATH. Skipping check.")
            return True  # Not a critical error
        except subprocess.TimeoutExpired:
            logger.error(f"ruff check timeout: {file_path}")
            return False
        except Exception as e:
            logger.error(f"ruff check error: {file_path}, {e}")
            return False
