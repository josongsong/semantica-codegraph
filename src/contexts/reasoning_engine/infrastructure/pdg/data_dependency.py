"""
Data Dependency Analyzer

Def-Use chains → Data Dependency Graph
"""


class DataDependencyAnalyzer:
    """
    Data Dependency Analyzer.

    A node B is data-dependent on node A if:
    - A defines variable x
    - B uses variable x
    - There exists a path A → B without redefining x

    간단한 구현: Reaching definitions.
    """

    def analyze(self, cfg_nodes: list[dict], cfg_edges: list[dict]) -> list[dict]:
        """
        Data dependency 계산.

        Args:
            cfg_nodes: CFG nodes with defined_vars, used_vars
            cfg_edges: CFG edges

        Returns:
            Data dependency edges
            [{"from": def_node, "to": use_node, "variable": "x"}]
        """
        data_deps = []

        # Build node map
        nodes = {node["id"]: node for node in cfg_nodes}

        # Build successors
        successors = {}
        for edge in cfg_edges:
            from_id = edge["from"]
            to_id = edge["to"]

            if from_id not in successors:
                successors[from_id] = []

            successors[from_id].append(to_id)

        # For each definition, find all uses
        for node_id, node in nodes.items():
            defined_vars = node.get("defined_vars", [])

            for var in defined_vars:
                # Find uses of var reachable from node_id
                uses = self._find_uses(var_name=var, start_node=node_id, nodes=nodes, successors=successors)

                for use_node_id in uses:
                    data_deps.append(
                        {
                            "from": node_id,
                            "to": use_node_id,
                            "variable": var,
                        }
                    )

        return data_deps

    def _find_uses(self, var_name: str, start_node: str, nodes: dict, successors: dict) -> list[str]:
        """
        var_name의 모든 uses 찾기 (reaching definitions).

        Returns:
            Node IDs that use var_name
        """
        uses = []
        visited = set()
        worklist = [start_node]

        while worklist:
            current = worklist.pop()

            if current in visited:
                continue

            visited.add(current)

            # Skip start node (definition node itself)
            if current != start_node:
                node = nodes.get(current, {})

                # Check if this node uses var_name
                used_vars = node.get("used_vars", [])
                if var_name in used_vars:
                    uses.append(current)

                # Check if this node redefines var_name
                defined_vars = node.get("defined_vars", [])
                if var_name in defined_vars:
                    # Redefinition → stop propagation on this path
                    continue

            # Propagate to successors
            if current in successors:
                for succ in successors[current]:
                    if succ not in visited:
                        worklist.append(succ)

        return uses
