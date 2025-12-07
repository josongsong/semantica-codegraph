"""
Incremental Builder Integration

Impact-based partial rebuild
"""

import copy
import logging
from dataclasses import dataclass
from typing import Any, Optional

from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument

from ..domain.impact_models import ImpactLevel, ImpactReport
from ..infrastructure.cache.rebuild_cache import RebuildCache
from ..infrastructure.impact.impact_analyzer import ImpactAnalyzer
from ..infrastructure.semantic_diff.effect_differ import EffectDiffer

logger = logging.getLogger(__name__)


@dataclass
class RebuildPlan:
    """
    재빌드 계획

    어떤 파일/심볼을 재분석할지 결정
    """

    changed_files: set[str]
    impacted_files: set[str]
    symbols_to_rebuild: set[str]
    estimated_cost: int  # Number of files to analyze
    strategy: str  # "full" | "partial" | "minimal"
    metadata: dict[str, Any]

    def total_files(self) -> int:
        """총 재분석 파일 수"""
        return len(self.changed_files | self.impacted_files)

    def is_minimal(self) -> bool:
        """Minimal rebuild인지"""
        return self.strategy == "minimal" and self.total_files() < 5

    def summary(self) -> str:
        """요약"""
        return (
            f"{self.strategy} rebuild: "
            f"{len(self.changed_files)} changed, "
            f"{len(self.impacted_files)} impacted, "
            f"{len(self.symbols_to_rebuild)} symbols"
        )


class IncrementalBuilder:
    """
    Impact 기반 증분 빌드

    변경된 파일만 분석하고, 영향받는 부분만 재빌드

    Example:
        builder = IncrementalBuilder(old_graph, new_graph)

        # 변경 분석
        changes = {'func1': (old_code, new_code)}
        builder.analyze_changes(changes)

        # 재빌드 계획
        plan = builder.create_rebuild_plan()

        # 실행
        updated_graph = builder.execute_rebuild(plan)
    """

    def __init__(
        self,
        old_graph: GraphDocument,
        new_graph: GraphDocument | None = None,
        program_slicer: Optional["ProgramSlicer"] = None,
        slicer_confidence_threshold: float = 0.5,
        cache: RebuildCache | None = None,
    ):
        """
        Initialize builder

        Args:
            old_graph: 이전 GraphDocument
            new_graph: 새 GraphDocument (optional)
            program_slicer: ProgramSlicer for impact analysis (optional)
            slicer_confidence_threshold: Minimum confidence for slicer results (default: 0.5)
            cache: Optional RebuildCache for caching results
        """
        self.old_graph = old_graph
        self.new_graph = new_graph or old_graph

        self.impact_analyzer = ImpactAnalyzer(old_graph, max_depth=3)
        self.effect_differ = EffectDiffer()
        self.program_slicer = program_slicer
        self.slicer_confidence_threshold = slicer_confidence_threshold
        self.cache = cache

        # State
        self.changed_symbols: set[str] = set()
        self.impacted_symbols: set[str] = set()
        self.impact_reports: dict[str, ImpactReport] = {}
        self.cached_changes: dict[str, tuple[str, str]] | None = None

        # Metrics
        self.slicer_failures: int = 0
        self.slicer_successes: int = 0

        logger.info(
            "IncrementalBuilder initialized: slicer=%s, threshold=%.2f, cache=%s",
            bool(program_slicer),
            slicer_confidence_threshold,
            bool(cache),
        )

    def analyze_changes(self, changes: dict[str, tuple[str, str]]) -> dict[str, ImpactReport]:
        """
        변경 분석 with ProgramSlicer

        Args:
            changes: {symbol_id: (old_code, new_code)}

        Returns:
            {symbol_id: ImpactReport}
        """
        logger.info(f"Analyzing {len(changes)} changes")

        # Store for caching
        self.cached_changes = changes

        # Effect analysis
        effect_diffs = self.effect_differ.batch_compare(changes)

        # Store changed symbols
        self.changed_symbols = set(changes.keys())

        # Impact analysis for breaking changes
        breaking = [d.symbol_id for d in effect_diffs if d.is_breaking]

        if breaking:
            logger.info(f"Analyzing impact for {len(breaking)} breaking changes")
            reports = self.impact_analyzer.batch_analyze(breaking, {d.symbol_id: d for d in effect_diffs})
            self.impact_reports.update(reports)

            # Collect impacted symbols
            for report in reports.values():
                self.impacted_symbols.update(n.symbol_id for n in report.impacted_nodes)

        # ProgramSlicer-based impact analysis (if available)
        if self.program_slicer:
            self._analyze_with_slicer(changes)

        logger.info(f"Found {len(self.impacted_symbols)} impacted symbols")
        return self.impact_reports

    def _analyze_with_slicer(self, changes: dict[str, tuple[str, str]]) -> None:
        """
        ProgramSlicer를 활용한 영향 분석

        변경된 심볼에서 forward slice를 수행하여
        영향받는 모든 코드 조각을 추출

        Args:
            changes: {symbol_id: (old_code, new_code)}
        """
        logger.info("Running ProgramSlicer-based impact analysis")

        for symbol_id, (_old_code, _new_code) in changes.items():
            try:
                # Get symbol location from graph
                node = self.old_graph.graph_nodes.get(symbol_id)
                if not node or not node.span:
                    continue

                # Run slice_for_impact
                slice_result = self.program_slicer.slice_for_impact(
                    source_location=symbol_id, file_path=node.path, line_number=node.span.start_line
                )

                # Extract impacted symbols from slice
                if slice_result.confidence > self.slicer_confidence_threshold:
                    for fragment in slice_result.code_fragments:
                        # Fragment에서 symbol 추출 (간단한 휴리스틱)
                        affected = self._extract_symbols_from_fragment(fragment)
                        self.impacted_symbols.update(affected)

                    self.slicer_successes += 1
                    logger.debug(
                        f"Slice for {symbol_id}: "
                        f"{len(slice_result.slice_nodes)} nodes, "
                        f"confidence={slice_result.confidence:.2f}"
                    )
            except Exception as e:
                self.slicer_failures += 1
                logger.warning(f"Slicer failed for {symbol_id}: {e.__class__.__name__}: {e}", exc_info=True)
                # Continue with graph-based analysis only
                continue

    def _extract_symbols_from_fragment(self, fragment: "CodeFragment") -> set[str]:
        """
        CodeFragment에서 심볼 ID 추출

        간단한 휴리스틱: fragment의 file_path + line range로 그래프 노드 매칭

        Args:
            fragment: CodeFragment

        Returns:
            Set of symbol IDs
        """
        symbols = set()

        # 같은 파일의 노드 중 line range가 겹치는 것만 추출
        for node_id, node in self.old_graph.graph_nodes.items():
            if node.path != fragment.file_path:
                continue

            # Node에 span이 있고, fragment의 line range와 겹치면 포함
            if node.span and (
                fragment.start_line <= node.span.start_line <= fragment.end_line
                or fragment.start_line <= node.span.end_line <= fragment.end_line
            ):
                symbols.add(node_id)

        return symbols

    def create_rebuild_plan(self, max_files: int | None = None) -> RebuildPlan:
        """
        재빌드 계획 생성

        Args:
            max_files: Maximum files to rebuild (fallback to full)

        Returns:
            RebuildPlan
        """
        logger.info("Creating rebuild plan")

        # Changed files
        changed_files = self._get_files_for_symbols(self.changed_symbols)

        # Impacted files
        impacted_files = self._get_files_for_symbols(self.impacted_symbols)

        # Total files
        total_files = changed_files | impacted_files

        # Decide strategy
        if max_files and len(total_files) > max_files:
            strategy = "full"
            logger.warning(f"Too many files ({len(total_files)} > {max_files}), falling back to full rebuild")
        elif len(total_files) <= 5:
            strategy = "minimal"
        elif len(total_files) <= 20:
            strategy = "partial"
        else:
            strategy = "full"

        # Symbols to rebuild
        if strategy == "full":
            symbols_to_rebuild = set(self.new_graph.graph_nodes.keys())
        else:
            symbols_to_rebuild = self.changed_symbols | self.impacted_symbols

        plan = RebuildPlan(
            changed_files=changed_files,
            impacted_files=impacted_files,
            symbols_to_rebuild=symbols_to_rebuild,
            estimated_cost=len(total_files),
            strategy=strategy,
            metadata={
                "changed_count": len(self.changed_symbols),
                "impacted_count": len(self.impacted_symbols),
                "breaking_count": sum(
                    1
                    for r in self.impact_reports.values()
                    if r.total_impact in [ImpactLevel.HIGH, ImpactLevel.CRITICAL]
                ),
            },
        )

        logger.info(f"Plan: {plan.summary()}")
        return plan

    def execute_rebuild(self, plan: RebuildPlan) -> GraphDocument:
        """
        재빌드 실행 (with caching)

        Args:
            plan: RebuildPlan

        Returns:
            Updated GraphDocument
        """
        # Check cache
        if self.cache and self.cached_changes:
            cached = self.cache.get(self.old_graph, self.cached_changes)
            if cached:
                logger.info("Cache HIT: using cached rebuild")
                return cached.updated_graph

        logger.info(f"Executing rebuild: {plan.strategy}")

        if plan.strategy == "full":
            # Full rebuild - return new graph as-is
            logger.info("Full rebuild - using new graph")
            updated_graph = self.new_graph
        else:
            # Partial rebuild - copy old + update changed/impacted
            logger.info(f"Partial rebuild - updating {len(plan.symbols_to_rebuild)} symbols")

            # IMPORTANT: Deep copy to avoid mutating old_graph
            updated_graph = copy.deepcopy(self.old_graph)

            # Update changed symbols
            for symbol_id in plan.symbols_to_rebuild:
                if symbol_id in self.new_graph.graph_nodes:
                    updated_graph.graph_nodes[symbol_id] = self.new_graph.graph_nodes[symbol_id]

            # Update edges: only those related to changed symbols
            affected_node_ids = plan.symbols_to_rebuild

            # Remove old edges related to changed symbols
            updated_graph.graph_edges = [
                edge
                for edge in updated_graph.graph_edges
                if edge.source_id not in affected_node_ids and edge.target_id not in affected_node_ids
            ]

            # Add new edges related to changed symbols
            for edge in self.new_graph.graph_edges:
                if edge.source_id in affected_node_ids or edge.target_id in affected_node_ids:
                    updated_graph.graph_edges.append(edge)

        # Cache result
        if self.cache and self.cached_changes:
            plan_meta = {
                "strategy": plan.strategy,
                "changed_files": list(plan.changed_files),
                "impacted_files": list(plan.impacted_files),
                "symbols_to_rebuild": len(plan.symbols_to_rebuild),
                "estimated_cost": plan.estimated_cost,
            }
            stats = self.get_statistics()

            self.cache.set(self.old_graph, self.cached_changes, updated_graph, plan_meta, stats)
            logger.info("Cached rebuild result")

        logger.info(f"Rebuild complete: {len(plan.symbols_to_rebuild)} symbols updated")
        return updated_graph

    def _get_files_for_symbols(self, symbol_ids: set[str]) -> set[str]:
        """Symbol IDs → file paths"""
        files = set()

        for symbol_id in symbol_ids:
            node = self.old_graph.get_node(symbol_id)
            if node:
                files.add(node.path)

        return files

    def get_statistics(self) -> dict[str, Any]:
        """빌드 통계 (with cache metrics)"""
        stats = {
            "changed_symbols": len(self.changed_symbols),
            "impacted_symbols": len(self.impacted_symbols),
            "total_impact_reports": len(self.impact_reports),
            "changed_files": len(self._get_files_for_symbols(self.changed_symbols)),
            "impacted_files": len(self._get_files_for_symbols(self.impacted_symbols)),
        }

        # Slicer metrics (if used)
        if self.program_slicer:
            total_slicer_ops = self.slicer_successes + self.slicer_failures
            stats.update(
                {
                    "slicer_successes": self.slicer_successes,
                    "slicer_failures": self.slicer_failures,
                    "slicer_success_rate": (self.slicer_successes / total_slicer_ops if total_slicer_ops > 0 else 0.0),
                }
            )

        # Cache metrics (if used)
        if self.cache:
            stats["cache"] = self.cache.get_metrics()

        return stats
