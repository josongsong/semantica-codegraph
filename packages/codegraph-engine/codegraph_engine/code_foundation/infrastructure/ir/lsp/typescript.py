"""
TypeScript/JavaScript LSP Adapter

Adapts TypeScriptLSPClient to unified LSP interface.

Uses: src/contexts/code_foundation/infrastructure/ir/external_analyzers/typescript_lsp.py

Replaces skeleton implementation with full TypeScript Language Server integration.
"""

from pathlib import Path

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.typescript_lsp import TypeScriptLSPClient
from codegraph_engine.code_foundation.infrastructure.ir.lsp.adapter import Diagnostic, Location, TypeInfo

logger = get_logger(__name__)


class TypeScriptAdapter:
    """
    TypeScript/JavaScript LSP adapter.

    Wraps TypeScriptLSPClient to match unified LSP interface.
    Supports TypeScript (.ts, .tsx) and JavaScript (.js, .jsx) files.
    """

    def __init__(self, project_root: Path):
        """
        Initialize TypeScript adapter.

        Args:
            project_root: Project root directory

        Raises:
            RuntimeError: If typescript-language-server not found
        """
        self.project_root = project_root
        self.client = TypeScriptLSPClient(project_root)
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
            file_path: File path
            line: 0-based line number
            col: 0-based column number

        Returns:
            TypeInfo or None
        """
        try:
            # Call existing client (synchronous)
            hover_result = self.client.hover(file_path, line, col)

            if not hover_result:
                return None

            # Parse hover result
            type_string = hover_result.get("type", "")
            docs = hover_result.get("docs")

            if not type_string:
                return None

            # TypeScript-specific type parsing
            return TypeInfo(
                type_string=type_string,
                documentation=docs,
                is_nullable="null" in type_string or "undefined" in type_string,
                is_union="|" in type_string,
                is_generic="<" in type_string and ">" in type_string,
            )

        except Exception as e:
            self.logger.debug(f"TypeScript hover failed at {file_path}:{line}:{col}: {e}")
            return None

    async def definition(
        self,
        file_path: Path,
        line: int,
        col: int,
    ) -> Location | None:
        """
        Get definition location.

        Args:
            file_path: File path
            line: 0-based line number
            col: 0-based column number

        Returns:
            Location or None
        """
        try:
            # Call existing client
            def_loc = self.client.definition(file_path, line, col)

            if not def_loc:
                return None

            return Location(
                file_path=def_loc.file_path,
                line=def_loc.line,
                column=def_loc.column,
            )

        except Exception as e:
            self.logger.debug(f"TypeScript definition failed at {file_path}:{line}:{col}: {e}")
            return None

    async def references(
        self,
        file_path: Path,
        line: int,
        col: int,
        include_declaration: bool = True,
    ) -> list[Location]:
        """
        Find all references.

        Args:
            file_path: File path
            line: 0-based line number
            col: 0-based column number
            include_declaration: Include declaration in results

        Returns:
            List of locations
        """
        try:
            # Call existing client
            ref_locs = self.client.references(file_path, line, col)

            return [
                Location(
                    file_path=loc.file_path,
                    line=loc.line,
                    column=loc.column,
                )
                for loc in ref_locs
            ]

        except Exception as e:
            self.logger.debug(f"TypeScript references failed at {file_path}:{line}:{col}: {e}")
            return []

    async def diagnostics(
        self,
        file_path: Path,
    ) -> list[Diagnostic]:
        """
        Get diagnostics for file.

        Args:
            file_path: File path

        Returns:
            List of diagnostics
        """
        try:
            # Call existing client
            raw_diagnostics = self.client.diagnostics(file_path)

            # Convert to unified Diagnostic format
            diagnostics = []
            for diag in raw_diagnostics:
                # Parse diagnostic
                message = diag.get("message", "")
                severity = diag.get("severity", 1)  # 1=Error, 2=Warning, 3=Info, 4=Hint

                # Get range
                range_data = diag.get("range", {})
                start = range_data.get("start", {})
                end = range_data.get("end", {})

                # Map severity (LSP → our format)
                severity_map = {
                    1: "error",
                    2: "warning",
                    3: "info",
                    4: "hint",
                }
                severity_str = severity_map.get(severity, "error")

                diagnostics.append(
                    Diagnostic(
                        message=message,
                        severity=severity_str,
                        line=start.get("line", 0),
                        column=start.get("character", 0),
                        end_line=end.get("line", 0),
                        end_column=end.get("character", 0),
                        code=diag.get("code"),
                        source=diag.get("source", "typescript"),
                    )
                )

            return diagnostics

        except Exception as e:
            self.logger.debug(f"TypeScript diagnostics failed for {file_path}: {e}")
            return []

    async def shutdown(self) -> None:
        """Shutdown TypeScript LSP server"""
        try:
            self.client.shutdown()
        except Exception as e:
            self.logger.warning(f"TypeScript shutdown failed: {e}")
