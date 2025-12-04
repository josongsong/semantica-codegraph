"""LSP Client for Pyright diagnostics."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.infra.observability import get_logger

logger = get_logger(__name__)


@dataclass
class Diagnostic:
    """LSP diagnostic message."""

    file_path: str
    line: int
    column: int
    severity: str  # error, warning, information, hint
    message: str
    code: str | None = None


class LSPClient:
    """Pyright LSP client for type checking and diagnostics."""

    def __init__(self, workspace_path: Path):
        """Initialize LSP client.

        Args:
            workspace_path: Workspace directory path
        """
        self.workspace_path = Path(workspace_path)

    async def check_file(self, file_path: Path) -> list[Diagnostic]:
        """Run Pyright on a single file.

        Args:
            file_path: File to check

        Returns:
            List of diagnostics
        """
        cmd = [
            "pyright",
            "--outputjson",
            str(file_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Parse JSON output
            if result.stdout:
                data = json.loads(result.stdout)
                return self._parse_diagnostics(data)

            return []

        except json.JSONDecodeError as e:
            logger.error("pyright_json_parse_failed", error=str(e))
            return []

        except subprocess.TimeoutExpired:
            logger.error("pyright_timeout", file_path=str(file_path))
            return []

        except Exception as e:
            logger.error("pyright_check_failed", file_path=str(file_path), error=str(e))
            return []

    async def check_workspace(self) -> list[Diagnostic]:
        """Run Pyright on entire workspace.

        Returns:
            List of all diagnostics
        """
        cmd = ["pyright", "--outputjson"]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.stdout:
                data = json.loads(result.stdout)
                return self._parse_diagnostics(data)

            return []

        except Exception as e:
            logger.error("pyright_workspace_check_failed", error=str(e))
            return []

    def _parse_diagnostics(self, data: dict) -> list[Diagnostic]:
        """Parse Pyright JSON output.

        Args:
            data: Pyright JSON output

        Returns:
            List of Diagnostics
        """
        diagnostics = []

        for file_diag in data.get("generalDiagnostics", []):
            diagnostic = Diagnostic(
                file_path=file_diag.get("file", ""),
                line=file_diag.get("range", {}).get("start", {}).get("line", 0),
                column=file_diag.get("range", {}).get("start", {}).get("character", 0),
                severity=file_diag.get("severity", "error"),
                message=file_diag.get("message", ""),
                code=file_diag.get("rule"),
            )
            diagnostics.append(diagnostic)

        return diagnostics

    def has_errors(self, diagnostics: list[Diagnostic]) -> bool:
        """Check if diagnostics contain errors.

        Args:
            diagnostics: List of diagnostics

        Returns:
            True if any error-level diagnostics
        """
        return any(d.severity == "error" for d in diagnostics)
