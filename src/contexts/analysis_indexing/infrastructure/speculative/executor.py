"""
Speculative Executor

Main entry point for speculative graph execution.
"""

from dataclasses import dataclass

import structlog

from .models import (
    GraphDelta,
    RiskLevel,
    SimulationContext,
    SpeculativePatch,
    SpeculativeResult,
)
from .risk_analyzer import RiskAnalyzer
from .simulator import GraphSimulator

logger = structlog.get_logger(__name__)


@dataclass
class SpeculativeExecutor:
    """
    Executes speculative analysis on patches

    Integrates:
    - GraphSimulator (what changes)
    - RiskAnalyzer (how risky)

    Example:
        executor = SpeculativeExecutor(context)

        # Analyze patch
        patch = SpeculativePatch(...)
        result = executor.execute(patch)

        print(f"Risk: {result.risk_level.name}")
        print(f"Changes: {result.graph_delta.size()}")
        print(f"Safe: {result.is_safe()}")

        if result.is_safe():
            apply_patch(patch)
    """

    context: SimulationContext
    simulator: GraphSimulator | None = None
    risk_analyzer: RiskAnalyzer | None = None

    def __post_init__(self):
        """Initialize components"""
        if self.simulator is None:
            self.simulator = GraphSimulator(self.context)
        if self.risk_analyzer is None:
            self.risk_analyzer = RiskAnalyzer(self.context)

    def execute(self, patch: SpeculativePatch) -> SpeculativeResult:
        """
        Execute speculative analysis

        Args:
            patch: SpeculativePatch to analyze

        Returns:
            SpeculativeResult with predictions and risk analysis
        """
        logger.info(
            "executing_speculative_analysis",
            patch_type=patch.patch_type.value,
            target=patch.target_symbol,
        )

        # Step 1: Simulate graph changes
        graph_delta = self.simulator.simulate(patch)

        # Step 2: Analyze risk
        risk_level, risk_reasons = self.risk_analyzer.analyze_risk(patch, graph_delta)

        # Step 3: Find affected symbols/files
        affected_symbols = self._compute_affected_symbols(graph_delta)
        affected_files = self._compute_affected_files(graph_delta)

        # Step 4: Find breaking changes
        breaking_changes = self._find_breaking_changes(patch, graph_delta)

        # Step 5: Analyze call graph impact
        callers_affected, callees_affected = self._analyze_call_graph_impact(patch, graph_delta)

        # Step 6: Generate recommendations
        recommendations = self.risk_analyzer.generate_recommendations(patch, graph_delta, risk_level)

        # Step 7: Estimate performance impact
        rebuild_time = self._estimate_rebuild_time(graph_delta)

        # Build result
        result = SpeculativeResult(
            patch=patch,
            graph_delta=graph_delta,
            risk_level=risk_level,
            risk_reasons=risk_reasons,
            affected_symbols=affected_symbols,
            affected_files=affected_files,
            breaking_changes=breaking_changes,
            callers_affected=callers_affected,
            callees_affected=callees_affected,
            recommendations=recommendations,
            estimated_rebuild_time_ms=rebuild_time,
        )

        logger.info(
            "speculative_execution_complete",
            risk_level=risk_level.name,
            graph_changes=graph_delta.size(),
            affected_symbols=len(affected_symbols),
            is_safe=result.is_safe(),
        )

        return result

    def execute_batch(
        self,
        patches: list[SpeculativePatch],
    ) -> list[SpeculativeResult]:
        """
        Execute speculative analysis on multiple patches

        Useful for analyzing a series of related patches
        """
        logger.info("executing_batch_analysis", num_patches=len(patches))

        results = []
        for patch in patches:
            result = self.execute(patch)
            results.append(result)

        logger.info(
            "batch_analysis_complete",
            num_patches=len(patches),
            high_risk=sum(1 for r in results if r.risk_level >= RiskLevel.HIGH),
        )

        return results

    def _compute_affected_symbols(self, delta: GraphDelta) -> set[str]:
        """Compute all affected symbols"""
        affected = set()

        affected.update(delta.nodes_added)
        affected.update(delta.nodes_removed)
        affected.update(delta.nodes_modified)

        # Add symbols involved in edge changes
        for source, target in delta.edges_added:
            affected.add(source)
            affected.add(target)

        for source, target in delta.edges_removed:
            affected.add(source)
            affected.add(target)

        return affected

    def _compute_affected_files(self, delta: GraphDelta) -> set[str]:
        """Compute affected files"""
        affected_files = set()

        # For each affected symbol, find its file
        for symbol in self._compute_affected_symbols(delta):
            # Try to extract file from symbol ID
            # Format: file.py:Class.method
            if ":" in symbol:
                file_path = symbol.split(":")[0]
                affected_files.add(file_path)

        return affected_files

    def _find_breaking_changes(
        self,
        patch: SpeculativePatch,
        delta: GraphDelta,
    ) -> list[str]:
        """Find potential breaking changes"""
        breaking = []

        # Removed nodes
        if delta.nodes_removed:
            for node in delta.nodes_removed:
                # Check if has callers
                if self.context.call_graph:
                    callers = self._find_callers(node)
                    if callers:
                        breaking.append(f"Removing {node} breaks {len(callers)} caller(s)")

        # Signature changes
        if patch.patch_type.value == "change_signature":
            breaking.append(f"Signature change to {patch.target_symbol} may break callers")

        # Rename with many references
        if patch.patch_type.value == "rename":
            ref_count = len(delta.edges_added) + len(delta.edges_removed)
            if ref_count > 5:
                breaking.append(f"Renaming {patch.target_symbol} affects {ref_count} references")

        return breaking

    def _analyze_call_graph_impact(
        self,
        patch: SpeculativePatch,
        delta: GraphDelta,
    ) -> tuple[set[str], set[str]]:
        """Analyze call graph impact"""
        callers_affected = set()
        callees_affected = set()

        target = patch.target_symbol

        # Find callers
        callers_affected = self._find_callers(target)

        # Find callees
        callees_affected = self._find_callees(target)

        return callers_affected, callees_affected

    def _find_callers(self, symbol: str) -> set[str]:
        """Find all callers"""
        callers = set()

        if self.context.call_graph and hasattr(self.context.call_graph, "edges"):
            edges = self.context.call_graph.edges
            for (caller, callee), _ in edges.items():
                if callee == symbol:
                    callers.add(caller)

        return callers

    def _find_callees(self, symbol: str) -> set[str]:
        """Find all callees"""
        callees = set()

        if self.context.call_graph and hasattr(self.context.call_graph, "edges"):
            edges = self.context.call_graph.edges
            for (caller, callee), _ in edges.items():
                if caller == symbol:
                    callees.add(callee)

        return callees

    def _estimate_rebuild_time(self, delta: GraphDelta) -> float:
        """Estimate rebuild time in milliseconds"""
        # Simple heuristic: 10ms per node, 5ms per edge
        nodes_time = delta.size() * 10.0
        edges_time = (len(delta.edges_added) + len(delta.edges_removed)) * 5.0

        return nodes_time + edges_time

    def __repr__(self) -> str:
        return f"SpeculativeExecutor(context={self.context})"
