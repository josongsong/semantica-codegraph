"""
Context-Sensitive Analyzer

Main analyzer that combines:
- Type narrowing (from precise_call_graph.py)
- Argument value tracking (from value_tracker.py)
- Context-sensitive call graph construction (from call_context.py)

This is the integration point for context-sensitive analysis.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from .call_context import CallContext, ContextSensitiveCallGraph
from .precise_call_graph import PreciseCallGraphBuilder
from .value_tracker import ArgumentValueTracker

logger = structlog.get_logger(__name__)


@dataclass
class ContextSensitiveAnalyzer:
    """
    Main analyzer for context-sensitive analysis

    Combines:
    1. Type narrowing → precise receiver types
    2. Argument tracking → precise argument values
    3. Call contexts → context-sensitive call graph

    Example:
        def process(use_fast: bool):
            if use_fast:
                return db.fast_query()  # Only reachable when use_fast=True
            return db.slow_query()      # Only reachable when use_fast=False

        # Context 1: process(True)
        # → CallContext(args={use_fast: True})
        # → Reachable: [db.fast_query]

        # Context 2: process(False)
        # → CallContext(args={use_fast: False})
        # → Reachable: [db.slow_query]
    """

    # Components
    value_tracker: ArgumentValueTracker = field(default_factory=ArgumentValueTracker)
    precise_cg_builder: PreciseCallGraphBuilder | None = None

    # Results
    cs_call_graph: ContextSensitiveCallGraph = field(default_factory=ContextSensitiveCallGraph)

    # IR input (optional, for analysis)
    _ir_docs: dict[str, Any] = field(default_factory=dict)

    async def analyze(
        self,
        ir_docs: dict[str, Any],
        use_type_narrowing: bool = True,
    ) -> ContextSensitiveCallGraph:
        """
        Analyze IR documents to build context-sensitive call graph

        Args:
            ir_docs: IR documents to analyze
            use_type_narrowing: Whether to use type narrowing

        Returns:
            Context-sensitive call graph
        """
        logger.info("starting_cs_analysis", num_files=len(ir_docs))

        # Store IR
        self._ir_docs = ir_docs

        # Step 1: Build precise call graph (with type narrowing)
        if use_type_narrowing and self.precise_cg_builder:
            logger.info("building_precise_cg")
            await self.precise_cg_builder.build_call_graph(ir_docs)

        # Step 2: Analyze call sites and track arguments
        logger.info("analyzing_call_sites")
        self._analyze_call_sites(ir_docs)

        # Step 3: Build context-sensitive call graph
        logger.info("building_cs_call_graph")
        self._build_cs_call_graph(ir_docs)

        logger.info(
            "cs_analysis_complete",
            num_contexts=len(self.cs_call_graph),
            num_edge_types=len(self.cs_call_graph.edges),
        )

        return self.cs_call_graph

    def _analyze_call_sites(self, ir_docs: dict[str, Any]):
        """
        Analyze all call sites to track argument values

        For each function call:
        1. Extract call site location
        2. Extract arguments
        3. Track argument values
        """
        for file_path, ir_doc in ir_docs.items():
            # Get edges (which represent relationships including calls)
            edges = getattr(ir_doc, "edges", [])

            for edge in edges:
                edge_type = getattr(edge, "type", "")

                # Filter for call edges
                if edge_type != "CALLS":
                    continue

                # Extract call site info
                getattr(edge, "source", "")
                getattr(edge, "target", "")
                metadata = getattr(edge, "metadata", {})

                # Get call site location
                call_site = metadata.get("call_site", f"{file_path}:0:0")

                # Extract arguments if available
                arguments = metadata.get("arguments", {})

                # Track each argument
                for param_name, arg_node in arguments.items():
                    self.value_tracker.track_argument(
                        call_site=call_site,
                        param_name=param_name,
                        value_node=arg_node if isinstance(arg_node, dict) else {"type": "unknown"},
                    )

    def _build_cs_call_graph(self, ir_docs: dict[str, Any]):
        """
        Build context-sensitive call graph

        For each call edge:
        1. Get call site
        2. Get argument values
        3. Create CallContext
        4. Add to CS call graph
        """
        for file_path, ir_doc in ir_docs.items():
            edges = getattr(ir_doc, "edges", [])

            for edge in edges:
                edge_type = getattr(edge, "type", "")

                if edge_type != "CALLS":
                    continue

                source_id = getattr(edge, "source", "")
                target_id = getattr(edge, "target", "")
                metadata = getattr(edge, "metadata", {})

                call_site = metadata.get("call_site", f"{file_path}:0:0")

                # Get concrete argument values
                # For now, we'll create one context per call site
                # More sophisticated: create multiple contexts for different value combinations

                arg_values = {}
                arguments = metadata.get("arguments", {})

                for param_name in arguments.keys():
                    concrete = self.value_tracker.get_concrete_values(call_site, param_name)
                    if concrete:
                        arg_values.update(concrete)

                # Create call context
                context = CallContext.from_dict(
                    call_site=call_site,
                    args=arg_values,
                    parent=None,  # TODO: Track parent context for call chains
                )

                # Add to CS call graph
                self.cs_call_graph.add_edge(
                    caller=source_id,
                    callee=target_id,
                    context=context,
                )

                logger.debug(
                    "added_cs_edge",
                    caller=source_id,
                    callee=target_id,
                    context=context.short_id(),
                    args=arg_values,
                )

    def query_reachable(
        self,
        start_function: str,
        argument_pattern: dict[str, Any],
        max_depth: int = 10,
    ) -> set[str]:
        """
        Query reachable functions under specific argument pattern

        Example:
            analyzer.query_reachable(
                start_function="process",
                argument_pattern={"use_fast": True},
                max_depth=5
            )
            → Returns functions reachable when use_fast=True
        """
        # Find contexts matching pattern
        matching_contexts = []

        for (caller, _callee), contexts in self.cs_call_graph.edges.items():
            if caller == start_function:
                for ctx in contexts:
                    if ctx.matches_pattern(argument_pattern):
                        matching_contexts.append(ctx)

        # Get reachable from each matching context
        reachable = set()
        for ctx in matching_contexts:
            reachable_in_ctx = self.cs_call_graph.get_reachable(
                start=start_function,
                context=ctx,
                max_depth=max_depth,
            )
            reachable.update(func for func, _ in reachable_in_ctx)

        return reachable

    def compare_contexts(
        self,
        function: str,
        context1: dict[str, Any],
        context2: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Compare reachable functions under two different contexts

        Example:
            analyzer.compare_contexts(
                function="process",
                context1={"use_fast": True},
                context2={"use_fast": False}
            )
            → Returns {
                "only_in_context1": [...],
                "only_in_context2": [...],
                "common": [...]
            }
        """
        reachable1 = self.query_reachable(function, context1)
        reachable2 = self.query_reachable(function, context2)

        return {
            "only_in_context1": reachable1 - reachable2,
            "only_in_context2": reachable2 - reachable1,
            "common": reachable1 & reachable2,
            "context1_size": len(reachable1),
            "context2_size": len(reachable2),
            "precision_gain_pct": (
                len(reachable1 - reachable2) / len(reachable1 | reachable2) * 100 if (reachable1 | reachable2) else 0
            ),
        }

    def get_impact_analysis(
        self,
        changed_function: str,
        context_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Analyze impact of changing a function

        With context sensitivity, we can identify:
        - Which callers are affected
        - Under what contexts
        - What the downstream impact is

        Returns:
            {
                "direct_callers": [...],
                "affected_contexts": [...],
                "downstream_impact": [...]
            }
        """
        direct_callers = set()
        affected_contexts = []

        # Find all callers
        for (caller, callee), contexts in self.cs_call_graph.edges.items():
            if callee == changed_function:
                direct_callers.add(caller)

                # Filter contexts if pattern provided
                if context_filter:
                    matching = [ctx for ctx in contexts if ctx.matches_pattern(context_filter)]
                    affected_contexts.extend(matching)
                else:
                    affected_contexts.extend(contexts)

        # Compute downstream impact
        downstream = set()
        for caller in direct_callers:
            for ctx in affected_contexts:
                # Get reachable from this caller
                reachable = self.cs_call_graph.get_reachable(
                    start=caller,
                    context=ctx,
                    max_depth=5,
                )
                downstream.update(func for func, _ in reachable)

        return {
            "changed_function": changed_function,
            "direct_callers": list(direct_callers),
            "num_affected_contexts": len(affected_contexts),
            "downstream_impact": list(downstream),
            "total_affected": len(direct_callers) + len(downstream),
        }

    def get_statistics(self) -> dict[str, Any]:
        """Get comprehensive statistics"""
        value_stats = self.value_tracker.get_statistics()

        # Compute CS call graph stats
        basic_edges = self.cs_call_graph.to_basic_cg()

        return {
            "value_tracking": value_stats,
            "cs_call_graph": {
                "total_contexts": len(self.cs_call_graph),
                "num_edge_types": len(self.cs_call_graph.edges),
                "basic_edges": len(basic_edges),
                "avg_contexts_per_edge": (len(self.cs_call_graph) / len(basic_edges) if basic_edges else 0),
            },
        }

    def __repr__(self) -> str:
        stats = self.get_statistics()
        cs_stats = stats["cs_call_graph"]
        return (
            f"ContextSensitiveAnalyzer({cs_stats['num_edge_types']} edge types, {cs_stats['total_contexts']} contexts)"
        )
