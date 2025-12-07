"""
SOTA IR Builder

Unified pipeline for building SCIP-level, retrieval-optimized IR.

Pipeline:
1. Structural IR (Tree-sitter parsing)
2. Occurrence Layer (SCIP-compatible)
3. LSP Type Enrichment (selective, Public APIs)
4. Cross-file Resolution (global context)
5. Retrieval Indexes (fast lookup)

Performance targets:
- Small repo (<100 files): <10s
- Medium repo (100-1K files): <90s
- Large repo (1K+ files): <10min

Example usage:
    builder = SOTAIRBuilder(project_root)

    # Full build
    ir_docs, global_ctx, retrieval_index = await builder.build_full(
        files=[Path("src/calc.py"), Path("src/main.py")]
    )

    # Incremental update
    ir_docs, global_ctx, retrieval_index = await builder.build_incremental(
        changed_files=[Path("src/calc.py")],
        existing_irs=ir_docs,
        global_ctx=global_ctx,
        retrieval_index=retrieval_index,
    )
"""

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING

from src.common.observability import get_logger, record_histogram
from src.contexts.code_foundation.infrastructure.ir.cross_file_resolver import CrossFileResolver, GlobalContext
from src.contexts.code_foundation.infrastructure.ir.diagnostic_collector import DiagnosticCollector
from src.contexts.code_foundation.infrastructure.ir.lsp.adapter import MultiLSPManager
from src.contexts.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator
from src.contexts.code_foundation.infrastructure.ir.package_analyzer import PackageAnalyzer
from src.contexts.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex
from src.contexts.code_foundation.infrastructure.ir.type_enricher import SelectiveTypeEnricher
from src.contexts.code_foundation.infrastructure.parsing.parser_registry import ParserRegistry

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.models.diagnostic import DiagnosticIndex
    from src.contexts.code_foundation.infrastructure.ir.models.document import IRDocument
    from src.contexts.code_foundation.infrastructure.ir.models.package import PackageIndex

logger = get_logger(__name__)


class SOTAIRBuilder:
    """
    SOTA IR Builder - Complete pipeline.

    Orchestrates all IR layers:
    1. Structural IR (AST-based)
    2. Occurrence IR (SCIP-compatible)
    3. LSP Type Enrichment (selective)
    4. Cross-file Resolution
    5. Retrieval Indexes

    This is the main entry point for building SOTA IR.
    """

    def __init__(
        self,
        project_root: Path,
        parser_registry: ParserRegistry | None = None,
        lsp_manager: MultiLSPManager | None = None,
    ):
        """
        Initialize SOTA IR builder.

        Args:
            project_root: Project root directory
            parser_registry: Parser registry (optional, will create if None)
            lsp_manager: LSP manager (optional, will create if None)
        """
        self.project_root = project_root
        self.logger = logger

        # Core components
        self.parser = parser_registry or ParserRegistry()
        self.lsp = lsp_manager or MultiLSPManager(project_root)

        # IR generators
        self.occurrence_gen = OccurrenceGenerator()
        self.type_enricher = SelectiveTypeEnricher(self.lsp)
        self.cross_file_resolver = CrossFileResolver()

        # SCIP-compatible features
        self.diagnostic_collector = DiagnosticCollector(self.lsp)
        self.package_analyzer = PackageAnalyzer(self.project_root)

    async def build_full(
        self,
        files: list[Path],
        collect_diagnostics: bool = True,
        analyze_packages: bool = True,
    ) -> tuple[
        dict[str, "IRDocument"], GlobalContext, RetrievalOptimizedIndex, "DiagnosticIndex | None", "PackageIndex | None"
    ]:
        """
        Build complete SOTA IR.

        Pipeline:
        1. Structural IR (Tree-sitter)
        2. Occurrence Layer
        3. LSP Type Enrichment (selective)
        4. Cross-file Resolution
        5. Retrieval Indexes
        6. Diagnostics Collection (SCIP-compatible)
        7. Package Analysis (SCIP-compatible)

        Args:
            files: List of files to index
            collect_diagnostics: Whether to collect diagnostics from LSP
            analyze_packages: Whether to analyze package dependencies

        Returns:
            (ir_documents, global_context, retrieval_index, diagnostic_index, package_index)
        """
        start_time = time.perf_counter()

        self.logger.info(f"Building SOTA IR for {len(files)} files")

        # ============================================================
        # Layer 1: Structural IR (parallel)
        # ============================================================
        self.logger.info("[1/5] Building Structural IR...")
        structural_irs = await self._build_structural_ir_parallel(files)

        # ============================================================
        # Layer 2: Occurrence Layer (SCIP-compatible)
        # ============================================================
        self.logger.info("[2/5] Generating Occurrences (SCIP-compatible)...")
        await self._generate_occurrences(structural_irs)

        # ============================================================
        # Layer 3: LSP Type Enrichment (selective, Public APIs)
        # ============================================================
        self.logger.info("[3/8] Enriching with LSP types (Public APIs)...")
        await self._enrich_types_parallel(structural_irs)

        # ============================================================
        # Layer 4: Cross-file Resolution
        # ============================================================
        self.logger.info("[4/8] Resolving cross-file references...")
        global_ctx = self.cross_file_resolver.resolve(structural_irs)

        # ============================================================
        # Layer 5: Advanced Analysis (PDG + Taint + Slicing) ⭐ v2.1
        # ============================================================
        self.logger.info("[5/8] Running advanced analysis (PDG + Taint + Slicing)...")
        try:
            from src.contexts.code_foundation.infrastructure.ir.unified_analyzer import UnifiedAnalyzer

            analyzer = UnifiedAnalyzer(
                enable_pdg=True,
                enable_taint=True,
                enable_slicing=True,
            )

            enhanced_count = 0
            for ir_doc in structural_irs.values():
                try:
                    analyzer.analyze(ir_doc, self.project_root)
                    enhanced_count += 1
                except Exception as e:
                    self.logger.warning(f"   ⚠️ Advanced analysis failed for {ir_doc.repo_id}: {e}")

            self.logger.info(f"   ✅ Advanced analysis complete: {enhanced_count}/{len(structural_irs)} files enhanced")
        except Exception as e:
            self.logger.warning(f"   ⚠️ Advanced analysis skipped: {e}")

        # ============================================================
        # Layer 6: Build Retrieval Indexes (PDG 생성 후)
        # ============================================================
        self.logger.info("[6/8] Building retrieval indexes...")
        retrieval_index = RetrievalOptimizedIndex()
        for ir_doc in structural_irs.values():
            retrieval_index.index_ir_document(ir_doc)

        # ============================================================
        # Layer 7: Collect Diagnostics (SCIP-compatible) ⭐ NEW
        # ============================================================
        diagnostic_index = None
        if collect_diagnostics:
            self.logger.info("[7/8] Collecting diagnostics from LSP...")
            try:
                diagnostic_index = await self.diagnostic_collector.collect(structural_irs)
                self.logger.info(
                    f"   ✅ Collected {diagnostic_index.total_diagnostics} diagnostics "
                    f"({diagnostic_index.error_count} errors, {diagnostic_index.warning_count} warnings)"
                )
            except Exception as e:
                self.logger.warning(f"   ⚠️ Diagnostic collection failed: {e}")

        # ============================================================
        # Layer 8: Analyze Packages (SCIP-compatible) ⭐ NEW
        # ============================================================
        package_index = None
        if analyze_packages:
            self.logger.info("[8/8] Analyzing package dependencies...")
            try:
                package_index = self.package_analyzer.analyze(structural_irs)
                stats = package_index.get_stats()
                self.logger.info(
                    f"   ✅ Found {stats['total_packages']} packages, {stats['total_imports']} import mappings"
                )
            except Exception as e:
                self.logger.warning(f"   ⚠️ Package analysis failed: {e}")

        # ============================================================
        # Complete
        # ============================================================
        elapsed = time.perf_counter() - start_time

        summary_lines = [
            f"✅ SOTA IR build complete in {elapsed:.1f}s",
            f"   - Files: {len(structural_irs)}",
            f"   - Symbols: {global_ctx.total_symbols}",
            f"   - Occurrences: {sum(len(ir.occurrences) for ir in structural_irs.values())}",
            f"   - Dependencies: {global_ctx.get_stats()['total_dependencies']}",
        ]

        if diagnostic_index:
            summary_lines.append(
                f"   - Diagnostics: {diagnostic_index.total_diagnostics} ({diagnostic_index.error_count} errors)"
            )

        if package_index:
            summary_lines.append(f"   - Packages: {package_index.total_packages}")

        self.logger.info("\n".join(summary_lines))

        record_histogram("ir_sota_build_duration_seconds", elapsed)
        record_histogram("ir_sota_build_files", len(structural_irs))

        return structural_irs, global_ctx, retrieval_index, diagnostic_index, package_index

    async def _build_structural_ir_parallel(
        self,
        files: list[Path],
    ) -> dict[str, "IRDocument"]:
        """
        Build structural IR for all files (parallel).

        Uses existing IR generators:
        - PythonIRGenerator for Python
        - TypeScriptIRGenerator for TypeScript/JavaScript
        - etc.

        Args:
            files: Files to parse

        Returns:
            Mapping of file_path → IRDocument
        """
        from src.contexts.code_foundation.infrastructure.generators.java_generator import JavaIRGenerator
        from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
        from src.contexts.code_foundation.infrastructure.generators.typescript_generator import TypeScriptIRGenerator
        from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile

        ir_docs: dict[str, IRDocument] = {}

        # Group files by language for batch processing
        by_language: dict[str, list[Path]] = {}
        for file_path in files:
            language = self._detect_language(file_path)
            if language:
                by_language.setdefault(language, []).append(file_path)

        # Generate IR per language (can be parallelized further)
        for language, lang_files in by_language.items():
            # Create generator
            if language == "python":
                generator = PythonIRGenerator(repo_id=str(self.project_root))
            elif language in ["typescript", "javascript"]:
                generator = TypeScriptIRGenerator(repo_id=str(self.project_root))
            elif language == "java":
                generator = JavaIRGenerator(repo_id=str(self.project_root))
            else:
                self.logger.warning(f"No IR generator for language: {language}")
                continue

            # Generate IR for each file
            for file_path in lang_files:
                try:
                    # Read file
                    content = file_path.read_text(encoding="utf-8")

                    # Create SourceFile
                    source = SourceFile.from_content(
                        file_path=str(file_path),
                        content=content,
                        language=language,
                    )

                    # Parse AST
                    ast = AstTree.parse(source)

                    # Generate IR
                    ir_doc = generator.generate(
                        source=source,
                        snapshot_id="sota",
                        ast=ast,
                    )

                    # Store
                    ir_docs[str(file_path)] = ir_doc

                except Exception as e:
                    self.logger.error(f"Failed to generate IR for {file_path}: {e}")
                    continue

        self.logger.debug(f"Generated structural IR for {len(ir_docs)}/{len(files)} files")

        return ir_docs

    async def _generate_occurrences(
        self,
        ir_docs: dict[str, "IRDocument"],
    ):
        """
        Generate occurrences for all IR documents.

        Args:
            ir_docs: IR documents
        """
        total_occs = 0

        for _file_path, ir_doc in ir_docs.items():
            occurrences, occ_index = self.occurrence_gen.generate(ir_doc)
            ir_doc.occurrences = occurrences
            ir_doc._occurrence_index = occ_index
            total_occs += len(occurrences)

        self.logger.debug(f"Generated {total_occs} occurrences")

    async def _enrich_types_parallel(
        self,
        ir_docs: dict[str, "IRDocument"],
    ):
        """
        Enrich IR documents with LSP types (parallel, per-language).

        Groups files by language and enriches in batches.

        Args:
            ir_docs: IR documents
        """
        # Group by language
        by_language: dict[str, list[tuple[str, IRDocument]]] = {}

        for file_path, ir_doc in ir_docs.items():
            # Detect language from file extension
            language = self._detect_language(Path(file_path))
            if language:
                by_language.setdefault(language, []).append((file_path, ir_doc))

        # Enrich per language
        tasks = []
        for language, docs in by_language.items():
            for _, ir_doc in docs:
                task = self.type_enricher.enrich(ir_doc, language)
                tasks.append(task)

        # Execute in parallel
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _detect_language(self, file_path: Path) -> str | None:
        """Detect language from file extension"""
        ext_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
        }
        return ext_map.get(file_path.suffix)

    async def build_incremental(
        self,
        changed_files: list[Path],
        existing_irs: dict[str, "IRDocument"],
        global_ctx: GlobalContext,
        retrieval_index: RetrievalOptimizedIndex,
        diagnostic_index: "DiagnosticIndex | None" = None,
        package_index: "PackageIndex | None" = None,
    ) -> tuple[
        dict[str, "IRDocument"], GlobalContext, RetrievalOptimizedIndex, "DiagnosticIndex | None", "PackageIndex | None"
    ]:
        """
        Incremental IR update (fast path).

        Strategy:
        1. Rebuild structural IR for changed files only
        2. Regenerate occurrences
        3. Re-enrich types (background, non-blocking)
        4. Update global context (affected symbols only)
        5. Update indexes (incremental)

        Args:
            changed_files: Files that changed
            existing_irs: Existing IR documents
            global_ctx: Existing global context
            retrieval_index: Existing retrieval index
            diagnostic_index: Existing diagnostic index (optional)
            package_index: Existing package index (optional)

        Returns:
            (updated_ir_docs, updated_global_ctx, updated_retrieval_index, diagnostic_index, package_index)
        """
        start_time = time.perf_counter()

        self.logger.info(f"Incremental IR update for {len(changed_files)} changed files")

        # 1. Rebuild structural IR for changed files
        new_irs = await self._build_structural_ir_parallel(changed_files)

        # 2. Regenerate occurrences
        await self._generate_occurrences(new_irs)

        # 3. Re-enrich types (background)
        asyncio.create_task(self._enrich_types_parallel(new_irs))

        # 4. Update existing IRs
        for file_path, new_ir in new_irs.items():
            existing_irs[str(file_path)] = new_ir

        # 5. Re-resolve cross-file (TODO: optimize to only affected symbols)
        global_ctx = self.cross_file_resolver.resolve(existing_irs)

        # 6. Update retrieval index (TODO: incremental update)
        # For now, rebuild index
        retrieval_index = RetrievalOptimizedIndex()
        for ir_doc in existing_irs.values():
            retrieval_index.index_ir_document(ir_doc)

        # 7. Update diagnostics (background, non-blocking)
        if diagnostic_index is not None:
            asyncio.create_task(self._update_diagnostics_incremental(new_irs, diagnostic_index))

        # Note: Package index doesn't need incremental update (file-level only)

        # 8. Advanced analysis (incremental) ⭐ v2.1
        try:
            from src.contexts.code_foundation.infrastructure.ir.unified_analyzer import UnifiedAnalyzer

            analyzer = UnifiedAnalyzer(
                enable_pdg=True,
                enable_taint=True,
                enable_slicing=True,
            )

            # 변경된 파일만 분석
            for ir_doc in new_irs.values():
                try:
                    analyzer.analyze(ir_doc, self.project_root)
                except Exception as e:
                    self.logger.warning(f"Advanced analysis failed for {ir_doc.repo_id}: {e}")

        except Exception as e:
            self.logger.warning(f"Advanced analysis skipped: {e}")

        elapsed = (time.perf_counter() - start_time) * 1000  # ms

        self.logger.info(f"✅ Incremental update complete in {elapsed:.0f}ms")

        record_histogram("ir_incremental_update_duration_ms", elapsed)

        return existing_irs, global_ctx, retrieval_index, diagnostic_index, package_index

    async def _update_diagnostics_incremental(
        self,
        changed_irs: dict[str, "IRDocument"],
        diagnostic_index: "DiagnosticIndex",
    ):
        """Update diagnostics for changed files (background task)"""
        try:
            # Collect diagnostics only for changed files
            new_diags = await self.diagnostic_collector.collect(changed_irs)

            # Update index (remove old, add new)
            for file_path in changed_irs.keys():
                # Remove old diagnostics for this file
                old_diag_ids = diagnostic_index.by_file.get(file_path, [])
                for diag_id in old_diag_ids:
                    if diag_id in diagnostic_index.by_id:
                        del diagnostic_index.by_id[diag_id]
                diagnostic_index.by_file[file_path] = []

            # Add new diagnostics
            for diag in new_diags.by_id.values():
                diagnostic_index.add(diag)

            self.logger.debug(f"Updated diagnostics for {len(changed_irs)} files")
        except Exception as e:
            self.logger.warning(f"Diagnostic update failed: {e}")

    async def shutdown(self):
        """Shutdown all resources"""
        await self.lsp.shutdown_all()
        self.logger.info("SOTA IR Builder shutdown complete")
