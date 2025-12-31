"""
RiskAnalyzer - Breaking Change Detection & Risk Scoring

패치 위험도 분석 및 Breaking change 감지
"""

import logging
import time
from typing import Any

from ...domain.speculative_models import (
    PatchType,
    RiskLevel,
    RiskReport,
    SpeculativePatch,
)
from .delta_graph import DeltaGraph
from .exceptions import RiskAnalysisError

logger = logging.getLogger(__name__)


# Risk analysis constants
MAX_PROPAGATION_DEPTH = 10  # Maximum BFS depth for affected symbols
RISK_SCORE_BASE_NORMALIZER = 100.0  # Normalize affected symbols count
RISK_SCORE_BASE_MAX = 0.7  # Maximum base score contribution
RISK_SCORE_BREAKING_PENALTY = 0.15  # Penalty per breaking change
RISK_SCORE_BREAKING_MAX = 0.3  # Maximum breaking penalty
RISK_SCORE_CONFIDENCE_WEIGHT = 0.1  # Weight for confidence penalty

# Risk level thresholds
RISK_THRESHOLD_SAFE = 0.2
RISK_THRESHOLD_LOW = 0.4
RISK_THRESHOLD_HIGH = 0.7


class RiskAnalyzer:
    """
    패치 위험도 분석

    - Breaking changes 감지
    - 영향받는 코드 범위 계산
    - 위험도 점수 산출

    Example:
        analyzer = RiskAnalyzer()
        risk = analyzer.analyze_risk(patch, delta_graph, base_graph)

        if risk.is_safe():
            apply_patch()
        else:
            print(f"Warning: {risk.recommendation}")
    """

    def __init__(self, semantic_differ: Any | None = None):
        """
        Initialize RiskAnalyzer

        Args:
            semantic_differ: Optional semantic diff engine
        """
        self.semantic_differ = semantic_differ
        logger.info("RiskAnalyzer initialized")

    def analyze_risk(self, patch: SpeculativePatch, delta_graph: DeltaGraph, base_graph: Any) -> RiskReport:
        """
        패치 위험도 분석

        Args:
            patch: Speculative patch
            delta_graph: Simulated delta graph
            base_graph: Base graph

        Returns:
            RiskReport

        Raises:
            RiskAnalysisError: Analysis failed
        """
        start = time.perf_counter()

        try:
            # 1. 영향받는 symbols 계산
            affected_symbols = self._compute_affected_symbols(patch, delta_graph, base_graph)

            # 2. Breaking changes 감지
            breaking_changes = self._detect_breaking_changes(patch, delta_graph, base_graph)

            # 3. 위험도 점수 계산
            risk_score = self._calculate_risk_score(affected_symbols, breaking_changes, patch)

            # 4. 위험도 레벨 결정
            risk_level = self._determine_risk_level(risk_score, breaking_changes)

            # 5. 추천 생성
            recommendation = self._generate_recommendation(risk_level, breaking_changes)

            # 6. 영향받는 파일 계산
            affected_files = self._compute_affected_files(affected_symbols, base_graph)

            elapsed_ms = (time.perf_counter() - start) * 1000

            logger.info(
                f"Risk analysis complete: {patch.patch_id}, "
                f"level={risk_level.value}, score={risk_score:.2f}, "
                f"affected={len(affected_symbols)}, time={elapsed_ms:.2f}ms"
            )

            return RiskReport(
                patch_id=patch.patch_id,
                risk_level=risk_level,
                risk_score=risk_score,
                affected_symbols=affected_symbols,
                affected_files=affected_files,
                breaking_changes=breaking_changes,
                recommendation=recommendation,
                safe_to_apply=risk_level in [RiskLevel.SAFE, RiskLevel.LOW],
                analysis_time_ms=elapsed_ms,
            )

        except Exception as e:
            logger.error(f"Risk analysis failed for {patch.patch_id}: {e}")
            raise RiskAnalysisError(f"Analysis failed: {e}") from e

    def _compute_affected_symbols(self, patch: SpeculativePatch, delta_graph: DeltaGraph, base_graph: Any) -> set[str]:
        """
        영향받는 symbols 계산

        1. Direct: patch가 직접 수정
        2. Transitive: call graph 역방향 추적
        """
        affected = {patch.target_symbol}

        # Transitive dependencies (call graph 역방향)
        # BFS
        from collections import deque

        worklist = deque([patch.target_symbol])
        visited = set()

        depth_map = {patch.target_symbol: 0}

        while worklist:
            symbol = worklist.popleft()
            current_depth = depth_map.get(symbol, 0)

            if symbol in visited or current_depth >= MAX_PROPAGATION_DEPTH:
                continue

            visited.add(symbol)

            # Get callers (mock implementation)
            callers = self._get_callers(symbol, base_graph)
            for caller in callers:
                if caller not in affected:
                    affected.add(caller)
                    worklist.append(caller)
                    depth_map[caller] = current_depth + 1

        logger.debug(f"Affected symbols: {len(affected)}")
        return affected

    def _detect_breaking_changes(self, patch: SpeculativePatch, delta_graph: DeltaGraph, base_graph: Any) -> list[str]:
        """
        Breaking changes 감지

        예:
        - Parameter 제거
        - Return type 변경
        - Function 삭제
        """
        breaking_changes = []

        # REMOVE_PARAMETER
        if patch.patch_type == PatchType.REMOVE_PARAMETER:
            breaking_changes.append(f"Removed parameter from {patch.target_symbol}")

        # DELETE_FUNCTION
        elif patch.patch_type == PatchType.DELETE_FUNCTION:
            callers = self._get_callers(patch.target_symbol, base_graph)
            if callers:
                breaking_changes.append(f"Deleted function {patch.target_symbol} with {len(callers)} caller(s)")

        # CHANGE_RETURN_TYPE
        elif patch.patch_type == PatchType.CHANGE_RETURN_TYPE:
            # Check if return type is incompatible
            base_node = self._get_base_node(patch.target_symbol, base_graph)
            if base_node:
                old_type = base_node.get("return_type", "Any")
                new_type = patch.return_type
                if old_type != new_type and old_type != "Any":
                    breaking_changes.append(f"Changed return type of {patch.target_symbol}: {old_type} → {new_type}")

        # RENAME_SYMBOL
        elif patch.patch_type == PatchType.RENAME_SYMBOL:
            callers = self._get_callers(patch.target_symbol, base_graph)
            if callers:
                breaking_changes.append(f"Renamed {patch.target_symbol} with {len(callers)} caller(s)")

        logger.debug(f"Breaking changes: {len(breaking_changes)}")
        return breaking_changes

    def _calculate_risk_score(
        self, affected_symbols: set[str], breaking_changes: list[str], patch: SpeculativePatch
    ) -> float:
        """
        위험도 점수 계산

        Returns:
            0.0 (safe) - 1.0 (very risky)
        """
        # Base: affected symbols (normalized)
        base_score = min(len(affected_symbols) / RISK_SCORE_BASE_NORMALIZER, RISK_SCORE_BASE_MAX)

        # Penalty: breaking changes
        breaking_penalty = min(len(breaking_changes) * RISK_SCORE_BREAKING_PENALTY, RISK_SCORE_BREAKING_MAX)

        # Penalty: patch confidence (low confidence = higher risk)
        confidence_penalty = (1.0 - patch.confidence) * RISK_SCORE_CONFIDENCE_WEIGHT

        total = base_score + breaking_penalty + confidence_penalty

        return min(total, 1.0)

    def _determine_risk_level(self, risk_score: float, breaking_changes: list[str]) -> RiskLevel:
        """위험도 레벨 결정"""
        if breaking_changes:
            return RiskLevel.BREAKING

        if risk_score < RISK_THRESHOLD_SAFE:
            return RiskLevel.SAFE
        elif risk_score < RISK_THRESHOLD_LOW:
            return RiskLevel.LOW
        elif risk_score < RISK_THRESHOLD_HIGH:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.HIGH

    def _generate_recommendation(self, risk_level: RiskLevel, breaking_changes: list[str]) -> str:
        """추천 메시지 생성"""
        if risk_level == RiskLevel.SAFE:
            return "✅ Safe to apply"

        elif risk_level == RiskLevel.LOW:
            return "⚠️  Review affected files before applying"

        elif risk_level == RiskLevel.MEDIUM:
            return "⚠️  Carefully review and test before applying"

        elif risk_level == RiskLevel.HIGH:
            return "🚨 High risk - thorough testing required"

        else:  # BREAKING
            msg = "🚨 BREAKING CHANGE - update all callers first"
            if breaking_changes:
                msg += f": {', '.join(breaking_changes[:2])}"
            return msg

    def _compute_affected_files(self, affected_symbols: set[str], base_graph: Any) -> set[str]:
        """영향받는 파일 목록"""
        files = set()

        for symbol in affected_symbols:
            node = self._get_base_node(symbol, base_graph)
            if node and "file" in node:
                files.add(node["file"])

        return files

    def _get_callers(self, symbol: str, base_graph: Any) -> list[str]:
        """
        Symbol을 호출하는 caller 목록

        실제 GraphDocument 또는 dict 지원
        """
        # GraphDocument (실제 Semantica Graph)
        from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument

        if isinstance(base_graph, GraphDocument):
            from .graph_adapter import GraphDocumentAdapter

            return GraphDocumentAdapter.get_callers(base_graph, symbol)

        # Dict (DeltaGraph 변환된 형식)
        if isinstance(base_graph, dict) and "edges" in base_graph:
            callers = []
            for node_id, edges in base_graph.get("edges", {}).items():
                for edge in edges:
                    if edge.get("target") == symbol and edge.get("kind") == "CALLS":
                        callers.append(node_id)
            return callers

        # Fallback
        if hasattr(base_graph, "get_callers"):
            try:
                return base_graph.get_callers(symbol)
            except (KeyError, AttributeError, TypeError):
                return []

        return []

    def _get_base_node(self, symbol: str, base_graph: Any) -> dict | None:
        """Base graph에서 노드 조회"""
        # GraphDocument (실제 Semantica Graph)
        from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument

        if isinstance(base_graph, GraphDocument):
            node = base_graph.graph_nodes.get(symbol)
            if node:
                return {
                    "id": node.id,
                    "name": node.name,
                    "kind": node.kind.value,
                    "fqn": node.fqn,
                    "file": node.path,
                    "return_type": node.attrs.get("return_type") if node.attrs else None,
                }
            return None

        # Dict (DeltaGraph 형식)
        if isinstance(base_graph, dict):
            return base_graph.get("nodes", {}).get(symbol)

        # Fallback
        if hasattr(base_graph, "get_node"):
            try:
                return base_graph.get_node(symbol)
            except (KeyError, AttributeError, TypeError):
                return None

        if hasattr(base_graph, "nodes"):
            return base_graph.nodes.get(symbol)

        return None

    def __repr__(self) -> str:
        return f"RiskAnalyzer(semantic_differ={self.semantic_differ is not None})"
