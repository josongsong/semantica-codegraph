"""
Reasoning Pipeline - RFC-06 통합 파이프라인

Effect → Impact → Slice → Speculative 전체 흐름
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument

from ..domain.effect_models import EffectDiff, EffectType
from ..domain.impact_models import ImpactLevel, ImpactReport
from ..domain.speculative_models import RiskLevel, RiskReport, SpeculativePatch
from ..infrastructure.impact.impact_analyzer import ImpactAnalyzer
from ..infrastructure.semantic_diff.effect_differ import EffectDiffer
from ..infrastructure.slicer.slicer import ProgramSlicer
from ..infrastructure.speculative.graph_adapter import GraphDocumentAdapter
from ..infrastructure.speculative.graph_simulator import GraphSimulator
from ..infrastructure.speculative.risk_analyzer import RiskAnalyzer
from .incremental_builder import IncrementalBuilder

logger = logging.getLogger(__name__)


@dataclass
class ReasoningContext:
    """
    추론 컨텍스트

    전체 파이프라인에서 사용되는 데이터
    """

    graph: GraphDocument
    source_code: str | None = None
    change_summary: dict[str, Any] = field(default_factory=dict)
    effect_diffs: dict[str, EffectDiff] = field(default_factory=dict)
    impact_reports: dict[str, ImpactReport] = field(default_factory=dict)
    slices: dict[str, Any] = field(default_factory=dict)
    risk_reports: dict[str, RiskReport] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # NEW: Cross-language analysis results (INTEGRATED)
    value_flow_graph: Any | None = None  # ValueFlowGraph
    boundary_matches: dict[str, Any] = field(default_factory=dict)  # {endpoint: MatchCandidate}
    cross_lang_flows: list[Any] = field(default_factory=list)  # Cross-service flows


@dataclass
class ReasoningResult:
    """
    추론 결과

    LLM에게 전달할 최종 결과
    """

    summary: str
    total_risk: RiskLevel
    total_impact: ImpactLevel
    breaking_changes: list[str]
    impacted_symbols: list[str]
    recommended_actions: list[str]
    context: ReasoningContext
    analyzed_at: float = field(default_factory=lambda: datetime.now().timestamp())

    def to_dict(self) -> dict[str, Any]:
        """LLM-friendly format"""
        return {
            "summary": self.summary,
            "total_risk": self.total_risk.value,
            "total_impact": self.total_impact.value,
            "breaking_changes": self.breaking_changes,
            "impacted_symbols": self.impacted_symbols,
            "recommended_actions": self.recommended_actions,
            "analyzed_at": self.analyzed_at,
        }


class ReasoningPipeline:
    """
    RFC-06 통합 추론 파이프라인

    Example:
        pipeline = ReasoningPipeline(graph)

        # 1. Effect analysis
        pipeline.analyze_effects({'func1': (before_code, after_code)})

        # 2. Impact analysis
        pipeline.analyze_impact(['func1'])

        # 3. Speculative execution
        patch = SpeculativePatch(...)
        pipeline.simulate_patch(patch)

        # 4. Get result
        result = pipeline.get_result()
    """

    def __init__(self, graph: GraphDocument, workspace_root: str | None = None, memgraph_store: Any | None = None):
        """
        Initialize pipeline

        Args:
            graph: GraphDocument
            workspace_root: Project root (for cross-language analysis)
            memgraph_store: Optional MemgraphGraphStore for Rust engine
        """
        self.ctx = ReasoningContext(graph=graph)

        # Existing components
        self.effect_differ = EffectDiffer()
        self.impact_analyzer = ImpactAnalyzer(graph, max_depth=5)
        self.slicer = ProgramSlicer(graph)
        self.risk_analyzer = RiskAnalyzer()
        self.incremental_builder: IncrementalBuilder | None = None

        # NEW: Cross-language analysis (INTEGRATED)
        self.value_flow_builder: Any | None = None
        if workspace_root:
            try:
                from ..infrastructure.cross_lang.value_flow_builder import ValueFlowBuilder

                self.value_flow_builder = ValueFlowBuilder(workspace_root)
                logger.info("Cross-language analysis enabled")
            except Exception as e:
                logger.warning(f"Cross-language analysis disabled: {e}")

        # RFC-007: Rust taint engine (10-50x speedup)
        self.rust_engine: Any | None = None
        self.memgraph_store = memgraph_store
        if memgraph_store:
            try:
                from ..infrastructure.engine.rust_taint_engine import RustTaintEngine

                self.rust_engine = RustTaintEngine()
                logger.info("Rust taint engine enabled (RFC-007)")
            except Exception as e:
                logger.warning(f"Rust taint engine disabled: {e}")

        logger.info("ReasoningPipeline initialized")

    def analyze_effects(self, changes: dict[str, tuple[str, str]]) -> dict[str, EffectDiff]:
        """
        Step 1: Effect 분석

        Args:
            changes: {symbol_id: (before_code, after_code)}

        Returns:
            {symbol_id: EffectDiff}
        """
        logger.info(f"Analyzing effects for {len(changes)} symbols")

        diffs = self.effect_differ.batch_compare(changes)

        # Store in context
        for diff in diffs:
            self.ctx.effect_diffs[diff.symbol_id] = diff

        # Update change summary
        breaking = [d for d in diffs if d.is_breaking]
        self.ctx.change_summary["breaking_count"] = len(breaking)
        self.ctx.change_summary["total_changes"] = len(diffs)

        logger.info(f"Found {len(breaking)} breaking changes")
        return self.ctx.effect_diffs

    def rebuild_graph_incrementally(
        self, changes: dict[str, tuple[str, str]], new_graph: GraphDocument | None = None
    ) -> GraphDocument:
        """
        Incremental graph rebuild

        변경된 심볼만 재분석하여 그래프를 효율적으로 업데이트

        Args:
            changes: {symbol_id: (old_code, new_code)}
            new_graph: Optional new graph (full rebuild용)

        Returns:
            Updated GraphDocument

        Example:
            changes = {'func1': (old_code, new_code)}
            updated_graph = pipeline.rebuild_graph_incrementally(changes)
            pipeline.ctx.graph = updated_graph
        """
        logger.info(f"Incremental rebuild: {len(changes)} changes")

        # Initialize builder
        self.incremental_builder = IncrementalBuilder(
            old_graph=self.ctx.graph, new_graph=new_graph, program_slicer=self.slicer
        )

        # Analyze changes
        impact_reports = self.incremental_builder.analyze_changes(changes)
        logger.info(f"Found {len(impact_reports)} breaking changes")

        # Create rebuild plan
        plan = self.incremental_builder.create_rebuild_plan()
        logger.info(f"Rebuild plan: {plan.summary()}")

        # Execute rebuild
        updated_graph = self.incremental_builder.execute_rebuild(plan)

        # Update context
        self.ctx.impact_reports.update(impact_reports)
        self.ctx.metadata["rebuild_plan"] = {
            "strategy": plan.strategy,
            "changed_files": list(plan.changed_files),
            "impacted_files": list(plan.impacted_files),
            "symbols_to_rebuild": len(plan.symbols_to_rebuild),
            "estimated_cost": plan.estimated_cost,
        }

        # Statistics
        stats = self.incremental_builder.get_statistics()
        self.ctx.metadata["rebuild_stats"] = stats

        logger.info(
            f"Rebuild complete: {plan.strategy}, "
            f"{stats['changed_symbols']} changed, "
            f"{stats['impacted_symbols']} impacted"
        )

        return updated_graph

    def analyze_impact(self, source_ids: list[str]) -> dict[str, ImpactReport]:
        """
        Step 2: Impact 분석

        Args:
            source_ids: Source symbol IDs

        Returns:
            {symbol_id: ImpactReport}
        """
        logger.info(f"Analyzing impact for {len(source_ids)} sources")

        reports = self.impact_analyzer.batch_analyze(source_ids, self.ctx.effect_diffs)

        # Store in context
        self.ctx.impact_reports.update(reports)

        # Calculate total impact
        total_impact = self._calculate_total_impact(reports)
        self.ctx.change_summary["total_impact"] = total_impact.value

        logger.info(f"Total impact: {total_impact.value}")
        return reports

    def extract_slices(self, symbol_ids: list[str], max_budget: int = 2000) -> dict[str, Any]:
        """
        Step 3: Program Slice 추출

        Args:
            symbol_ids: Symbol IDs to slice
            max_budget: Max tokens

        Returns:
            {symbol_id: slice_data}
        """
        logger.info(f"Extracting slices for {len(symbol_ids)} symbols")

        for symbol_id in symbol_ids:
            try:
                slice_data = self.slicer.backward_slice(
                    symbol_id,
                    max_depth=3,
                )

                # Budget check after slicing
                if slice_data.total_tokens > max_budget:
                    logger.warning(f"Slice for {symbol_id} exceeds budget: {slice_data.total_tokens} > {max_budget}")
                    # Truncate fragments if needed
                    # (or skip this slice)

                self.ctx.slices[symbol_id] = slice_data
            except Exception as e:
                logger.error(f"Failed to slice {symbol_id}: {e}")

        logger.info(f"Extracted {len(self.ctx.slices)} slices")
        return self.ctx.slices

    def simulate_patch(self, patch: SpeculativePatch) -> RiskReport:
        """
        Step 4: Speculative 실행

        Args:
            patch: SpeculativePatch

        Returns:
            RiskReport
        """
        logger.info(f"Simulating patch: {patch.patch_id}")

        # Convert GraphDocument to dict
        base_dict = GraphDocumentAdapter.to_dict(self.ctx.graph)

        # Simulate
        simulator = GraphSimulator(base_dict)
        delta_graph = simulator.simulate_patch(patch)

        # Analyze risk
        risk = self.risk_analyzer.analyze_risk(patch, delta_graph, self.ctx.graph)

        # Store in context
        self.ctx.risk_reports[patch.patch_id] = risk
        self.ctx.change_summary["risk_level"] = risk.risk_level.value

        logger.info(f"Risk: {risk.risk_level.value}, breaking={risk.is_breaking()}")
        return risk

    def analyze_cross_language_flows(self, ir_documents: list[Any]) -> dict[str, Any]:
        """
        NEW: Cross-language flow analysis (INTEGRATED)

        Analyzes data flow across services:
        - Frontend → Backend
        - Backend → Database
        - Service → Service

        Args:
            ir_documents: IR documents from code analysis

        Returns:
            Analysis results
        """
        if not self.value_flow_builder:
            logger.warning("Cross-language analysis not enabled")
            return {}

        logger.info("Analyzing cross-language flows...")

        # 1. Discover service boundaries
        boundaries = self.value_flow_builder.discover_boundaries()
        logger.info(f"Found {len(boundaries)} service boundaries")

        # 2. Build ValueFlowGraph from IR
        vfg = self.value_flow_builder.build_from_ir(ir_documents, self.ctx.graph)

        # 3. Add boundary flows
        boundary_count = self.value_flow_builder.add_boundary_flows(vfg, boundaries, ir_documents)

        # 4. Analyze cross-service flows
        cross_flows = vfg.find_cross_service_flows()

        # 5. Taint analysis (PII tracking)
        pii_paths = vfg.trace_taint(taint_label="PII")

        # Store in context
        self.ctx.value_flow_graph = vfg
        self.ctx.cross_lang_flows = cross_flows
        self.ctx.metadata["cross_lang_stats"] = {
            "total_nodes": len(vfg.nodes),
            "total_edges": len(vfg.edges),
            "boundaries": len(boundaries),
            "boundary_edges": boundary_count,
            "cross_service_flows": len(cross_flows),
            "pii_paths": len(pii_paths),
        }

        logger.info(f"Cross-language analysis complete: {len(vfg.nodes)} nodes, {len(cross_flows)} cross-service flows")

        return {
            "graph": vfg,
            "boundaries": boundaries,
            "cross_flows": cross_flows,
            "pii_paths": pii_paths,
            "stats": self.ctx.metadata["cross_lang_stats"],
        }

    def get_result(self) -> ReasoningResult:
        """
        최종 결과 생성

        Returns:
            ReasoningResult
        """
        logger.info("Generating reasoning result")

        # Summary
        summary = self._generate_summary()

        # Total risk
        total_risk = self._calculate_total_risk()

        # Total impact
        total_impact = self._calculate_total_impact(self.ctx.impact_reports)

        # Breaking changes
        breaking = [d.symbol_id for d in self.ctx.effect_diffs.values() if d.is_breaking]

        # Impacted symbols
        impacted = set()
        for report in self.ctx.impact_reports.values():
            impacted.update(n.symbol_id for n in report.impacted_nodes)

        # Recommended actions
        actions = self._generate_recommendations()

        result = ReasoningResult(
            summary=summary,
            total_risk=total_risk,
            total_impact=total_impact,
            breaking_changes=breaking,
            impacted_symbols=list(impacted),
            recommended_actions=actions,
            context=self.ctx,
        )

        logger.info(f"Result: risk={total_risk.value}, impact={total_impact.value}")
        return result

    def _generate_summary(self) -> str:
        """요약 생성"""
        parts = []

        # Changes
        total = self.ctx.change_summary.get("total_changes", 0)
        breaking = self.ctx.change_summary.get("breaking_count", 0)
        parts.append(f"{total} changes ({breaking} breaking)")

        # Impact
        total_impacted = sum(len(r.impacted_nodes) for r in self.ctx.impact_reports.values())
        parts.append(f"{total_impacted} symbols impacted")

        # Risk
        risk = self.ctx.change_summary.get("risk_level")
        if risk:
            parts.append(f"Risk: {risk}")

        return " | ".join(parts)

    def _calculate_total_risk(self) -> RiskLevel:
        """전체 risk 계산"""
        if not self.ctx.risk_reports:
            return RiskLevel.LOW  # RiskLevel.NONE이 없음

        # Max risk
        max_risk = max(r.risk_level for r in self.ctx.risk_reports.values())

        # Count breaking
        breaking_count = sum(1 for r in self.ctx.risk_reports.values() if r.is_breaking())

        # Upgrade if many breaking
        if breaking_count >= 3:
            if max_risk == RiskLevel.HIGH:
                return RiskLevel.BREAKING

        return max_risk

    def _calculate_total_impact(self, reports: dict[str, ImpactReport]) -> ImpactLevel:
        """전체 impact 계산"""
        if not reports:
            return ImpactLevel.NONE

        # Max impact
        max_impact = max(r.total_impact for r in reports.values())

        # Total impacted nodes
        total_nodes = sum(len(r.impacted_nodes) for r in reports.values())

        # Upgrade if many nodes
        if total_nodes >= 20:
            return ImpactLevel.CRITICAL

        if total_nodes >= 10:
            if max_impact == ImpactLevel.HIGH and ImpactLevel.CRITICAL in [ImpactLevel.CRITICAL]:
                return ImpactLevel.CRITICAL

        return max_impact

    def _generate_recommendations(self) -> list[str]:
        """권장 사항 생성"""
        actions = []

        # Breaking changes
        breaking = [d for d in self.ctx.effect_diffs.values() if d.is_breaking]
        if breaking:
            actions.append(f"Review {len(breaking)} breaking changes carefully")

        # High impact
        high_impact = [
            r for r in self.ctx.impact_reports.values() if r.total_impact in [ImpactLevel.HIGH, ImpactLevel.CRITICAL]
        ]
        if high_impact:
            actions.append(f"Test {len(high_impact)} high-impact areas")

        # Breaking risk
        breaking_risks = [r for r in self.ctx.risk_reports.values() if r.risk_level == RiskLevel.BREAKING]
        if breaking_risks:
            actions.append("Address breaking changes before deployment")

        # Global mutations
        global_mutations = [d for d in self.ctx.effect_diffs.values() if EffectType.GLOBAL_MUTATION in d.added]
        if global_mutations:
            actions.append(f"Refactor {len(global_mutations)} global mutations")

        if not actions:
            actions.append("Changes look safe to deploy")

        return actions

    # ==================== RFC-007: Rust Taint Analysis ====================

    def analyze_taint_fast(
        self,
        repo_id: str | None = None,
        snapshot_id: str | None = None,
        sources: list[str] | None = None,
        sinks: list[str] | None = None,
        reload: bool = False,
    ) -> dict[str, Any]:
        """
        Fast taint analysis using Rust engine (RFC-007).

        Performance:
        - Cold: 1-10ms (vs 50-200ms Memgraph Cypher)
        - Cache hit: 0.001-0.01ms (1000x faster)

        Args:
            repo_id: Repository ID (for filtering)
            snapshot_id: Snapshot ID (for filtering)
            sources: Source node IDs (if None, auto-detect from Memgraph)
            sinks: Sink node IDs (if None, auto-detect from Memgraph)
            reload: Force reload from Memgraph

        Returns:
            {
                "paths": [[node_id, ...], ...],
                "num_paths": int,
                "stats": {...},
                "performance": {"analysis_time_ms": float, ...}
            }
        """
        import time

        if not self.rust_engine or not self.memgraph_store:
            logger.warning("Rust engine not available. Use Python fallback.")
            return self._taint_analysis_fallback(sources or [], sinks or [])

        start_time = time.time()

        # 1. Load VFG from Memgraph (if needed)
        if reload or self.rust_engine.graph is None:
            load_start = time.time()
            load_stats = self.rust_engine.load_from_memgraph(self.memgraph_store, repo_id, snapshot_id)
            load_time = (time.time() - load_start) * 1000
            logger.info(f"VFG loaded: {load_stats} ({load_time:.2f}ms)")

        # 2. Auto-detect sources/sinks if not provided
        if sources is None or sinks is None:
            from ..infrastructure.engine.memgraph_extractor import MemgraphVFGExtractor

            extractor = MemgraphVFGExtractor(self.memgraph_store)
            auto_detected = extractor.extract_sources_and_sinks(repo_id, snapshot_id)

            sources = sources or auto_detected["sources"]
            sinks = sinks or auto_detected["sinks"]

            logger.info(f"Auto-detected: {len(sources)} sources, {len(sinks)} sinks")

        # 3. Fast taint analysis (Rust)
        analysis_start = time.time()
        paths = self.rust_engine.trace_taint(sources, sinks)
        analysis_time = (time.time() - analysis_start) * 1000

        # 4. Get stats
        stats = self.rust_engine.get_stats()

        total_time = (time.time() - start_time) * 1000

        logger.info(
            f"Taint analysis: {len(paths)} paths in {analysis_time:.2f}ms "
            f"(total: {total_time:.2f}ms, cache: {stats['cache_hit_rate']})"
        )

        return {
            "paths": paths,
            "num_paths": len(paths),
            "num_sources": len(sources),
            "num_sinks": len(sinks),
            "stats": stats,
            "performance": {
                "total_time_ms": total_time,
                "analysis_time_ms": analysis_time,
                "cache_hit_rate": stats["cache_hit_rate"],
            },
        }

    def invalidate_taint_cache(self, file_paths: list[str], repo_id: str, snapshot_id: str) -> dict[str, Any]:
        """
        Incremental cache invalidation for changed files.

        Args:
            file_paths: Changed file paths
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            Invalidation stats
        """
        if not self.rust_engine or not self.memgraph_store:
            return {"invalidated": 0, "error": "Rust engine not available"}

        from ..infrastructure.engine.memgraph_extractor import MemgraphVFGExtractor

        # 1. Get affected nodes from Memgraph
        extractor = MemgraphVFGExtractor(self.memgraph_store)
        affected_nodes = extractor.get_affected_nodes(file_paths, repo_id, snapshot_id)

        # 2. Invalidate cache
        num_invalidated = self.rust_engine.invalidate(affected_nodes)

        logger.info(
            f"Cache invalidated: {num_invalidated} entries for "
            f"{len(affected_nodes)} affected nodes ({len(file_paths)} files)"
        )

        return {
            "num_files": len(file_paths),
            "num_affected_nodes": len(affected_nodes),
            "num_invalidated": num_invalidated,
        }

    def _taint_analysis_fallback(self, sources: list[str], sinks: list[str]) -> dict[str, Any]:
        """
        Fallback to Python-based taint analysis.

        Used when Rust engine is not available.
        """
        logger.warning("Using slow Python fallback for taint analysis")

        # Use existing VFG if available
        if self.ctx.value_flow_graph:
            paths = self.ctx.value_flow_graph.trace_taint(
                source_id=sources[0] if sources else None, sink_id=sinks[0] if sinks else None
            )
            return {"paths": paths, "num_paths": len(paths), "performance": {"method": "python_fallback"}}

        return {"paths": [], "num_paths": 0, "error": "No VFG available"}
