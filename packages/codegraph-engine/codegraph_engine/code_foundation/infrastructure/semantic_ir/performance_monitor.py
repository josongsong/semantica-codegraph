"""
Performance Monitor for Semantic IR Pipeline

Tracks execution time, memory usage, and cache statistics
across all pipeline stages.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class StageMetrics:
    """Metrics for a single pipeline stage"""

    name: str
    duration_ms: float = 0.0
    items_processed: int = 0
    memory_mb: float = 0.0
    cache_stats: dict[str, Any] = field(default_factory=dict)
    errors: int = 0
    warnings: int = 0
    failed_items: int = 0  # For tracking failed syncs, failed validations, etc.


@dataclass
class PipelineMetrics:
    """Complete pipeline execution metrics"""

    total_duration_ms: float = 0.0
    stages: list[StageMetrics] = field(default_factory=list)
    total_nodes: int = 0
    total_blocks: int = 0
    total_edges: int = 0
    total_expressions: int = 0
    total_variables: int = 0
    peak_memory_mb: float = 0.0
    validation_errors: list[str] = field(default_factory=list)  # Track validation failures

    def get_stage(self, name: str) -> StageMetrics | None:
        """Get metrics for a specific stage"""
        for stage in self.stages:
            if stage.name == name:
                return stage
        return None

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics"""
        total_errors = sum(s.errors for s in self.stages)
        total_warnings = sum(s.warnings for s in self.stages)
        return {
            "total_duration_ms": self.total_duration_ms,
            "total_duration_s": self.total_duration_ms / 1000.0,
            "num_stages": len(self.stages),
            "nodes": self.total_nodes,
            "blocks": self.total_blocks,
            "edges": self.total_edges,
            "expressions": self.total_expressions,
            "variables": self.total_variables,
            "peak_memory_mb": self.peak_memory_mb,
            "validation_errors": len(self.validation_errors),
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "stages": [
                {
                    "name": s.name,
                    "duration_ms": s.duration_ms,
                    "items": s.items_processed,
                    "errors": s.errors,
                    "warnings": s.warnings,
                    "failed_items": s.failed_items,
                }
                for s in self.stages
            ],
        }

    def format_report(self) -> str:
        """Format metrics as human-readable report"""
        total_errors = sum(s.errors for s in self.stages)
        total_warnings = sum(s.warnings for s in self.stages)
        total_failed = sum(s.failed_items for s in self.stages)

        lines = [
            "=" * 70,
            "SEMANTIC IR PIPELINE PERFORMANCE REPORT",
            "=" * 70,
            "",
            f"Total Duration: {self.total_duration_ms:.1f}ms ({self.total_duration_ms / 1000:.2f}s)",
            f"Peak Memory: {self.peak_memory_mb:.1f}MB",
            "",
            "Pipeline Output:",
            f"  - Nodes: {self.total_nodes}",
            f"  - Blocks: {self.total_blocks}",
            f"  - Edges: {self.total_edges}",
            f"  - Expressions: {self.total_expressions}",
            f"  - Variables: {self.total_variables}",
            "",
            "Quality Metrics:",
            f"  - Total Errors: {total_errors}",
            f"  - Total Warnings: {total_warnings}",
            f"  - Failed Items: {total_failed}",
            f"  - Validation Errors: {len(self.validation_errors)}",
            "",
        ]

        # Show validation errors if any
        if self.validation_errors:
            lines.append("Validation Failures:")
            for err in self.validation_errors:
                lines.append(f"  ⚠️  {err}")
            lines.append("")

        lines.extend(
            [
                "Stage Breakdown:",
                "-" * 70,
            ]
        )

        # Stage details
        for stage in self.stages:
            pct = (stage.duration_ms / self.total_duration_ms * 100) if self.total_duration_ms > 0 else 0
            lines.append(f"{stage.name:30s} {stage.duration_ms:8.1f}ms ({pct:5.1f}%)")
            if stage.items_processed > 0:
                per_item = stage.duration_ms / stage.items_processed
                lines.append(f"  {'Items':28s} {stage.items_processed:8d}  ({per_item:.2f}ms/item)")
            if stage.failed_items > 0:
                lines.append(f"  {'Failed Items':28s} {stage.failed_items:8d}")
            if stage.cache_stats:
                # Format cache stats nicely
                cache_str = self._format_cache_stats(stage.cache_stats)
                lines.append(f"  {'Cache':28s} {cache_str}")
            # Handle multi-builder cache stats
            if hasattr(stage, "cache_stats_by_builder") and stage.cache_stats_by_builder:
                for builder_name, builder_stats in stage.cache_stats_by_builder.items():
                    cache_str = self._format_cache_stats(builder_stats)
                    lines.append(f"  {'Cache (' + builder_name + ')':28s} {cache_str}")
            if stage.errors > 0:
                lines.append(f"  {'Errors':28s} {stage.errors:8d}")
            if stage.warnings > 0:
                lines.append(f"  {'Warnings':28s} {stage.warnings:8d}")

        lines.append("-" * 70)
        lines.append("")

        return "\n".join(lines)

    def _format_cache_stats(self, cache_stats: dict[str, Any]) -> str:
        """Format cache statistics in a readable way"""
        if not cache_stats:
            return "N/A"

        # Check if this is LRU cache stats with hit rate
        if "hit_rate" in cache_stats:
            hit_rate = cache_stats.get("hit_rate", 0.0)
            hits = cache_stats.get("hits", 0)
            misses = cache_stats.get("misses", 0)
            evictions = cache_stats.get("evictions", 0)
            size = cache_stats.get("size", 0)
            max_size = cache_stats.get("max_size", 0)

            parts = [f"hit_rate={hit_rate:.1f}%", f"hits={hits}", f"misses={misses}"]
            if evictions > 0:
                parts.append(f"evict={evictions}")
            if max_size > 0:
                parts.append(f"size={size}/{max_size}")

            return ", ".join(parts)

        # Generic key-value formatting
        parts = [f"{k}={v}" for k, v in cache_stats.items()]
        return ", ".join(parts[:5])  # Limit to first 5 items


class PerformanceMonitor:
    """
    Monitors performance of Semantic IR pipeline.

    Usage:
        monitor = PerformanceMonitor()
        monitor.start_pipeline()

        with monitor.stage("Phase 1: Type System"):
            # ... build types ...
            monitor.record_items(len(types))

        metrics = monitor.end_pipeline()
        print(metrics.format_report())
    """

    def __init__(self, enable_memory_tracking: bool = False):
        """
        Initialize performance monitor.

        Args:
            enable_memory_tracking: Enable memory profiling (slower but more detailed)
        """
        self.enable_memory_tracking = enable_memory_tracking
        self._pipeline_start: float = 0.0
        self._stage_start: float = 0.0
        self._current_stage: StageMetrics | None = None
        self._metrics: PipelineMetrics = PipelineMetrics()

    def start_pipeline(self):
        """Start monitoring pipeline execution"""
        self._pipeline_start = time.perf_counter()
        self._metrics = PipelineMetrics()

        if self.enable_memory_tracking:
            try:
                import os

                import psutil

                process = psutil.Process(os.getpid())
                self._initial_memory_mb = process.memory_info().rss / 1024 / 1024
            except ImportError:
                self.enable_memory_tracking = False

    def start_stage(self, name: str) -> StageMetrics:
        """Start monitoring a pipeline stage"""
        # Finish previous stage if any
        if self._current_stage:
            self._finish_stage()

        self._stage_start = time.perf_counter()
        self._current_stage = StageMetrics(name=name)
        return self._current_stage

    def record_items(self, count: int):
        """Record number of items processed in current stage"""
        if self._current_stage:
            self._current_stage.items_processed = count

    def record_failed_items(self, count: int):
        """Record number of failed items in current stage"""
        if self._current_stage:
            self._current_stage.failed_items = count

    def record_cache_stats(self, stats: dict[str, Any], builder_name: str | None = None):
        """
        Record cache statistics for current stage.

        Args:
            stats: Cache statistics dictionary
            builder_name: Optional builder name for multi-builder stages (e.g., "bfg", "expression")
        """
        if self._current_stage:
            if builder_name:
                # Multi-builder stage: merge stats under builder name
                if not hasattr(self._current_stage, "cache_stats_by_builder"):
                    self._current_stage.cache_stats_by_builder = {}
                self._current_stage.cache_stats_by_builder[builder_name] = stats
            else:
                # Single-builder stage: direct assignment
                self._current_stage.cache_stats = stats

    def record_error(self):
        """Record an error in current stage"""
        if self._current_stage:
            self._current_stage.errors += 1

    def record_warning(self):
        """Record a warning in current stage"""
        if self._current_stage:
            self._current_stage.warnings += 1

    def record_validation_error(self, error_msg: str):
        """Record a validation error in the pipeline"""
        self._metrics.validation_errors.append(error_msg)

    def _finish_stage(self):
        """Finish current stage and record metrics"""
        if not self._current_stage:
            return

        # Calculate duration
        duration_ms = (time.perf_counter() - self._stage_start) * 1000
        self._current_stage.duration_ms = duration_ms

        # Track memory if enabled
        if self.enable_memory_tracking:
            try:
                import os

                import psutil

                process = psutil.Process(os.getpid())
                current_memory_mb = process.memory_info().rss / 1024 / 1024
                self._current_stage.memory_mb = current_memory_mb
                self._metrics.peak_memory_mb = max(self._metrics.peak_memory_mb, current_memory_mb)
            except Exception as e:
                # FIX: High - Add logging for better debuggability
                # psutil is optional, so we don't fail if it's not available
                logger.debug(f"Memory tracking failed (psutil may not be installed): {e}")

        # Add to metrics
        self._metrics.stages.append(self._current_stage)
        self._current_stage = None

    def end_pipeline(
        self,
        total_nodes: int = 0,
        total_blocks: int = 0,
        total_edges: int = 0,
        total_expressions: int = 0,
        total_variables: int = 0,
    ) -> PipelineMetrics:
        """
        End pipeline monitoring and return metrics.

        Args:
            total_nodes: Total IR nodes
            total_blocks: Total CFG blocks
            total_edges: Total CFG edges
            total_expressions: Total expressions
            total_variables: Total DFG variables

        Returns:
            Complete pipeline metrics
        """
        # Finish last stage
        if self._current_stage:
            self._finish_stage()

        # Calculate total duration
        self._metrics.total_duration_ms = (time.perf_counter() - self._pipeline_start) * 1000

        # Record output counts
        self._metrics.total_nodes = total_nodes
        self._metrics.total_blocks = total_blocks
        self._metrics.total_edges = total_edges
        self._metrics.total_expressions = total_expressions
        self._metrics.total_variables = total_variables

        return self._metrics

    def stage(self, name: str):
        """Context manager for tracking a stage"""
        return _StageContext(self, name)


class _StageContext:
    """Context manager for stage tracking"""

    def __init__(self, monitor: PerformanceMonitor, name: str):
        self.monitor = monitor
        self.name = name

    def __enter__(self):
        self.monitor.start_stage(self.name)
        return self.monitor._current_stage

    def __exit__(self, exc_type, _exc_val, _exc_tb):
        if exc_type is not None:
            self.monitor.record_error()
        self.monitor._finish_stage()
        return False
