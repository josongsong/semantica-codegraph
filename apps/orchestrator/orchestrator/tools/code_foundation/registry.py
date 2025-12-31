"""
Tool Registry with Embedding-based Search

SOTA Reference:
- ScaleMCP (arXiv 2025): TDWA (Tool Document Weighted Average) embedding
- Semantic search for tool retrieval
"""

import logging

import numpy as np

from .base import CodeFoundationTool, ToolCategory, ToolMetadata

logger = logging.getLogger(__name__)


class CodeFoundationToolRegistry:
    """
    도구 등록 및 검색 레지스트리

    Features:
    1. 카테고리별 필터링
    2. 임베딩 기반 시맨틱 검색
    3. 의존성 관리

    SOTA: ScaleMCP의 TDWA 임베딩 전략
    """

    def __init__(self, embedding_service=None):
        """
        Args:
            embedding_service: 임베딩 생성 서비스 (선택)
        """
        self._tools: dict[str, CodeFoundationTool] = {}
        self._embeddings: dict[str, np.ndarray] = {}
        self._category_index: dict[ToolCategory, list[str]] = {cat: [] for cat in ToolCategory}
        self.embedding_service = embedding_service

        logger.info("CodeFoundationToolRegistry initialized")

    def register(self, tool: CodeFoundationTool) -> None:
        """
        도구 등록

        Args:
            tool: 등록할 도구

        Raises:
            ValueError: 도구가 None이거나 메타데이터가 없을 경우
        """
        # STRICT: Null check
        if tool is None:
            raise ValueError("Cannot register None tool")

        if not hasattr(tool, "metadata") or tool.metadata is None:
            raise ValueError(f"Tool {type(tool).__name__} has no metadata")

        metadata = tool.metadata

        # STRICT: Metadata validation
        if not hasattr(metadata, "name") or not metadata.name:
            raise ValueError("Tool metadata must have non-empty 'name'")
        if not hasattr(metadata, "category") or metadata.category is None:
            raise ValueError(f"Tool '{metadata.name}' has no category")

        name = metadata.name

        if name in self._tools:
            logger.warning(f"Tool '{name}' already registered. Overwriting.")

        # 도구 저장
        self._tools[name] = tool

        # 카테고리 인덱스 업데이트
        if name not in self._category_index[metadata.category]:
            self._category_index[metadata.category].append(name)

        # 임베딩 생성 (TDWA 스타일)
        if self.embedding_service is not None:
            try:
                doc = self._create_tool_document(metadata)
                self._embeddings[name] = self.embedding_service.embed(doc)
            except Exception as e:
                logger.warning(f"Failed to create embedding for tool '{name}': {e}. Continuing without embedding.")

        logger.info(f"Registered tool: {name} (category={metadata.category}, complexity={metadata.complexity})")

    def _create_tool_document(self, metadata: ToolMetadata) -> str:
        """
        도구 문서 생성 (TDWA 전략)

        중요도 가중치:
        - Name: 3x
        - Description: 2x
        - Tags: 1x
        """
        parts = [
            metadata.name * 3,  # 이름 강조
            metadata.description * 2,  # 설명 강조
            " ".join(metadata.tags),  # 태그
        ]
        return " ".join(parts)

    def get(self, name: str) -> CodeFoundationTool | None:
        """
        이름으로 도구 가져오기

        Args:
            name: 도구 이름

        Returns:
            도구 객체 또는 None

        Raises:
            ValueError: 이름이 None이거나 빈 문자열일 경우
        """
        if not name or not isinstance(name, str):
            raise ValueError(f"Tool name must be non-empty string, got: {name}")

        return self._tools.get(name)

    def get_by_category(self, category: ToolCategory) -> list[CodeFoundationTool]:
        """카테고리로 도구 필터링"""
        tool_names = self._category_index.get(category, [])
        return [self._tools[name] for name in tool_names]

    def search(
        self, query: str, k: int = 8, category: ToolCategory | None = None, min_confidence: float = 0.0
    ) -> list[tuple[CodeFoundationTool, float]]:
        """
        임베딩 기반 시맨틱 검색

        Args:
            query: 검색 쿼리
            k: 반환할 도구 개수
            category: 카테고리 필터 (선택)
            min_confidence: 최소 신뢰도

        Returns:
            (도구, 유사도 점수) 튜플 리스트
        """
        if not self.embedding_service or not self._embeddings:
            logger.warning("Embedding service not available, using fallback")
            return self._fallback_search(query, k, category)

        # 쿼리 임베딩
        query_emb = self.embedding_service.embed(query)

        # 카테고리 필터링
        if category:
            candidate_names = self._category_index.get(category, [])
        else:
            candidate_names = list(self._tools.keys())

        # 코사인 유사도 계산
        similarities = []
        for name in candidate_names:
            if name not in self._embeddings:
                continue

            tool_emb = self._embeddings[name]
            similarity = self._cosine_similarity(query_emb, tool_emb)

            if similarity >= min_confidence:
                similarities.append((name, similarity))

        # Top-K 선택
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_k = similarities[:k]

        # 도구 객체로 변환
        results = [(self._tools[name], score) for name, score in top_k]

        logger.debug(f"Search query='{query}' returned {len(results)} tools (requested k={k})")

        return results

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """코사인 유사도"""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def _fallback_search(
        self, query: str, k: int, category: ToolCategory | None
    ) -> list[tuple[CodeFoundationTool, float]]:
        """
        임베딩 없을 때 폴백 검색 (키워드 매칭)
        """
        query_lower = query.lower()

        # 후보 도구
        if category:
            candidates = self.get_by_category(category)
        else:
            candidates = list(self._tools.values())

        # 키워드 점수 계산
        scored = []
        for tool in candidates:
            metadata = tool.metadata

            # 이름/설명/태그에서 매칭
            text = f"{metadata.name} {metadata.description} {' '.join(metadata.tags)}".lower()

            # 간단한 점수: 매칭된 단어 개수
            words = query_lower.split()
            score = sum(1 for word in words if word in text)

            if score > 0:
                scored.append((tool, float(score)))

        # 정렬 및 Top-K
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def get_dependencies(self, tool_name: str) -> list[CodeFoundationTool]:
        """도구의 의존성 가져오기"""
        tool = self.get(tool_name)
        if not tool:
            return []

        dep_names = tool.metadata.dependencies
        return [self._tools[name] for name in dep_names if name in self._tools]

    def get_all(self) -> list[CodeFoundationTool]:
        """모든 도구 가져오기"""
        return list(self._tools.values())

    def get_statistics(self) -> dict[str, any]:
        """통계 정보"""
        return {
            "total_tools": len(self._tools),
            "by_category": {cat.value: len(tools) for cat, tools in self._category_index.items() if tools},
            "has_embeddings": len(self._embeddings) > 0,
        }

    def clear(self) -> None:
        """모든 도구 제거"""
        self._tools.clear()
        self._embeddings.clear()
        for cat in self._category_index:
            self._category_index[cat].clear()
        logger.info("Registry cleared")
