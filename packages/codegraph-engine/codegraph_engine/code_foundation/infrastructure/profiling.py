"""
SOTA-level Profiling Infrastructure

OpenTelemetry-style tracing and metrics for code foundation components.
Zero-overhead when disabled (profiler=None).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Profiler(Protocol):
    """
    Protocol for profiling pipeline components.

    Inspired by OpenTelemetry spans and metrics API.
    """

    @contextmanager
    def phase(self, name: str, **attributes: Any):
        """
        Context manager for profiling a phase.

        Usage:
            with profiler.phase("ir_generation", file=file_path):
                # ... do work
                pass

        Args:
            name: Phase name (e.g., "ir_generation", "ast_traverse")
            **attributes: Additional metadata
        """
        ...

    def record_metric(self, name: str, value: float | int, **labels: Any) -> None:
        """
        Record a metric value.

        Args:
            name: Metric name (e.g., "nodes_created", "loc")
            value: Metric value
            **labels: Additional labels
        """
        ...

    def increment(self, name: str, delta: int = 1, **labels: Any) -> None:
        """
        Increment a counter metric.

        Args:
            name: Counter name
            delta: Amount to increment
            **labels: Additional labels
        """
        ...


class NoOpProfiler:
    """
    No-op profiler for production use.
    Zero overhead - all methods are empty.
    """

    @contextmanager
    def phase(self, name: str, **attributes: Any):
        yield

    def start_phase(self, name: str, **attributes: Any) -> None:
        pass

    def end_phase(self, name: str | None = None) -> None:
        pass

    def record_metric(self, name: str, value: float | int, **labels: Any) -> None:
        pass

    def increment(self, name: str, delta: int = 1, **labels: Any) -> None:
        pass


class SimpleProfiler:
    """
    Simple profiler implementation for benchmarking.

    Tracks:
    - Phase timings (hierarchical)
    - Counters
    - Custom metrics
    """

    def __init__(self):
        self.phases: list[PhaseSpan] = []
        self._phase_stack: list[PhaseSpan] = []
        self.counters: dict[str, int | float] = {}
        self.metrics: dict[str, list[tuple[float | int, dict[str, Any]]]] = {}

    @contextmanager
    def phase(self, name: str, **attributes: Any):
        """Start a profiling phase."""
        span = PhaseSpan(
            name=name,
            start_time=time.perf_counter(),
            attributes=attributes,
            parent=self._phase_stack[-1] if self._phase_stack else None,
        )

        self._phase_stack.append(span)

        try:
            yield span
        finally:
            span.end_time = time.perf_counter()
            self._phase_stack.pop()

            if span.parent:
                span.parent.children.append(span)
            else:
                self.phases.append(span)

    def record_metric(self, name: str, value: float | int, **labels: Any) -> None:
        """Record a metric value."""
        if name not in self.metrics:
            self.metrics[name] = []
        self.metrics[name].append((value, labels))

    def increment(self, name: str, delta: int = 1, **labels: Any) -> None:
        """Increment a counter."""
        key = name
        if labels:
            label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
            key = f"{name}[{label_str}]"

        self.counters[key] = self.counters.get(key, 0) + delta

    def start_phase(self, name: str, **attributes: Any) -> None:
        """Start a named phase (imperative API for non-context-manager usage)."""
        span = PhaseSpan(
            name=name,
            start_time=time.perf_counter(),
            attributes=attributes,
            parent=self._phase_stack[-1] if self._phase_stack else None,
        )
        self._phase_stack.append(span)

    def end_phase(self, name: str | None = None) -> None:
        """End the current phase (imperative API for non-context-manager usage)."""
        if not self._phase_stack:
            return

        span = self._phase_stack.pop()
        span.end_time = time.perf_counter()

        if span.parent:
            span.parent.children.append(span)
        else:
            self.phases.append(span)

    def get_phase_summary(self) -> dict[str, Any]:
        """Get summary of all phases."""
        summary = {}

        def collect_phase(span: PhaseSpan, prefix: str = ""):
            phase_key = f"{prefix}{span.name}"
            duration_ms = (span.end_time - span.start_time) * 1000 if span.end_time else 0

            if phase_key not in summary:
                summary[phase_key] = {
                    "count": 0,
                    "total_ms": 0.0,
                    "min_ms": float("inf"),
                    "max_ms": 0.0,
                }

            summary[phase_key]["count"] += 1
            summary[phase_key]["total_ms"] += duration_ms
            summary[phase_key]["min_ms"] = min(summary[phase_key]["min_ms"], duration_ms)
            summary[phase_key]["max_ms"] = max(summary[phase_key]["max_ms"], duration_ms)

            # Recurse into children
            for child in span.children:
                collect_phase(child, prefix=f"{phase_key}.")

        for phase in self.phases:
            collect_phase(phase)

        # Calculate averages
        for phase_data in summary.values():
            if phase_data["count"] > 0:
                phase_data["avg_ms"] = phase_data["total_ms"] / phase_data["count"]

        return summary

    def get_total_time(self, phase_name: str) -> float:
        """Get total time spent in a phase (ms)."""
        summary = self.get_phase_summary()
        return summary.get(phase_name, {}).get("total_ms", 0.0)

    def get_pipeline_report(self) -> str:
        """
        Generate a formatted pipeline profiling report.

        Returns:
            Human-readable report string with timing breakdown.

        Example output:
            Pipeline Profiling Report
            ========================
            Phase                      Count    Total(ms)   Avg(ms)    %
            -------------------------- -------- ----------- ---------- ------
            discovery                  1        12.34       12.34      5.2%
            ir_generation              78       234.56      3.01       45.6%
              └─ ast_parse             78       45.67       0.59       8.9%
              └─ node_creation         78       89.12       1.14       17.4%
            graph_build                1        123.45      123.45     24.0%
            ...
        """
        summary = self.get_phase_summary()
        if not summary:
            return "No profiling data collected."

        # Calculate total time
        total_ms = sum(data.get("total_ms", 0) for data in summary.values())
        if total_ms == 0:
            total_ms = 1  # Avoid division by zero

        lines = [
            "Pipeline Profiling Report",
            "=" * 60,
            f"{'Phase':<30} {'Count':>8} {'Total(ms)':>12} {'Avg(ms)':>10} {'%':>7}",
            "-" * 60,
        ]

        # Sort phases by hierarchy (top-level first, then children)
        sorted_phases = sorted(summary.keys(), key=lambda x: (x.count("."), x))

        for phase_name in sorted_phases:
            data = summary[phase_name]
            count = data.get("count", 0)
            total = data.get("total_ms", 0)
            avg = data.get("avg_ms", 0)
            pct = (total / total_ms) * 100

            # Indent nested phases
            depth = phase_name.count(".")
            indent = "  └─ " * depth if depth > 0 else ""
            display_name = phase_name.split(".")[-1]

            lines.append(
                f"{indent}{display_name:<{30 - len(indent)}} {count:>8} {total:>12.2f} {avg:>10.2f} {pct:>6.1f}%"
            )

        lines.append("-" * 60)
        lines.append(f"{'TOTAL':<30} {'':<8} {total_ms:>12.2f}")

        # Add counters if any
        if self.counters:
            lines.append("")
            lines.append("Counters:")
            for name, value in sorted(self.counters.items()):
                lines.append(f"  {name}: {value}")

        return "\n".join(lines)

    def log_pipeline_summary(self, logger=None):
        """
        Log pipeline profiling summary.

        Args:
            logger: Logger instance (optional, uses print if None)
        """
        report = self.get_pipeline_report()
        if logger:
            logger.info("pipeline_profiling_complete", report=report)
        else:
            print(report)


class PhaseSpan:
    """
    Represents a single phase/span in the profiling trace.
    """

    def __init__(
        self,
        name: str,
        start_time: float,
        attributes: dict[str, Any] | None = None,
        parent: PhaseSpan | None = None,
    ):
        self.name = name
        self.start_time = start_time
        self.end_time: float | None = None
        self.attributes = attributes or {}
        self.parent = parent
        self.children: list[PhaseSpan] = []

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000


# Singleton instance for global no-op profiler
_noop_profiler = NoOpProfiler()


def get_noop_profiler() -> Profiler:
    """Get a singleton no-op profiler."""
    return _noop_profiler
