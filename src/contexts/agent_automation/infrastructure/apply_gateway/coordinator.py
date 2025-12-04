"""Format/Lint Coordinator - Orchestrates code quality checks."""

from dataclasses import dataclass
from pathlib import Path

from src.infra.observability import get_logger

from .lsp_client import LSPClient
from .pre_commit import PreCommitRunner

logger = get_logger(__name__)


@dataclass
class QualityCheckResult:
    """Result of quality checks."""

    success: bool
    formatted: bool = False
    linted: bool = False
    type_checked: bool = False
    hooks_passed: bool = False
    error_count: int = 0
    warning_count: int = 0
    output: str = ""


class FormatLintCoordinator:
    """Coordinates format, lint, type check, and hook execution.

    Pipeline:
    1. ruff format (auto-fix formatting)
    2. ruff check --fix (auto-fix linting)
    3. pyright (type checking)
    4. pre-commit (final validation)
    """

    def __init__(
        self,
        workspace_path: Path,
        enable_format: bool = True,
        enable_lint: bool = True,
        enable_type_check: bool = False,
        enable_hooks: bool = False,
    ):
        """Initialize coordinator.

        Args:
            workspace_path: Workspace directory
            enable_format: Run ruff format
            enable_lint: Run ruff check
            enable_type_check: Run pyright
            enable_hooks: Run pre-commit hooks
        """
        self.workspace_path = Path(workspace_path)
        self.enable_format = enable_format
        self.enable_lint = enable_lint
        self.enable_type_check = enable_type_check
        self.enable_hooks = enable_hooks

        self.lsp_client = LSPClient(workspace_path)
        self.pre_commit = PreCommitRunner(workspace_path)

    async def run_checks(self, file_paths: list[Path]) -> QualityCheckResult:
        """Run all enabled quality checks.

        Args:
            file_paths: Files to check

        Returns:
            QualityCheckResult
        """
        result = QualityCheckResult(success=True)
        outputs = []

        # Step 1: Format
        if self.enable_format:
            formatted, output = await self._run_format(file_paths)
            result.formatted = formatted
            outputs.append(f"[FORMAT]\n{output}")

            if not formatted:
                result.success = False

        # Step 2: Lint
        if self.enable_lint:
            linted, output = await self._run_lint(file_paths)
            result.linted = linted
            outputs.append(f"[LINT]\n{output}")

            if not linted:
                result.success = False

        # Step 3: Type check
        if self.enable_type_check:
            type_checked, errors, warnings = await self._run_type_check(file_paths)
            result.type_checked = type_checked
            result.error_count = errors
            result.warning_count = warnings
            outputs.append(f"[TYPE CHECK] {errors} errors, {warnings} warnings")

            if not type_checked:
                result.success = False

        # Step 4: Pre-commit hooks
        if self.enable_hooks:
            hooks_passed, output = await self.pre_commit.run_on_files(file_paths)
            result.hooks_passed = hooks_passed
            outputs.append(f"[HOOKS]\n{output}")

            if not hooks_passed:
                result.success = False

        result.output = "\n\n".join(outputs)

        logger.info(
            "quality_checks_completed",
            success=result.success,
            formatted=result.formatted,
            linted=result.linted,
            type_checked=result.type_checked,
            hooks_passed=result.hooks_passed,
        )

        return result

    async def _run_format(self, file_paths: list[Path]) -> tuple[bool, str]:
        """Run ruff format.

        Args:
            file_paths: Files to format

        Returns:
            Tuple of (success, output)
        """
        import subprocess

        cmd = ["ruff", "format"] + [str(f) for f in file_paths]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            return result.returncode == 0, result.stdout + result.stderr

        except Exception as e:
            logger.error("format_failed", error=str(e))
            return False, str(e)

    async def _run_lint(self, file_paths: list[Path]) -> tuple[bool, str]:
        """Run ruff check --fix.

        Args:
            file_paths: Files to lint

        Returns:
            Tuple of (success, output)
        """
        import subprocess

        cmd = ["ruff", "check", "--fix"] + [str(f) for f in file_paths]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            return result.returncode == 0, result.stdout + result.stderr

        except Exception as e:
            logger.error("lint_failed", error=str(e))
            return False, str(e)

    async def _run_type_check(self, file_paths: list[Path]) -> tuple[bool, int, int]:
        """Run pyright type checking.

        Args:
            file_paths: Files to check

        Returns:
            Tuple of (success, error_count, warning_count)
        """
        diagnostics = []

        for file_path in file_paths:
            file_diags = await self.lsp_client.check_file(file_path)
            diagnostics.extend(file_diags)

        errors = sum(1 for d in diagnostics if d.severity == "error")
        warnings = sum(1 for d in diagnostics if d.severity == "warning")

        return errors == 0, errors, warnings
