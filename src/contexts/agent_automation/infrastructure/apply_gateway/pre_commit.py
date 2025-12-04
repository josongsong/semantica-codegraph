"""Pre-commit Hook Runner."""

import subprocess
from pathlib import Path

from src.infra.observability import get_logger

logger = get_logger(__name__)


class PreCommitRunner:
    """Runs pre-commit hooks on files."""

    def __init__(self, workspace_path: Path):
        """Initialize pre-commit runner.

        Args:
            workspace_path: Workspace directory
        """
        self.workspace_path = Path(workspace_path)

    async def run_on_files(self, file_paths: list[Path]) -> tuple[bool, str]:
        """Run pre-commit on specific files.

        Args:
            file_paths: List of files to check

        Returns:
            Tuple of (success, output)
        """
        if not file_paths:
            return True, ""

        cmd = ["pre-commit", "run", "--files"] + [str(f) for f in file_paths]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            success = result.returncode == 0
            output = result.stdout + result.stderr

            if success:
                logger.info(
                    "pre_commit_passed",
                    file_count=len(file_paths),
                )
            else:
                logger.warning(
                    "pre_commit_failed",
                    file_count=len(file_paths),
                    output=output[:500],
                )

            return success, output

        except subprocess.TimeoutExpired:
            logger.error("pre_commit_timeout", file_count=len(file_paths))
            return False, "Pre-commit timeout (60s)"

        except FileNotFoundError:
            logger.warning("pre_commit_not_installed")
            return True, "pre-commit not installed, skipping"

        except Exception as e:
            logger.error("pre_commit_exception", error=str(e))
            return False, str(e)

    async def run_all_hooks(self) -> tuple[bool, str]:
        """Run all pre-commit hooks.

        Returns:
            Tuple of (success, output)
        """
        cmd = ["pre-commit", "run", "--all-files"]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=120,
            )

            success = result.returncode == 0
            output = result.stdout + result.stderr

            if success:
                logger.info("pre_commit_all_passed")
            else:
                logger.warning("pre_commit_all_failed", output=output[:500])

            return success, output

        except Exception as e:
            logger.error("pre_commit_all_exception", error=str(e))
            return False, str(e)

    async def install_hooks(self) -> bool:
        """Install pre-commit hooks.

        Returns:
            True if successful
        """
        cmd = ["pre-commit", "install"]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                logger.info("pre_commit_installed")
                return True
            else:
                logger.error("pre_commit_install_failed", error=result.stderr)
                return False

        except Exception as e:
            logger.error("pre_commit_install_exception", error=str(e))
            return False
