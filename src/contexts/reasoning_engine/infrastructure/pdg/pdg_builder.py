"""
PDG Builder

PDG = CFG + DFG
     = Control Dependency + Data Dependency
"""

from dataclasses import dataclass
from enum import Enum


class DependencyType(Enum):
    """Dependency 타입"""

    CONTROL = "control"  # Control dependency (if, while, etc.)
    DATA = "data"  # Data dependency (def-use)
    CONTROL_DATA = "both"  # Both control and data dependency


@dataclass
class PDGNode:
    """
    PDG Node.

    각 IR statement를 나타냄.
    """

    node_id: str  # Unique ID (e.g., "func:foo:stmt:3")
    statement: str  # Source code statement
    line_number: int  # Line number in source
    defined_vars: list[str]  # Variables defined (write)
    used_vars: list[str]  # Variables used (read)
    is_entry: bool = False  # Entry node
    is_exit: bool = False  # Exit node
    file_path: str = ""  # Source file path
    start_line: int = 0  # Statement start line (for multi-line)
    end_line: int = 0  # Statement end line


@dataclass
class PDGEdge:
    """
    PDG Edge.

    Node 간 dependency를 나타냄.
    """

    from_node: str  # Source node ID
    to_node: str  # Target node ID
    dependency_type: DependencyType
    label: str | None = None  # e.g., "x" for data dependency on variable x


class PDGBuilder:
    """
    PDG Builder.

    CFG + DFG → PDG
    """

    def __init__(self):
        self.nodes: dict[str, PDGNode] = {}
        self.edges: list[PDGEdge] = []

    def add_node(self, node: PDGNode):
        """Node 추가"""
        self.nodes[node.node_id] = node

    def add_edge(self, edge: PDGEdge):
        """Edge 추가"""
        self.edges.append(edge)

    def build(self, cfg_nodes: list, cfg_edges: list, dfg_edges: list) -> tuple[dict[str, PDGNode], list[PDGEdge]]:
        """
        PDG 생성.

        Args:
            cfg_nodes: CFG nodes (from v5 IR)
            cfg_edges: CFG edges
            dfg_edges: DFG edges (def-use chains)

        Returns:
            (PDG nodes, PDG edges)
        """
        # 1. CFG nodes → PDG nodes
        for cfg_node in cfg_nodes:
            pdg_node = PDGNode(
                node_id=cfg_node.get("id", ""),
                statement=cfg_node.get("statement", ""),
                line_number=cfg_node.get("line", 0),
                defined_vars=cfg_node.get("defined_vars", []),
                used_vars=cfg_node.get("used_vars", []),
                is_entry=cfg_node.get("is_entry", False),
                is_exit=cfg_node.get("is_exit", False),
            )
            self.add_node(pdg_node)

        # 2. CFG edges → Control dependency edges
        for cfg_edge in cfg_edges:
            from_id = cfg_edge.get("from")
            to_id = cfg_edge.get("to")

            pdg_edge = PDGEdge(
                from_node=from_id,
                to_node=to_id,
                dependency_type=DependencyType.CONTROL,
                label=cfg_edge.get("condition"),  # e.g., "True" or "False"
            )
            self.add_edge(pdg_edge)

        # 3. DFG edges → Data dependency edges
        for dfg_edge in dfg_edges:
            from_id = dfg_edge.get("from")  # Definition
            to_id = dfg_edge.get("to")  # Use
            var_name = dfg_edge.get("variable")

            pdg_edge = PDGEdge(
                from_node=from_id,
                to_node=to_id,
                dependency_type=DependencyType.DATA,
                label=var_name,
            )
            self.add_edge(pdg_edge)

        return (self.nodes, self.edges)

    def get_dependencies(self, node_id: str) -> list[PDGEdge]:
        """
        특정 node의 모든 dependency (incoming edges).

        Returns:
            Edges that have node_id as target
        """
        return [e for e in self.edges if e.to_node == node_id]

    def get_dependents(self, node_id: str) -> list[PDGEdge]:
        """
        특정 node에 dependent한 모든 nodes (outgoing edges).

        Returns:
            Edges that have node_id as source
        """
        return [e for e in self.edges if e.from_node == node_id]

    def backward_slice(self, node_id: str) -> set[str]:
        """
        Backward slice: node_id에 영향을 주는 모든 nodes.

        Program slicing의 핵심.

        Returns:
            Set of node IDs that affect node_id
        """
        slice_nodes = set()
        worklist = [node_id]

        while worklist:
            current = worklist.pop()

            if current in slice_nodes:
                continue

            slice_nodes.add(current)

            # 모든 dependencies 추가
            deps = self.get_dependencies(current)
            for dep in deps:
                if dep.from_node not in slice_nodes:
                    worklist.append(dep.from_node)

        return slice_nodes

    def forward_slice(self, node_id: str) -> set[str]:
        """
        Forward slice: node_id가 영향을 주는 모든 nodes.

        Returns:
            Set of node IDs affected by node_id
        """
        slice_nodes = set()
        worklist = [node_id]

        while worklist:
            current = worklist.pop()

            if current in slice_nodes:
                continue

            slice_nodes.add(current)

            # 모든 dependents 추가
            deps = self.get_dependents(current)
            for dep in deps:
                if dep.to_node not in slice_nodes:
                    worklist.append(dep.to_node)

        return slice_nodes

    def get_stats(self) -> dict:
        """PDG 통계"""
        control_edges = sum(1 for e in self.edges if e.dependency_type == DependencyType.CONTROL)
        data_edges = sum(1 for e in self.edges if e.dependency_type == DependencyType.DATA)

        return {
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "control_edges": control_edges,
            "data_edges": data_edges,
        }
