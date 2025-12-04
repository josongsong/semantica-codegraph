"""
Parsing Handler for Indexing Pipeline

Stage 3: Parse source files with Tree-sitter.
Supports parallel and sequential parsing with cooperative cancellation.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.contexts.analysis_indexing.infrastructure.handlers.base import BaseHandler, HandlerContext
from src.contexts.analysis_indexing.infrastructure.models import IndexingResult, IndexingStage
from src.infra.observability import get_logger, record_counter
from src.pipeline.decorators import stage_execution

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.parsing.registry import ParserRegistry

logger = get_logger(__name__)


# Language detection mapping
EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".md": "markdown",
    ".rst": "rst",
    ".txt": "text",
}


def detect_language(file_path: str | Path) -> str:
    """
    Detect programming language from file path.

    Args:
        file_path: Can be str or Path object

    Returns:
        Language name or "unknown" if unrecognized
    """
    if not file_path:
        return "unknown"

    # Convert Path to str if needed
    if hasattr(file_path, "__fspath__"):
        file_path = str(file_path)
    elif not isinstance(file_path, str):
        return "unknown"

    try:
        ext = Path(file_path).suffix.lower()
        return EXT_TO_LANG.get(ext, "unknown")
    except (ValueError, OSError):
        return "unknown"


class ParsingHandler(BaseHandler):
    """
    Stage 3: Parse source files with Tree-sitter.

    Supports:
    - Parallel parsing with ThreadPoolExecutor
    - Sequential parsing (fallback)
    - Cooperative cancellation
    - Progress tracking
    """

    stage = IndexingStage.PARSING

    def __init__(self, parser_registry: ParserRegistry, config: Any):
        """
        Initialize parsing handler.

        Args:
            parser_registry: Registry for language parsers
            config: IndexingConfig with parallel, max_workers, skip_parse_errors
        """
        super().__init__()
        self.parser_registry = parser_registry
        self.config = config

    @stage_execution(IndexingStage.PARSING)
    async def execute(
        self,
        ctx: HandlerContext,
        result: IndexingResult,
        files: list[Path],
    ) -> dict[str, Any]:
        """
        Execute parsing stage.

        Args:
            ctx: Handler context
            result: Indexing result to update
            files: List of file paths to parse

        Returns:
            Dictionary mapping file paths to AST trees
        """
        logger.info("parsing_started", file_count=len(files), parallel=self.config.parallel)
        record_counter("parsing_started_total", value=len(files))

        # Skip already completed files (cooperative cancellation resume)
        if ctx.progress and ctx.progress.completed_files:
            original_count = len(files)
            completed_set = set(ctx.progress.completed_files)
            files = [f for f in files if str(f) not in completed_set]
            logger.info(
                "parsing_skip_completed",
                original_count=original_count,
                skipped=original_count - len(files),
                remaining=len(files),
            )

        if self.config.parallel and len(files) > 1:
            return await self._parse_files_parallel(ctx, result, files)
        else:
            return await self._parse_files_sequential(ctx, result, files)

    async def _parse_files_parallel(
        self,
        ctx: HandlerContext,
        result: IndexingResult,
        files: list[Path],
    ) -> dict[str, Any]:
        """
        Parse files in parallel using thread pool.

        Uses ThreadPoolExecutor with thread-local parsers for thread safety.
        """
        ast_results: dict[str, Any] = {}
        completed = 0
        total = len(files)
        lock = asyncio.Lock()

        # Thread-local storage for parsers
        thread_local = threading.local()

        def get_thread_local_parser(language: str):
            """Get or create a thread-local parser for the given language."""
            if not hasattr(thread_local, "parsers"):
                thread_local.parsers = {}

            if language not in thread_local.parsers:
                from tree_sitter import Parser
                from tree_sitter_language_pack import get_language

                try:
                    lang = get_language(language)
                    thread_local.parsers[language] = Parser(lang)
                except (ValueError, LookupError, OSError) as e:
                    logger.debug("parser_init_failed", language=language, error=str(e))
                    return None

            return thread_local.parsers[language]

        def parse_single_sync(file_path: Path) -> tuple[str, Any, str | None]:
            """
            Synchronous parsing function for thread pool.

            Returns:
                (file_path_str, ast_tree_or_none, error_msg_or_none)
            """
            try:
                language = detect_language(file_path)
                if not language or language == "unknown":
                    return (str(file_path), None, "skipped")

                parser = get_thread_local_parser(language)
                if not parser:
                    return (str(file_path), None, f"No parser for language: {language}")

                with open(file_path, encoding="utf-8") as f:
                    content = f.read()

                tree = parser.parse(content.encode("utf-8"))

                if tree:
                    return (str(file_path), tree, None)
                else:
                    return (str(file_path), None, f"Failed to parse: {file_path}")

            except Exception as e:
                return (str(file_path), None, f"Parse error in {file_path}: {e}")

        executor = ThreadPoolExecutor(max_workers=self.config.max_workers)

        try:

            async def run_in_thread(file_path: Path):
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(executor, parse_single_sync, file_path)

            tasks = [run_in_thread(f) for f in files]

            for coro in asyncio.as_completed(tasks):
                # Check cancellation
                if self._check_cancelled(ctx):
                    logger.info(
                        "parsing_parallel_stopped",
                        completed=completed,
                        total=total,
                    )
                    break

                try:
                    file_path_str, ast_tree, error = await coro

                    async with lock:
                        completed += 1

                        if error == "skipped":
                            result.files_skipped += 1
                        elif error:
                            result.files_failed += 1
                            if not self.config.skip_parse_errors:
                                logger.error(error)
                            else:
                                logger.warning(error)
                            result.add_warning(error)

                            if ctx.progress:
                                ctx.progress.mark_file_failed(file_path_str, error)
                        elif ast_tree:
                            ast_results[file_path_str] = ast_tree
                            result.files_processed += 1

                        # Track progress
                        if ctx.progress:
                            ctx.progress.mark_file_completed(file_path_str)
                            await self._persist_progress(ctx)

                        # Report progress
                        progress_pct = (completed / total) * 100
                        self._report_progress(ctx, progress_pct)

                except Exception as e:
                    if not self.config.skip_parse_errors:
                        raise
                    logger.warning(f"Unexpected error in parallel parsing: {e}")

        finally:
            executor.shutdown(wait=True)

        logger.info(
            f"   Parsed (parallel, workers={self.config.max_workers}): {result.files_processed}, "
            f"Failed: {result.files_failed}, "
            f"Skipped: {result.files_skipped}"
        )

        return ast_results

    async def _parse_files_sequential(
        self,
        ctx: HandlerContext,
        result: IndexingResult,
        files: list[Path],
    ) -> dict[str, Any]:
        """Parse files sequentially (fallback or when parallel=False)."""
        ast_results: dict[str, Any] = {}

        for i, file_path in enumerate(files):
            # Check cancellation
            if self._check_cancelled(ctx):
                logger.info(
                    "parsing_stopped",
                    completed=i,
                    total=len(files),
                )
                break

            # Track current file
            if ctx.progress:
                ctx.progress.processing_file = str(file_path)

            try:
                language = detect_language(file_path)
                if not language or language == "unknown":
                    result.files_skipped += 1
                    continue

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

                if ctx.progress:
                    ctx.progress.mark_file_failed(str(file_path), str(e))

                if not self.config.skip_parse_errors:
                    raise

            # Update progress
            if ctx.progress:
                ctx.progress.mark_file_completed(str(file_path))
                ctx.progress.processing_file = None
                await self._persist_progress(ctx)

            progress_pct = ((i + 1) / len(files)) * 100
            self._report_progress(ctx, progress_pct)

        logger.info(
            f"   Parsed (sequential): {result.files_processed}, "
            f"Failed: {result.files_failed}, "
            f"Skipped: {result.files_skipped}"
        )

        return ast_results

    async def _parse_file(self, parser: Any, file_path: Path) -> Any:
        """Parse a single file."""
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            tree = parser.parse(content.encode("utf-8"))
            return tree
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return None
