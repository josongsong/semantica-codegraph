"""
Graph Storage Adapter

그래프 저장소 어댑터
"""


class GraphStorageAdapter:
    """그래프 저장소 어댑터"""

    def __init__(self, graph_store):
        """
        초기화

        Args:
            graph_store: Graph Store
        """
        self.graph_store = graph_store

    async def save_graph(self, repo_id: str, graph) -> None:
        """
        그래프 저장

        Args:
            repo_id: 리포지토리 ID
            graph: GraphDocument
        """
        await self.graph_store.save_graph(
            repo_id=repo_id,
            graph_doc=graph,
        )

    async def delete_graph_nodes(self, repo_id: str, node_ids: list[str]) -> None:
        """
        그래프 노드 삭제

        Args:
            repo_id: 리포지토리 ID
            node_ids: 삭제할 노드 ID 리스트
        """
        await self.graph_store.delete_nodes(
            repo_id=repo_id,
            node_ids=node_ids,
        )
