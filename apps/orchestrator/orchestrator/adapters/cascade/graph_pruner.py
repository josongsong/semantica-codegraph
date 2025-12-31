"""
Graph RAG PageRank Pruner Adapter (SOTA 구현)
토큰 최적화를 위한 그래프 기반 컨텍스트 Pruning
"""

import logging

import numpy as np

from codegraph_agent.ports.cascade import (
    GraphNode,
    IGraphPruner,
    PrunedContext,
)

logger = logging.getLogger(__name__)


class GraphPrunerAdapter(IGraphPruner):
    """Graph RAG PageRank Pruner 구현체"""

    def __init__(
        self,
        tokens_per_char: float = 0.25,  # GPT 기준 대략 1 token = 4 chars
        signature_ratio: float = 0.1,  # 시그니처는 본문의 10%
    ):
        self.tokens_per_char = tokens_per_char
        self.signature_ratio = signature_ratio

    async def calculate_pagerank(
        self, nodes: list[GraphNode], edges: list[tuple[str, str]], damping: float = 0.85
    ) -> dict[str, float]:
        """PageRank 계산 (Power Iteration 방법)"""

        logger.debug(f"Calculating PageRank for {len(nodes)} nodes")

        # 노드 ID -> 인덱스 매핑
        node_ids = [node.node_id for node in nodes]
        id_to_idx = {node_id: i for i, node_id in enumerate(node_ids)}
        n = len(nodes)

        if n == 0:
            return {}

        # 인접 행렬 구성 (Transition Matrix)
        M = np.zeros((n, n))

        for from_id, to_id in edges:
            if from_id in id_to_idx and to_id in id_to_idx:
                from_idx = id_to_idx[from_id]
                to_idx = id_to_idx[to_id]
                M[to_idx, from_idx] = 1.0

        # Out-degree로 정규화
        out_degree = M.sum(axis=0)
        out_degree[out_degree == 0] = 1.0  # Dangling node 방지
        M = M / out_degree

        # PageRank 초기값 (균등 분포)
        pr = np.ones(n) / n

        # Power Iteration
        max_iter = 100
        tolerance = 1e-6

        for iteration in range(max_iter):
            pr_new = damping * M @ pr + (1 - damping) / n * np.ones(n)

            # 수렴 확인
            diff = np.abs(pr_new - pr).sum()
            if diff < tolerance:
                logger.debug(f"PageRank converged at iteration {iteration}")
                break

            pr = pr_new

        # Normalize to sum to 1.0
        pr_sum = pr.sum()
        if pr_sum > 0:
            pr = pr / pr_sum

        # 결과 매핑
        pagerank = {node_ids[i]: float(pr[i]) for i in range(n)}

        logger.debug(f"PageRank distribution: max={max(pagerank.values()):.4f}, min={min(pagerank.values()):.4f}")

        return pagerank

    async def prune_context(
        self, nodes: list[GraphNode], max_tokens: int = 8000, top_k_full: int = 20
    ) -> PrunedContext:
        """토큰 예산 내에서 컨텍스트 최적화"""

        logger.info(f"Pruning context: {len(nodes)} nodes, budget={max_tokens} tokens")

        # 1. PageRank로 정렬
        sorted_nodes = sorted(nodes, key=lambda n: n.pagerank_score, reverse=True)

        # 2. Top-K 노드는 본문 포함
        full_nodes = []
        signature_only_nodes = []
        total_tokens = 0

        for i, node in enumerate(sorted_nodes):
            # 본문 포함 여부 결정
            include_full = i < top_k_full or node.should_include_body()

            # 토큰 계산
            if include_full:
                node_tokens = await self.estimate_tokens(node.content)

                if total_tokens + node_tokens <= max_tokens:
                    full_nodes.append(node)
                    total_tokens += node_tokens
                else:
                    # 예산 초과 시 시그니처만
                    sig_tokens = int(node_tokens * self.signature_ratio)
                    if total_tokens + sig_tokens <= max_tokens:
                        signature_only_nodes.append(node)
                        total_tokens += sig_tokens
            else:
                # 시그니처만
                node_tokens = await self.estimate_tokens(node.content)
                sig_tokens = int(node_tokens * self.signature_ratio)

                if total_tokens + sig_tokens <= max_tokens:
                    signature_only_nodes.append(node)
                    total_tokens += sig_tokens

        # 3. 압축률 계산
        original_tokens = sum([await self.estimate_tokens(node.content) for node in nodes])
        compression_ratio = total_tokens / original_tokens if original_tokens > 0 else 1.0

        logger.info(
            f"Context pruned: "
            f"{len(full_nodes)} full nodes, "
            f"{len(signature_only_nodes)} signature-only, "
            f"{total_tokens}/{max_tokens} tokens "
            f"(compression: {compression_ratio:.2%})"
        )

        return PrunedContext(
            full_nodes=full_nodes,
            signature_only_nodes=signature_only_nodes,
            total_tokens=total_tokens,
            compression_ratio=compression_ratio,
        )

    async def estimate_tokens(self, content: str) -> int:
        """토큰 수 추정 (단순 휴리스틱)"""

        # 간단한 추정: 4 chars ≈ 1 token (GPT 기준)
        return int(len(content) * self.tokens_per_char)
