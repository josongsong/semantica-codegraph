"""Stage Orchestrator

Executes pipeline stages sequentially or in parallel.

SOTA Features:
- Skip logic for conditional execution
- Hook invocation for observability
- Metrics tracking per stage
- Error handling (fail-fast or continue)
- Parallel execution with asyncio.gather
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import TYPE_CHECKING

from codegraph_shared.infra.logging import get_logger

if TYPE_CHECKING:
    from .protocol import PipelineHook, PipelineStage, StageContext, StageMetrics

logger = get_logger(__name__)


class StageOrchestrator:
    """Orchestrates execution of pipeline stages.

    Features:
    - Sequential execution with skip logic
    - Parallel execution with context merging
    - Hook invocation (on_stage_start, on_stage_complete, on_stage_error)
    - Per-stage metrics collection
    - Error handling (fail-fast or graceful degradation)

    Example:
        ```python
        stages = [CacheStage(), StructuralIRStage(), CrossFileStage()]
        orchestrator = StageOrchestrator(stages)

        ctx = await orchestrator.execute(initial_ctx)
        ```
    """

    def __init__(
        self,
        stages: list["PipelineStage"],
        hooks: "PipelineHook | None" = None,
    ):
        """Initialize orchestrator.

        Args:
            stages: List of stages to execute
            hooks: Optional hooks for observability
        """
        self.stages = stages
        self.hooks = hooks or self._default_hooks()

    async def execute(self, ctx: "StageContext") -> "StageContext":
        """Execute all stages sequentially.

        Strategy:
        1. For each stage:
           a. Check should_skip()
           b. Invoke on_stage_start hook
           c. Execute stage
           d. Collect metrics
           e. Invoke on_stage_complete hook
        2. Return final context

        Args:
            ctx: Initial context

        Returns:
            Final context after all stages
        """
        current_ctx = ctx

        for i, stage in enumerate(self.stages):
            stage_name = stage.__class__.__name__

            # Check if should skip
            should_skip, skip_reason = stage.should_skip(current_ctx)
            if should_skip:
                logger.debug(f"Skipping {stage_name}: {skip_reason}")
                continue

            # Invoke on_stage_start hook
            for hook in self.hooks.on_stage_start:
                try:
                    hook(stage_name, current_ctx)
                except Exception as e:
                    logger.warning(f"on_stage_start hook failed: {e}")

            # Execute stage
            start_time = time.perf_counter()
            error = None

            try:
                current_ctx = await stage.run(current_ctx)
            except Exception as e:
                error = str(e)
                logger.error(f"Stage {stage_name} failed: {e}", exc_info=True)

                # Invoke on_stage_error hook
                for hook in self.hooks.on_stage_error:
                    try:
                        hook(stage_name, current_ctx, e)
                    except Exception as hook_error:
                        logger.warning(f"on_stage_error hook failed: {hook_error}")

                # Re-raise to fail pipeline
                raise

            duration_ms = (time.perf_counter() - start_time) * 1000

            # Create metric
            from .protocol import StageMetrics

            metric = StageMetrics(
                stage_name=stage_name,
                duration_ms=duration_ms,
                error=error,
            )

            # Add to context
            current_ctx = replace(
                current_ctx,
                stage_metrics=current_ctx.stage_metrics + [metric],
            )

            # Invoke on_stage_complete hook
            for hook in self.hooks.on_stage_complete:
                try:
                    hook(stage_name, current_ctx, duration_ms)
                except Exception as e:
                    logger.warning(f"on_stage_complete hook failed: {e}")

        return current_ctx

    async def execute_parallel(
        self,
        ctx: "StageContext",
        parallel_groups: list[list[int]],
    ) -> "StageContext":
        """Execute stages in parallel groups.

        Args:
            ctx: Initial context
            parallel_groups: Groups of stage indices to run in parallel
                Example: [[0], [1, 2], [3]] means:
                - Stage 0 runs alone
                - Stages 1 and 2 run in parallel
                - Stage 3 runs after 1 and 2 complete

        Returns:
            Final context after all groups
        """
        current_ctx = ctx

        for group_indices in parallel_groups:
            # Get stages for this group
            group_stages = [self.stages[i] for i in group_indices]

            if len(group_stages) == 1:
                # Sequential execution for single-stage group
                current_ctx = await self._execute_single(group_stages[0], current_ctx)
            else:
                # Parallel execution for multi-stage group
                tasks = [self._execute_single(stage, current_ctx) for stage in group_stages]
                group_results = await asyncio.gather(*tasks, return_exceptions=True)

                # Check for errors
                for result in group_results:
                    if isinstance(result, Exception):
                        raise result

                # Merge contexts
                current_ctx = self._merge_contexts(group_results, current_ctx)

        return current_ctx

    async def _execute_single(
        self,
        stage: "PipelineStage",
        ctx: "StageContext",
    ) -> "StageContext":
        """Execute a single stage (helper for parallel execution).

        Args:
            stage: Stage to execute
            ctx: Context

        Returns:
            Updated context
        """
        stage_name = stage.__class__.__name__

        # Check skip
        should_skip, skip_reason = stage.should_skip(ctx)
        if should_skip:
            logger.debug(f"Skipping {stage_name}: {skip_reason}")
            return ctx

        # Execute
        start_time = time.perf_counter()
        error = None

        try:
            result_ctx = await stage.run(ctx)
        except Exception as e:
            error = str(e)
            logger.error(f"Stage {stage_name} failed: {e}", exc_info=True)
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000

        # Add metric
        from .protocol import StageMetrics

        metric = StageMetrics(
            stage_name=stage_name,
            duration_ms=duration_ms,
            error=error,
        )

        result_ctx = replace(
            result_ctx,
            stage_metrics=result_ctx.stage_metrics + [metric],
        )

        return result_ctx

    def _merge_contexts(
        self,
        contexts: list["StageContext"],
        base_ctx: "StageContext",
    ) -> "StageContext":
        """Merge multiple contexts from parallel execution.

        Strategy: Union merge
        - IR documents: Union of all
        - Metrics: Concatenate all
        - Global context: Take first non-None

        Args:
            contexts: List of contexts from parallel stages
            base_ctx: Base context to start from

        Returns:
            Merged context
        """
        # Merge IR documents (union)
        merged_irs = dict(base_ctx.ir_documents)
        for ctx in contexts:
            merged_irs.update(ctx.ir_documents)

        # Merge metrics (concatenate)
        merged_metrics = list(base_ctx.stage_metrics)
        for ctx in contexts:
            merged_metrics.extend(ctx.stage_metrics)

        # Take first non-None global context
        merged_global_ctx = base_ctx.global_ctx
        for ctx in contexts:
            if ctx.global_ctx and not merged_global_ctx:
                merged_global_ctx = ctx.global_ctx

        return replace(
            base_ctx,
            ir_documents=merged_irs,
            stage_metrics=merged_metrics,
            global_ctx=merged_global_ctx,
        )

    def _default_hooks(self) -> "PipelineHook":
        """Create default (empty) hooks."""
        from .protocol import PipelineHook

        return PipelineHook(
            on_stage_start=[],
            on_stage_complete=[],
            on_stage_error=[],
        )
