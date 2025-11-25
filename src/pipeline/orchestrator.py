"""
Indexing Orchestrator

End-to-end pipeline from source files to indexed chunks.

Architecture:
    Source Files → Parser → IR Generator → Graph Builder → Chunk Builder → Index Service

Pipeline Stages:
    1. File Discovery: Find all relevant source files
    2. Parsing: Parse files to AST (with incremental parsing support)
    3. IR Generation: Generate intermediate representation
    4. Graph Building: Build call graph and relationships
    5. Chunk Creation: Create searchable code chunks
    6. Transformation: Convert chunks to index documents
    7. Indexing: Index into all available indexes
    8. (Optional) RepoMap: Build repository map for navigation
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from src.foundation.chunk import ChunkBuilder, ChunkIdGenerator, ChunkStore
from src.foundation.generators.python_generator import PythonIRGenerator
from src.foundation.graph.builder import GraphBuilder
from src.foundation.graph.models import GraphDocument
from src.foundation.ir.models import IRDocument
from src.foundation.parsing import SourceFile, get_registry
from src.index.common.transformer import IndexDocumentTransformer
from src.index.service import IndexingService

logger = logging.getLogger(__name__)


@dataclass
class IndexingResult:
    """Result of indexing operation."""

    success: bool
    repo_id: str
    snapshot_id: str
    files_processed: int
    chunks_created: int
    chunks_indexed: int
    errors: list[str]
    details: dict


class IndexingOrchestrator:
    """
    Orchestrates end-to-end indexing pipeline.

    Usage:
        orchestrator = IndexingOrchestrator(
            indexing_service=container.indexing_service,
            chunk_store=container.chunk_store,
        )

        # Full indexing
        result = await orchestrator.index_repository_full(
            repo_id="my-repo",
            snapshot_id="abc123",
            repo_path="/path/to/repo",
        )
    """

    def __init__(
        self,
        indexing_service: IndexingService,
        chunk_store: ChunkStore,
        enable_repomap: bool = False,
        repomap_builder=None,
    ):
        """Initialize orchestrator."""
        self.indexing_service = indexing_service
        self.chunk_store = chunk_store
        self.enable_repomap = enable_repomap
        self.repomap_builder = repomap_builder

        # Initialize components
        self.parser_registry = get_registry()
        self.ir_generator = None  # Will be initialized per repo
        self.graph_builder = GraphBuilder()
        self.id_generator = None  # Will be initialized per repo
        self.transformer = IndexDocumentTransformer()

    async def index_repository_full(
        self,
        repo_id: str,
        snapshot_id: str,
        repo_path: str,
    ) -> IndexingResult:
        """
        Perform full repository indexing.

        Args:
            repo_id: Repository identifier
            snapshot_id: Git commit hash or snapshot ID
            repo_path: Local path to repository

        Returns:
            IndexingResult with success status and details
        """
        logger.info(f"Starting full indexing for {repo_id}:{snapshot_id} at {repo_path}")

        errors = []
        files_processed = 0
        chunks_created = 0
        chunks_indexed = 0

        try:
            # Initialize ID generator and IR generator for this repo
            self.id_generator = ChunkIdGenerator(repo_id=repo_id)
            self.ir_generator = PythonIRGenerator(repo_id=repo_id)
            self.ir_generator = PythonIRGenerator(repo_id=repo_id)

            # Stage 1: Discover files
            logger.info("Stage 1: Discovering source files")
            source_files = self._discover_files(repo_path)
            logger.info(f"Found {len(source_files)} source files")

            if not source_files:
                return IndexingResult(
                    success=False,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    files_processed=0,
                    chunks_created=0,
                    chunks_indexed=0,
                    errors=["No source files found in repository"],
                    details={},
                )

            # Stage 2-3: Parse files and generate IR
            logger.info("Stage 2-3: Parsing files and generating IR")
            ir_documents = []
            for file_path in source_files:
                try:
                    ir_doc = self._parse_and_generate_ir(
                        repo_id=repo_id,
                        snapshot_id=snapshot_id,
                        file_path=file_path,
                    )
                    if ir_doc:
                        ir_documents.append(ir_doc)
                        files_processed += 1
                except Exception as e:
                    error_msg = f"Failed to process {file_path}: {e}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)

            logger.info(f"Generated IR for {len(ir_documents)} files")

            if not ir_documents:
                return IndexingResult(
                    success=False,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    files_processed=files_processed,
                    chunks_created=0,
                    chunks_indexed=0,
                    errors=errors + ["No IR documents generated"],
                    details={},
                )

            # Stage 4: Build graph
            logger.info("Stage 4: Building graph")
            graph_doc = self._build_graph(ir_documents, repo_id, snapshot_id)
            logger.info(
                f"Graph built: {len(graph_doc.nodes)} nodes, {len(graph_doc.edges)} edges"
            )

            # Stage 5: Create chunks
            logger.info("Stage 5: Creating chunks")
            all_chunks = []
            for ir_doc in ir_documents:
                try:
                    file_chunks = self._create_chunks_for_file(
                        repo_id, ir_doc, graph_doc, snapshot_id
                    )
                    all_chunks.extend(file_chunks)
                except Exception as e:
                    error_msg = f"Failed to create chunks for {ir_doc.file_path}: {e}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)

            chunks_created = len(all_chunks)
            logger.info(f"Created {chunks_created} chunks")

            # Save chunks to store
            for chunk in all_chunks:
                await self.chunk_store.save_chunk(chunk)

            # Stage 6: Transform to index documents
            logger.info("Stage 6: Transforming chunks to index documents")
            index_docs = self.transformer.transform_chunks(all_chunks)
            logger.info(f"Transformed {len(index_docs)} index documents")

            # Stage 7: Index into all indexes
            logger.info("Stage 7: Indexing into all available indexes")
            await self.indexing_service.index_repo_full(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                chunks=all_chunks,
                source_codes={},  # TODO: Extract source code snippets
                graph_doc=graph_doc,
            )
            chunks_indexed = len(all_chunks)
            logger.info(f"Indexed {chunks_indexed} chunks")

            # Stage 8: Build RepoMap (optional)
            if self.enable_repomap and self.repomap_builder:
                logger.info("Stage 8: Building RepoMap")
                try:
                    repomap_snapshot = self.repomap_builder.build(
                        repo_id=repo_id,
                        snapshot_id=snapshot_id,
                        chunks=all_chunks,
                        graph_doc=graph_doc,
                    )
                    logger.info(f"RepoMap built: {len(repomap_snapshot.nodes)} nodes")
                except Exception as e:
                    error_msg = f"RepoMap build failed: {e}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)

            # Success
            logger.info(f"Indexing complete for {repo_id}:{snapshot_id}")
            return IndexingResult(
                success=True,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                files_processed=files_processed,
                chunks_created=chunks_created,
                chunks_indexed=chunks_indexed,
                errors=errors,
                details={
                    "graph_nodes": len(graph_doc.nodes),
                    "graph_edges": len(graph_doc.edges),
                    "index_documents": len(index_docs),
                },
            )

        except Exception as e:
            error_msg = f"Fatal error during indexing: {e}"
            logger.error(error_msg, exc_info=True)
            return IndexingResult(
                success=False,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                files_processed=files_processed,
                chunks_created=chunks_created,
                chunks_indexed=chunks_indexed,
                errors=errors + [error_msg],
                details={},
            )

    async def index_repository_incremental(
        self,
        repo_id: str,
        snapshot_id: str,
        changed_files: list[str],
        deleted_files: list[str],
        old_snapshot_id: str | None = None,
    ) -> IndexingResult:
        """
        Perform incremental repository indexing.

        Args:
            repo_id: Repository identifier
            snapshot_id: New snapshot ID
            changed_files: List of changed file paths
            deleted_files: List of deleted file paths
            old_snapshot_id: Previous snapshot ID (for incremental parsing)

        Returns:
            IndexingResult with success status and details
        """
        logger.info(
            f"Starting incremental indexing for {repo_id}:{snapshot_id} "
            f"({len(changed_files)} changed, {len(deleted_files)} deleted)"
        )

        errors = []
        files_processed = 0
        chunks_created = 0
        chunks_indexed = 0

        try:
            self.id_generator = ChunkIdGenerator(repo_id=repo_id)
            self.ir_generator = PythonIRGenerator(repo_id=repo_id)

            # Process changed files
            ir_documents = []
            for file_path in changed_files:
                try:
                    ir_doc = self._parse_and_generate_ir(
                        repo_id=repo_id,
                        snapshot_id=snapshot_id,
                        file_path=file_path,
                    )
                    if ir_doc:
                        ir_documents.append(ir_doc)
                        files_processed += 1
                except Exception as e:
                    error_msg = f"Failed to process {file_path}: {e}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)

            # Build graph and chunks from changed files
            if ir_documents:
                graph_doc = self._build_graph(ir_documents, repo_id, snapshot_id)

                all_chunks = []
                for ir_doc in ir_documents:
                    try:
                        file_chunks = self._create_chunks_for_file(
                            repo_id, ir_doc, graph_doc, snapshot_id
                        )
                        all_chunks.extend(file_chunks)
                    except Exception as e:
                        error_msg = f"Failed to create chunks for {ir_doc.file_path}: {e}"
                        logger.error(error_msg, exc_info=True)
                        errors.append(error_msg)

                chunks_created = len(all_chunks)

                # Save chunks
                for chunk in all_chunks:
                    await self.chunk_store.save_chunk(chunk)

                # Upsert into indexes
                await self.indexing_service.index_repo_incremental(
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    upserted_chunks=all_chunks,
                    deleted_chunk_ids=[],  # TODO: Map deleted files to chunk IDs
                    source_codes={},
                )
                chunks_indexed = len(all_chunks)

            # Handle deleted files
            if deleted_files:
                logger.warning(f"Delete handling not fully implemented: {len(deleted_files)} files")

            return IndexingResult(
                success=True,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                files_processed=files_processed,
                chunks_created=chunks_created,
                chunks_indexed=chunks_indexed,
                errors=errors,
                details={
                    "changed_files": len(changed_files),
                    "deleted_files": len(deleted_files),
                },
            )

        except Exception as e:
            error_msg = f"Fatal error during incremental indexing: {e}"
            logger.error(error_msg, exc_info=True)
            return IndexingResult(
                success=False,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                files_processed=files_processed,
                chunks_created=chunks_created,
                chunks_indexed=chunks_indexed,
                errors=errors + [error_msg],
                details={},
            )

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _discover_files(self, repo_path: str) -> list[str]:
        """Discover all Python source files in repository."""
        repo_root = Path(repo_path)

        if not repo_root.exists():
            logger.error(f"Repository path does not exist: {repo_path}")
            return []

        # Find all Python files, excluding common ignore patterns
        ignore_patterns = {
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            "node_modules",
            ".pytest_cache",
            ".tox",
            "build",
            "dist",
        }

        python_files = []
        for py_file in repo_root.rglob("*.py"):
            # Skip if any parent directory matches ignore patterns
            if any(pattern in py_file.parts for pattern in ignore_patterns):
                continue
            python_files.append(str(py_file))

        return sorted(python_files)

    def _parse_and_generate_ir(
        self,
        repo_id: str,
        snapshot_id: str,
        file_path: str,
    ) -> IRDocument | None:
        """Parse a single file and generate IR."""
        try:
            # Read file content
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Create SourceFile
            source = SourceFile(
                file_path=file_path,
                content=content,
                language="python",
                encoding="utf-8",
            )

            # Generate IR
            ir_doc = self.ir_generator.generate(
                source=source,
                snapshot_id=snapshot_id,
            )

            return ir_doc

        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}", exc_info=True)
            return None

    def _build_graph(
        self, ir_documents: list[IRDocument], repo_id: str, snapshot_id: str
    ) -> GraphDocument:
        """Build unified graph from IR documents."""
        # Merge all IR nodes
        all_ir_nodes = []
        for ir_doc in ir_documents:
            all_ir_nodes.extend(ir_doc.nodes)

        # Build graph
        graph_doc = self.graph_builder.build(
            ir_nodes=all_ir_nodes,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
        )

        return graph_doc

    def _create_chunks_for_file(
        self,
        repo_id: str,
        ir_doc: IRDocument,
        graph_doc: GraphDocument,
        snapshot_id: str,
    ) -> list:
        """Create chunks for a single file."""
        # Read file for source text
        try:
            with open(ir_doc.file_path, encoding="utf-8") as f:
                file_text = f.readlines()
        except Exception as e:
            logger.warning(f"Could not read source for {ir_doc.file_path}: {e}")
            file_text = []

        # Build chunks using ChunkBuilder
        chunk_builder = ChunkBuilder(self.id_generator)

        # Simple repo config
        repo_config = {
            "repo_path": repo_id,
            "project_roots": [],
        }

        chunks, _, _ = chunk_builder.build(
            repo_id=repo_id,
            ir_doc=ir_doc,
            graph_doc=graph_doc,
            file_text=file_text,
            repo_config=repo_config,
            snapshot_id=snapshot_id,
        )

        return chunks
