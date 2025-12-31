"""
Gopls LSP Adapter

Adapts GoplsLSPClient to unified LSP interface.
Supports .go files with module detection.
"""

from pathlib import Path

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.gopls import GoplsLSPClient
from codegraph_engine.code_foundation.infrastructure.ir.lsp.adapter import Diagnostic, Location, TypeInfo

logger = get_logger(__name__)


class GoplsAdapter:
    """
    Gopls LSP adapter.

    Wraps GoplsLSPClient to match unified LSP interface.
    Supports Go (.go) files with go.mod workspace detection.
    """

    def __init__(self, project_root: Path):
        """
        Initialize Gopls adapter.

        Args:
            project_root: Project root (should contain go.mod)

        Raises:
            RuntimeError: If gopls not found
        """
        self.project_root = project_root
        self.client = GoplsLSPClient(project_root)
        self.logger = logger

    async def hover(self, file_path: Path, line: int, col: int) -> TypeInfo | None:
        """Get type and docs at position"""
        try:
            result = await self.client.hover(file_path, line, col)

            if not result or "contents" not in result:
                return None

            contents = result["contents"]

            type_str = ""
            docs = ""

            if isinstance(contents, str):
                type_str = contents
            elif isinstance(contents, dict):
                if "value" in contents:
                    type_str = contents["value"]
            elif isinstance(contents, list):
                for item in contents:
                    if isinstance(item, str):
                        type_str += item + "\n"
                    elif isinstance(item, dict):
                        if item.get("language") == "go":
                            type_str = item.get("value", "")
                        else:
                            docs += item.get("value", "") + "\n"

            return TypeInfo(
                type=type_str.strip(),
                docs=docs.strip() if docs else None,
            )

        except Exception as e:
            self.logger.warning(f"Hover failed for {file_path}:{line}:{col}: {e}")
            return None

    async def definition(self, file_path: Path, line: int, col: int) -> list[Location]:
        """Get definition location(s)"""
        try:
            result = await self.client.definition(file_path, line, col)

            if not result:
                return []

            locations = []
            for loc in result:
                uri = loc.get("uri", "")
                range_data = loc.get("range", {})

                if uri.startswith("file://"):
                    path = Path(uri[7:])
                else:
                    continue

                locations.append(
                    Location(
                        file_path=path,
                        line=range_data.get("start", {}).get("line", 0),
                        col=range_data.get("start", {}).get("character", 0),
                    )
                )

            return locations

        except Exception as e:
            self.logger.warning(f"Definition failed for {file_path}:{line}:{col}: {e}")
            return []

    async def references(self, file_path: Path, line: int, col: int) -> list[Location]:
        """Get all references"""
        try:
            result = await self.client.references(file_path, line, col)

            if not result:
                return []

            locations = []
            for loc in result:
                uri = loc.get("uri", "")
                range_data = loc.get("range", {})

                if uri.startswith("file://"):
                    path = Path(uri[7:])
                else:
                    continue

                locations.append(
                    Location(
                        file_path=path,
                        line=range_data.get("start", {}).get("line", 0),
                        col=range_data.get("start", {}).get("character", 0),
                    )
                )

            return locations

        except Exception as e:
            self.logger.warning(f"References failed for {file_path}:{line}:{col}: {e}")
            return []

    async def diagnostics(self, file_path: Path) -> list[Diagnostic]:
        """Get diagnostics"""
        try:
            result = await self.client.diagnostics(file_path)

            diagnostics = []
            for diag in result:
                severity_map = {
                    1: "ERROR",
                    2: "WARNING",
                    3: "INFO",
                    4: "HINT",
                }

                severity = severity_map.get(diag.get("severity", 1), "ERROR")
                message = diag.get("message", "")
                range_data = diag.get("range", {})

                diagnostics.append(
                    Diagnostic(
                        severity=severity,
                        message=message,
                        line=range_data.get("start", {}).get("line", 0),
                        col=range_data.get("start", {}).get("character", 0),
                    )
                )

            return diagnostics

        except Exception as e:
            self.logger.warning(f"Diagnostics failed for {file_path}: {e}")
            return []

    async def shutdown(self) -> None:
        """Shutdown LSP client"""
        try:
            await self.client.stop()
        except Exception as e:
            self.logger.warning(f"Shutdown failed: {e}")

    async def __aenter__(self):
        await self.client.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.shutdown()
