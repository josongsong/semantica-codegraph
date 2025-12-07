"""
Control Dependency Analyzer

CFG → Control Dependency Graph
"""


class ControlDependencyAnalyzer:
    """
    Control Dependency Analyzer.

    A node B is control-dependent on node A if:
    1. A has multiple successors (e.g., if/while)
    2. B is reachable from A
    3. B is not post-dominated by A

    간단한 구현: CFG branching point (if, while) 기반.
    """

    def analyze(self, cfg_nodes: list[dict], cfg_edges: list[dict]) -> list[dict]:
        """
        Control dependency 계산.

        Args:
            cfg_nodes: CFG nodes
            cfg_edges: CFG edges with conditions

        Returns:
            Control dependency edges
            [{"from": node_id, "to": node_id, "condition": "True/False"}]
        """
        control_deps = []

        # Build adjacency list
        successors = {}
        for edge in cfg_edges:
            from_id = edge.get("from")
            to_id = edge.get("to")
            condition = edge.get("condition")

            if from_id not in successors:
                successors[from_id] = []

            successors[from_id].append(
                {
                    "to": to_id,
                    "condition": condition,
                }
            )

        # Find branching nodes (nodes with >1 successors)
        for node_id, succ_list in successors.items():
            if len(succ_list) > 1:
                # Branching node (if, while, etc.)
                for succ in succ_list:
                    # All nodes in this branch are control-dependent on node_id
                    branch_nodes = self._get_branch_nodes(
                        start_node=succ["to"], successors=successors, branch_condition=succ["condition"]
                    )

                    for branch_node in branch_nodes:
                        control_deps.append(
                            {
                                "from": node_id,
                                "to": branch_node,
                                "condition": succ["condition"],
                            }
                        )

        return control_deps

    def _get_branch_nodes(self, start_node: str, successors: dict, branch_condition: str | None) -> list[str]:
        """
        Branch 내 모든 nodes (간단한 구현).

        실제로는 post-dominator 계산 필요하지만,
        여기서는 단순하게 reachable nodes만 반환.
        """
        visited = set()
        worklist = [start_node]
        branch_nodes = []

        while worklist:
            current = worklist.pop()

            if current in visited:
                continue

            visited.add(current)
            branch_nodes.append(current)

            # Successors 추가 (단, branching 만나면 중단)
            if current in successors:
                succ_list = successors[current]

                # Single successor → continue
                if len(succ_list) == 1:
                    worklist.append(succ_list[0]["to"])
                # Multiple successors → stop (nested branch)
                # 실제로는 더 복잡한 로직 필요

        return branch_nodes
