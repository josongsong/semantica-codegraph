"""
Simple Graph Analyzer Adapter

AST 기반 로컬 분석 (Memgraph 없이)
"""

import ast
import logging
from pathlib import Path

from src.agent.domain.reasoning.reflection_models import (
    ExecutionTrace,
    GraphImpact,
)

logger = logging.getLogger(__name__)


class SimpleGraphAnalyzer:
    """
    Simple Graph Analyzer (로컬 AST)

    구현: IGraphAnalyzer Port

    특징:
    - AST 기반 CFG 분석
    - 함수/클래스 개수 추적
    - Memgraph 없이 작동
    """

    def analyze_graph_impact(self, file_changes: dict[str, str]) -> GraphImpact:
        """
        Graph Impact 분석 (간략)

        Args:
            file_changes: {file_path: new_content}

        Returns:
            GraphImpact
        """
        logger.info(f"Analyzing graph impact for {len(file_changes)} files")

        # Before/After 추정
        total_nodes_before = 0
        total_nodes_after = 0
        total_edges_changed = 0

        for file_path, new_content in file_changes.items():
            if not file_path.endswith(".py"):
                continue

            # After (new content)
            nodes_after, edges_after = self._count_ast_nodes(new_content)
            total_nodes_after += nodes_after

            # Before (기존 파일 있으면 읽기, 없으면 0)
            try:
                path = Path(file_path)
                if path.exists():
                    old_content = path.read_text()
                    nodes_before, edges_before = self._count_ast_nodes(old_content)
                    total_nodes_before += nodes_before
                    total_edges_changed += abs(edges_after - edges_before)
                else:
                    # 신규 파일
                    total_nodes_before += 0
                    total_edges_changed += edges_after
            except Exception as e:
                logger.warning(f"Failed to read {file_path}: {e}")
                total_nodes_before += nodes_after  # 동일하다고 가정

        # Deltas
        nodes_added = max(total_nodes_after - total_nodes_before, 0)
        nodes_removed = max(total_nodes_before - total_nodes_after, 0)

        # Impact Radius (간략 추정)
        impact_radius = min(nodes_added + nodes_removed, 50)

        impact = GraphImpact(
            cfg_nodes_before=total_nodes_before,
            cfg_nodes_after=total_nodes_after,
            cfg_nodes_added=nodes_added,
            cfg_nodes_removed=nodes_removed,
            cfg_edges_changed=total_edges_changed,
            dfg_nodes_before=total_nodes_before,  # 간략화
            dfg_nodes_after=total_nodes_after,
            dfg_edges_changed=total_edges_changed,
            pdg_impact_radius=impact_radius,
        )

        # Score 계산
        impact.impact_score = impact.calculate_impact_score()
        impact.stability_level = impact.determine_stability()

        logger.info(f"Graph Impact: {impact.impact_score:.2f} ({impact.stability_level.value})")

        return impact

    def calculate_impact_radius(self, changed_files: list[str]) -> int:
        """영향 반경 (간략)"""
        # 파일 수 기반 추정
        return min(len(changed_files) * 10, 100)

    def analyze_execution_trace(self, before_code: str, after_code: str) -> ExecutionTrace:
        """
        실행 추적 분석 (간략)

        Note: 실제로는 Coverage Tool 필요
        """
        logger.info("Analyzing execution trace (simplified)")

        # Function 개수로 coverage 추정
        funcs_before = before_code.count("def ")
        funcs_after = after_code.count("def ")

        # Coverage 추정 (함수 수 기반)
        coverage_before = min(funcs_before / 10.0, 1.0)
        coverage_after = min(funcs_after / 10.0, 1.0)

        trace = ExecutionTrace(
            functions_executed=[],  # TODO: 실제 profiling
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            new_exceptions=[],
            fixed_exceptions=[],
            execution_time_delta=0.0,
            memory_delta=0,
        )

        return trace

    # ========================================================================
    # Private Methods
    # ========================================================================

    def _count_ast_nodes(self, code: str) -> tuple[int, int]:
        """
        AST 노드/엣지 개수 추정

        Returns:
            (nodes, edges)
        """
        try:
            tree = ast.parse(code)

            # 노드 개수 (함수, 클래스, 제어문)
            nodes = 0
            edges = 0

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    nodes += 1
                elif isinstance(node, (ast.If, ast.For, ast.While, ast.With)):
                    nodes += 1
                    edges += 1  # Control flow edge
                elif isinstance(node, ast.Call):
                    edges += 1  # Function call edge

            return (nodes, edges)

        except SyntaxError:
            logger.warning("Syntax error in code, returning 0")
            return (0, 0)

        except Exception as e:
            logger.error(f"Failed to parse AST: {e}")
            return (0, 0)
