"""
Indexing Orchestrator

Orchestrates the complete indexing pipeline from parsing to indexing.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .file_discovery import FileDiscovery
from .git_helper import GitHelper
from .models import IndexingConfig, IndexingResult, IndexingStage, IndexingStatus

logger = logging.getLogger(__name__)


class IndexingOrchestrator:
    """
    Orchestrates the complete indexing pipeline.

    Coordinates all components to transform a repository from source code
    to fully indexed and searchable state.

    Pipeline:
        1. Git operations (clone/fetch/pull)
        2. File discovery (find all source files)
        3. Parsing (Tree-sitter AST generation)
        4. IR building (language-neutral intermediate representation)
        5. Semantic IR building (CFG, DFG, types, signatures)
        6. Graph building (code graph with nodes and edges)
        7. Chunk generation (LLM-friendly chunks)
        8. RepoMap building (tree, PageRank, summaries)
        9. Indexing (lexical, vector, symbol, fuzzy, domain)
    """

    def __init__(
        self,
        # Builders
        parser_registry,
        ir_builder,
        semantic_ir_builder,
        graph_builder,
        chunk_builder,
        # RepoMap components
        repomap_tree_builder,
        repomap_pagerank_engine,
        repomap_summarizer,
        # Stores
        graph_store,
        chunk_store,
        repomap_store,
        # Index services
        lexical_index,
        vector_index,
        symbol_index,
        fuzzy_index,
        domain_index,
        # Configuration
        config: IndexingConfig | None = None,
        # Optional callbacks
        progress_callback: Callable[[IndexingStage, float], None] | None = None,
        # Container (for Pyright integration)
        container=None,
    ):
        """
        Initialize orchestrator with all required components.

        Args:
            parser_registry: Registry for language parsers
            ir_builder: IR builder
            semantic_ir_builder: Semantic IR builder (CFG/DFG/types)
            graph_builder: Graph builder
            chunk_builder: Chunk builder
            repomap_tree_builder: RepoMap tree builder
            repomap_pagerank_engine: PageRank engine
            repomap_summarizer: LLM summarizer
            graph_store: Graph storage
            chunk_store: Chunk storage
            repomap_store: RepoMap storage
            lexical_index: Lexical index service
            vector_index: Vector index service
            symbol_index: Symbol index service
            fuzzy_index: Fuzzy index service
            domain_index: Domain index service
            config: Indexing configuration
            progress_callback: Optional callback for progress updates
            container: Optional DI container for Pyright integration (RFC-023)
        """
        # Builders
        self.parser_registry = parser_registry
        self.ir_builder = ir_builder
        self.semantic_ir_builder = semantic_ir_builder
        self.graph_builder = graph_builder
        self.chunk_builder = chunk_builder

        # RepoMap
        self.repomap_tree_builder = repomap_tree_builder
        self.repomap_pagerank_engine = repomap_pagerank_engine
        self.repomap_summarizer = repomap_summarizer

        # Stores
        self.graph_store = graph_store
        self.chunk_store = chunk_store
        self.repomap_store = repomap_store

        # Indexes
        self.lexical_index = lexical_index
        self.vector_index = vector_index
        self.symbol_index = symbol_index
        self.fuzzy_index = fuzzy_index
        self.domain_index = domain_index

        # Configuration
        self.config = config or IndexingConfig()

        # Progress tracking
        self.progress_callback = progress_callback

        # Container (for Pyright integration)
        self.container = container

        # Runtime state
        self.project_root = None

    async def index_repository(
        self,
        repo_path: str | Path,
        repo_id: str,
        snapshot_id: str = "main",
        incremental: bool = False,
        force: bool = False,
    ) -> IndexingResult:
        """
        Index a complete repository.

        This is the main entry point that orchestrates the entire pipeline.

        Args:
            repo_path: Path to repository
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier (e.g., branch name, commit hash)
            incremental: If True, only process changed files
            force: If True, force full reindex even if already indexed

        Returns:
            IndexingResult with statistics and metrics

        Raises:
            Exception: If indexing fails
        """
        repo_path = Path(repo_path)
        self.project_root = repo_path  # Save for Pyright integration
        start_time = datetime.now()

        # Initialize result
        result = IndexingResult(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            status=IndexingStatus.IN_PROGRESS,
            start_time=start_time,
            incremental=incremental,
        )

        logger.info(
            f"{'🔄 Incremental' if incremental else '🚀 Full'} indexing started: "
            f"{repo_id} @ {snapshot_id}"
        )

        try:
            # === Stage 1: Git Operations ===
            await self._stage_git_operations(repo_path, result)

            # === Stage 2: File Discovery ===
            files = await self._stage_file_discovery(
                repo_path, result, incremental=incremental
            )

            if not files:
                logger.warning("No files to process")
                result.mark_completed()
                return result

            # === Stage 3: Parsing ===
            ast_results = await self._stage_parsing(files, result)

            # === Stage 4: IR Building ===
            ir_doc = await self._stage_ir_building(ast_results, repo_id, snapshot_id, result)

            # === Stage 5: Semantic IR Building ===
            semantic_ir = await self._stage_semantic_ir_building(ir_doc, result)

            # === Stage 6: Graph Building ===
            graph_doc = await self._stage_graph_building(
                semantic_ir, ir_doc, repo_id, snapshot_id, result
            )

            # === Stage 7: Chunk Generation ===
            chunks = await self._stage_chunk_generation(
                graph_doc, ir_doc, semantic_ir, repo_id, snapshot_id, result
            )

            # === Stage 8: RepoMap Building ===
            if self.config.repomap_enabled:
                repomap = await self._stage_repomap_building(
                    chunks, graph_doc, repo_id, snapshot_id, result
                )
            else:
                repomap = None

            # === Stage 9: Indexing ===
            await self._stage_indexing(
                repo_id, snapshot_id, chunks, graph_doc, ir_doc, repomap, result
            )

            # === Stage 10: Finalization ===
            await self._stage_finalization(result)

            result.mark_completed()
            logger.info(
                f"✅ Indexing completed: {result.files_processed} files, "
                f"{result.chunks_created} chunks, "
                f"{result.total_duration_seconds:.1f}s"
            )

            return result

        except Exception as e:
            logger.error(f"❌ Indexing failed: {e}", exc_info=True)
            result.mark_failed(str(e))
            raise

    async def _stage_git_operations(
        self, repo_path: Path, result: IndexingResult
    ):
        """Stage 1: Git operations."""
        stage = IndexingStage.GIT_OPERATIONS
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()

        try:
            git = GitHelper(repo_path)

            if git.is_git_repo():
                # Get commit info
                commit_hash = git.get_current_commit_hash()
                result.git_commit_hash = commit_hash

                repo_info = git.get_repo_info()
                result.metadata["git_info"] = repo_info

                logger.info(
                    f"📂 Git repo: {repo_info['current_branch']} @ {commit_hash[:8] if commit_hash else 'unknown'}"
                )
            else:
                logger.warning(f"Not a Git repository: {repo_path}")
                result.add_warning("Not a Git repository")

        except Exception as e:
            logger.warning(f"Git operations failed: {e}")
            result.add_warning(f"Git operations failed: {e}")

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        self._report_progress(stage, 100.0)

    async def _stage_file_discovery(
        self, repo_path: Path, result: IndexingResult, incremental: bool = False
    ) -> list[Path]:
        """Stage 2: File discovery."""
        stage = IndexingStage.FILE_DISCOVERY
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()

        try:
            discovery = FileDiscovery(self.config)

            if incremental:
                # Get changed files from Git
                git = GitHelper(repo_path)
                changed_files = git.get_changed_files()
                logger.info(f"📝 Found {len(changed_files)} changed files (incremental)")

                files = discovery.discover_files(repo_path, changed_files=changed_files)
            else:
                # Discover all files
                files = discovery.discover_files(repo_path)
                logger.info(f"📝 Discovered {len(files)} source files (full scan)")

            result.files_discovered = len(files)

            # Get file stats
            stats = discovery.get_file_stats(files)
            result.metadata["file_stats"] = stats

            logger.info(
                f"   Languages: {', '.join(f'{lang}({count})' for lang, count in stats['by_language'].items())}"
            )
            logger.info(f"   Total size: {stats['total_size_mb']:.1f} MB")

        except Exception as e:
            logger.error(f"File discovery failed: {e}")
            raise

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        self._report_progress(stage, 100.0)

        return files

    async def _stage_parsing(
        self, files: list[Path], result: IndexingResult
    ) -> dict:
        """Stage 3: Parsing with Tree-sitter."""
        stage = IndexingStage.PARSING
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()
        ast_results = {}

        logger.info(f"🌲 Parsing {len(files)} files...")

        for i, file_path in enumerate(files):
            try:
                # Get parser for file
                language = self._detect_language(file_path)
                if not language:
                    result.files_skipped += 1
                    continue

                # Parse file
                # Note: Assuming parser_registry has get_parser method
                # You'll need to adapt based on actual implementation
                parser = self.parser_registry.get_parser(language)
                ast_tree = await self._parse_file(parser, file_path)

                if ast_tree:
                    ast_results[str(file_path)] = ast_tree
                    result.files_processed += 1
                else:
                    result.files_failed += 1
                    result.add_warning(f"Failed to parse: {file_path}")

            except Exception as e:
                result.files_failed += 1
                error_msg = f"Parse error in {file_path}: {e}"
                logger.warning(error_msg)
                result.add_warning(error_msg)

                if not self.config.skip_parse_errors:
                    raise

            # Progress update
            progress = ((i + 1) / len(files)) * 100
            self._report_progress(stage, progress)

        logger.info(
            f"   Parsed: {result.files_processed}, "
            f"Failed: {result.files_failed}, "
            f"Skipped: {result.files_skipped}"
        )

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        return ast_results

    async def _stage_ir_building(
        self, ast_results: dict, repo_id: str, snapshot_id: str, result: IndexingResult
    ):
        """Stage 4: IR building."""
        stage = IndexingStage.IR_BUILDING
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()

        logger.info("🔧 Building Intermediate Representation...")

        try:
            # Build IR from AST results
            # Note: Adapt based on actual ir_builder interface
            ir_doc = await self._build_ir(ast_results, repo_id, snapshot_id)

            if ir_doc:
                result.ir_nodes_created = len(getattr(ir_doc, 'nodes', []))
                logger.info(f"   Created {result.ir_nodes_created} IR nodes")

        except Exception as e:
            logger.error(f"IR building failed: {e}")
            raise

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        self._report_progress(stage, 100.0)

        return ir_doc

    async def _stage_semantic_ir_building(self, ir_doc, result: IndexingResult):
        """Stage 5: Semantic IR building (CFG, DFG, types)."""
        stage = IndexingStage.SEMANTIC_IR_BUILDING
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()

        logger.info("🧠 Building Semantic IR (CFG/DFG/Types/Signatures)...")

        try:
            # Build semantic IR (pass incremental flag for RFC-023 M2)
            semantic_ir = await self._build_semantic_ir(ir_doc, incremental=result.incremental)

            logger.info("   CFG, DFG, Types, Signatures built")

        except Exception as e:
            logger.error(f"Semantic IR building failed: {e}")
            raise

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        self._report_progress(stage, 100.0)

        return semantic_ir

    async def _stage_graph_building(
        self, semantic_ir, ir_doc, repo_id: str, snapshot_id: str, result: IndexingResult
    ):
        """Stage 6: Graph building."""
        stage = IndexingStage.GRAPH_BUILDING
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()

        logger.info("🕸️  Building code graph...")

        try:
            # Build graph
            graph_doc = await self._build_graph(semantic_ir, ir_doc, repo_id, snapshot_id)

            if graph_doc:
                result.graph_nodes_created = len(getattr(graph_doc, 'nodes', []))
                result.graph_edges_created = len(getattr(graph_doc, 'edges', []))

                logger.info(
                    f"   Created {result.graph_nodes_created} nodes, "
                    f"{result.graph_edges_created} edges"
                )

                # Save to graph store
                await self._save_graph(graph_doc)

        except Exception as e:
            logger.error(f"Graph building failed: {e}")
            raise

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        self._report_progress(stage, 100.0)

        return graph_doc

    async def _stage_chunk_generation(
        self,
        graph_doc,
        ir_doc,
        semantic_ir,
        repo_id: str,
        snapshot_id: str,
        result: IndexingResult,
    ):
        """Stage 7: Chunk generation."""
        stage = IndexingStage.CHUNK_GENERATION
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()

        logger.info("📦 Generating chunks...")

        try:
            # Build chunks
            chunks = await self._build_chunks(
                graph_doc, ir_doc, semantic_ir, repo_id, snapshot_id
            )

            result.chunks_created = len(chunks)
            logger.info(f"   Created {result.chunks_created} chunks")

            # Save to chunk store
            await self._save_chunks(chunks)

        except Exception as e:
            logger.error(f"Chunk generation failed: {e}")
            raise

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        self._report_progress(stage, 100.0)

        return chunks

    async def _stage_repomap_building(
        self,
        chunks,
        graph_doc,
        repo_id: str,
        snapshot_id: str,
        result: IndexingResult,
    ):
        """Stage 8: RepoMap building."""
        stage = IndexingStage.REPOMAP_BUILDING
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()

        logger.info("🗺️  Building RepoMap (Tree + PageRank + Summaries)...")

        try:
            # Build tree
            tree = await self._build_repomap_tree(chunks, graph_doc)
            self._report_progress(stage, 33.0)

            # Compute PageRank
            importance_scores = await self._compute_pagerank(graph_doc)
            self._report_progress(stage, 66.0)

            # Generate summaries (if enabled)
            summaries = {}
            if self.config.repomap_use_llm_summaries:
                summaries = await self._generate_summaries(tree, chunks, importance_scores)

            result.repomap_nodes_created = len(getattr(tree, 'nodes', []))
            result.repomap_summaries_generated = len(summaries)

            logger.info(
                f"   RepoMap: {result.repomap_nodes_created} nodes, "
                f"{result.repomap_summaries_generated} summaries"
            )

            # Save RepoMap
            repomap = {
                "tree": tree,
                "importance": importance_scores,
                "summaries": summaries,
            }
            await self._save_repomap(repo_id, snapshot_id, repomap)

        except Exception as e:
            logger.error(f"RepoMap building failed: {e}")
            raise

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        self._report_progress(stage, 100.0)

        return repomap

    async def _stage_indexing(
        self,
        repo_id: str,
        snapshot_id: str,
        chunks,
        graph_doc,
        ir_doc,
        repomap,
        result: IndexingResult,
    ):
        """Stage 9: Indexing to all indexes."""
        logger.info("📊 Indexing to all indexes...")

        # Lexical index
        if self.config.enable_lexical_index:
            await self._index_lexical(repo_id, snapshot_id, chunks, result)

        # Vector index
        if self.config.enable_vector_index:
            await self._index_vector(repo_id, snapshot_id, chunks, result)

        # Symbol index
        if self.config.enable_symbol_index:
            await self._index_symbol(repo_id, snapshot_id, graph_doc, result)

        # Fuzzy index
        if self.config.enable_fuzzy_index:
            await self._index_fuzzy(repo_id, snapshot_id, ir_doc, result)

        # Domain index
        if self.config.enable_domain_index:
            await self._index_domain(repo_id, snapshot_id, chunks, result)

        logger.info(
            f"   Indexed: Lexical({result.lexical_docs_indexed}), "
            f"Vector({result.vector_docs_indexed}), "
            f"Symbol({result.symbol_entries_indexed})"
        )

    async def _index_lexical(
        self, repo_id: str, snapshot_id: str, chunks, result: IndexingResult
    ):
        """Index to lexical index."""
        stage = IndexingStage.LEXICAL_INDEXING
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()

        try:
            # Note: Adapt based on actual lexical_index interface
            await self.lexical_index.reindex_repo(repo_id, snapshot_id)
            result.lexical_docs_indexed = len(chunks)

        except Exception as e:
            logger.warning(f"Lexical indexing failed: {e}")
            result.add_warning(f"Lexical indexing failed: {e}")

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        self._report_progress(stage, 100.0)

    async def _index_vector(
        self, repo_id: str, snapshot_id: str, chunks, result: IndexingResult
    ):
        """Index to vector index."""
        stage = IndexingStage.VECTOR_INDEXING
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()

        try:
            # Convert chunks to index documents
            docs = self._chunks_to_index_docs(chunks)

            # Batch indexing
            batch_size = self.config.vector_batch_size
            for i in range(0, len(docs), batch_size):
                batch = docs[i : i + batch_size]
                await self.vector_index.index(repo_id, snapshot_id, batch)

                progress = ((i + len(batch)) / len(docs)) * 100
                self._report_progress(stage, progress)

            result.vector_docs_indexed = len(docs)

        except Exception as e:
            logger.warning(f"Vector indexing failed: {e}")
            result.add_warning(f"Vector indexing failed: {e}")

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        self._report_progress(stage, 100.0)

    async def _index_symbol(
        self, repo_id: str, snapshot_id: str, graph_doc, result: IndexingResult
    ):
        """Index to symbol index."""
        stage = IndexingStage.SYMBOL_INDEXING
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()

        try:
            # Index symbols from graph
            # Note: Adapt based on actual symbol_index interface
            await self.symbol_index.index_symbols(repo_id, snapshot_id, graph_doc)
            result.symbol_entries_indexed = len(getattr(graph_doc, 'nodes', []))

        except Exception as e:
            logger.warning(f"Symbol indexing failed: {e}")
            result.add_warning(f"Symbol indexing failed: {e}")

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        self._report_progress(stage, 100.0)

    async def _index_fuzzy(
        self, repo_id: str, snapshot_id: str, ir_doc, result: IndexingResult
    ):
        """Index to fuzzy index."""
        stage = IndexingStage.FUZZY_INDEXING
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()

        try:
            # Index identifiers for fuzzy search
            # Note: Adapt based on actual fuzzy_index interface
            await self.fuzzy_index.index_identifiers(repo_id, snapshot_id, ir_doc)
            result.fuzzy_entries_indexed = len(getattr(ir_doc, 'nodes', []))

        except Exception as e:
            logger.warning(f"Fuzzy indexing failed: {e}")
            result.add_warning(f"Fuzzy indexing failed: {e}")

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        self._report_progress(stage, 100.0)

    async def _index_domain(
        self, repo_id: str, snapshot_id: str, chunks, result: IndexingResult
    ):
        """Index to domain metadata index."""
        stage = IndexingStage.DOMAIN_INDEXING
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()

        try:
            # Index domain metadata (README, docs, etc.)
            # Note: Adapt based on actual domain_index interface
            await self.domain_index.index_metadata(repo_id, snapshot_id, chunks)
            result.domain_docs_indexed = len(chunks)

        except Exception as e:
            logger.warning(f"Domain indexing failed: {e}")
            result.add_warning(f"Domain indexing failed: {e}")

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        self._report_progress(stage, 100.0)

    async def _stage_finalization(self, result: IndexingResult):
        """Stage 10: Finalization."""
        stage = IndexingStage.FINALIZATION
        self._report_progress(stage, 0.0)

        # Any cleanup or finalization tasks
        # (flush caches, update metadata, etc.)

        self._report_progress(stage, 100.0)

    # === Helper Methods ===

    def _detect_language(self, file_path: Path) -> str | None:
        """Detect programming language from file extension."""
        discovery = FileDiscovery(self.config)
        return discovery.get_language(file_path)

    async def _parse_file(self, parser, file_path: Path):
        """Parse a single file."""
        # Placeholder - adapt based on actual parser interface
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Assuming parser has a parse method
            return parser.parse(content, str(file_path))
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return None

    async def _build_ir(self, ast_results: dict, repo_id: str, snapshot_id: str):
        """Build IR from AST results."""
        return await self.ir_builder.build(ast_results, repo_id, snapshot_id)

    async def _build_semantic_ir(self, ir_doc, incremental=False):
        """
        Build semantic IR.

        If Pyright is enabled (settings.enable_pyright=True), uses Pyright-enabled
        semantic IR builder with external type analysis. Otherwise, uses default
        internal type inference.

        RFC-023 Integration:
        - M0: Uses PyrightSemanticDaemon for type analysis
        - M1: Persists PyrightSemanticSnapshot to PostgreSQL
        - M2: Supports incremental updates with ChangeDetector

        Args:
            ir_doc: IRDocument with structural information
            incremental: If True, use incremental Pyright snapshot update (M2)
        """
        from src.config import settings

        # Determine which semantic IR builder to use
        if settings.enable_pyright and self.container and self.project_root:
            # Use Pyright-enabled builder (RFC-023)
            logger.info("🔍 Using Pyright for semantic analysis")
            try:
                # Create Pyright-enabled builder for this project
                pyright_builder = self.container.create_semantic_ir_builder_with_pyright(
                    self.project_root
                )

                # Build semantic IR with Pyright
                semantic_snapshot, semantic_index = pyright_builder.build_full(ir_doc)

                logger.info("   ✓ Pyright semantic analysis complete")

                # RFC-023 M1+M2: Persist Pyright snapshot to PostgreSQL
                await self._persist_pyright_snapshot(
                    ir_doc, pyright_builder.external_analyzer, incremental=incremental
                )

            except Exception as e:
                # Fallback to internal types if Pyright fails
                logger.warning(f"Pyright failed ({e}), falling back to internal types")
                semantic_snapshot, semantic_index = self.semantic_ir_builder.build_full(
                    ir_doc
                )
        else:
            # Use default semantic IR builder (internal types only)
            semantic_snapshot, semantic_index = self.semantic_ir_builder.build_full(ir_doc)

        # Return the snapshot along with index for later use
        return {"snapshot": semantic_snapshot, "index": semantic_index}

    async def _persist_pyright_snapshot(
        self, ir_doc, pyright_analyzer, incremental=False
    ):
        """
        Persist Pyright semantic snapshot to PostgreSQL.

        RFC-023 M1: Save PyrightSemanticSnapshot for future incremental updates.
        RFC-023 M2: Support incremental updates using ChangeDetector.

        Args:
            ir_doc: IRDocument with structural information
            pyright_analyzer: PyrightExternalAnalyzer instance
            incremental: If True, use incremental export (M2)

        Note:
            - Full: Analyzes all files and saves snapshot
            - Incremental: Only analyzes changed files and merges with previous snapshot
        """
        try:
            from pathlib import Path

            snapshot_store = self.container.semantic_snapshot_store

            # Step 1: Extract locations from IR document
            file_locations = self._extract_ir_locations(ir_doc)

            if not file_locations:
                logger.warning("   ⚠️  No IR locations found, skipping snapshot persist")
                return

            # RFC-023 M2: Incremental update path
            if incremental and self.project_root:
                logger.info("   🔄 Incremental Pyright snapshot update...")

                # Detect changed files using Git
                from src.foundation.ir.external_analyzers import ChangeDetector

                try:
                    detector = ChangeDetector(self.project_root)
                    changed_files, deleted_files = detector.detect_changed_files()

                    # Filter file_locations to only changed files
                    changed_locations = {
                        path: locs
                        for path, locs in file_locations.items()
                        if path in changed_files
                    }

                    if not changed_locations and not deleted_files:
                        logger.info("   ✓ No changes detected, keeping existing snapshot")
                        return

                    # Load previous snapshot
                    project_id = ir_doc.repo_id
                    previous_snapshot = await snapshot_store.load_latest_snapshot(
                        project_id
                    )

                    if previous_snapshot:
                        # Incremental export (M2)
                        logger.info(
                            f"   Analyzing {len(changed_locations)} changed files "
                            f"(previously {len(previous_snapshot.files)} files)..."
                        )

                        pyright_snapshot = (
                            pyright_analyzer.export_semantic_incremental(
                                changed_files=changed_locations,
                                previous_snapshot=previous_snapshot,
                                deleted_files=deleted_files,
                            )
                        )

                        logger.info(
                            f"   ✓ Incremental update: {len(changed_locations)} changed, "
                            f"{len(deleted_files) if deleted_files else 0} deleted"
                        )
                    else:
                        # No previous snapshot, fall back to full export
                        logger.info("   No previous snapshot found, using full export")
                        pyright_snapshot = pyright_analyzer.export_semantic_for_files(
                            file_locations
                        )

                except Exception as e:
                    # Fall back to full export on error
                    logger.warning(f"   ⚠️  Incremental update failed: {e}")
                    logger.info("   Falling back to full export...")
                    pyright_snapshot = pyright_analyzer.export_semantic_for_files(
                        file_locations
                    )

            # RFC-023 M1: Full export path
            else:
                logger.info("   💾 Full Pyright snapshot export...")
                pyright_snapshot = pyright_analyzer.export_semantic_for_files(
                    file_locations
                )

            # Save to PostgreSQL
            await snapshot_store.save_snapshot(pyright_snapshot)

            logger.info(
                f"   ✓ Saved Pyright snapshot: {pyright_snapshot.snapshot_id} "
                f"({len(pyright_snapshot.files)} files, "
                f"{len(pyright_snapshot.typing_info)} types)"
            )

        except Exception as e:
            logger.warning(f"   ⚠️  Failed to persist Pyright snapshot: {e}")

    def _extract_ir_locations(self, ir_doc) -> dict:
        """
        Extract file locations from IR document for Pyright analysis.

        Args:
            ir_doc: IRDocument with nodes containing spans

        Returns:
            Dict mapping file paths to list of (line, col) tuples

        Example:
            {
                Path("main.py"): [(10, 5), (15, 0), (20, 4)],
                Path("utils.py"): [(5, 0), (10, 4)]
            }
        """
        from pathlib import Path

        file_locations = {}

        for node in ir_doc.nodes:
            if not hasattr(node, "span") or not node.span or not node.span.file_path:
                continue

            file_path = Path(node.span.file_path)
            line = node.span.start_line
            col = node.span.start_column

            if file_path not in file_locations:
                file_locations[file_path] = []

            # Avoid duplicates
            location = (line, col)
            if location not in file_locations[file_path]:
                file_locations[file_path].append(location)

        return file_locations

    async def _build_graph(self, semantic_ir, ir_doc, repo_id: str, snapshot_id: str):
        """Build code graph."""
        # Extract semantic_snapshot from the dict returned by _build_semantic_ir
        semantic_snapshot = semantic_ir["snapshot"]
        # GraphBuilder.build_full(ir_doc, semantic_snapshot) -> GraphDocument
        return self.graph_builder.build_full(ir_doc, semantic_snapshot)

    async def _save_graph(self, graph_doc):
        """Save graph to store."""
        self.graph_store.save_graph(graph_doc)

    async def _build_chunks(
        self, graph_doc, ir_doc, semantic_ir, repo_id: str, snapshot_id: str
    ):
        """Build chunks."""
        # ChunkBuilder.build needs: repo_id, ir_doc, graph_doc, file_text, repo_config, snapshot_id
        # For now, we'll build chunks for each file in ir_doc
        all_chunks = []

        # Group IR nodes by file
        files_map = {}
        for node in ir_doc.nodes:
            if hasattr(node, "span") and node.span and node.span.file_path:
                file_path = node.span.file_path
                if file_path not in files_map:
                    files_map[file_path] = []
                files_map[file_path].append(node)

        # Build chunks for each file
        for file_path, nodes in files_map.items():
            try:
                # Read file content
                with open(file_path, encoding="utf-8") as f:
                    file_text = f.readlines()

                # Build chunks for this file
                chunks, chunk_to_ir, chunk_to_graph = self.chunk_builder.build(
                    repo_id=repo_id,
                    ir_doc=ir_doc,
                    graph_doc=graph_doc,
                    file_text=file_text,
                    repo_config={"root": str(Path(file_path).parent.parent)},
                    snapshot_id=snapshot_id,
                )

                all_chunks.extend(chunks)

            except Exception as e:
                logger.warning(f"Failed to build chunks for {file_path}: {e}")
                continue

        return all_chunks

    async def _save_chunks(self, chunks):
        """Save chunks to store."""
        for chunk in chunks:
            await self.chunk_store.save(chunk)

    async def _build_repomap_tree(self, chunks, graph_doc):
        """Build RepoMap tree."""
        # RepoMapTreeBuilder needs repo_id and snapshot_id in constructor
        repo_id = graph_doc.repo_id
        snapshot_id = graph_doc.snapshot_id

        tree_builder = type(self.repomap_tree_builder)(repo_id, snapshot_id)
        # RepoMapTreeBuilder.build(chunks) -> list[RepoMapNode]
        nodes = tree_builder.build(chunks)

        return {"nodes": nodes, "repo_id": repo_id, "snapshot_id": snapshot_id}

    async def _compute_pagerank(self, graph_doc):
        """Compute PageRank scores."""
        # PageRankEngine.compute_pagerank(graph_doc) -> dict[str, float]
        return self.repomap_pagerank_engine.compute_pagerank(graph_doc)

    async def _generate_summaries(self, tree, chunks, importance_scores):
        """Generate LLM summaries."""
        # LLMSummarizer generates summaries for important nodes
        # For now, return empty dict as summarization is optional and expensive
        # TODO: Implement proper summarization logic
        summaries = {}

        # Only summarize if enabled in config
        if not self.config.repomap_use_llm_summaries:
            return summaries

        # Get top N nodes by importance
        top_nodes = sorted(
            importance_scores.items(), key=lambda x: x[1], reverse=True
        )[:20]

        # Generate summaries for top nodes
        # Note: This is a simplified version - full implementation would need proper async handling
        for node_id, score in top_nodes:
            try:
                # Find corresponding chunk
                chunk = next((c for c in chunks if c.chunk_id == node_id), None)
                if chunk:
                    # Generate summary (this would call LLM)
                    # summaries[node_id] = await self.repomap_summarizer.generate_summary(chunk)
                    pass
            except Exception as e:
                logger.warning(f"Failed to generate summary for {node_id}: {e}")

        return summaries

    async def _save_repomap(self, repo_id: str, snapshot_id: str, repomap):
        """Save RepoMap to store."""
        # Placeholder - adapt based on actual repomap_store interface
        await self.repomap_store.save(repo_id, snapshot_id, repomap)

    def _chunks_to_index_docs(self, chunks) -> list[dict]:
        """Convert chunks to index documents."""
        docs = []
        for chunk in chunks:
            doc = {
                "chunk_id": getattr(chunk, 'chunk_id', ''),
                "content": getattr(chunk, 'content', ''),
                "metadata": getattr(chunk, 'metadata', {}),
            }
            docs.append(doc)
        return docs

    def _report_progress(self, stage: IndexingStage, progress: float):
        """Report progress to callback."""
        if self.progress_callback:
            self.progress_callback(stage, progress)
