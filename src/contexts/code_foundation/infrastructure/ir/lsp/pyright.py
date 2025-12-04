"""
Pyright LSP Adapter

Adapts existing PyrightLSPClient to unified LSP interface.

Uses: src/contexts/code_foundation/infrastructure/ir/external_analyzers/pyright_lsp.py
"""

from pathlib import Path

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.ir.external_analyzers.pyright_lsp import PyrightLSPClient
from src.contexts.code_foundation.infrastructure.ir.lsp.adapter import Diagnostic, Location, TypeInfo

logger = get_logger(__name__)


class PyrightAdapter:
    """
    Pyright LSP adapter (Python).

    Wraps existing PyrightLSPClient to match unified LSP interface.
    """

    def __init__(self, project_root: Path):
        """
        Initialize Pyright adapter.

        Args:
            project_root: Project root directory
        """
        self.project_root = project_root
        self.client = PyrightLSPClient(project_root)
        self.logger = logger

    async def hover(
        self,
        file_path: Path,
        line: int,
        col: int,
    ) -> TypeInfo | None:
        """Get type and documentation at position"""
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

            return TypeInfo(
                type_string=type_string,
                documentation=docs,
                is_nullable="None" in type_string or "Optional" in type_string,
                is_union="|" in type_string or "Union" in type_string,
            )

        except Exception as e:
            self.logger.debug(f"Pyright hover failed at {file_path}:{line}:{col}: {e}")
            return None

    async def definition(
        self,
        file_path: Path,
        line: int,
        col: int,
    ) -> Location | None:
        """Get definition location"""
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
            self.logger.debug(f"Pyright definition failed at {file_path}:{line}:{col}: {e}")
            return None

    async def references(
        self,
        file_path: Path,
        line: int,
        col: int,
        include_declaration: bool = True,
    ) -> list[Location]:
        """Find all references"""
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
            self.logger.debug(f"Pyright references failed at {file_path}:{line}:{col}: {e}")
            return []

    async def diagnostics(
        self,
        file_path: Path,
    ) -> list[Diagnostic]:
        """
        Get diagnostics for file.

        Note: Current PyrightLSPClient doesn't expose diagnostics API.
        This is a placeholder for future implementation.
        """
        # TODO: Implement diagnostics collection
        # Pyright publishes diagnostics via publishDiagnostics notification
        # Need to capture and store them in PyrightLSPClient
        return []

    async def shutdown(self) -> None:
        """Shutdown Pyright LSP server"""
        try:
            self.client.shutdown()
        except Exception as e:
            self.logger.warning(f"Pyright shutdown failed: {e}")
