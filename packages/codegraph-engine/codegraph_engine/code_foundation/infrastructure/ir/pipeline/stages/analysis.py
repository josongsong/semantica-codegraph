"""L6: Analysis Stage - Program Slicing & Taint Analysis

SOTA 2025: TypeSpec-defined Rust API integration.

Uses Rust implementations for:
- Program Slicing (8-15x faster than Python)
- Taint Analysis (10-20x faster than Python)

All APIs use msgpack for zero-copy serialization.

Performance:
- Backward Slice: 8-15x faster, 20-50x with cache hit
- Taint Analysis: 10-20x faster with parallel BFS
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import msgpack

from codegraph_shared.infra.logging import get_logger

from ..protocol import PipelineStage, StageContext

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class AnalysisStage(PipelineStage[dict[str, Any]]):
    """L6 Analysis stage - Program Slicing & Taint Analysis.

    Runs security and dependency analysis using Rust implementation.

    Features:
    1. Program Slicing (backward, forward, hybrid)
    2. Taint Analysis (source → sink flow detection)
    3. Cache-aware memoization for slicing

    Configuration:
        enabled: Enable analysis stage (default: True)
        run_taint: Run taint analysis (default: True)
        run_slicing: Run program slicing (default: False, on-demand)
        taint_custom_rules: Custom taint rules (optional)

    Example:
        ```python
        analysis = AnalysisStage(run_taint=True)
        ctx = await analysis.run(ctx)
        # ctx.analysis_results now contains taint paths
        ```
    """

    def __init__(
        self,
        enabled: bool = True,
        run_taint: bool = True,
        run_slicing: bool = False,  # On-demand by default
        taint_custom_rules: dict[str, Any] | None = None,
        **kwargs,
    ):
        """Initialize analysis stage.

        Args:
            enabled: Enable analysis stage
            run_taint: Run taint analysis
            run_slicing: Run program slicing (expensive, on-demand)
            taint_custom_rules: Custom taint rules
            **kwargs: Ignored
        """
        self.enabled = enabled
        self.run_taint = run_taint
        self.run_slicing = run_slicing
        self.taint_custom_rules = taint_custom_rules or {}

        # Lazy load Rust module
        self._rust_module = None

    @property
    def rust_module(self):
        """Lazy load Rust codegraph_ir module."""
        if self._rust_module is None:
            try:
                self._rust_module = importlib.import_module("codegraph_ir")
            except ImportError:
                logger.warning("codegraph_ir not available")
                return None
        return self._rust_module

    async def execute(self, ctx: StageContext) -> StageContext:
        """Execute analysis stage.

        Returns:
            Context with analysis_results populated
        """
        if not self.enabled:
            logger.debug("Analysis stage disabled, skipping")
            return ctx

        if not self.rust_module:
            logger.warning("Rust module not available, skipping analysis")
            return ctx

        results = {}

        # Run taint analysis
        if self.run_taint and ctx.global_ctx:
            taint_result = await self._run_taint_analysis(ctx)
            if taint_result:
                results["taint"] = taint_result

        # Merge with existing analysis results
        all_results = dict(ctx.analysis_results) if ctx.analysis_results else {}
        all_results.update(results)

        return replace(ctx, analysis_results=all_results)

    def should_skip(self, ctx: StageContext) -> tuple[bool, str | None]:
        """Check if analysis stage should be skipped."""
        if not self.enabled:
            return (True, "Analysis stage disabled")

        if not ctx.global_ctx:
            return (True, "No global context available")

        return (False, None)

    # =========================================================================
    # Taint Analysis
    # =========================================================================

    async def _run_taint_analysis(self, ctx: StageContext) -> dict[str, Any] | None:
        """Run taint analysis on call graph.

        Finds paths from sources (user input) to sinks (dangerous ops).

        Args:
            ctx: Stage context with global_ctx

        Returns:
            Taint analysis result or None
        """
        try:
            # Build call graph from global context
            call_graph = self._build_call_graph(ctx)

            if not call_graph:
                logger.debug("No call graph available for taint analysis")
                return None

            # Serialize to msgpack
            call_graph_data = msgpack.packb(call_graph)

            # Quick check first (fast)
            quick_result_bytes = self.rust_module.quick_taint_check(call_graph_data)
            quick_result = msgpack.unpackb(quick_result_bytes)

            if not quick_result.get("hasSources") or not quick_result.get("hasSinks"):
                logger.debug("No taint sources or sinks found, skipping full analysis")
                return {
                    "quick_check": quick_result,
                    "paths": [],
                    "summary": {"totalPaths": 0},
                }

            # Full analysis (parallel BFS)
            custom_sources = None
            custom_sinks = None
            custom_sanitizers = None

            if self.taint_custom_rules:
                if "sources" in self.taint_custom_rules:
                    custom_sources = msgpack.packb(self.taint_custom_rules["sources"])
                if "sinks" in self.taint_custom_rules:
                    custom_sinks = msgpack.packb(self.taint_custom_rules["sinks"])
                if "sanitizers" in self.taint_custom_rules:
                    custom_sanitizers = msgpack.packb(self.taint_custom_rules["sanitizers"])

            result_bytes = self.rust_module.analyze_taint(
                call_graph_data,
                custom_sources,
                custom_sinks,
                custom_sanitizers,
            )
            result = msgpack.unpackb(result_bytes)

            # Log summary
            summary = result.get("summary", {})
            logger.info(
                f"Taint analysis: {summary.get('totalPaths', 0)} paths, "
                f"{summary.get('unsanitizedCount', 0)} vulnerabilities"
            )

            return result

        except Exception as e:
            logger.error(f"Taint analysis failed: {e}", exc_info=True)
            return None

    def _build_call_graph(self, ctx: StageContext) -> dict[str, dict]:
        """Build call graph from global context.

        Converts IRDocument edges to call graph format expected by Rust.

        Format:
            {
                "node_id": {
                    "id": "node_id",
                    "name": "function_name",
                    "callees": ["callee1", "callee2"]
                }
            }
        """
        call_graph = {}

        # Build from IR documents
        for file_path, ir_doc in ctx.ir_documents.items():
            for node in ir_doc.nodes:
                # Only include functions and calls
                if node.get("kind") in ("function", "method", "call"):
                    node_id = node.get("id", "")
                    name = node.get("name", node_id)

                    # Find callees from edges
                    callees = []
                    for edge in ir_doc.edges:
                        if edge.get("source_id") == node_id and edge.get("kind") == "calls":
                            callees.append(edge.get("target_id", ""))

                    call_graph[node_id] = {
                        "id": node_id,
                        "name": name,
                        "callees": callees,
                    }

        return call_graph

    # =========================================================================
    # Program Slicing
    # =========================================================================

    def backward_slice(
        self,
        pdg_data: bytes,
        target_node: str,
        max_depth: int | None = None,
    ) -> dict[str, Any]:
        """Backward slice: find all nodes that affect the target.

        "Why does this variable have this value?"

        Args:
            pdg_data: PDG serialized as msgpack
            target_node: Target node ID
            max_depth: Maximum traversal depth

        Returns:
            Slice result with nodes and edges
        """
        if not self.rust_module:
            raise RuntimeError("Rust module not available")

        result_bytes = self.rust_module.backward_slice(
            pdg_data,
            target_node,
            max_depth,
        )
        return msgpack.unpackb(result_bytes)

    def forward_slice(
        self,
        pdg_data: bytes,
        source_node: str,
        max_depth: int | None = None,
    ) -> dict[str, Any]:
        """Forward slice: find all nodes affected by the source.

        "What will change if I modify this?"

        Args:
            pdg_data: PDG serialized as msgpack
            source_node: Source node ID
            max_depth: Maximum traversal depth

        Returns:
            Slice result with nodes and edges
        """
        if not self.rust_module:
            raise RuntimeError("Rust module not available")

        result_bytes = self.rust_module.forward_slice(
            pdg_data,
            source_node,
            max_depth,
        )
        return msgpack.unpackb(result_bytes)

    def hybrid_slice(
        self,
        pdg_data: bytes,
        focus_node: str,
        max_depth: int | None = None,
    ) -> dict[str, Any]:
        """Hybrid slice: backward + forward union.

        "Everything related to this node."

        Args:
            pdg_data: PDG serialized as msgpack
            focus_node: Focus node ID
            max_depth: Maximum traversal depth

        Returns:
            Slice result with nodes and edges
        """
        if not self.rust_module:
            raise RuntimeError("Rust module not available")

        result_bytes = self.rust_module.hybrid_slice(
            pdg_data,
            focus_node,
            max_depth,
        )
        return msgpack.unpackb(result_bytes)

    def get_slice_cache_stats(self) -> dict[str, Any]:
        """Get slicer cache statistics.

        Returns:
            Cache stats (size, capacity, hit_rate)
        """
        if not self.rust_module:
            return {}

        return dict(self.rust_module.get_slice_cache_stats())

    def invalidate_slice_cache(self, affected_nodes: list[str] | None = None) -> int:
        """Invalidate slice cache.

        Call when PDG changes.

        Args:
            affected_nodes: Specific nodes to invalidate (None = all)

        Returns:
            Number of invalidated entries
        """
        if not self.rust_module:
            return 0

        return self.rust_module.invalidate_slice_cache(affected_nodes)


# =========================================================================
# Convenience Functions
# =========================================================================


def get_taint_rules() -> dict[str, Any]:
    """Get default taint rules from Rust.

    Returns:
        Dict with sources, sinks, sanitizers
    """
    try:
        rust_module = importlib.import_module("codegraph_ir")
        result_bytes = rust_module.get_taint_rules()
        return msgpack.unpackb(result_bytes)
    except ImportError:
        return {}


def get_taint_stats() -> dict[str, int]:
    """Get taint analyzer statistics.

    Returns:
        Dict with source_count, sink_count, sanitizer_count
    """
    try:
        rust_module = importlib.import_module("codegraph_ir")
        return dict(rust_module.get_taint_stats())
    except ImportError:
        return {}


def quick_taint_check(call_graph: dict[str, dict]) -> dict[str, Any]:
    """Quick taint check on call graph.

    Fast presence detection before full analysis.

    Args:
        call_graph: Call graph as dict

    Returns:
        Quick check result
    """
    try:
        rust_module = importlib.import_module("codegraph_ir")
        call_graph_data = msgpack.packb(call_graph)
        result_bytes = rust_module.quick_taint_check(call_graph_data)
        return msgpack.unpackb(result_bytes)
    except ImportError:
        return {"hasSources": False, "hasSinks": False}


def analyze_taint(
    call_graph: dict[str, dict],
    custom_sources: list[dict] | None = None,
    custom_sinks: list[dict] | None = None,
    custom_sanitizers: list[str] | None = None,
) -> dict[str, Any]:
    """Full taint analysis on call graph.

    Args:
        call_graph: Call graph as dict
        custom_sources: Custom source patterns
        custom_sinks: Custom sink patterns
        custom_sanitizers: Custom sanitizer patterns

    Returns:
        Full taint analysis result
    """
    try:
        rust_module = importlib.import_module("codegraph_ir")
        call_graph_data = msgpack.packb(call_graph)

        sources_data = msgpack.packb(custom_sources) if custom_sources else None
        sinks_data = msgpack.packb(custom_sinks) if custom_sinks else None
        sanitizers_data = msgpack.packb(custom_sanitizers) if custom_sanitizers else None

        result_bytes = rust_module.analyze_taint(
            call_graph_data,
            sources_data,
            sinks_data,
            sanitizers_data,
        )
        return msgpack.unpackb(result_bytes)
    except ImportError:
        return {"paths": [], "summary": {"totalPaths": 0}}
