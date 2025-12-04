"""
Pipeline Stage Decorators

Provides decorators to eliminate boilerplate code in pipeline stages.

Usage:
    @stage_execution(IndexingStage.PARSING)
    async def _stage_parsing(self, ...):
        # Only write the core logic
        return result
"""

import functools
from collections.abc import Callable
from datetime import datetime

from src.common.observability import get_logger

logger = get_logger(__name__)


def stage_execution(stage):
    """
    Decorator for pipeline stage execution.

    Automatically handles:
    - Progress reporting (start/end)
    - Timing measurement
    - Error logging
    - Duration recording

    Args:
        stage: IndexingStage enum value

    Usage:
        @stage_execution(IndexingStage.PARSING)
        async def _stage_parsing(self, result, ...):
            # Core logic only
            parsed_files = self.parser.parse(...)
            result.files_parsed = len(parsed_files)
            return parsed_files

    The decorator expects:
    - self._report_progress(stage, percent) method
    - result parameter with stage_durations dict
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            # Extract result object (usually first arg after self)
            result = args[0] if args else kwargs.get("result")

            # Report start
            if hasattr(self, "_report_progress"):
                self._report_progress(stage, 0.0)

            # Start timing
            stage_start = datetime.now()

            try:
                # Execute core logic
                return_value = await func(self, *args, **kwargs)

                # Report completion
                if hasattr(self, "_report_progress"):
                    self._report_progress(stage, 100.0)

                return return_value

            except Exception as e:
                logger.error(f"[{stage.value}] Stage failed: {e}", exc_info=True)
                raise

            finally:
                # Record duration
                stage_duration = (datetime.now() - stage_start).total_seconds()
                if result and hasattr(result, "stage_durations"):
                    result.stage_durations[stage.value] = stage_duration

        @functools.wraps(func)
        def sync_wrapper(self, *args, **kwargs):
            # Extract result object
            result = args[0] if args else kwargs.get("result")

            # Report start
            if hasattr(self, "_report_progress"):
                self._report_progress(stage, 0.0)

            # Start timing
            stage_start = datetime.now()

            try:
                # Execute core logic
                return_value = func(self, *args, **kwargs)

                # Report completion
                if hasattr(self, "_report_progress"):
                    self._report_progress(stage, 100.0)

                return return_value

            except Exception as e:
                logger.error(f"[{stage.value}] Stage failed: {e}", exc_info=True)
                raise

            finally:
                # Record duration
                stage_duration = (datetime.now() - stage_start).total_seconds()
                if result and hasattr(result, "stage_durations"):
                    result.stage_durations[stage.value] = stage_duration

        # Return appropriate wrapper based on function type
        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def index_execution(stage, index_name: str):
    """
    Decorator for index operation execution.

    Similar to stage_execution but specialized for indexing operations.
    Adds warning-level error handling (doesn't raise) for optional indexes.

    Args:
        stage: IndexingStage enum value
        index_name: Name of index for logging (e.g., "Lexical", "Vector")

    Usage:
        @index_execution(IndexingStage.INDEX_LEXICAL, "Lexical")
        async def _index_lexical(self, result, docs):
            # Core indexing logic only
            await self.lexical_index.index(docs)
            result.lexical_indexed = len(docs)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            result = args[0] if args else kwargs.get("result")

            # Report start
            if hasattr(self, "_report_progress"):
                self._report_progress(stage, 0.0)

            stage_start = datetime.now()

            try:
                return_value = await func(self, *args, **kwargs)

                # Report completion
                if hasattr(self, "_report_progress"):
                    self._report_progress(stage, 100.0)

                return return_value

            except Exception as e:
                # Indexing failures are warnings (not critical)
                logger.warning(f"[{index_name}] Index operation failed: {e}")
                if result and hasattr(result, "add_warning"):
                    result.add_warning(f"{index_name} indexing failed: {e}")
                # Don't raise - allow pipeline to continue

            finally:
                stage_duration = (datetime.now() - stage_start).total_seconds()
                if result and hasattr(result, "stage_durations"):
                    result.stage_durations[stage.value] = stage_duration

        @functools.wraps(func)
        def sync_wrapper(self, *args, **kwargs):
            result = args[0] if args else kwargs.get("result")

            if hasattr(self, "_report_progress"):
                self._report_progress(stage, 0.0)

            stage_start = datetime.now()

            try:
                return_value = func(self, *args, **kwargs)

                if hasattr(self, "_report_progress"):
                    self._report_progress(stage, 100.0)

                return return_value

            except Exception as e:
                logger.warning(f"[{index_name}] Index operation failed: {e}")
                if result and hasattr(result, "add_warning"):
                    result.add_warning(f"{index_name} indexing failed: {e}")

            finally:
                stage_duration = (datetime.now() - stage_start).total_seconds()
                if result and hasattr(result, "stage_durations"):
                    result.stage_durations[stage.value] = stage_duration

        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
