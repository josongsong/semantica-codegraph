"""Context와 Agent 사이의 통역사 (Facade Pattern)

Context 패키지(Graph, Vector, AST)는 Low-level
Agent는 High-level (관련 코드, 심볼 정의, 영향도) 필요

직접 연결 시:
- 복잡도 폭발
- Contexts 내부 변경 시 Agent 코드 깨짐

Facade Pattern:
- Agent와 Contexts 격리 (Loose coupling)
- LLM이 읽기 좋은 포맷으로 변환 (핵심 가치!)
- 테스트 시 Mock 교체 용이

Phase 0 Week 3-4: 실제 contexts 연동 시작
"""

from typing import Any


class ContextAdapter:
    """
    Agent가 Contexts를 쉽게 사용하기 위한 Facade

    Day 14-16: 실제 contexts 연동
    - retrieval_search (hybrid search)
    - symbol_index (심볼 찾기)
    """

    def __init__(
        self,
        retrieval_service=None,  # contexts/retrieval_search
        symbol_index=None,  # contexts/multi_index/symbol
        graph_store=None,  # contexts/multi_index (Phase 1)
        impact_analyzer=None,  # contexts/analysis_indexing/impact (Phase 1)
    ):
        """
        Args:
            retrieval_service: RetrieverService from retrieval_search
            symbol_index: MemgraphSymbolIndex from multi_index
            graph_store: Graph store (Phase 1)
            impact_analyzer: Impact analyzer (Phase 1)
        """
        self.retrieval_service = retrieval_service
        self.symbol_index = symbol_index
        self.graph_store = graph_store
        self.impact_analyzer = impact_analyzer

    async def get_relevant_code(
        self,
        query: str,
        repo_id: str,
        snapshot_id: str = "main",
        limit: int = 5,
        token_budget: int = 4000,
    ) -> str:
        """
        LLM이 읽기 좋은 포맷으로 관련 코드 검색

        내부: Retrieval Search (hybrid: vector + lexical + graph + symbol)
        출력: Markdown 포맷 (LLM 프롬프트에 바로 삽입 가능)

        Args:
            query: 검색 쿼리
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID (기본: "main")
            limit: 결과 개수
            token_budget: 토큰 예산

        Returns:
            Markdown 포맷의 관련 코드
        """
        if not self.retrieval_service:
            # Fallback: Mock
            return self._mock_relevant_code(query)

        try:
            # 실제 RetrieverService 호출
            result = await self.retrieval_service.retrieve(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                query=query,
                token_budget=token_budget,
            )

            # LLM용 포맷 변환
            return self._format_retrieval_for_llm(result, limit)

        except Exception as e:
            # 에러 시 Mock fallback
            from src.common.observability import get_logger

            logger = get_logger(__name__)
            logger.warning(f"Retrieval failed, using mock: {e}", repo_id=repo_id, query=query)
            return self._mock_relevant_code(query)

    async def get_symbol_definition(
        self,
        symbol_name: str,
        repo_id: str,
        snapshot_id: str = "main",
    ) -> dict[str, Any]:
        """
        심볼 정의 찾기 (함수, 클래스 등)

        Args:
            symbol_name: 심볼 이름
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID

        Returns:
            심볼 정보 딕셔너리
        """
        if not self.symbol_index:
            # Fallback: Mock
            return self._mock_symbol_definition(symbol_name)

        try:
            # 실제 SymbolIndex 검색
            hits = await self.symbol_index.search(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                query=symbol_name,
                limit=1,
            )

            if not hits:
                return {
                    "name": symbol_name,
                    "found": False,
                    "error": "Symbol not found",
                }

            # 첫 번째 결과 반환
            hit = hits[0]

            # SearchHit은 content가 없고 metadata에 정보가 있음
            # file_path는 최상위 속성으로 있음
            return {
                "name": symbol_name,
                "found": True,
                "file_path": hit.file_path or hit.metadata.get("file_path", ""),
                "line": hit.metadata.get("line_number", 0),
                "code": hit.metadata.get("preview", "") or hit.metadata.get("content", ""),
                "type": hit.metadata.get("symbol_type", "unknown"),
                "fqn": hit.metadata.get("fqn", ""),
                "score": hit.score,
            }

        except Exception as e:
            from src.common.observability import get_logger

            logger = get_logger(__name__)
            logger.warning(f"Symbol search failed, using mock: {e}", repo_id=repo_id, symbol_name=symbol_name)
            return self._mock_symbol_definition(symbol_name)

    async def get_call_graph(
        self,
        function_name: str,
        repo_id: str,
        snapshot_id: str = "main",
        depth: int = 2,
    ) -> dict[str, Any]:
        """
        함수 호출 그래프 (누가 이 함수를 호출하는가)

        Phase 1: graph_store 연동
        Phase 0: Mock
        """
        if not self.graph_store:
            return self._mock_call_graph(function_name)

        # Phase 1: 실제 구현
        # callers = await self.graph_store.get_callers(...)
        return self._mock_call_graph(function_name)

    async def get_impact_scope(
        self,
        file_path: str,
        repo_id: str,
        snapshot_id: str = "main",
    ) -> list[str]:
        """
        파일 변경 시 영향 받는 파일들

        Phase 1: impact_analyzer 연동
        Phase 0: Mock
        """
        if not self.impact_analyzer:
            return self._mock_impact_scope(file_path)

        # Phase 1: 실제 구현
        # impacted = await self.impact_analyzer.analyze(...)
        return self._mock_impact_scope(file_path)

    async def get_related_tests(
        self,
        file_path: str,
        repo_id: str,
        snapshot_id: str = "main",
    ) -> list[str]:
        """
        파일과 관련된 테스트 파일들

        Phase 1: graph_store 연동
        Phase 0: Mock
        """
        if not self.graph_store:
            return self._mock_related_tests(file_path)

        # Phase 1: 실제 구현
        # tests = await self.graph_store.find_tests_for_file(...)
        return self._mock_related_tests(file_path)

    # Private helper methods

    def _format_retrieval_for_llm(self, retrieval_result: Any, limit: int) -> str:
        """
        RetrievalResult를 LLM 프롬프트용 Markdown으로 변환

        Raw 객체 → 읽기 쉬운 텍스트
        """
        from src.contexts.retrieval_search.infrastructure.models import RetrievalResult

        if not isinstance(retrieval_result, RetrievalResult):
            return self._mock_relevant_code("(conversion error)")

        formatted = ["# Relevant Code\n"]

        # Context 확인
        if not retrieval_result.context:
            formatted.append("(No context built)")
            return "\n".join(formatted)

        # ContextResult의 chunks는 ContextChunk 리스트
        chunks = retrieval_result.context.chunks[:limit]

        for idx, chunk in enumerate(chunks, 1):
            # ContextChunk 속성 직접 접근
            file_path = chunk.file_path
            score = chunk.priority_score
            source = chunk.source

            formatted.append(f"## Result {idx}: {file_path}")
            formatted.append(f"**Score**: {score:.3f}")
            formatted.append(f"**Source**: {source}")
            formatted.append(f"**Lines**: {chunk.start_line}-{chunk.end_line}")
            formatted.append("\n```python")

            # Content 길이 제한
            content = chunk.content
            if len(content) > 500:
                formatted.append(content[:500])
                formatted.append("\n... (truncated)")
            else:
                formatted.append(content)
            formatted.append("```\n")

        if not chunks:
            formatted.append("(No results found)")

        # Footer: 메타 정보
        formatted.append("\n---")
        formatted.append(f"**Query**: {retrieval_result.query}")
        formatted.append(f"**Intent**: {retrieval_result.intent_kind}")
        formatted.append(f"**Total chunks**: {retrieval_result.context.chunk_count}")
        formatted.append(
            f"**Token usage**: {retrieval_result.context.total_tokens}/{retrieval_result.context.token_budget}"
        )

        return "\n".join(formatted)

    # Mock methods for Phase 0 fallback

    def _mock_relevant_code(self, query: str) -> str:
        """Phase 0: Mock 관련 코드"""
        return f"""# Relevant Code for: {query}

## Result 1: src/app.py
**Score**: 0.950
**Type**: function

```python
def calculate_total(items):
    total = 0
    for item in items:
        total += item.price  # Bug: missing null check
    return total
```

## Result 2: src/utils.py
**Score**: 0.750
**Type**: function

```python
def validate_items(items):
    if not items:
        raise ValueError("Items cannot be empty")
    return True
```
"""

    def _mock_symbol_definition(self, symbol_name: str) -> dict[str, Any]:
        """Phase 0: Mock 심볼 정의"""
        return {
            "name": symbol_name,
            "found": True,
            "type": "function",
            "file_path": "src/app.py",
            "line": 10,
            "code": f"def {symbol_name}(): pass",
            "fqn": f"src.app.{symbol_name}",
            "score": 1.0,
        }

    def _mock_call_graph(self, function_name: str) -> dict[str, Any]:
        """Phase 0: Mock 호출 그래프"""
        return {
            "function": function_name,
            "called_by": ["main", "process_order"],
            "depth": 2,
        }

    def _mock_impact_scope(self, file_path: str) -> list[str]:
        """Phase 0: Mock 영향 범위"""
        return [
            "tests/test_app.py",
            "src/main.py",
        ]

    def _mock_related_tests(self, file_path: str) -> list[str]:
        """Phase 0: Mock 관련 테스트"""
        base_name = file_path.replace("src/", "").replace(".py", "")
        return [
            f"tests/test_{base_name}.py",
        ]
