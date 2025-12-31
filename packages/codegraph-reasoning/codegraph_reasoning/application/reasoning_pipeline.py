"""
Reasoning Pipeline - RFC-06 통합 파이프라인

Effect → Impact → Slice → Speculative 전체 흐름

Architecture: Hexagonal (Port/Adapter pattern)
- Application layer orchestrates domain logic
- Uses Ports for all infrastructure dependencies
- All dependencies are injected via adapters

Refactored: RFC-007 compliant - no direct Infrastructure imports
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument

if TYPE_CHECKING:
    from ..adapters.simulator_adapter import SimulatorAdapter

from ..domain.effect_models import EffectDiff, EffectType
from ..domain.impact_models import ImpactLevel, ImpactReport
from ..domain.speculative_models import RiskLevel, RiskReport, SpeculativePatch
from ..ports import (
    EffectAnalyzerPort,
    ImpactAnalyzerPort,
    TaintEnginePort,
    ValueFlowBuilderPort,
    VFGExtractorPort,
)
from .incremental_builder import ImpactAnalysisPlanner

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

    def __init__(
        self,
        graph: GraphDocument,
        workspace_root: str | None = None,
        memgraph_store: Any | None = None,
        # DI parameters (optional - uses factory methods if not provided)
        taint_engine: TaintEnginePort | None = None,
        vfg_extractor: VFGExtractorPort | None = None,
        value_flow_builder: ValueFlowBuilderPort | None = None,
    ):
        """
        Initialize pipeline with dependency injection

        Args:
            graph: GraphDocument
            workspace_root: Project root (for cross-language analysis)
            memgraph_store: Optional MemgraphGraphStore for Rust engine
            taint_engine: Optional TaintEnginePort (DI)
            vfg_extractor: Optional VFGExtractorPort (DI)
            value_flow_builder: Optional ValueFlowBuilderPort (DI)
        """
        self.ctx = ReasoningContext(graph=graph)

        # Port-based components via Adapters (DI pattern)
        from ..adapters import (
            EffectAnalyzerAdapter,
            ImpactAnalyzerAdapter,
            RiskAnalyzerAdapter,
            SimulatorAdapter,
            SlicerAdapter,
        )

        self.effect_differ: EffectAnalyzerPort = EffectAnalyzerAdapter()
        self.impact_analyzer: ImpactAnalyzerPort = ImpactAnalyzerAdapter(graph, max_depth=5)
        self.slicer = SlicerAdapter(graph)
        self.risk_analyzer = RiskAnalyzerAdapter()
        self._simulator: SimulatorAdapter | None = None  # Lazy init
        self.impact_planner: ImpactAnalysisPlanner | None = None

        # Store graph for simulator lazy init
        self._graph = graph

        # Store memgraph_store for factory methods
        self.memgraph_store = memgraph_store

        # RFC-007: Cross-language analysis (DI or factory)
        self.value_flow_builder: ValueFlowBuilderPort | None = value_flow_builder

        # RFC-028: Cost Analyzer (DI, optional)
        self.cost_analyzer = None  # Lazy init when needed

    def analyze_performance(self, function_fqn: str, request_id: str = "default") -> dict:
        """
        Analyze function performance cost (RFC-028 Integration).

        SOLID:
        - S: ReasoningPipeline이 cost_analyzer 사용 (delegation)
        - D: CostAnalyzer abstraction에 의존

        Args:
            function_fqn: Function FQN
            request_id: Request ID

        Returns:
            CostResult as dict

        Raises:
            ValueError: If function not found in IR
        """
        if not self._graph or not hasattr(self._graph, "ir_doc"):
            raise ValueError("ReasoningPipeline requires graph with ir_doc")

        from codegraph_engine.code_foundation.infrastructure.analyzers.cost import (
            CostAnalyzer,
        )

        if not hasattr(self, "_cost_analyzer"):
            self._cost_analyzer = CostAnalyzer()

        ir_doc = self._graph.ir_doc

        # Analyze (RFC-028)
        cost_result = self._cost_analyzer.analyze_function(ir_doc, function_fqn, request_id)

        return cost_result.to_dict()

    def analyze_performance_regression(self, changes: dict[str, tuple[str, str]], request_id: str = "default") -> dict:
        """
        Analyze performance regression (before/after).

        RFC-028 Differential Cost Integration.

        Args:
            changes: {function_fqn: (before_ir, after_ir)}
            request_id: Request ID

        Returns:
            Performance regression report
        """
        regressions = []

        for func_fqn, (before_snapshot, after_snapshot) in changes.items():
            # TODO: Load before/after IR Documents
            # TODO: Compare CostResult
            # For now: NotImplementedError
            raise NotImplementedError(
                "Performance regression analysis requires IR Document loading. "
                "Need: load_ir(repo_id, before_snapshot) and load_ir(repo_id, after_snapshot)"
            )

        return {"regressions": regressions}

        """
        Architecture Principle (CRITICAL):

        IRDocument = Source of Truth (ephemeral, indexing 단계에서 생성)
        GraphDocument = Derived Index/View (persistent, 검색용)

        변환 방향: IR → Graph (단방향!)
        금지: Graph → IR "재구성" (정보 손실, 비용 높음)

        Cost 분석은 IRDocument 필요:
        - analyze_cost(ir_doc, functions) ← ir_doc 명시적으로 받음
        - Caller가 IRDocument 제공 (IRStage, API 등)
        """
        if self.value_flow_builder is None and workspace_root:
            self.value_flow_builder = self._create_value_flow_builder(workspace_root)

        # RFC-007: Rust taint engine (DI or factory)
        self.taint_engine: TaintEnginePort | None = taint_engine
        if self.taint_engine is None and memgraph_store:
            self.taint_engine = self._create_taint_engine()

        # RFC-007: VFG Extractor (DI or factory)
        self.vfg_extractor: VFGExtractorPort | None = vfg_extractor
        if self.vfg_extractor is None and memgraph_store:
            self.vfg_extractor = self._create_vfg_extractor(memgraph_store)

        logger.info("ReasoningPipeline initialized (RFC-007 compliant)")

    # ==================== Factory Methods (DIP-compliant) ====================

    @staticmethod
    def _create_value_flow_builder(workspace_root: str) -> ValueFlowBuilderPort | None:
        """Factory method for ValueFlowBuilder (DIP-compliant)"""
        try:
            from ..adapters import ValueFlowBuilderAdapter

            builder = ValueFlowBuilderAdapter(workspace_root)
            logger.info("Cross-language analysis enabled")
            return builder
        except ImportError as e:
            logger.warning(f"Cross-language analysis disabled: {e}")
            return None

    @staticmethod
    def _create_taint_engine() -> TaintEnginePort | None:
        """Factory method for TaintEngine (DIP-compliant)"""
        try:
            from ..adapters import TaintEngineAdapter

            engine = TaintEngineAdapter()
            logger.info("Rust taint engine enabled (RFC-007)")
            return engine
        except ImportError as e:
            logger.warning(f"Rust taint engine disabled: {e}")
            return None

    @staticmethod
    def _create_vfg_extractor(memgraph_store: Any) -> VFGExtractorPort | None:
        """Factory method for VFGExtractor (DIP-compliant)"""
        try:
            from ..adapters import VFGExtractorAdapter

            extractor = VFGExtractorAdapter(memgraph_store)
            logger.info("VFG extractor enabled (RFC-007)")
            return extractor
        except ImportError as e:
            logger.warning(f"VFG extractor disabled: {e}")
            return None

    @property
    def simulator(self) -> "SimulatorAdapter":
        """Lazy-initialized simulator"""
        if self._simulator is None:
            from ..adapters import SimulatorAdapter

            self._simulator = SimulatorAdapter(self._graph)
        return self._simulator

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

        # Initialize planner
        self.impact_planner = ImpactAnalysisPlanner(
            old_graph=self.ctx.graph, new_graph=new_graph, program_slicer=self.slicer
        )

        # Analyze changes
        impact_reports = self.impact_planner.analyze_changes(changes)
        logger.info(f"Found {len(impact_reports)} breaking changes")

        # Create rebuild plan
        plan = self.impact_planner.create_rebuild_plan()
        logger.info(f"Rebuild plan: {plan.summary()}")

        # Execute rebuild
        updated_graph = self.impact_planner.execute_rebuild(plan)

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
        stats = self.impact_planner.get_statistics()
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

        # Simulate using adapter (lazy-initialized)
        delta_graph = self.simulator.simulate_patch(patch)

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

    def analyze_cost(self, ir_doc, functions: list[str]) -> dict[str, Any]:
        """
        Cost 분석 (RFC-028 Point 2)

        Target: PR/Audit 모드 (2-5초 허용)

        Args:
            ir_doc: IRDocument (must be provided, not in Graph!)
            functions: Function FQNs to analyze

        Returns:
            Map of function_fqn → CostResult

        Raises:
            ValueError: If ir_doc invalid
            RuntimeError: If cost_analyzer initialization fails

        Note:
            IRDocument는 GraphDocument에 포함되지 않음.
            Caller가 IRDocument를 제공해야 함.
            (IRStage에서 생성 후 전달)
        """
        if not ir_doc:
            raise ValueError("IRDocument is required for cost analysis")

        if not self.cost_analyzer:
            # Lazy initialization
            try:
                from codegraph_engine.code_foundation.infrastructure.analyzers.cost import CostAnalyzer

                self.cost_analyzer = CostAnalyzer()
                logger.info("cost_analyzer lazy initialized")
            except Exception as e:
                raise RuntimeError(f"Failed to initialize CostAnalyzer: {e}") from e

        # Analyze each function
        results = {}
        for func_fqn in functions:
            try:
                result = self.cost_analyzer.analyze_function(ir_doc, func_fqn, request_id=self.ctx.graph.snapshot_id)
                results[func_fqn] = result
            except Exception as e:
                logger.warning(f"Cost analysis failed for {func_fqn}: {e}")
                continue

        return results

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

        # Impact escalation thresholds
        CRITICAL_NODE_THRESHOLD = 20
        HIGH_NODE_THRESHOLD = 10

        # Upgrade if many nodes
        if total_nodes >= CRITICAL_NODE_THRESHOLD:
            return ImpactLevel.CRITICAL

        # Escalate HIGH to CRITICAL when significant spread
        if total_nodes >= HIGH_NODE_THRESHOLD and max_impact == ImpactLevel.HIGH:
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

        Uses Port/Adapter pattern - no direct Infrastructure imports.

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

        if not self.taint_engine or not self.vfg_extractor:
            logger.warning("Taint engine or VFG extractor not available. Use Python fallback.")
            return self._taint_analysis_fallback(sources or [], sinks or [])

        start_time = time.time()

        # 1. Load VFG from Memgraph via Port (if needed)
        if reload:
            load_start = time.time()
            vfg_data = self.vfg_extractor.extract_vfg(repo_id, snapshot_id)
            load_stats = self.taint_engine.load_from_data(vfg_data)
            load_time = (time.time() - load_start) * 1000
            logger.info(f"VFG loaded: {load_stats} ({load_time:.2f}ms)")

        # 2. Auto-detect sources/sinks via Port (if not provided)
        if sources is None or sinks is None:
            auto_detected = self.vfg_extractor.extract_sources_and_sinks(repo_id, snapshot_id)

            sources = sources or auto_detected["sources"]
            sinks = sinks or auto_detected["sinks"]

            logger.info(f"Auto-detected: {len(sources)} sources, {len(sinks)} sinks")

        # 3. Fast taint analysis via Port (Rust)
        analysis_start = time.time()
        paths = self.taint_engine.trace_taint(sources, sinks)
        analysis_time = (time.time() - analysis_start) * 1000

        # 4. Get stats via Port
        stats = self.taint_engine.get_stats()

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

        Uses Port/Adapter pattern - no direct Infrastructure imports.

        Args:
            file_paths: Changed file paths
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            Invalidation stats
        """
        if not self.taint_engine or not self.vfg_extractor:
            return {"invalidated": 0, "error": "Taint engine or VFG extractor not available"}

        # 1. Get affected nodes via Port
        affected_nodes = self.vfg_extractor.get_affected_nodes(file_paths, repo_id, snapshot_id)

        # 2. Invalidate cache via Port
        num_invalidated = self.taint_engine.invalidate(affected_nodes)

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
