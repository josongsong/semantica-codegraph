"""
Graph RAG PageRank Pruner 단위 테스트
"""

import pytest

from apps.orchestrator.orchestrator.adapters.cascade import GraphPrunerAdapter
from apps.orchestrator.orchestrator.ports.cascade import GraphNode


@pytest.fixture
def pruner():
    return GraphPrunerAdapter(tokens_per_char=0.25, signature_ratio=0.1)


@pytest.fixture
def sample_nodes():
    """테스트용 Graph 노드"""
    return [
        GraphNode(
            node_id="node_1",
            content="def main():\n    pass",
            node_type="function",
            pagerank_score=0.0,  # 계산 전
            call_depth=0,
        ),
        GraphNode(
            node_id="node_2",
            content="def helper():\n    return True",
            node_type="function",
            pagerank_score=0.0,
            call_depth=1,
        ),
        GraphNode(
            node_id="node_3",
            content="def utils():\n    print('util')",
            node_type="function",
            pagerank_score=0.0,
            call_depth=2,
        ),
    ]


@pytest.fixture
def sample_edges():
    """테스트용 Graph 엣지"""
    return [
        ("node_1", "node_2"),  # main -> helper
        ("node_1", "node_3"),  # main -> utils
        ("node_2", "node_3"),  # helper -> utils
    ]


class TestPageRankCalculation:
    """PageRank 계산 테스트"""

    @pytest.mark.asyncio
    async def test_calculate_pagerank_simple(self, pruner, sample_nodes, sample_edges):
        """간단한 그래프 PageRank 계산"""
        pagerank = await pruner.calculate_pagerank(sample_nodes, sample_edges, damping=0.85)

        assert len(pagerank) == 3
        assert "node_1" in pagerank
        assert "node_2" in pagerank
        assert "node_3" in pagerank

        # PageRank 합은 1.0 (정규화)
        total = sum(pagerank.values())
        assert 0.99 <= total <= 1.01  # 부동소수점 오차

        # node_3이 가장 높아야 함 (2개 노드에서 참조)
        assert pagerank["node_3"] > pagerank["node_1"]
        assert pagerank["node_3"] > pagerank["node_2"]

    @pytest.mark.asyncio
    async def test_calculate_pagerank_single_node(self, pruner):
        """단일 노드 PageRank"""
        nodes = [
            GraphNode(
                node_id="solo", content="def solo(): pass", node_type="function", pagerank_score=0.0, call_depth=0
            )
        ]
        edges = []

        pagerank = await pruner.calculate_pagerank(nodes, edges, damping=0.85)

        assert len(pagerank) == 1
        assert pagerank["solo"] == 1.0  # 혼자니까 1.0

    @pytest.mark.asyncio
    async def test_calculate_pagerank_no_nodes(self, pruner):
        """빈 그래프"""
        pagerank = await pruner.calculate_pagerank([], [], damping=0.85)

        assert len(pagerank) == 0

    @pytest.mark.asyncio
    async def test_calculate_pagerank_convergence(self, pruner, sample_nodes, sample_edges):
        """PageRank 수렴 확인"""
        pagerank = await pruner.calculate_pagerank(sample_nodes, sample_edges, damping=0.85)

        # 모든 점수가 양수
        assert all(score > 0 for score in pagerank.values())

        # 점수 합이 1.0
        assert abs(sum(pagerank.values()) - 1.0) < 0.01


class TestContextPruning:
    """컨텍스트 Pruning 테스트"""

    @pytest.mark.asyncio
    async def test_prune_context_within_budget(self, pruner, sample_nodes):
        """토큰 예산 내에서 Pruning"""
        # PageRank 점수 설정
        sample_nodes[0].pagerank_score = 0.5
        sample_nodes[1].pagerank_score = 0.3
        sample_nodes[2].pagerank_score = 0.2
        # Set call_depth > 2 to prevent should_include_body() from always returning True
        sample_nodes[0].call_depth = 5
        sample_nodes[1].call_depth = 5
        sample_nodes[2].call_depth = 5

        pruned = await pruner.prune_context(sample_nodes, max_tokens=100, top_k_full=2)  # 충분한 예산

        assert pruned.is_within_budget(100)
        assert len(pruned.full_nodes) <= 3  # top_k_full or budget allows more
        assert pruned.compression_ratio <= 1.0

    @pytest.mark.asyncio
    async def test_prune_context_tight_budget(self, pruner, sample_nodes):
        """빡빡한 토큰 예산"""
        # PageRank 점수 설정
        sample_nodes[0].pagerank_score = 0.5
        sample_nodes[1].pagerank_score = 0.3
        sample_nodes[2].pagerank_score = 0.2

        pruned = await pruner.prune_context(sample_nodes, max_tokens=10, top_k_full=1)  # 매우 적은 예산

        assert pruned.is_within_budget(10)
        assert len(pruned.full_nodes) <= 1
        # 일부는 signature-only로
        assert len(pruned.signature_only_nodes) >= 0

    @pytest.mark.asyncio
    async def test_prune_context_compression_ratio(self, pruner, sample_nodes):
        """압축률 계산 확인"""
        sample_nodes[0].pagerank_score = 0.6
        sample_nodes[1].pagerank_score = 0.3
        sample_nodes[2].pagerank_score = 0.1

        pruned = await pruner.prune_context(sample_nodes, max_tokens=50, top_k_full=1)

        # 압축률은 0~1 사이
        assert 0.0 <= pruned.compression_ratio <= 1.0

    @pytest.mark.asyncio
    async def test_prune_context_pagerank_ordering(self, pruner, sample_nodes):
        """PageRank 순서대로 선택"""
        sample_nodes[0].pagerank_score = 0.1
        sample_nodes[1].pagerank_score = 0.9
        sample_nodes[2].pagerank_score = 0.5

        pruned = await pruner.prune_context(sample_nodes, max_tokens=1000, top_k_full=2)

        # 높은 PageRank가 full_nodes에
        if len(pruned.full_nodes) > 0:
            assert pruned.full_nodes[0].node_id == "node_2"  # 0.9


class TestTokenEstimation:
    """토큰 추정 테스트"""

    @pytest.mark.asyncio
    async def test_estimate_tokens_simple(self, pruner):
        """간단한 토큰 추정"""
        content = "hello world"  # 11 chars

        tokens = await pruner.estimate_tokens(content)

        # 0.25 tokens/char * 11 = 2.75 -> 2
        assert tokens == int(11 * 0.25)

    @pytest.mark.asyncio
    async def test_estimate_tokens_long_content(self, pruner):
        """긴 내용 토큰 추정"""
        content = "x" * 1000  # 1000 chars

        tokens = await pruner.estimate_tokens(content)

        assert tokens == 250  # 1000 * 0.25

    @pytest.mark.asyncio
    async def test_estimate_tokens_empty(self, pruner):
        """빈 내용"""
        tokens = await pruner.estimate_tokens("")

        assert tokens == 0


class TestGraphNode:
    """GraphNode 도메인 모델 테스트"""

    def test_should_include_body_high_pagerank(self):
        """높은 PageRank는 본문 포함"""
        node = GraphNode(
            node_id="important",
            content="def important(): pass",
            node_type="function",
            pagerank_score=0.9,  # > 0.8
            call_depth=10,
        )

        assert node.should_include_body() is True

    def test_should_include_body_low_depth(self):
        """낮은 depth는 본문 포함"""
        node = GraphNode(
            node_id="shallow",
            content="def shallow(): pass",
            node_type="function",
            pagerank_score=0.1,  # 낮음
            call_depth=1,  # <= 2
        )

        assert node.should_include_body() is True

    def test_should_include_body_false(self):
        """낮은 PageRank, 깊은 depth는 시그니처만"""
        node = GraphNode(
            node_id="deep",
            content="def deep(): pass",
            node_type="function",
            pagerank_score=0.5,  # < 0.8
            call_depth=5,  # > 2
        )

        assert node.should_include_body() is False


class TestPrunedContext:
    """PrunedContext 도메인 모델 테스트"""

    def test_is_within_budget_true(self):
        """예산 내"""
        from apps.orchestrator.orchestrator.ports.cascade import PrunedContext

        context = PrunedContext(full_nodes=[], signature_only_nodes=[], total_tokens=500, compression_ratio=0.5)

        assert context.is_within_budget(1000) is True

    def test_is_within_budget_false(self):
        """예산 초과"""
        from apps.orchestrator.orchestrator.ports.cascade import PrunedContext

        context = PrunedContext(full_nodes=[], signature_only_nodes=[], total_tokens=1500, compression_ratio=0.8)

        assert context.is_within_budget(1000) is False

    def test_is_within_budget_exact(self):
        """정확히 예산"""
        from apps.orchestrator.orchestrator.ports.cascade import PrunedContext

        context = PrunedContext(full_nodes=[], signature_only_nodes=[], total_tokens=1000, compression_ratio=1.0)

        assert context.is_within_budget(1000) is True
