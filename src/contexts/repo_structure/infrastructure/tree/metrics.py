"""
RepoMap Heuristic Metrics Calculator

Computes importance scores based on code structure heuristics.

Phase 1: Basic heuristics (LOC, symbol count, edge degree)
Phase 2: Graph-based (PageRank)
Phase 3: Git history (change frequency)
Phase 4: Runtime data (hot score, error rate)
"""

from src.contexts.repo_structure.infrastructure.models import RepoMapBuildConfig, RepoMapNode


class HeuristicMetricsCalculator:
    """
    Calculate heuristic importance scores for RepoMap nodes.

    Importance = w1 * LOC + w2 * symbol_count + w3 * edge_degree
    """

    def __init__(self, config: RepoMapBuildConfig):
        self.config = config

    def compute_importance(self, nodes: list[RepoMapNode]) -> None:
        """
        Compute importance scores for all nodes (in-place).

        Args:
            nodes: List of RepoMapNodes to update
        """
        # Normalize metrics first
        normalized = self._normalize_metrics(nodes)

        # Compute weighted importance
        for i, node in enumerate(nodes):
            norm = normalized[i]
            importance = (
                self.config.heuristic_loc_weight * norm["loc"]
                + self.config.heuristic_symbol_weight * norm["symbol_count"]
                + self.config.heuristic_edge_weight * norm["edge_degree"]
            )
            node.metrics.importance = min(1.0, max(0.0, importance))

    def _normalize_metrics(self, nodes: list[RepoMapNode]) -> list[dict[str, float]]:
        """
        Normalize metrics to [0, 1] range using min-max scaling.

        Args:
            nodes: List of nodes

        Returns:
            List of normalized metric dicts
        """
        if not nodes:
            return []

        # Collect raw values
        locs = [node.metrics.loc for node in nodes]
        symbol_counts = [node.metrics.symbol_count for node in nodes]
        edge_degrees = [node.metrics.edge_degree for node in nodes]

        # Min-max normalization
        loc_min, loc_max = min(locs), max(locs)
        sym_min, sym_max = min(symbol_counts), max(symbol_counts)
        edge_min, edge_max = min(edge_degrees), max(edge_degrees)

        normalized = []
        for node in nodes:
            norm = {
                "loc": self._normalize_value(node.metrics.loc, loc_min, loc_max),
                "symbol_count": self._normalize_value(node.metrics.symbol_count, sym_min, sym_max),
                "edge_degree": self._normalize_value(node.metrics.edge_degree, edge_min, edge_max),
            }
            normalized.append(norm)

        return normalized

    def _normalize_value(self, value: float, min_val: float, max_val: float) -> float:
        """Normalize single value to [0, 1] range."""
        if max_val == min_val:
            return 0.0
        return (value - min_val) / (max_val - min_val)

    def boost_entrypoints(self, nodes: list[RepoMapNode], boost_factor: float = 1.5) -> None:
        """
        Boost importance of entrypoint nodes.

        Args:
            nodes: List of nodes
            boost_factor: Multiplier for entrypoint importance
        """
        for node in nodes:
            if node.is_entrypoint:
                node.metrics.importance = min(1.0, node.metrics.importance * boost_factor)

    def penalize_tests(self, nodes: list[RepoMapNode], penalty_factor: float = 0.5) -> None:
        """
        Reduce importance of test files/functions.

        Args:
            nodes: List of nodes
            penalty_factor: Multiplier for test importance
        """
        for node in nodes:
            if node.is_test:
                node.metrics.importance *= penalty_factor


class EntrypointDetector:
    """
    Detect entrypoint nodes (routes, main, CLI, etc.).
    """

    @staticmethod
    def detect(nodes: list[RepoMapNode]) -> None:
        """
        Detect and mark entrypoint nodes (in-place).

        Heuristics:
        - Filename contains: main, cli, app, server, router, routes
        - FQN contains: main, route, endpoint, handler
        - Future: Use Graph layer route detection
        """
        for node in nodes:
            if EntrypointDetector._is_entrypoint(node):
                node.is_entrypoint = True

    @staticmethod
    def _is_entrypoint(node: RepoMapNode) -> bool:
        """Check if node is an entrypoint using word boundary patterns."""
        import re

        # Check filename with word boundaries
        if node.path:
            filename = node.path.lower()
            # Match whole words to avoid false positives (e.g., "contain" shouldn't match "main")
            entrypoint_patterns = [
                r"\bmain\b",
                r"\bcli\b",
                r"\bapp\b",
                r"\bserver\b",
                r"\brouter\b",
                r"\broutes\b",
                r"__main__",
            ]
            if any(re.search(pattern, filename) for pattern in entrypoint_patterns):
                return True

        # Check FQN with word boundaries
        if node.fqn:
            fqn_lower = node.fqn.lower()
            fqn_patterns = [r"\bmain\b", r"\broute\b", r"\bendpoint\b", r"\bhandler\b", r"\bentrypoint\b"]
            if any(re.search(pattern, fqn_lower) for pattern in fqn_patterns):
                return True

        return False


class TestDetector:
    """
    Detect test files/functions.
    """

    @staticmethod
    def detect(nodes: list[RepoMapNode]) -> None:
        """
        Detect and mark test nodes (in-place).

        Heuristics:
        - Path contains: tests/, test/, __tests__/, __test__/
        - Filename starts with: test_
        - Filename ends with: _test, .test, .spec
        - Modern patterns: conftest.py, pytest fixtures
        - FQN starts with: test_
        """
        for node in nodes:
            if TestDetector._is_test(node):
                node.is_test = True

    @staticmethod
    def _is_test(node: RepoMapNode) -> bool:
        """Check if node is a test."""
        # Check path
        if node.path:
            path_lower = node.path.lower()
            # Test directories
            if any(
                test_dir in path_lower
                for test_dir in ["tests/", "test/", "__tests__/", "__test__/", "/tests/", "/test/"]
            ):
                return True

            filename = path_lower.split("/")[-1]
            # Modern test file patterns
            if (
                filename.startswith("test_")
                or filename.endswith(
                    (
                        "_test.py",
                        ".test.js",
                        ".test.ts",
                        ".test.jsx",
                        ".test.tsx",
                        ".spec.js",
                        ".spec.ts",
                        ".spec.jsx",
                        ".spec.tsx",
                        ".spec.py",
                    )
                )
                or filename in ("conftest.py", "pytest.ini", "test_utils.py")
            ):
                return True

        # Check FQN
        if node.fqn:
            name = node.fqn.split(".")[-1].lower()
            if name.startswith("test_") or name.startswith("fixture_"):
                return True

        return False
