"""
Chunk Stage - Chunk Generation

Stage 7: Generate code chunks from graph and IR
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from codegraph_engine.analysis_indexing.infrastructure.change_detector import ChangeSet
from codegraph_engine.analysis_indexing.infrastructure.models import IndexingStage
from codegraph_shared.infra.observability import get_logger, record_counter

from .base import BaseStage, StageContext

logger = get_logger(__name__)


class ChunkStage(BaseStage):
    """Chunk Generation Stage"""

    stage_name = IndexingStage.CHUNK_GENERATION

    def __init__(self, components: Any = None):
        super().__init__(components)
        self.chunk_builder = getattr(components, "chunk_builder", None)
        self.chunk_store = getattr(components, "chunk_store", None)
        self.chunk_refresher = getattr(components, "chunk_refresher", None)
        self.config = getattr(components, "config", None)
        self.project_root = getattr(components, "project_root", None)

    async def execute(self, ctx: StageContext) -> None:
        """Execute chunk generation stage."""
        stage_start = datetime.now()

        logger.info("chunk_generation_started")

        if ctx.is_incremental and ctx.change_set:
            chunk_ids = await self._generate_incremental(ctx)
        else:
            chunk_ids = await self._generate_full(ctx)

        ctx.chunk_ids = chunk_ids

        self._record_duration(ctx, stage_start)

    async def _generate_full(self, ctx: StageContext) -> list[str]:
        """Generate chunks for full indexing."""
        chunk_ids = await self._build_chunks(
            ctx.graph_doc,
            ctx.ir_doc,
            ctx.semantic_ir,
            ctx.repo_id,
            ctx.snapshot_id,
        )

        ctx.result.chunks_created = len(chunk_ids)
        logger.info("chunk_generation_completed", count=ctx.result.chunks_created)
        record_counter("chunks_generated_total", value=ctx.result.chunks_created)

        # Enrich with Git history if enabled
        if self.config and self.config.enable_git_history and self.project_root:
            chunks = await self._load_chunks_by_ids(chunk_ids)
            await self._enrich_chunks_with_history(chunks, ctx.repo_id, ctx.result)
            await self._save_chunks(chunks)

        return chunk_ids

    async def _generate_incremental(self, ctx: StageContext) -> list[str]:
        """Generate chunks incrementally using ChunkIncrementalRefresher."""
        change_set: ChangeSet = ctx.change_set

        logger.info(
            "incremental_chunk_generation_started",
            added=len(change_set.added),
            modified=len(change_set.modified),
            deleted=len(change_set.deleted),
        )

        # Initialize refresher if needed
        if not self.chunk_refresher:
            self._init_chunk_refresher(ctx.repo_id)

        old_commit = ctx.result.metadata.get("previous_commit", "HEAD~1")
        new_commit = ctx.result.git_commit_hash or ctx.snapshot_id

        refresh_result = await self.chunk_refresher.refresh_files(
            repo_id=ctx.repo_id,
            old_commit=old_commit,
            new_commit=new_commit,
            added_files=list(change_set.added),
            deleted_files=list(change_set.deleted),
            modified_files=list(change_set.modified),
            repo_config={"root": str(self.project_root)},
        )

        logger.info(
            "incremental_chunk_refresh_completed",
            added=len(refresh_result.added_chunks),
            updated=len(refresh_result.updated_chunks),
            deleted=len(refresh_result.deleted_chunks),
            renamed=len(refresh_result.renamed_chunks),
            drifted=len(refresh_result.drifted_chunks),
        )
        record_counter("chunks_incrementally_added_total", value=len(refresh_result.added_chunks))
        record_counter("chunks_incrementally_updated_total", value=len(refresh_result.updated_chunks))
        record_counter("chunks_incrementally_deleted_total", value=len(refresh_result.deleted_chunks))

        all_affected_chunks = refresh_result.added_chunks + refresh_result.updated_chunks
        all_affected_chunk_ids = [c.chunk_id for c in all_affected_chunks]
        deleted_chunk_ids = [c.chunk_id for c in refresh_result.deleted_chunks]

        ctx.result.chunks_created = len(refresh_result.added_chunks)
        ctx.result.metadata["chunks_updated"] = len(refresh_result.updated_chunks)
        ctx.result.metadata["chunks_deleted"] = len(refresh_result.deleted_chunks)
        ctx.result.metadata["chunks_renamed"] = len(refresh_result.renamed_chunks)
        ctx.result.metadata["chunks_drifted"] = len(refresh_result.drifted_chunks)
        ctx.result.metadata["deleted_chunk_ids"] = deleted_chunk_ids

        if all_affected_chunks:
            await self._save_chunks(all_affected_chunks)

        # Enrich with Git history if enabled
        if self.config and self.config.enable_git_history and self.project_root and all_affected_chunks:
            await self._enrich_chunks_with_history(all_affected_chunks, ctx.repo_id, ctx.result)
            await self._save_chunks(all_affected_chunks)

        return all_affected_chunk_ids

    def _init_chunk_refresher(self, repo_id: str) -> None:
        """Initialize ChunkIncrementalRefresher with required dependencies."""
        from codegraph_engine.code_foundation.infrastructure.chunk.incremental_refresher import (
            ChunkIncrementalRefresher,
        )

        ir_builder = getattr(self.components, "ir_builder", None)
        parser_registry = getattr(self.components, "parser_registry", None)
        graph_builder = getattr(self.components, "graph_builder", None)
        semantic_ir_builder = getattr(self.components, "semantic_ir_builder", None)

        class IRGeneratorAdapter:
            def __init__(self, ir_builder, parser_registry, project_root):
                self.ir_builder = ir_builder
                self.parser_registry = parser_registry
                self.project_root = project_root

            def generate_for_file(self, repo_id: str, file_path: str, commit: str):
                full_path = Path(self.project_root) / file_path
                if not full_path.exists():
                    return None

                try:
                    with open(full_path, encoding="utf-8") as f:
                        content = f.read()

                    ext = full_path.suffix.lower()
                    language = {".py": "python", ".js": "javascript", ".ts": "typescript"}.get(ext)
                    if not language:
                        return None

                    parser = self.parser_registry.get_parser(language)
                    tree = parser.parse(content.encode("utf-8"))

                    from codegraph_engine.code_foundation.infrastructure.ir.models import SourceFile

                    source_file = SourceFile(
                        file_path=str(full_path),
                        content=content,
                        language=language,
                    )
                    return self.ir_builder.generate(source=source_file, snapshot_id=commit, ast=tree)
                except Exception as e:
                    logger.warning(f"IR generation failed for {file_path}: {e}")
                    return None

        class GraphGeneratorAdapter:
            def __init__(self, graph_builder, semantic_ir_builder):
                self.graph_builder = graph_builder
                self.semantic_ir_builder = semantic_ir_builder

            def build_for_file(self, ir_doc, snapshot_id: str):
                if not ir_doc:
                    return None
                try:
                    semantic_snapshot, _ = self.semantic_ir_builder.build_full(ir_doc, source_map={})
                    return self.graph_builder.build_full(ir_doc, semantic_snapshot)
                except Exception as e:
                    logger.warning(f"Graph generation failed: {e}")
                    return None

        ir_gen = IRGeneratorAdapter(ir_builder, parser_registry, self.project_root)
        graph_gen = GraphGeneratorAdapter(graph_builder, semantic_ir_builder)

        self.chunk_refresher = ChunkIncrementalRefresher(
            chunk_builder=self.chunk_builder,
            chunk_store=self.chunk_store,
            ir_generator=ir_gen,
            graph_generator=graph_gen,
            repo_path=str(self.project_root),
            use_partial_updates=getattr(self.config, "enable_partial_chunk_updates", False),
        )

    async def _build_chunks(self, graph_doc, ir_doc, semantic_ir, repo_id: str, snapshot_id: str) -> list[str]:
        """Build chunks with memory-efficient streaming."""
        if ir_doc is None:
            logger.error("_build_chunks called with ir_doc=None")
            return []

        if graph_doc is None:
            logger.error("_build_chunks called with graph_doc=None")
            return []

        if not hasattr(ir_doc, "nodes") or ir_doc.nodes is None:
            logger.error("_build_chunks: ir_doc has no nodes attribute")
            return []

        batch_size = self.config.chunk_batch_size if self.config else 100
        batch_chunks = []
        batch_count = 0
        total_chunks = 0
        all_chunk_ids: list[str] = []

        # Group IR nodes by file
        files_map = {}
        for node in ir_doc.nodes:
            if hasattr(node, "file_path") and node.file_path:
                file_path = node.file_path
                if file_path not in files_map:
                    files_map[file_path] = []
                files_map[file_path].append(node)

        total_files = len(files_map)
        processed_files = 0

        logger.debug(f"Building chunks for {total_files} files (batch_size={batch_size})...")

        for file_path, _nodes in files_map.items():
            try:
                abs_file_path = Path(file_path)
                if not abs_file_path.is_absolute():
                    abs_file_path = self.project_root / file_path

                if not abs_file_path.exists() or "<external>" in str(file_path):
                    continue

                with open(abs_file_path, encoding="utf-8") as f:
                    file_text = [line.rstrip("\n\r") for line in f]

                chunks, chunk_to_ir, chunk_to_graph = self.chunk_builder.build(
                    repo_id=repo_id,
                    ir_doc=ir_doc,
                    graph_doc=graph_doc,
                    file_text=file_text,
                    repo_config={"root": str(Path(file_path).parent.parent)},
                    snapshot_id=snapshot_id,
                )

                all_chunk_ids.extend(c.chunk_id for c in chunks)
                batch_chunks.extend(chunks)
                batch_count += 1
                processed_files += 1

                if batch_count >= batch_size:
                    batch_chunks = self._dedupe_chunks(batch_chunks)
                    await self._save_chunks(batch_chunks)
                    total_chunks += len(batch_chunks)
                    logger.debug(
                        f"Saved batch: {len(batch_chunks)} chunks (progress: {processed_files}/{total_files} files)"
                    )
                    batch_chunks = []
                    batch_count = 0

            except Exception as e:
                logger.warning(f"Failed to build chunks for {file_path}: {e}")
                if self.config and not self.config.continue_on_error:
                    raise

        if batch_chunks:
            batch_chunks = self._dedupe_chunks(batch_chunks)
            await self._save_chunks(batch_chunks)
            total_chunks += len(batch_chunks)
            logger.debug(f"Saved final batch: {len(batch_chunks)} chunks")

        logger.info(f"Built and saved {total_chunks} chunks from {processed_files} files")
        return all_chunk_ids

    def _dedupe_chunks(self, chunks: list) -> list:
        """Remove duplicate chunk_ids, keeping last occurrence."""
        seen_chunks = {}
        for chunk in chunks:
            seen_chunks[chunk.chunk_id] = chunk
        return list(seen_chunks.values())

    async def _save_chunks(self, chunks):
        """Save chunks to store."""
        await self.chunk_store.save_chunks(chunks)

    # NOTE: _load_chunks_by_ids는 BaseStage에서 상속받음

    async def _enrich_chunks_with_history(self, chunks, repo_id: str, result):
        """Enrich chunks with Git history (placeholder)."""
        # Implementation would be extracted from orchestrator
        pass
