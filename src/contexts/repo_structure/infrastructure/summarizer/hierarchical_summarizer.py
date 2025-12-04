"""
Hierarchical LLM Summarizer

Bottom-up 계층적 요약 생성:
- Leaf 노드: 기존 LLMSummarizer로 직접 요약
- Parent 노드: 자식 요약들을 집계하여 상위 요약 생성

전략:
1. Depth 순으로 정렬 (깊은 것부터 = leaf부터)
2. 각 depth별로 병렬 처리
3. Parent는 자식 overview를 모아서 집계 요약
"""

import asyncio
from typing import TYPE_CHECKING

from src.contexts.repo_structure.infrastructure.models import RepoMapNode, TwoLevelSummary
from src.contexts.repo_structure.infrastructure.summarizer.llm_summarizer import LLMSummarizer

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.chunk.models import ChunkStore
    from src.contexts.repo_structure.infrastructure.summarizer.cache import SummaryCache
    from src.contexts.repo_structure.infrastructure.summarizer.cost_control import CostController
    from src.infra.llm.ports import LLMPort
from src.common.observability import get_logger

logger = get_logger(__name__)


class HierarchicalSummarizer:
    """
    계층적 LLM 요약 생성기.

    Bottom-up 방식:
    1. Leaf 노드 (function/class): LLMSummarizer로 직접 요약
    2. Parent 노드 (file/module/dir): 자식 요약 집계

    특징:
    - 기존 LLMSummarizer 재사용
    - 자식이 많으면 중요한 것만 선택
    - 2단계 요약 (overview + detailed)
    """

    def __init__(
        self,
        llm: "LLMPort",
        cache: "SummaryCache",
        cost_controller: "CostController",
        chunk_store: "ChunkStore",
        repo_path: str | None = None,
    ):
        """
        Initialize hierarchical summarizer.

        Args:
            llm: LLM port
            cache: Summary cache
            cost_controller: Cost controller
            chunk_store: Chunk store for content retrieval
            repo_path: Repository path
        """
        self.llm = llm
        self.cache = cache
        self.cost_controller = cost_controller
        self.chunk_store = chunk_store
        self.repo_path = repo_path

        # Leaf 노드 요약은 기존 LLMSummarizer 재사용
        self.leaf_summarizer = LLMSummarizer(
            llm=llm,
            cache=cache,
            cost_controller=cost_controller,
            chunk_store=chunk_store,
            repo_path=repo_path,
        )

        # 노드 ID -> 노드 매핑 (internal cache)
        self._node_map: dict[str, RepoMapNode] = {}

    async def summarize_tree(
        self,
        nodes: list[RepoMapNode],
        max_concurrent: int = 5,
    ) -> dict[str, TwoLevelSummary]:
        """
        트리 전체를 계층적으로 요약.

        Bottom-up 방식으로 leaf부터 처리하여
        parent 노드가 자식 요약을 사용할 수 있게 함.

        Args:
            nodes: RepoMap 노드 리스트
            max_concurrent: 동시 처리 수

        Returns:
            node_id -> TwoLevelSummary 매핑
        """
        # 노드 맵 구축 (빠른 조회용)
        self._node_map = {node.id: node for node in nodes}

        # Depth별로 그룹화
        by_depth = self._group_by_depth(nodes)

        summaries: dict[str, TwoLevelSummary] = {}

        # Bottom-up: 깊은 depth부터 처리
        for depth in sorted(by_depth.keys(), reverse=True):
            depth_nodes = by_depth[depth]

            logger.info(f"Processing depth {depth}: {len(depth_nodes)} nodes")

            # 같은 depth는 병렬 처리 가능
            tasks = [self._summarize_node(node, summaries) for node in depth_nodes]

            # Semaphore로 동시 실행 제한
            sem = asyncio.Semaphore(max_concurrent)

            async def bounded_task(task, semaphore=sem):
                async with semaphore:
                    return await task

            results = await asyncio.gather(
                *[bounded_task(task) for task in tasks],
                return_exceptions=True,
            )

            # 결과 수집
            for node, result in zip(depth_nodes, results, strict=False):
                if isinstance(result, Exception):
                    logger.error(
                        f"Summarization failed for {node.id}: {result}",
                        exc_info=result,
                    )
                    continue

                summaries[node.id] = result

        logger.info(f"Hierarchical summarization completed: {len(summaries)}/{len(nodes)} nodes")

        return summaries

    async def _summarize_node(
        self,
        node: RepoMapNode,
        child_summaries: dict[str, TwoLevelSummary],
    ) -> TwoLevelSummary:
        """
        단일 노드 요약.

        Leaf 노드: LLMSummarizer 사용
        Parent 노드: 자식 요약 집계

        Args:
            node: RepoMap 노드
            child_summaries: 이미 처리된 자식 노드 요약들

        Returns:
            TwoLevelSummary
        """
        # Leaf 판단
        has_children = len(node.children_ids) > 0
        is_symbol_node = node.kind in ["function", "class", "symbol"]

        if not has_children or is_symbol_node:
            # Leaf 노드: 직접 요약
            return await self._summarize_leaf(node)
        else:
            # Parent 노드: 자식 집계
            return await self._summarize_parent(node, child_summaries)

    async def _summarize_leaf(self, node: RepoMapNode) -> TwoLevelSummary:
        """
        Leaf 노드 요약 (기존 LLMSummarizer 재사용).

        Args:
            node: Leaf 노드

        Returns:
            TwoLevelSummary
        """
        try:
            # 기존 LLMSummarizer의 _summarize_node 사용
            summary_text = await self.leaf_summarizer._summarize_node(node)

            if not summary_text:
                return TwoLevelSummary(
                    overview=f"{node.kind}: {node.name}",
                    detailed=f"No summary available for {node.name}",
                    aggregated_from=0,
                )

            # Overview: 첫 문장
            overview = self._extract_first_sentence(summary_text)

            return TwoLevelSummary(
                overview=overview,
                detailed=summary_text,
                aggregated_from=0,
            )

        except Exception as e:
            logger.error(f"Leaf summarization failed for {node.id}: {e}")
            return TwoLevelSummary(
                overview=f"{node.kind}: {node.name}",
                detailed=f"Summarization failed: {e}",
                aggregated_from=0,
            )

    async def _summarize_parent(
        self,
        node: RepoMapNode,
        child_summaries: dict[str, TwoLevelSummary],
    ) -> TwoLevelSummary:
        """
        Parent 노드 요약 (자식 요약 집계).

        Args:
            node: Parent 노드
            child_summaries: 자식 노드 요약들

        Returns:
            TwoLevelSummary
        """
        # 자식 요약 수집
        children_overviews = []
        for child_id in node.children_ids:
            if child_id in child_summaries:
                child_summary = child_summaries[child_id]
                child_node = self._node_map.get(child_id)
                child_name = child_node.name if child_node else "unknown"
                children_overviews.append((child_name, child_summary.overview, child_node))

        if not children_overviews:
            # 자식 요약 없으면 fallback
            logger.warning(f"No child summaries for parent {node.id}, using fallback")
            return TwoLevelSummary(
                overview=f"{node.kind}: {node.name}",
                detailed=f"Contains {len(node.children_ids)} components",
                aggregated_from=0,
            )

        # 너무 많으면 중요한 것만 선택
        if len(children_overviews) > 15:
            children_overviews = self._select_important_children(node, children_overviews)[:15]

        # Prompt 생성
        prompt = self._build_aggregation_prompt(node, children_overviews)

        # LLM 호출
        try:
            response = await self.llm.generate(
                prompt,
                max_tokens=200,
                temperature=0.3,
            )

            # 파싱
            overview, detailed = self._parse_response(response)

            return TwoLevelSummary(
                overview=overview,
                detailed=detailed,
                aggregated_from=len(children_overviews),
            )

        except Exception as e:
            logger.error(f"Parent summarization failed for {node.id}: {e}")
            # Fallback
            return TwoLevelSummary(
                overview=f"{node.kind}: {node.name}",
                detailed=f"Contains {len(children_overviews)} key components",
                aggregated_from=len(children_overviews),
            )

    def _build_aggregation_prompt(
        self,
        node: RepoMapNode,
        children_overviews: list[tuple[str, str, RepoMapNode]],
    ) -> str:
        """
        자식 집계용 프롬프트 생성.

        Args:
            node: Parent 노드
            children_overviews: (name, overview, node) 튜플 리스트

        Returns:
            프롬프트 텍스트
        """
        # 자식 리스트 포맷팅
        children_list = "\n".join([f"- {name}: {overview}" for name, overview, _ in children_overviews])

        kind_kr = {
            "file": "파일",
            "module": "모듈",
            "dir": "디렉토리",
            "project": "프로젝트",
            "repo": "레포지토리",
        }.get(node.kind, node.kind)

        prompt = f"""다음은 {kind_kr} '{node.name}'의 주요 구성 요소입니다:

{children_list}

이 {kind_kr}의 전체 목적과 역할을 요약해주세요.

출력 형식:
1줄 개요: [간결한 한 줄 설명]
상세 설명: [2-3문장으로 목적, 주요 기능, 책임 설명]"""

        return prompt

    def _parse_response(self, response: str) -> tuple[str, str]:
        """
        LLM 응답 파싱.

        형식:
        1줄 개요: ...
        상세 설명: ...

        Args:
            response: LLM 응답

        Returns:
            (overview, detailed) 튜플
        """
        lines = response.strip().split("\n")

        overview = ""
        detailed = ""

        for line in lines:
            line = line.strip()
            if line.startswith("1줄 개요:"):
                overview = line.replace("1줄 개요:", "").strip()
            elif line.startswith("상세 설명:"):
                detailed = line.replace("상세 설명:", "").strip()
            elif overview and not detailed:
                # "1줄 개요:" 이후 첫 줄
                overview = line
            elif overview and detailed:
                # "상세 설명:" 이후 추가 줄
                detailed += " " + line

        # Fallback
        if not overview:
            overview = lines[0] if lines else "No overview"
        if not detailed:
            detailed = " ".join(lines[1:]) if len(lines) > 1 else overview

        # 길이 제한
        overview = overview[:150]
        detailed = detailed[:500]

        return overview, detailed

    def _select_important_children(
        self,
        parent: RepoMapNode,
        children_overviews: list[tuple[str, str, RepoMapNode]],
    ) -> list[tuple[str, str, RepoMapNode]]:
        """
        중요한 자식만 선택 (importance 기준).

        Args:
            parent: Parent 노드
            children_overviews: 자식 리스트

        Returns:
            중요도 순으로 정렬된 자식 리스트
        """
        # importance로 정렬
        sorted_children = sorted(
            children_overviews,
            key=lambda x: x[2].metrics.importance if x[2] else 0.0,
            reverse=True,
        )
        return sorted_children

    def _extract_first_sentence(self, text: str) -> str:
        """
        첫 문장 추출.

        Args:
            text: 전체 텍스트

        Returns:
            첫 문장 (최대 150자)
        """
        # ". " 또는 ".\n"로 구분
        for sep in [". ", ".\n", "? ", "!\n"]:
            if sep in text:
                first = text.split(sep)[0] + sep[0]
                return first[:150]

        # 구분자 없으면 전체 (최대 150자)
        return text[:150]

    def _group_by_depth(self, nodes: list[RepoMapNode]) -> dict[int, list[RepoMapNode]]:
        """
        노드를 depth별로 그룹화.

        Args:
            nodes: RepoMap 노드 리스트

        Returns:
            depth -> 노드 리스트 매핑
        """
        by_depth: dict[int, list[RepoMapNode]] = {}
        for node in nodes:
            depth = node.depth
            if depth not in by_depth:
                by_depth[depth] = []
            by_depth[depth].append(node)
        return by_depth

    def update_node_summaries(
        self,
        nodes: list[RepoMapNode],
        summaries: dict[str, TwoLevelSummary],
    ) -> None:
        """
        노드에 생성된 요약 적용.

        Args:
            nodes: RepoMap 노드 리스트
            summaries: node_id -> TwoLevelSummary 매핑
        """
        for node in nodes:
            if node.id in summaries:
                summary = summaries[node.id]
                node.summary_overview = summary.overview
                node.summary_detailed = summary.detailed
                node.summary_aggregated_count = summary.aggregated_from

                # Legacy 필드도 업데이트 (호환성)
                node.summary_title = summary.overview
                node.summary_body = summary.detailed
