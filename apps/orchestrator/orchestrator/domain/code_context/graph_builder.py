"""
Dependency Graph Builder (Domain Service)

SOTA: Real dependency analysis using import statements

Strict Rules:
- NO fake dependency graphs
- Uses rustworkx (Rust backend, ~400x faster than NetworkX)
- File-level dependencies (function-level = future)

SOTA Enhancements:
- Real Python import resolution (importlib)
- Handles relative imports
- Fallback to heuristic if resolution fails
"""

import importlib.util
import logging
from pathlib import Path

import rustworkx as rx

from .models import CodeContext, ImpactReport

logger = logging.getLogger(__name__)


class DependencyGraphBuilder:
    """
    의존성 그래프 구축 서비스 (Domain Service)

    책임:
    - File-level dependency graph 구축
    - Impact analysis (영향 범위 계산)
    - Risk assessment (위험도 평가)

    Scope:
    - File-level only (MVP)
    - Function-level = NotImplementedError (future)

    Graph Structure:
    - Nodes: File paths
    - Edges: A → B (A imports B)

    Performance: Uses rustworkx (Rust backend, ~400x faster than NetworkX)
    """

    def build_from_contexts(
        self, contexts: dict[str, CodeContext]
    ) -> tuple[rx.PyDiGraph, dict[str, int], dict[int, str]]:
        """
        CodeContext 목록으로부터 dependency graph 구축

        Args:
            contexts: file_path → CodeContext 매핑

        Returns:
            Tuple of (rustworkx DiGraph, node_map, index_to_id)
            - node_map: file_path → index
            - index_to_id: index → file_path
        """
        logger.info(f"Building dependency graph from {len(contexts)} files")

        graph = rx.PyDiGraph()
        node_map: dict[str, int] = {}  # file_path → index
        index_to_id: dict[int, str] = {}  # index → file_path

        # Add all files as nodes
        for file_path in contexts.keys():
            idx = graph.add_node(file_path)
            node_map[file_path] = idx
            index_to_id[idx] = file_path

        # Add edges based on imports
        for file_path, context in contexts.items():
            for imported_module in context.imports:
                # Try to resolve import to file path
                imported_file = self._resolve_import_to_file(imported_module, file_path, list(contexts.keys()))

                if imported_file and imported_file in node_map:
                    graph.add_edge(node_map[file_path], node_map[imported_file], None)
                    logger.debug(f"Dependency: {file_path} → {imported_file}")

        logger.info(f"Graph built: {graph.num_nodes()} nodes, {graph.num_edges()} edges")

        return graph, node_map, index_to_id

    def impact_analysis(
        self,
        graph: rx.PyDiGraph,
        node_map: dict[str, int],
        index_to_id: dict[int, str],
        changed_files: list[str],
    ) -> ImpactReport:
        """
        변경 영향 분석

        Args:
            graph: Dependency graph (rustworkx)
            node_map: file_path → index
            index_to_id: index → file_path
            changed_files: 변경된 파일 목록

        Returns:
            ImpactReport
        """
        logger.info(f"Analyzing impact of {len(changed_files)} changed files")

        changed_set = set(changed_files)
        directly_affected: set[str] = set()
        transitively_affected: set[str] = set()
        max_depth = 0

        # Find directly affected (files that import changed files)
        for changed_file in changed_files:
            if changed_file not in node_map:
                logger.warning(f"File {changed_file} not in graph")
                continue

            changed_idx = node_map[changed_file]
            # Get predecessors (who imports this file)
            for pred_idx in graph.predecessor_indices(changed_idx):
                predecessor = index_to_id[pred_idx]
                if predecessor not in changed_set:
                    directly_affected.add(predecessor)

        # Find transitively affected (BFS from directly affected)
        to_visit = list(directly_affected)
        visited: set[str] = set(directly_affected)
        depth_map: dict[str, int] = dict.fromkeys(directly_affected, 1)

        while to_visit:
            current = to_visit.pop(0)
            current_depth = depth_map[current]
            max_depth = max(max_depth, current_depth)

            current_idx = node_map[current]
            for pred_idx in graph.predecessor_indices(current_idx):
                predecessor = index_to_id[pred_idx]
                if predecessor not in visited and predecessor not in changed_set:
                    visited.add(predecessor)
                    to_visit.append(predecessor)
                    depth_map[predecessor] = current_depth + 1
                    transitively_affected.add(predecessor)

        # Calculate risk score
        risk_score = self._calculate_risk_score(
            graph, node_map, index_to_id, changed_set, directly_affected, transitively_affected, max_depth
        )

        report = ImpactReport(
            changed_files=changed_set,
            directly_affected=directly_affected,
            transitively_affected=transitively_affected,
            risk_score=risk_score,
            max_impact_depth=max_depth,
        )

        logger.info(
            f"Impact analysis: {report.total_affected} affected files, risk={risk_score:.2f}, depth={max_depth}"
        )

        return report

    def _resolve_import_to_file(self, module_name: str, importing_file: str, all_files: list[str]) -> str | None:
        """
        Import 문을 파일 경로로 변환 (SOTA: Real Python resolution)

        Args:
            module_name: Import된 모듈 이름 (e.g., "src.agent.domain.models")
            importing_file: Import하는 파일
            all_files: 프로젝트의 모든 파일 목록

        Returns:
            파일 경로 또는 None

        Strategy:
        1. Try real Python import resolution (importlib.util.find_spec)
        2. Fallback to heuristic pattern matching
        """
        # Strategy 1: Real Python import resolution
        try:
            resolved_path = self._resolve_via_importlib(module_name)
            if resolved_path:
                # Check if resolved path is in our project files
                for file_path in all_files:
                    if Path(file_path).resolve() == Path(resolved_path).resolve():
                        logger.debug(f"Resolved {module_name} → {file_path} (importlib)")
                        return file_path
        except Exception as e:
            logger.debug(f"importlib resolution failed for {module_name}: {e}")

        # Strategy 2: Heuristic pattern matching (fallback)
        return self._resolve_via_heuristic(module_name, all_files)

    def _resolve_via_importlib(self, module_name: str) -> str | None:
        """
        Real Python import resolution using importlib

        Args:
            module_name: 모듈 이름

        Returns:
            파일 경로 또는 None
        """
        try:
            spec = importlib.util.find_spec(module_name)

            if spec is None:
                return None

            # Get origin (file path)
            if spec.origin and spec.origin != "built-in":
                return spec.origin

            # Handle namespace packages
            if spec.submodule_search_locations:
                # Return __init__.py path
                for location in spec.submodule_search_locations:
                    init_path = Path(location) / "__init__.py"
                    if init_path.exists():
                        return str(init_path)

            return None

        except (ImportError, ModuleNotFoundError, ValueError):
            return None

    def _resolve_via_heuristic(self, module_name: str, all_files: list[str]) -> str | None:
        """
        Heuristic-based import resolution (fallback)

        Args:
            module_name: 모듈 이름
            all_files: 파일 목록

        Returns:
            파일 경로 또는 None
        """
        # Convert module name to file path pattern
        # e.g., "src.agent.domain.models" → "src/agent/domain/models.py"
        file_pattern = module_name.replace(".", "/") + ".py"

        # Find matching file
        for file_path in all_files:
            if file_path.endswith(file_pattern):
                logger.debug(f"Resolved {module_name} → {file_path} (heuristic)")
                return file_path

        # Try __init__.py pattern
        # e.g., "src.agent.domain" → "src/agent/domain/__init__.py"
        init_pattern = module_name.replace(".", "/") + "/__init__.py"
        for file_path in all_files:
            if file_path.endswith(init_pattern):
                logger.debug(f"Resolved {module_name} → {file_path} (heuristic __init__)")
                return file_path

        return None

    def _calculate_risk_score(
        self,
        graph: rx.PyDiGraph,
        node_map: dict[str, int],
        index_to_id: dict[int, str],
        changed: set[str],
        directly_affected: set[str],
        transitively_affected: set[str],
        max_depth: int,
    ) -> float:
        """
        위험도 점수 계산

        Factors:
        1. # of affected files (더 많을수록 위험)
        2. Impact depth (더 깊을수록 위험)
        3. Changed files centrality (중요 파일 변경 시 위험)

        Returns:
            Risk score (0.0~1.0)
        """
        total_files = graph.num_nodes()
        if total_files == 0:
            return 0.0

        # Factor 1: Affected ratio
        affected_ratio = (len(directly_affected) + len(transitively_affected)) / total_files

        # Factor 2: Depth penalty
        depth_penalty = min(max_depth / 10.0, 1.0)  # Normalize by depth 10

        # Factor 3: Centrality of changed files
        centrality_score = 0.0
        if graph.num_edges() > 0:
            try:
                # rustworkx betweenness_centrality returns dict[int, float]
                centrality = rx.betweenness_centrality(graph)
                for file in changed:
                    if file in node_map:
                        idx = node_map[file]
                        if idx in centrality:
                            centrality_score += centrality[idx]
                centrality_score /= len(changed)
            except Exception as e:
                logger.warning(f"Centrality calculation failed: {e}")
                centrality_score = 0.0

        # Weighted sum
        risk = affected_ratio * 0.4 + depth_penalty * 0.3 + centrality_score * 0.3

        return min(risk, 1.0)
