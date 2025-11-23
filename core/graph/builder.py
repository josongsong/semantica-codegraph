from typing import Dict, List

import networkx as nx

from core.parsers.base import CodeNode


class GraphBuilder:
    """코드 그래프 빌더"""

    def __init__(self):
        self.graph = nx.DiGraph()

    def build_from_nodes(self, nodes: List[CodeNode], file_path: str) -> nx.DiGraph:
        """CodeNode 리스트로부터 그래프 구성"""
        for node in nodes:
            self._add_node(node, file_path)
            if node.parent:
                self._add_edge(node.parent, node, "contains")

        return self.graph

    def add_import_edges(self, file_imports: Dict[str, List[str]]):
        """파일 간 import 관계 추가"""
        for source_file, imports in file_imports.items():
            for import_path in imports:
                if import_path in self.graph.nodes:
                    self.graph.add_edge(source_file, import_path, relation="imports")

    def add_call_edges(self, caller: str, callee: str):
        """함수 호출 관계 추가"""
        self.graph.add_edge(caller, callee, relation="calls")

    def get_subgraph(self, node_id: str, depth: int = 1) -> nx.DiGraph:
        """특정 노드 주변의 서브그래프 추출"""
        nodes = set([node_id])
        current_nodes = set([node_id])

        for _ in range(depth):
            next_nodes = set()
            for node in current_nodes:
                next_nodes.update(self.graph.predecessors(node))
                next_nodes.update(self.graph.successors(node))
            nodes.update(next_nodes)
            current_nodes = next_nodes

        return self.graph.subgraph(nodes)

    def _add_node(self, node: CodeNode, file_path: str):
        """노드 추가"""
        node_id = f"{file_path}::{node.name}:{node.start_line}"
        self.graph.add_node(
            node_id,
            type=node.type,
            name=node.name,
            file=file_path,
            start_line=node.start_line,
            end_line=node.end_line,
        )

    def _add_edge(self, source: CodeNode, target: CodeNode, relation: str):
        """엣지 추가"""
        source_id = f"{source.name}:{source.start_line}"
        target_id = f"{target.name}:{target.start_line}"
        self.graph.add_edge(source_id, target_id, relation=relation)

