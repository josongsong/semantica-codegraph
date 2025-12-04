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
from src.contexts.code_foundation.infrastructure.ir.lsp.adapter import MultiLSPManager
from src.contexts.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator
from src.contexts.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex
from src.contexts.code_foundation.infrastructure.ir.type_enricher import SelectiveTypeEnricher
from src.contexts.code_foundation.infrastructure.parsing.parser_registry import ParserRegistry

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.models.document import IRDocument

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

    async def build_full(
        self,
        files: list[Path],
    ) -> tuple[dict[str, "IRDocument"], GlobalContext, RetrievalOptimizedIndex]:
        """
        Build complete SOTA IR.

        Pipeline:
        1. Structural IR (Tree-sitter)
        2. Occurrence Layer
        3. LSP Type Enrichment (selective)
        4. Cross-file Resolution
        5. Retrieval Indexes

        Args:
            files: List of files to index

        Returns:
            (ir_documents, global_context, retrieval_index)
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
        self.logger.info("[3/5] Enriching with LSP types (Public APIs)...")
        await self._enrich_types_parallel(structural_irs)

        # ============================================================
        # Layer 4: Cross-file Resolution
        # ============================================================
        self.logger.info("[4/5] Resolving cross-file references...")
        global_ctx = self.cross_file_resolver.resolve(structural_irs)

        # ============================================================
        # Layer 5: Build Retrieval Indexes
        # ============================================================
        self.logger.info("[5/5] Building retrieval indexes...")
        retrieval_index = RetrievalOptimizedIndex()
        for ir_doc in structural_irs.values():
            retrieval_index.index_ir_document(ir_doc)

        # ============================================================
        # Complete
        # ============================================================
        elapsed = time.perf_counter() - start_time

        self.logger.info(
            f"✅ SOTA IR build complete in {elapsed:.1f}s\n"
            f"   - Files: {len(structural_irs)}\n"
            f"   - Symbols: {global_ctx.total_symbols}\n"
            f"   - Occurrences: {sum(len(ir.occurrences) for ir in structural_irs.values())}\n"
            f"   - Dependencies: {global_ctx.get_stats()['total_dependencies']}"
        )

        record_histogram("ir_sota_build_duration_seconds", elapsed)
        record_histogram("ir_sota_build_files", len(structural_irs))

        return structural_irs, global_ctx, retrieval_index

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
        from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
        from src.contexts.code_foundation.infrastructure.generators.typescript_generator import TypeScriptIRGenerator
        from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile

        ir_docs: dict[str, "IRDocument"] = {}

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

        for file_path, ir_doc in ir_docs.items():
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
        by_language: dict[str, list[tuple[str, "IRDocument"]]] = {}

        for file_path, ir_doc in ir_docs.items():
            # Detect language from file extension
            language = self._detect_language(Path(file_path))
            if language:
                by_language.setdefault(language, []).append((file_path, ir_doc))

        # Enrich per language
        tasks = []
        for language, docs in by_language.items():
            for file_path, ir_doc in docs:
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
        }
        return ext_map.get(file_path.suffix)

    async def build_incremental(
        self,
        changed_files: list[Path],
        existing_irs: dict[str, "IRDocument"],
        global_ctx: GlobalContext,
        retrieval_index: RetrievalOptimizedIndex,
    ) -> tuple[dict[str, "IRDocument"], GlobalContext, RetrievalOptimizedIndex]:
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

        Returns:
            (updated_ir_docs, updated_global_ctx, updated_retrieval_index)
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

        elapsed = (time.perf_counter() - start_time) * 1000  # ms

        self.logger.info(f"✅ Incremental update complete in {elapsed:.0f}ms")

        record_histogram("ir_incremental_update_duration_ms", elapsed)

        return existing_irs, global_ctx, retrieval_index

    async def shutdown(self):
        """Shutdown all resources"""
        await self.lsp.shutdown_all()
        self.logger.info("SOTA IR Builder shutdown complete")
