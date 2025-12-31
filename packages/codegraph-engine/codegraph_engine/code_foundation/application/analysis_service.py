"""
Advanced Analysis Service

Provides on-demand advanced analysis capabilities:
- PDG (Program Dependence Graph)
- Taint Analysis (Security vulnerabilities)
- Program Slicing (Impact analysis)

Separated from indexing pipeline for performance.
"""

import asyncio
from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.ir.models import IRDocument

logger = get_logger(__name__)


class AdvancedAnalysisService:
    """
    On-demand advanced analysis service.

    Usage:
        service = AdvancedAnalysisService()
        results = await service.analyze(ir_docs, enable_taint=True)
    """

    def __init__(
        self,
        enable_pdg: bool = True,
        enable_taint: bool = True,
        enable_slicing: bool = True,
        taint_mode: str = "basic",
    ):
        """
        Initialize analysis service.

        Args:
            enable_pdg: Enable PDG construction
            enable_taint: Enable taint analysis
            enable_slicing: Enable program slicing
            taint_mode: Taint analysis mode ("basic", "path_sensitive", "field_sensitive")
        """
        self.enable_pdg = enable_pdg
        self.enable_taint = enable_taint
        self.enable_slicing = enable_slicing
        self.taint_mode = taint_mode

        self._analyzer = None
        self._stats: dict[str, Any] = {}

    async def analyze(
        self,
        ir_documents: dict[str, IRDocument] | list[IRDocument],
        project_root: Path | None = None,
    ) -> dict[str, Any]:
        """
        Run advanced analysis on IR documents.

        Args:
            ir_documents: IR documents to analyze (dict or list)
            project_root: Project root path

        Returns:
            Analysis results with stats
        """
        # Convert list to dict if needed
        if isinstance(ir_documents, list):
            ir_docs = {doc.file_path: doc for doc in ir_documents}
        else:
            ir_docs = ir_documents

        logger.info(
            "advanced_analysis_started",
            file_count=len(ir_docs),
            enable_pdg=self.enable_pdg,
            enable_taint=self.enable_taint,
            enable_slicing=self.enable_slicing,
        )

        # Lazy import to avoid circular dependency
        from codegraph_engine.code_foundation.infrastructure.ir.unified_analyzer import UnifiedAnalyzer

        self._analyzer = UnifiedAnalyzer(
            enable_pdg=self.enable_pdg,
            enable_taint=self.enable_taint,
            enable_slicing=self.enable_slicing,
            taint_mode=self.taint_mode,
        )

        # Parallel analysis with asyncio.gather
        async def analyze_single(ir_doc: IRDocument) -> tuple[str, bool]:
            try:
                # UnifiedAnalyzer.analyze is sync, run in executor
                await asyncio.get_event_loop().run_in_executor(None, self._analyzer.analyze, ir_doc, project_root)
                return (ir_doc.file_path, True)
            except Exception as e:
                logger.warning(
                    f"Analysis failed for {ir_doc.file_path}: {e}",
                    exc_info=True,
                )
                return (ir_doc.file_path, False)

        results = await asyncio.gather(*[analyze_single(doc) for doc in ir_docs.values()])

        # Collect results
        success_count = sum(1 for _, success in results if success)
        failed_files = [path for path, success in results if not success]

        # Collect stats
        self._stats = self._analyzer.get_stats() if self._analyzer else {}
        self._stats["total_files"] = len(ir_docs)
        self._stats["success_count"] = success_count
        self._stats["failed_count"] = len(failed_files)
        self._stats["failed_files"] = failed_files

        logger.info(
            "advanced_analysis_completed",
            success_count=success_count,
            failed_count=len(failed_files),
            stats=self._stats,
        )

        return {
            "success": success_count > 0,
            "stats": self._stats,
            "ir_documents": ir_docs,  # Updated with analysis results
        }

    async def analyze_taint_only(
        self,
        ir_documents: dict[str, IRDocument] | list[IRDocument],
        project_root: Path | None = None,
        mode: str = "basic",
    ) -> dict[str, Any]:
        """
        Run taint analysis only (faster).

        Args:
            ir_documents: IR documents to analyze
            project_root: Project root path
            mode: Taint analysis mode

        Returns:
            Taint analysis results
        """
        # Temporarily disable other analyses
        original_pdg = self.enable_pdg
        original_slicing = self.enable_slicing
        original_mode = self.taint_mode

        self.enable_pdg = False
        self.enable_slicing = False
        self.taint_mode = mode

        try:
            return await self.analyze(ir_documents, project_root)
        finally:
            # Restore settings
            self.enable_pdg = original_pdg
            self.enable_slicing = original_slicing
            self.taint_mode = original_mode

    async def analyze_pdg_only(
        self,
        ir_documents: dict[str, IRDocument] | list[IRDocument],
        project_root: Path | None = None,
    ) -> dict[str, Any]:
        """
        Run PDG construction only (for refactoring analysis).

        Args:
            ir_documents: IR documents to analyze
            project_root: Project root path

        Returns:
            PDG analysis results
        """
        # Temporarily disable other analyses
        original_taint = self.enable_taint
        original_slicing = self.enable_slicing

        self.enable_taint = False
        self.enable_slicing = False

        try:
            return await self.analyze(ir_documents, project_root)
        finally:
            # Restore settings
            self.enable_taint = original_taint
            self.enable_slicing = original_slicing

    def get_stats(self) -> dict[str, Any]:
        """Get analysis statistics."""
        return self._stats


# Convenience functions for common use cases


async def analyze_security(
    ir_documents: dict[str, IRDocument] | list[IRDocument],
    project_root: Path | None = None,
    mode: str = "path_sensitive",
) -> dict[str, Any]:
    """
    Run security-focused analysis (Taint only).

    Args:
        ir_documents: IR documents
        project_root: Project root
        mode: Taint analysis mode

    Returns:
        Security analysis results
    """
    service = AdvancedAnalysisService(
        enable_pdg=False,
        enable_taint=True,
        enable_slicing=False,
    )
    return await service.analyze_taint_only(ir_documents, project_root, mode)


async def analyze_refactoring(
    ir_documents: dict[str, IRDocument] | list[IRDocument],
    project_root: Path | None = None,
) -> dict[str, Any]:
    """
    Run refactoring-focused analysis (PDG + Slicing).

    Args:
        ir_documents: IR documents
        project_root: Project root

    Returns:
        Refactoring analysis results
    """
    service = AdvancedAnalysisService(
        enable_pdg=True,
        enable_taint=False,
        enable_slicing=True,
    )
    return await service.analyze(ir_documents, project_root)
