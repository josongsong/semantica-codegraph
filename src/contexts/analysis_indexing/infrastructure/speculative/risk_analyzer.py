"""
Risk Analyzer

Analyzes risk of applying speculative patches.
"""

from dataclasses import dataclass

import structlog

from .models import (
    GraphDelta,
    PatchType,
    RiskLevel,
    SimulationContext,
    SpeculativePatch,
)

logger = structlog.get_logger(__name__)


@dataclass
class RiskAnalyzer:
    """
    Analyzes risk of patch application

    Factors:
    1. Patch type (rename vs delete)
    2. Number of affected symbols
    3. Breaking changes
    4. Test coverage

    Example:
        analyzer = RiskAnalyzer(context)
        risk_level, reasons = analyzer.analyze_risk(patch, delta)

        if risk_level >= RiskLevel.HIGH:
            print("High risk! Reasons:")
            for reason in reasons:
                print(f"  - {reason}")
    """

    context: SimulationContext

    def analyze_risk(
        self,
        patch: SpeculativePatch,
        delta: GraphDelta,
    ) -> tuple[RiskLevel, list[str]]:
        """
        Analyze risk of applying patch

        Args:
            patch: SpeculativePatch to analyze
            delta: GraphDelta from simulation

        Returns:
            (RiskLevel, list of risk reasons)
        """
        logger.info(
            "analyzing_risk",
            patch_type=patch.patch_type.value,
            delta_size=delta.size(),
        )

        risk_reasons = []
        risk_score = 0

        # Factor 1: Patch type risk
        type_risk, type_reasons = self._assess_patch_type_risk(patch)
        risk_score += type_risk
        risk_reasons.extend(type_reasons)

        # Factor 2: Graph impact
        impact_risk, impact_reasons = self._assess_impact_risk(delta)
        risk_score += impact_risk
        risk_reasons.extend(impact_reasons)

        # Factor 3: Breaking changes
        breaking_risk, breaking_reasons = self._assess_breaking_changes(patch, delta)
        risk_score += breaking_risk
        risk_reasons.extend(breaking_reasons)

        # Factor 4: Affected symbols
        affected_risk, affected_reasons = self._assess_affected_symbols(delta)
        risk_score += affected_risk
        risk_reasons.extend(affected_reasons)

        # Map score to risk level
        risk_level = self._score_to_level(risk_score)

        logger.info(
            "risk_analysis_complete",
            risk_level=risk_level.name,
            risk_score=risk_score,
            num_reasons=len(risk_reasons),
        )

        return risk_level, risk_reasons

    def _assess_patch_type_risk(
        self,
        patch: SpeculativePatch,
    ) -> tuple[int, list[str]]:
        """Assess risk based on patch type"""
        reasons = []
        score = 0

        if patch.patch_type == PatchType.DELETE:
            score += 30
            reasons.append("DELETE patch - high risk of breaking dependencies")

        elif patch.patch_type == PatchType.CHANGE_SIGNATURE:
            score += 25
            reasons.append("SIGNATURE change - may break callers")

        elif patch.patch_type == PatchType.RENAME:
            score += 15
            reasons.append("RENAME - requires updating all references")

        elif patch.patch_type == PatchType.CODE_MOVE:
            score += 10
            reasons.append("CODE_MOVE - may break imports")

        elif patch.patch_type in (PatchType.ADD_FIELD, PatchType.ADD_METHOD):
            score += 5
            reasons.append("ADD operation - generally safe")

        else:  # MODIFY, REFACTOR
            score += 10
            reasons.append("MODIFY - impact depends on changes")

        return score, reasons

    def _assess_impact_risk(
        self,
        delta: GraphDelta,
    ) -> tuple[int, list[str]]:
        """Assess risk based on graph impact"""
        reasons = []
        score = 0

        # Nodes removed (high risk)
        if delta.nodes_removed:
            score += len(delta.nodes_removed) * 10
            reasons.append(f"{len(delta.nodes_removed)} nodes will be removed")

        # Nodes modified (medium risk)
        if delta.nodes_modified:
            score += len(delta.nodes_modified) * 3
            reasons.append(f"{len(delta.nodes_modified)} nodes will be modified")

        # Edges changed (low-medium risk)
        edges_changed = len(delta.edges_added) + len(delta.edges_removed)
        if edges_changed > 0:
            score += edges_changed * 2
            reasons.append(f"{edges_changed} edges will change")

        # Large changes (cumulative risk)
        if delta.size() > 20:
            score += 15
            reasons.append(f"Large change: {delta.size()} total modifications")

        return score, reasons

    def _assess_breaking_changes(
        self,
        patch: SpeculativePatch,
        delta: GraphDelta,
    ) -> tuple[int, list[str]]:
        """Assess risk from potential breaking changes"""
        reasons = []
        score = 0

        if patch.is_breaking_change():
            score += 20
            reasons.append(f"Patch type {patch.patch_type.value} is likely breaking")

        # Removing nodes that have callers
        if delta.nodes_removed:
            for node in delta.nodes_removed:
                callers = self._find_callers(node)
                if callers:
                    score += len(callers) * 5
                    reasons.append(f"Removing {node} will break {len(callers)} caller(s)")

        return score, reasons

    def _assess_affected_symbols(
        self,
        delta: GraphDelta,
    ) -> tuple[int, list[str]]:
        """Assess risk based on affected symbols"""
        reasons = []
        score = 0

        affected_count = len(delta.nodes_added) + len(delta.nodes_removed) + len(delta.nodes_modified)

        if affected_count > 10:
            score += 10
            reasons.append(f"Many symbols affected: {affected_count}")
        elif affected_count > 5:
            score += 5
            reasons.append(f"Multiple symbols affected: {affected_count}")

        return score, reasons

    def _score_to_level(self, score: int) -> RiskLevel:
        """Convert risk score to risk level"""
        if score >= 50:
            return RiskLevel.CRITICAL
        elif score >= 35:
            return RiskLevel.HIGH
        elif score >= 20:
            return RiskLevel.MEDIUM
        elif score >= 10:
            return RiskLevel.LOW
        else:
            return RiskLevel.SAFE

    def _find_callers(self, symbol: str) -> set[str]:
        """Find all callers of a symbol"""
        callers = set()

        if self.context.call_graph and hasattr(self.context.call_graph, "edges"):
            edges = self.context.call_graph.edges
            for (caller, callee), _ in edges.items():
                if callee == symbol:
                    callers.add(caller)

        return callers

    def generate_recommendations(
        self,
        patch: SpeculativePatch,
        delta: GraphDelta,
        risk_level: RiskLevel,
    ) -> list[str]:
        """
        Generate recommendations for patch application
        """
        recommendations = []

        if risk_level >= RiskLevel.HIGH:
            recommendations.append("⚠️ High risk - review carefully before applying")
            recommendations.append("📋 Run full test suite after applying")
            recommendations.append("🔄 Consider smaller incremental changes")

        if delta.nodes_removed:
            recommendations.append(f"🔍 Check {len(delta.nodes_removed)} symbols to be removed")

        if patch.patch_type == PatchType.RENAME:
            recommendations.append("✏️ Verify all references are updated")
            recommendations.append("🔤 Check string literals for old name")

        if patch.patch_type == PatchType.CHANGE_SIGNATURE:
            recommendations.append("📞 Update all call sites")
            recommendations.append("📝 Update documentation")

        if risk_level == RiskLevel.SAFE:
            recommendations.append("✅ Low risk - safe to apply")

        return recommendations

    def __repr__(self) -> str:
        return f"RiskAnalyzer(context={self.context})"
