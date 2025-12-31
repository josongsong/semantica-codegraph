"""
Thought Decomposer

복잡한 문제를 하위 사고로 분해.
"""

import logging
import uuid
from collections.abc import Callable

from .deep_models import ThoughtNode, ThoughtType

logger = logging.getLogger(__name__)


class ThoughtDecomposer:
    """사고 분해기"""

    def __init__(self, max_depth: int = 5):
        self.max_depth = max_depth

    async def decompose(
        self,
        question: str,
        decompose_fn: Callable[[str], list[str]],
        current_depth: int = 0,
        parent_id: str | None = None,
    ) -> list[ThoughtNode]:
        """
        질문을 하위 사고로 분해

        Args:
            question: 분해할 질문
            decompose_fn: 분해 함수 (LLM)
            current_depth: 현재 깊이
            parent_id: 부모 노드 ID

        Returns:
            사고 노드 리스트
        """
        if current_depth >= self.max_depth:
            logger.debug(f"Max depth {self.max_depth} reached")
            return []

        try:
            # LLM으로 하위 질문 생성
            sub_questions = decompose_fn(question)

            nodes: list[ThoughtNode] = []

            for sub_q in sub_questions:
                node = ThoughtNode(
                    node_id=str(uuid.uuid4()),
                    depth=current_depth,
                    parent_id=parent_id,
                    thought_type=ThoughtType.DECOMPOSITION,
                    content=sub_q,
                    reasoning=f"Decomposed from: {question[:50]}...",
                )
                nodes.append(node)

                # 재귀적으로 분해 (depth + 1)
                if current_depth < self.max_depth - 1:
                    children = await self.decompose(
                        sub_q,
                        decompose_fn,
                        current_depth + 1,
                        parent_id=node.node_id,
                    )
                    node.children = [child.node_id for child in children]
                    nodes.extend(children)

            logger.debug(f"Decomposed into {len(sub_questions)} sub-thoughts at depth {current_depth}")
            return nodes

        except Exception as e:
            logger.warning(f"Failed to decompose: {e}")
            return []

    def decompose_sync(
        self,
        question: str,
        decompose_fn: Callable[[str], list[str]],
        current_depth: int = 0,
        parent_id: str | None = None,
    ) -> list[ThoughtNode]:
        """동기 버전"""
        import asyncio

        return asyncio.run(self.decompose(question, decompose_fn, current_depth, parent_id))
