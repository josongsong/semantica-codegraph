"""
Indexing Performance Profiler

Tracks timing, memory usage, and counters for each phase of the indexing pipeline.
"""

import time
import tracemalloc
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def classify_phase_layer(phase_name: str) -> str:
    """
    Classify a phase into its logical layer.

    Layers:
    - parsing: Tree-sitter parsing → StructuralIR
    - ir: IR generation (converting AST to IRDocument)
    - semantic: Pyright, TypingIR, SignatureIR → SemanticIR
    - cfg: Control Flow Graph
    - dfg: Data Flow Graph
    - graph: SymbolGraph, RelationIndex
    - chunk: Chunk building
    - index: Lexical, vector, symbol indexing
    - retriever: Scope, fusion, rerank
    - other: Bootstrap, scan, finalize, etc.
    """
    name_lower = phase_name.lower()

    # Parse phase
    if "parse:" in name_lower or "parsing" in name_lower or phase_name == "scan_files":
        return "parsing"

    # IR generation phase
    if "ir_gen:" in name_lower or "ir_generation" in name_lower:
        return "ir"

    # Build phase - needs more granular classification
    if "build:" in name_lower:
        # Check for semantic-related keywords
        if any(
            kw in name_lower
            for kw in [
                "semantic",
                "typing",
                "signature",
                "type_resolution",
                "pyright",
            ]
        ):
            return "semantic"
        # Check for graph-related
        elif any(kw in name_lower for kw in ["graph", "symbol_graph", "relation"]):
            return "graph"
        # Check for chunk-related
        elif "chunk" in name_lower:
            return "chunk"
        # Default build to graph layer (most common)
        else:
            return "graph"

    # Infrastructure phases (must check before specific keywords)
    if phase_name in ["bootstrap", "repo_scan", "indexing_core", "finalize"]:
        return "other"

    # Specific layer keywords
    if "cfg" in name_lower or "control_flow" in name_lower:
        return "cfg"
    if "dfg" in name_lower or "data_flow" in name_lower:
        return "dfg"
    if "chunk" in name_lower:
        return "chunk"
    if any(kw in name_lower for kw in ["lexical", "vector", "symbol_index", "zoekt", "qdrant"]):
        return "index"
    if any(kw in name_lower for kw in ["retriev", "scope", "fusion", "rerank", "search", "query"]):
        return "retriever"

    # Default
    return "other"


@dataclass
class PhaseMetrics:
    """Metrics for a single phase."""

    name: str
    start_time: float
    end_time: float | None = None
    start_memory: float = 0.0  # MB
    end_memory: float = 0.0  # MB
    peak_memory: float = 0.0  # MB
    counters: dict[str, Any] = field(default_factory=dict)
    children: list["PhaseMetrics"] = field(default_factory=list)
    parent: "PhaseMetrics | None" = None
    layer: str = field(default="other")

    def __post_init__(self):
        """Classify layer after initialization."""
        if self.layer == "other":
            self.layer = classify_phase_layer(self.name)

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000

    @property
    def memory_delta_mb(self) -> float:
        """Memory delta in MB."""
        return self.end_memory - self.start_memory


@dataclass
class FileMetrics:
    """Metrics for a single file."""

    file_path: str
    language: str
    loc: int
    parse_time_ms: float = 0.0
    build_time_ms: float = 0.0
    total_time_ms: float = 0.0
    nodes: int = 0
    edges: int = 0
    chunks: int = 0
    symbols: int = 0


@dataclass
class FailedFileInfo:
    """Information about a failed file."""

    file_path: str
    error_type: str  # parsing_error, type_error, build_error, etc.
    error_message: str
    phase: str  # parse, build, chunk, etc.
    traceback: str | None = None


class IndexingProfiler:
    """
    Profiler for indexing pipeline.

    Tracks phases, timing, memory usage, and produces detailed reports.
    """

    def __init__(self, repo_id: str, repo_path: str):
        """
        Initialize profiler.

        Args:
            repo_id: Repository identifier
            repo_path: Path to repository
        """
        self.repo_id = repo_id
        self.repo_path = repo_path
        self.run_id = f"idx_{time.strftime('%Y%m%dT%H%M%S')}_{repo_id}"

        # Tracking
        self._phase_stack: list[PhaseMetrics] = []
        self._all_phases: list[PhaseMetrics] = []
        self._file_metrics: dict[str, FileMetrics] = {}
        self._failed_files: list[FailedFileInfo] = []
        self._global_counters: dict[str, Any] = defaultdict(int)

        # Timing
        self._start_time: float = 0.0
        self._end_time: float = 0.0

        # Memory
        self._start_memory: float = 0.0
        self._end_memory: float = 0.0
        self._peak_memory: float = 0.0
        self._memory_tracking_active = False

    def start(self):
        """Start profiling."""
        self._start_time = time.time()

        # Start memory tracking
        tracemalloc.start()
        self._memory_tracking_active = True
        self._start_memory = self._get_memory_mb()

    def end(self):
        """End profiling."""
        self._end_time = time.time()
        self._end_memory = self._get_memory_mb()

        # Get peak memory
        if self._memory_tracking_active:
            _, peak = tracemalloc.get_traced_memory()
            self._peak_memory = peak / 1024 / 1024
            tracemalloc.stop()
            self._memory_tracking_active = False

    def start_phase(self, name: str) -> PhaseMetrics:
        """
        Start a new phase.

        Args:
            name: Phase name

        Returns:
            PhaseMetrics instance
        """
        phase = PhaseMetrics(
            name=name,
            start_time=time.time(),
            start_memory=self._get_memory_mb(),
        )

        # Link to parent if exists
        if self._phase_stack:
            parent = self._phase_stack[-1]
            phase.parent = parent
            parent.children.append(phase)

        self._phase_stack.append(phase)
        self._all_phases.append(phase)

        return phase

    def end_phase(self, name: str | None = None):
        """
        End current phase.

        Args:
            name: Optional phase name for validation
        """
        if not self._phase_stack:
            return

        phase = self._phase_stack.pop()

        if name and phase.name != name:
            raise ValueError(f"Phase name mismatch: expected {name}, got {phase.name}")

        phase.end_time = time.time()
        phase.end_memory = self._get_memory_mb()
        phase.peak_memory = self._get_peak_memory_mb()

    def record_counter(self, key: str, value: Any):
        """
        Record a counter value for current phase.

        Args:
            key: Counter key
            value: Counter value
        """
        if self._phase_stack:
            phase = self._phase_stack[-1]
            phase.counters[key] = value
        else:
            self._global_counters[key] = value

    def increment_counter(self, key: str, delta: int = 1):
        """
        Increment a counter for current phase.

        Args:
            key: Counter key
            delta: Increment amount
        """
        if self._phase_stack:
            phase = self._phase_stack[-1]
            phase.counters[key] = phase.counters.get(key, 0) + delta
        else:
            self._global_counters[key] += delta

    def record_file(
        self,
        file_path: str,
        language: str,
        loc: int,
        parse_time_ms: float,
        build_time_ms: float,
        nodes: int = 0,
        edges: int = 0,
        chunks: int = 0,
        symbols: int = 0,
    ):
        """
        Record metrics for a processed file.

        Args:
            file_path: Relative file path
            language: Programming language
            loc: Lines of code
            parse_time_ms: Parse time in milliseconds
            build_time_ms: Build time in milliseconds
            nodes: Number of nodes created
            edges: Number of edges created
            chunks: Number of chunks created
            symbols: Number of symbols created
        """
        self._file_metrics[file_path] = FileMetrics(
            file_path=file_path,
            language=language,
            loc=loc,
            parse_time_ms=parse_time_ms,
            build_time_ms=build_time_ms,
            total_time_ms=parse_time_ms + build_time_ms,
            nodes=nodes,
            edges=edges,
            chunks=chunks,
            symbols=symbols,
        )

    def record_failed_file(
        self,
        file_path: str,
        error_type: str,
        error_message: str,
        phase: str,
        traceback: str | None = None,
    ):
        """
        Record a failed file with error information.

        Args:
            file_path: Relative file path
            error_type: Type of error (parsing_error, type_error, build_error, etc.)
            error_message: Error message
            phase: Phase where error occurred (parse, build, chunk, etc.)
            traceback: Optional full traceback
        """
        self._failed_files.append(
            FailedFileInfo(
                file_path=file_path,
                error_type=error_type,
                error_message=error_message,
                phase=phase,
                traceback=traceback,
            )
        )

    def _get_memory_mb(self) -> float:
        """Get current memory usage in MB."""
        if not self._memory_tracking_active:
            return 0.0

        current, _ = tracemalloc.get_traced_memory()
        return current / 1024 / 1024

    def _get_peak_memory_mb(self) -> float:
        """Get peak memory usage in MB."""
        if not self._memory_tracking_active:
            return 0.0

        _, peak = tracemalloc.get_traced_memory()
        return peak / 1024 / 1024

    @property
    def total_duration_s(self) -> float:
        """Total duration in seconds."""
        return self._end_time - self._start_time

    @property
    def root_phases(self) -> list[PhaseMetrics]:
        """Get root-level phases (no parent)."""
        return [p for p in self._all_phases if p.parent is None]

    @property
    def all_phases(self) -> list[PhaseMetrics]:
        """Get all phases."""
        return self._all_phases

    @property
    def file_metrics(self) -> dict[str, FileMetrics]:
        """Get all file metrics."""
        return self._file_metrics

    @property
    def global_counters(self) -> dict[str, Any]:
        """Get global counters."""
        return dict(self._global_counters)

    @property
    def failed_files(self) -> list[FailedFileInfo]:
        """Get all failed files."""
        return self._failed_files

    def get_slow_files(self, limit: int = 10) -> list[FileMetrics]:
        """
        Get slowest files.

        Args:
            limit: Maximum number of files to return

        Returns:
            List of FileMetrics sorted by total time
        """
        return sorted(self._file_metrics.values(), key=lambda f: f.total_time_ms, reverse=True)[:limit]

    def get_files_by_symbols(self, limit: int = 10) -> list[FileMetrics]:
        """
        Get files with most symbols.

        Args:
            limit: Maximum number of files to return

        Returns:
            List of FileMetrics sorted by symbol count
        """
        return sorted(self._file_metrics.values(), key=lambda f: f.symbols, reverse=True)[:limit]

    def get_layer_statistics(self) -> dict[str, dict[str, float]]:
        """
        Get aggregated statistics by logical layer.

        Only aggregates leaf phases (phases with no children) to avoid double-counting.
        For example, 'indexing_core' contains all 'parse:*' and 'build:*' phases,
        so we only count the leaf phases.

        Returns:
            Dict mapping layer name to stats:
            {
                "parsing": {
                    "total_time_ms": float,
                    "total_memory_mb": float,
                    "peak_memory_mb": float,
                    "phase_count": int,
                    "percentage": float,
                },
                ...
            }
        """
        layer_stats: dict[str, dict[str, Any]] = {}

        # Get leaf phases only (no children)
        leaf_phases = [p for p in self._all_phases if not p.children]

        # Calculate total from leaf phases only, excluding infrastructure
        processing_phases = [p for p in leaf_phases if p.layer != "other"]
        total_duration_ms = sum(p.duration_ms for p in processing_phases)

        # Aggregate stats for each layer
        for phase in leaf_phases:
            layer = phase.layer
            if layer not in layer_stats:
                layer_stats[layer] = {
                    "total_time_ms": 0.0,
                    "total_memory_mb": 0.0,
                    "peak_memory_mb": 0.0,
                    "phase_count": 0,
                }

            layer_stats[layer]["total_time_ms"] += phase.duration_ms
            layer_stats[layer]["total_memory_mb"] += phase.memory_delta_mb
            layer_stats[layer]["peak_memory_mb"] = max(layer_stats[layer]["peak_memory_mb"], phase.peak_memory)
            layer_stats[layer]["phase_count"] += 1

        # Calculate percentages
        for layer, stats in layer_stats.items():
            stats["percentage"] = (stats["total_time_ms"] / total_duration_ms * 100) if total_duration_ms > 0 else 0

        return layer_stats
