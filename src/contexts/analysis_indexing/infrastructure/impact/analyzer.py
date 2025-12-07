"""
Impact Analyzer

Analyzes code changes to determine impact level and rebuild scope.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from .models import (
    ChangeImpact,
    ChangeImpactLevel,
    ImpactAnalysisResult,
    RebuildStrategy,
)

logger = structlog.get_logger(__name__)


@dataclass
class ImpactAnalyzer:
    """
    Analyzes code changes to determine impact

    Strategy:
    1. Detect change type (signature, body, metadata)
    2. Determine impact level
    3. Find affected symbols
    4. Recommend rebuild strategy

    Example:
        # Signature change
        - def foo(a) → def foo(a, b)
        → Impact: SIGNATURE
        → Rebuild: foo + all callers

        # Body change
        - if x > 0: ... → if x >= 0: ...
        → Impact: CFG_DFG
        → Rebuild: foo's CFG/DFG only

        # Comment change
        - # old comment → # new comment
        → Impact: NONE
        → Rebuild: nothing
    """

    # IR docs for analysis
    _base_ir: dict[str, Any] = field(default_factory=dict)
    _new_ir: dict[str, Any] = field(default_factory=dict)

    # Call graph for finding callers
    _call_graph: Any | None = None

    async def analyze_changes(
        self,
        base_ir: dict[str, Any],
        new_ir: dict[str, Any],
        call_graph: Any | None = None,
    ) -> ImpactAnalysisResult:
        """
        Analyze changes between base and new IR

        Args:
            base_ir: Base IR (before changes)
            new_ir: New IR (after changes)
            call_graph: Optional call graph for finding dependencies

        Returns:
            ImpactAnalysisResult with all detected impacts
        """
        logger.info(
            "analyzing_impact",
            base_files=len(base_ir),
            new_files=len(new_ir),
        )

        self._base_ir = base_ir
        self._new_ir = new_ir
        self._call_graph = call_graph

        result = ImpactAnalysisResult()

        # Analyze each file
        all_files = set(base_ir.keys()) | set(new_ir.keys())

        for file_path in all_files:
            base_doc = base_ir.get(file_path)
            new_doc = new_ir.get(file_path)

            # File added
            if base_doc is None and new_doc is not None:
                impact = self._analyze_file_added(file_path, new_doc)
                if impact:
                    result.add_impact(impact)

            # File removed
            elif base_doc is not None and new_doc is None:
                impact = self._analyze_file_removed(file_path, base_doc)
                if impact:
                    result.add_impact(impact)

            # File modified
            else:
                file_impacts = self._analyze_file_modified(file_path, base_doc, new_doc)
                for impact in file_impacts:
                    result.add_impact(impact)

        # Build recommended strategy
        if result.impacts:
            result.strategy = self._build_strategy(result)

        logger.info(
            "impact_analysis_complete",
            total_impacts=len(result.impacts),
            max_level=result.get_max_impact_level().name,
        )

        return result

    def _analyze_file_added(
        self,
        file_path: str,
        new_doc: Any,
    ) -> ChangeImpact | None:
        """Analyze newly added file"""
        # New file - structural change
        return ChangeImpact(
            file_path=file_path,
            symbol_id=f"file:{file_path}",
            level=ChangeImpactLevel.STRUCTURAL,
            reason="File added",
            change_type="file_added",
        )

    def _analyze_file_removed(
        self,
        file_path: str,
        base_doc: Any,
    ) -> ChangeImpact | None:
        """Analyze removed file"""
        # File removed - structural change
        impact = ChangeImpact(
            file_path=file_path,
            symbol_id=f"file:{file_path}",
            level=ChangeImpactLevel.STRUCTURAL,
            reason="File removed",
            change_type="file_removed",
        )

        # All symbols in file need removal
        nodes = getattr(base_doc, "nodes", [])
        for node in nodes:
            node_id = getattr(node, "id", "")
            if node_id:
                impact.add_affected(node_id)

        return impact

    def _analyze_file_modified(
        self,
        file_path: str,
        base_doc: Any,
        new_doc: Any,
    ) -> list[ChangeImpact]:
        """Analyze modified file"""
        impacts = []

        # Get symbols from both versions
        base_nodes = {
            getattr(node, "id", ""): node for node in getattr(base_doc, "nodes", []) if getattr(node, "id", "")
        }

        new_nodes = {getattr(node, "id", ""): node for node in getattr(new_doc, "nodes", []) if getattr(node, "id", "")}

        # Symbol added
        for symbol_id in new_nodes.keys() - base_nodes.keys():
            impact = ChangeImpact(
                file_path=file_path,
                symbol_id=symbol_id,
                level=ChangeImpactLevel.STRUCTURAL,
                reason="Symbol added",
                change_type="symbol_added",
            )
            impacts.append(impact)

        # Symbol removed
        for symbol_id in base_nodes.keys() - new_nodes.keys():
            impact = ChangeImpact(
                file_path=file_path,
                symbol_id=symbol_id,
                level=ChangeImpactLevel.STRUCTURAL,
                reason="Symbol removed",
                change_type="symbol_removed",
            )
            # Find callers if call graph available
            if self._call_graph:
                callers = self._find_callers(symbol_id)
                for caller in callers:
                    impact.add_affected(caller)
                    impact.add_rebuild_target(caller)
            impacts.append(impact)

        # Symbol modified
        for symbol_id in base_nodes.keys() & new_nodes.keys():
            base_node = base_nodes[symbol_id]
            new_node = new_nodes[symbol_id]

            impact = self._analyze_symbol_change(file_path, symbol_id, base_node, new_node)
            if impact:
                impacts.append(impact)

        return impacts

    def _analyze_symbol_change(
        self,
        file_path: str,
        symbol_id: str,
        base_node: Any,
        new_node: Any,
    ) -> ChangeImpact | None:
        """
        Analyze change to a single symbol

        Determines impact level based on what changed:
        - Signature → SIGNATURE
        - Body logic → CFG_DFG
        - Local variable → LOCAL
        - Comment → NONE
        """
        # Get signatures
        base_sig = getattr(base_node, "signature", "")
        new_sig = getattr(new_node, "signature", "")

        # Signature changed
        if base_sig != new_sig:
            impact = ChangeImpact(
                file_path=file_path,
                symbol_id=symbol_id,
                level=ChangeImpactLevel.SIGNATURE,
                reason="Signature changed",
                change_type="signature_changed",
                old_value=base_sig,
                new_value=new_sig,
            )

            # Add symbol itself for rebuild
            impact.add_rebuild_target(symbol_id)

            # Find callers
            if self._call_graph:
                callers = self._find_callers(symbol_id)
                for caller in callers:
                    impact.add_affected(caller)
                    impact.add_rebuild_target(caller)

                logger.debug(
                    "signature_change_detected",
                    symbol=symbol_id,
                    callers=len(callers),
                )

            return impact

        # Check for body changes (simplified)
        # In real impl, would do AST diff
        base_location = getattr(base_node, "location", None)
        new_location = getattr(new_node, "location", None)

        if base_location and new_location:
            base_lines = getattr(base_location, "end_line", 0) - getattr(base_location, "start_line", 0)
            new_lines = getattr(new_location, "end_line", 0) - getattr(new_location, "start_line", 0)

            # Line count changed - likely body change
            if base_lines != new_lines:
                impact = ChangeImpact(
                    file_path=file_path,
                    symbol_id=symbol_id,
                    level=ChangeImpactLevel.CFG_DFG,
                    reason=f"Body changed ({base_lines} → {new_lines} lines)",
                    change_type="body_changed",
                )
                impact.add_rebuild_target(symbol_id)
                return impact

        # If we reach here, assume minimal change (or same)
        # Could be comment, whitespace, etc.
        return None

    def _find_callers(self, symbol_id: str) -> set[str]:
        """Find all callers of a symbol"""
        callers = set()

        if not self._call_graph:
            return callers

        # Check if call_graph has edges attribute
        if hasattr(self._call_graph, "edges"):
            edges = self._call_graph.edges
            for (caller, callee), _ in edges.items():
                if callee == symbol_id:
                    callers.add(caller)

        return callers

    def _build_strategy(self, result: ImpactAnalysisResult) -> RebuildStrategy:
        """
        Build rebuild strategy from analysis result

        Uses the maximum impact level to determine strategy
        """
        max_level = result.get_max_impact_level()

        # Create a representative impact for strategy
        representative_impact = ChangeImpact(
            file_path="",
            symbol_id="",
            level=max_level,
        )
        representative_impact.needs_rebuild = result.get_total_rebuild_needed()

        # Build strategy
        strategy = RebuildStrategy()
        strategy = strategy.from_impact(representative_impact)

        logger.info(
            "rebuild_strategy_created",
            rebuild_symbols=len(strategy.rebuild_symbols),
            max_depth=strategy.max_depth,
            components=[c for c in ["CFG", "DFG", "CG", "TG"] if getattr(strategy, f"rebuild_{c.lower()}", False)],
        )

        return strategy

    def quick_check(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
    ) -> ChangeImpactLevel:
        """
        Quick heuristic check for impact level

        Uses simple heuristics without full IR:
        - Same content → NONE
        - Only whitespace/comments → NONE
        - Line count change → CFG_DFG
        - Signature patterns → SIGNATURE
        """
        # Same content
        if old_content == new_content:
            return ChangeImpactLevel.NONE

        # Remove whitespace and compare
        old_stripped = "".join(old_content.split())
        new_stripped = "".join(new_content.split())

        if old_stripped == new_stripped:
            return ChangeImpactLevel.NONE  # Only whitespace

        # Line count
        old_lines = old_content.count("\n")
        new_lines = new_content.count("\n")

        line_diff = abs(old_lines - new_lines)

        if line_diff == 0:
            return ChangeImpactLevel.LOCAL  # Same line count, probably small change
        elif line_diff < 5:
            return ChangeImpactLevel.CFG_DFG  # Minor change
        else:
            return ChangeImpactLevel.SIGNATURE  # Significant change

    def __repr__(self) -> str:
        return f"ImpactAnalyzer(base_files={len(self._base_ir)}, new_files={len(self._new_ir)})"
