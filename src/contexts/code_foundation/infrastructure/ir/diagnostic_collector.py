"""
Diagnostic Collector

Collects diagnostics from LSP servers and populates DiagnosticIndex.
"""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.ir.models.diagnostic import (
    Diagnostic,
    DiagnosticIndex,
    DiagnosticSeverity,
    create_diagnostic,
)
from src.contexts.code_foundation.infrastructure.ir.models.core import Span

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.lsp.adapter import LSPDiagnostic, MultiLSPManager
    from src.contexts.code_foundation.infrastructure.ir.models import IRDocument

logger = get_logger(__name__)


class DiagnosticCollector:
    """
    Collects diagnostics from LSP servers.

    Queries LSP diagnostics (errors, warnings) for each file and
    populates the DiagnosticIndex.
    """

    def __init__(self, lsp_manager: "MultiLSPManager"):
        self.lsp_manager = lsp_manager
        self.logger = get_logger(__name__)

    async def collect(self, ir_docs: dict[str, "IRDocument"]) -> DiagnosticIndex:
        """
        Collect diagnostics from LSP for all files.

        Args:
            ir_docs: Mapping of file_path → IRDocument

        Returns:
            DiagnosticIndex with all collected diagnostics
        """
        diagnostic_index = DiagnosticIndex()

        self.logger.info(f"Collecting diagnostics for {len(ir_docs)} files...")

        # Group files by language
        files_by_lang: dict[str, list[tuple[str, "IRDocument"]]] = {}
        for file_path, ir_doc in ir_docs.items():
            # Detect language from first node
            if ir_doc.nodes:
                language = ir_doc.nodes[0].language
                files_by_lang.setdefault(language, []).append((file_path, ir_doc))

        # Collect diagnostics per language
        for language, files in files_by_lang.items():
            client = self.lsp_manager.get_client(language)
            if not client:
                self.logger.debug(f"No LSP client for {language}, skipping diagnostics")
                continue

            # Collect diagnostics for each file
            tasks = []
            for file_path, ir_doc in files:
                tasks.append(self._collect_file_diagnostics(client, Path(file_path), ir_doc, diagnostic_index))

            await asyncio.gather(*tasks)

        stats = diagnostic_index.get_stats()
        self.logger.info(
            f"Collected {stats['total']} diagnostics ({stats['errors']} errors, {stats['warnings']} warnings)"
        )

        return diagnostic_index

    async def _collect_file_diagnostics(
        self,
        client: "Any",  # LSPClient protocol
        file_path: Path,
        ir_doc: "IRDocument",
        diagnostic_index: DiagnosticIndex,
    ):
        """Collect diagnostics for a single file"""
        try:
            # Query LSP for diagnostics
            lsp_diagnostics = await client.diagnostics(file_path)

            # Convert LSP diagnostics to our format
            for lsp_diag in lsp_diagnostics:
                diagnostic = self._convert_lsp_diagnostic(lsp_diag, str(file_path))
                diagnostic_index.add(diagnostic)
                ir_doc.diagnostics.append(diagnostic)

        except Exception as e:
            self.logger.debug(f"Failed to collect diagnostics for {file_path}: {e}")

    def _convert_lsp_diagnostic(
        self,
        lsp_diag: "LSPDiagnostic",
        file_path: str,
    ) -> Diagnostic:
        """
        Convert LSP diagnostic to our Diagnostic model.

        Args:
            lsp_diag: LSP diagnostic from server
            file_path: File path

        Returns:
            Diagnostic
        """
        # Map LSP severity to our severity
        severity_map = {
            "error": DiagnosticSeverity.ERROR,
            "warning": DiagnosticSeverity.WARNING,
            "information": DiagnosticSeverity.INFORMATION,
            "info": DiagnosticSeverity.INFORMATION,
            "hint": DiagnosticSeverity.HINT,
        }
        severity = severity_map.get(lsp_diag.severity.lower(), DiagnosticSeverity.INFORMATION)

        return create_diagnostic(
            file_path=file_path,
            span=lsp_diag.span,
            severity=severity,
            message=lsp_diag.message,
            source=lsp_diag.source,
            code=lsp_diag.code,
        )
