"""
Parsing Stage - Tree-sitter AST Parsing

Stage 3: Parse source files into AST using Tree-sitter
"""

import asyncio
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from codegraph_engine.analysis_indexing.infrastructure.models import IndexingStage
from codegraph_shared.infra.observability import get_logger, record_counter

from .base import BaseStage, StageContext

if TYPE_CHECKING:
    from codegraph_engine.analysis_indexing.infrastructure.models.job import JobProgress

logger = get_logger(__name__)


# Language extension mapping
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


def detect_language(file_path) -> str:
    """Detect programming language from file path."""
    if not file_path:
        return "unknown"

    if hasattr(file_path, "__fspath__"):
        file_path = str(file_path)
    elif not isinstance(file_path, str):
        return "unknown"

    try:
        ext = Path(file_path).suffix.lower()
        return EXT_TO_LANG.get(ext, "unknown")
    except (ValueError, OSError):
        return "unknown"


class ParsingStage(BaseStage):
    """AST Parsing Stage using Tree-sitter"""

    stage_name = IndexingStage.PARSING

    def __init__(self, components: Any = None):
        super().__init__(components)
        self.config = getattr(components, "config", None)
        self.parser_registry = getattr(components, "parser_registry", None)

    async def execute(
        self,
        ctx: StageContext,
        progress: "JobProgress | None" = None,
        stop_event: asyncio.Event | None = None,
        progress_persist_callback: Callable[["JobProgress"], Awaitable[None]] | None = None,
    ) -> None:
        """Execute parsing stage."""
        stage_start = datetime.now()
        files = ctx.files

        logger.info("parsing_started", file_count=len(files), parallel=self._is_parallel)
        record_counter("parsing_started_total", value=len(files))

        # Skip already completed files (cooperative cancellation)
        if progress and progress.completed_files:
            original_count = len(files)
            completed_set = set(progress.completed_files)
            files = [f for f in files if str(f) not in completed_set]
            logger.info(
                "parsing_skip_completed",
                original_count=original_count,
                skipped=original_count - len(files),
                remaining=len(files),
            )

        if self._is_parallel and len(files) > 1:
            ctx.ast_results = await self._parse_parallel(ctx, files, progress, stop_event, progress_persist_callback)
        else:
            ctx.ast_results = await self._parse_sequential(ctx, files, progress, stop_event, progress_persist_callback)

        self._record_duration(ctx, stage_start)

    @property
    def _is_parallel(self) -> bool:
        """Check if parallel parsing is enabled."""
        return self.config.parallel if self.config else True

    @property
    def _max_workers(self) -> int:
        """Get max worker count."""
        return self.config.max_workers if self.config else 4

    @property
    def _skip_parse_errors(self) -> bool:
        """Check if parse errors should be skipped."""
        return self.config.skip_parse_errors if self.config else True

    async def _parse_parallel(
        self,
        ctx: StageContext,
        files: list[Path],
        job_progress: "JobProgress | None" = None,
        stop_event: asyncio.Event | None = None,
        progress_persist_callback: Callable[["JobProgress"], Awaitable[None]] | None = None,
    ) -> dict:
        """Parse files in parallel using thread pool."""
        ast_results = {}
        completed = 0
        total = len(files)
        lock = asyncio.Lock()

        # Thread-local storage for parsers
        thread_local = threading.local()

        def get_thread_local_parser(language: str):
            """Get or create thread-local parser for the language."""
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
            """Synchronous parsing function for thread pool."""
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

        executor = ThreadPoolExecutor(max_workers=self._max_workers)

        try:

            async def run_in_thread(file_path: Path):
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(executor, parse_single_sync, file_path)

            tasks = [run_in_thread(f) for f in files]

            for coro in asyncio.as_completed(tasks):
                # Cooperative cancellation check
                if stop_event and stop_event.is_set():
                    logger.info(
                        "parsing_parallel_stopped_by_request",
                        completed=completed,
                        total=total,
                    )
                    break

                try:
                    file_path_str, ast_tree, error = await coro

                    async with lock:
                        completed += 1
                        if error == "skipped":
                            ctx.result.files_skipped += 1
                        elif error:
                            ctx.result.files_failed += 1
                            if not self._skip_parse_errors:
                                logger.error(error)
                            else:
                                logger.warning(error)
                            ctx.result.add_warning(error)
                            if job_progress:
                                job_progress.mark_file_failed(file_path_str, error)
                        elif ast_tree:
                            ast_results[file_path_str] = ast_tree
                            ctx.result.files_processed += 1

                        # Record completion
                        if job_progress:
                            job_progress.mark_file_completed(file_path_str)
                            if progress_persist_callback:
                                await progress_persist_callback(job_progress)

                except Exception as e:
                    if not self._skip_parse_errors:
                        raise
                    logger.warning(f"Unexpected error in parallel parsing: {e}")

        finally:
            executor.shutdown(wait=True)

        logger.info(
            f"   Parsed (parallel, workers={self._max_workers}): {ctx.result.files_processed}, "
            f"Failed: {ctx.result.files_failed}, "
            f"Skipped: {ctx.result.files_skipped}"
        )

        return ast_results

    async def _parse_sequential(
        self,
        ctx: StageContext,
        files: list[Path],
        job_progress: "JobProgress | None" = None,
        stop_event: asyncio.Event | None = None,
        progress_persist_callback: Callable[["JobProgress"], Awaitable[None]] | None = None,
    ) -> dict:
        """Parse files sequentially."""
        ast_results = {}

        for i, file_path in enumerate(files):
            # Cooperative cancellation check
            if stop_event and stop_event.is_set():
                logger.info(
                    "parsing_stopped_by_request",
                    completed=i,
                    total=len(files),
                )
                break

            if job_progress:
                job_progress.processing_file = str(file_path)

            try:
                language = detect_language(file_path)
                if not language or language == "unknown":
                    ctx.result.files_skipped += 1
                    continue

                parser = self.parser_registry.get_parser(language) if self.parser_registry else None
                if not parser:
                    ctx.result.files_skipped += 1
                    continue

                ast_tree = await self._parse_file(parser, file_path)

                if ast_tree:
                    ast_results[str(file_path)] = ast_tree
                    ctx.result.files_processed += 1
                else:
                    ctx.result.files_failed += 1
                    ctx.result.add_warning(f"Failed to parse: {file_path}")

            except Exception as e:
                ctx.result.files_failed += 1
                error_msg = f"Parse error in {file_path}: {e}"
                logger.warning(error_msg)
                ctx.result.add_warning(error_msg)

                if job_progress:
                    job_progress.mark_file_failed(str(file_path), str(e))

                if not self._skip_parse_errors:
                    raise

            # Record completion
            if job_progress:
                job_progress.mark_file_completed(str(file_path))
                job_progress.processing_file = None

                if progress_persist_callback:
                    await progress_persist_callback(job_progress)

        logger.info(
            f"   Parsed (sequential): {ctx.result.files_processed}, "
            f"Failed: {ctx.result.files_failed}, "
            f"Skipped: {ctx.result.files_skipped}"
        )

        return ast_results

    async def _parse_file(self, parser, file_path: Path):
        """Parse a single file."""
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            tree = parser.parse(content.encode("utf-8"))
            return tree
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return None
