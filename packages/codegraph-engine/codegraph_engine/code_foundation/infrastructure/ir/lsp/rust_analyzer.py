"""
Rust Analyzer LSP Adapter

Adapts RustAnalyzerLSPClient to unified LSP interface.
Supports .rs files with full type inference and trait resolution.
"""

from pathlib import Path

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.rust_analyzer import RustAnalyzerLSPClient
from codegraph_engine.code_foundation.infrastructure.ir.lsp.adapter import Diagnostic, Location, TypeInfo

logger = get_logger(__name__)


class RustAnalyzerAdapter:
    """
    Rust Analyzer LSP adapter.

    Wraps RustAnalyzerLSPClient to match unified LSP interface.
    Supports Rust (.rs) files with cargo workspace detection.
    """

    def __init__(self, project_root: Path):
        """
        Initialize Rust Analyzer adapter.

        Args:
            project_root: Project root directory (should contain Cargo.toml)

        Raises:
            RuntimeError: If rust-analyzer not found
        """
        self.project_root = project_root
        self.client = RustAnalyzerLSPClient(project_root)
        self.logger = logger

    async def hover(
        self,
        file_path: Path,
        line: int,
        col: int,
    ) -> TypeInfo | None:
        """
        Get type and documentation at position.

        Args:
            file_path: File path (.rs)
            line: Line number (0-based)
            col: Column number (0-based)

        Returns:
            Type information or None

        Example:
            let x: i32 = 42;
                   ^^^
            Returns: TypeInfo(type="i32", docs="32-bit signed integer")
        """
        try:
            result = await self.client.hover(file_path, line, col)

            if not result or "contents" not in result:
                return None

            contents = result["contents"]

            # Extract type and docs
            type_str = ""
            docs = ""

            if isinstance(contents, str):
                type_str = contents
            elif isinstance(contents, dict):
                if "value" in contents:
                    type_str = contents["value"]
                elif "kind" in contents and contents["kind"] == "markdown":
                    type_str = contents.get("value", "")
            elif isinstance(contents, list):
                for item in contents:
                    if isinstance(item, str):
                        type_str += item + "\n"
                    elif isinstance(item, dict):
                        if item.get("language") == "rust":
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

    async def definition(
        self,
        file_path: Path,
        line: int,
        col: int,
    ) -> list[Location]:
        """
        Get definition location(s).

        Args:
            file_path: File path (.rs)
            line: Line number (0-based)
            col: Column number (0-based)

        Returns:
            List of definition locations (may be empty)

        Example:
            use std::collections::HashMap;
                                 ^^^^^^^
            Returns: Location to HashMap definition in std
        """
        try:
            result = await self.client.definition(file_path, line, col)

            if not result:
                return []

            locations = []
            for loc in result:
                uri = loc.get("uri", "")
                range_data = loc.get("range", {})

                # Parse URI to path
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

    async def references(
        self,
        file_path: Path,
        line: int,
        col: int,
    ) -> list[Location]:
        """
        Get all references to symbol.

        Args:
            file_path: File path (.rs)
            line: Line number (0-based)
            col: Column number (0-based)

        Returns:
            List of reference locations (workspace-wide)

        Example:
            fn compute(x: i32) -> i32 { x * 2 }
               ^^^^^^^
            Returns: All calls to compute() across workspace
        """
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

    async def diagnostics(
        self,
        file_path: Path,
    ) -> list[Diagnostic]:
        """
        Get diagnostics (errors/warnings) for file.

        Args:
            file_path: File path (.rs)

        Returns:
            List of diagnostics from cargo check

        Example:
            let x = "hello" + 5;
                            ^^^
            Returns: Diagnostic(severity=ERROR, message="cannot add...")
        """
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
