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

통합 현황:
- retrieval_search: 완료
- multi_index/symbol: 완료
- session_memory: 완료
- security_analysis: 완료
- codegen_loop: CodeGenAdapter로 분리
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codegraph_engine.multi_index.domain.ports import SearchableIndex
    from codegraph_analysis.security_analysis.domain.models.vulnerability import Vulnerability
    from codegraph_analysis.security_analysis.ports.protocols import SecurityAnalyzerPort
    from codegraph_runtime.session_memory.domain.models import Memory
    from codegraph_runtime.session_memory.domain.ports import MemoryStorePort


def _require_service(service: Any, service_name: str) -> None:
    """
    서비스 존재 검증 헬퍼 (L11 SOTA: DRY)

    Args:
        service: 검증할 서비스
        service_name: 서비스 이름

    Raises:
        RuntimeError: 서비스 미설정
    """
    if not service:
        raise RuntimeError(f"{service_name} not configured. Inject via constructor.")


def _handle_service_error(error: Exception, operation: str, **context) -> None:
    """
    서비스 에러 처리 헬퍼 (L11 SOTA: DRY)

    Args:
        error: 발생한 에러
        operation: 작업 이름
        **context: 로그 컨텍스트

    Raises:
        RuntimeError: 체인된 에러
    """
    from codegraph_shared.common.observability import get_logger

    logger = get_logger(__name__)
    logger.error(f"{operation} failed: {error}", **context)
    raise RuntimeError(f"{operation} failed: {error}") from error


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
        symbol_index: "SearchableIndex | None" = None,  # contexts/multi_index/symbol
        graph_store=None,  # contexts/multi_index (Phase 1)
        impact_analyzer=None,  # contexts/analysis_indexing/impact (Phase 1)
        memory_service: "MemoryStorePort | None" = None,  # contexts/session_memory
        security_analyzer: "SecurityAnalyzerPort | None" = None,  # contexts/security_analysis
    ):
        """
        Args:
            retrieval_service: RetrieverService from retrieval_search
            symbol_index: MemgraphSymbolIndex from multi_index
            graph_store: Graph store (Phase 1)
            impact_analyzer: Impact analyzer (Phase 1)
            memory_service: MemoryStore from session_memory
            security_analyzer: SecurityAnalyzer from security_analysis
        """
        self.retrieval_service = retrieval_service
        self.symbol_index = symbol_index
        self.graph_store = graph_store
        self.impact_analyzer = impact_analyzer
        self.memory_service = memory_service
        self.security_analyzer = security_analyzer

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
        _require_service(self.retrieval_service, "retrieval_service")

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
            _handle_service_error(e, "Retrieval", repo_id=repo_id, query=query)

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
        _require_service(self.symbol_index, "symbol_index")

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
            _handle_service_error(e, "Symbol search", repo_id=repo_id, symbol_name=symbol_name)

    async def get_call_graph(
        self,
        function_name: str,
        repo_id: str,
        snapshot_id: str = "main",
        depth: int = 2,
    ) -> dict[str, Any]:
        """
        함수 호출 그래프 (누가 이 함수를 호출하는가)

        Args:
            function_name: 함수 FQN
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            depth: 탐색 깊이 (기본 2)

        Returns:
            호출 그래프 정보 (callers, callees, graph)
        """
        try:
            from codegraph_engine.multi_index.infrastructure.symbol.call_graph_query import CallGraphQueryBuilder

            query_builder = CallGraphQueryBuilder()

            # Get callers and callees
            callers = await query_builder.search_callers(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                symbol_name=function_name,
                limit=50,
            )

            callees = await query_builder.search_callees(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                symbol_name=function_name,
                limit=50,
            )

            # Build simple graph representation
            nodes = [{"id": function_name, "type": "target"}]
            edges = []

            for caller in callers:
                caller_fqn = caller.get("fqn", caller.get("name", "unknown"))
                nodes.append({"id": caller_fqn, "type": "caller"})
                edges.append({"from": caller_fqn, "to": function_name})

            for callee in callees:
                callee_fqn = callee.get("fqn", callee.get("name", "unknown"))
                nodes.append({"id": callee_fqn, "type": "callee"})
                edges.append({"from": function_name, "to": callee_fqn})

            return {
                "function": function_name,
                "callers": callers,
                "callees": callees,
                "graph": {"nodes": nodes, "edges": edges},
                "depth": depth,
            }

        except Exception as e:
            _handle_service_error(e, "Call graph", function_name=function_name)

    async def get_impact_scope(
        self,
        file_path: str,
        repo_id: str,
        snapshot_id: str = "main",
    ) -> list[str]:
        """
        파일 변경 시 영향 받는 파일들

        Args:
            file_path: 변경된 파일 경로
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID

        Returns:
            영향 받는 파일 경로 목록
        """
        try:
            from codegraph_engine.multi_index.infrastructure.symbol.call_graph_query import CallGraphQueryBuilder

            query_builder = CallGraphQueryBuilder()

            # Get all symbols in file
            # Then find all files that import/reference those symbols
            references = await query_builder.search_imports(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                module_name=file_path,
                limit=100,
            )

            # Extract unique file paths
            affected_files = set()
            for ref in references:
                ref_file = ref.get("file_path", ref.get("file", ""))
                if ref_file and ref_file != file_path:
                    affected_files.add(ref_file)

            return list(affected_files)

        except Exception as e:
            _handle_service_error(e, "Impact scope", file_path=file_path)

    async def get_related_tests(
        self,
        file_path: str,
        repo_id: str,
        snapshot_id: str = "main",
    ) -> list[str]:
        """
        파일과 관련된 테스트 파일들

        Args:
            file_path: 소스 파일 경로
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID

        Returns:
            관련 테스트 파일 경로 목록

        Heuristics:
        1. test_*.py 또는 *_test.py 패턴
        2. tests/ 디렉토리 내 동일 이름
        3. import 관계 기반 (해당 파일을 import하는 테스트)
        """
        try:
            from pathlib import Path

            from codegraph_engine.multi_index.infrastructure.symbol.call_graph_query import CallGraphQueryBuilder

            query_builder = CallGraphQueryBuilder()

            test_files: set[str] = set()

            # 1. Naming convention: test_*.py, *_test.py
            path = Path(file_path)
            file_stem = path.stem
            parent = path.parent

            # Common test file patterns
            candidates = [
                f"test_{file_stem}.py",
                f"{file_stem}_test.py",
                f"tests/test_{file_stem}.py",
                f"tests/{file_stem}_test.py",
                str(parent / "tests" / f"test_{file_stem}.py"),
            ]

            # 2. Find files that import this module
            references = await query_builder.search_imports(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                module_name=file_path,
                limit=50,
            )

            for ref in references:
                ref_file = ref.get("file_path", ref.get("file", ""))
                if ref_file:
                    # Check if it's a test file
                    if "test" in ref_file.lower() or ref_file.startswith("tests/"):
                        test_files.add(ref_file)

            # Add naming convention candidates if they exist
            # (In real implementation, would check file existence)
            for candidate in candidates:
                if "test" in candidate:
                    test_files.add(candidate)

            return list(test_files)

        except Exception as e:
            _handle_service_error(e, "Related tests", file_path=file_path)

    # ============================================================
    # Session Memory Integration
    # ============================================================

    async def get_relevant_memories(
        self,
        query: str,
        session_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        과거 대화/경험에서 관련 기억 검색

        Args:
            query: 검색 쿼리 (non-empty)
            session_id: 세션 ID (non-empty)
            limit: 결과 개수 (> 0)

        Returns:
            관련 메모리 리스트

        Raises:
            ValueError: 입력 검증 실패
            RuntimeError: memory_service 미설정
        """
        # 입력 검증
        if not query or not query.strip():
            raise ValueError("query cannot be empty")
        if not session_id or not session_id.strip():
            raise ValueError("session_id cannot be empty")
        if limit <= 0:
            raise ValueError("limit must be positive")

        # 서비스 존재 검증
        if not self.memory_service:
            raise RuntimeError("memory_service not configured. Inject MemoryStorePort via constructor.")

        try:
            memories = await self.memory_service.search(
                query=query,
                session_id=session_id,
                limit=limit,
            )
            return [self._format_memory(m) for m in memories]

        except Exception as e:
            _handle_service_error(e, "Memory search", session_id=session_id)

    async def save_experience(
        self,
        session_id: str,
        content: str,
        memory_type: str = "experience",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        경험 저장

        Args:
            session_id: 세션 ID (non-empty)
            content: 저장할 내용 (non-empty)
            memory_type: 메모리 타입
            metadata: 추가 메타데이터

        Raises:
            ValueError: 입력 검증 실패
            RuntimeError: memory_service 미설정 또는 저장 실패
        """
        # 입력 검증
        if not session_id or not session_id.strip():
            raise ValueError("session_id cannot be empty")
        if not content or not content.strip():
            raise ValueError("content cannot be empty")

        # 서비스 존재 검증
        if not self.memory_service:
            raise RuntimeError("memory_service not configured. Inject MemoryStorePort via constructor.")

        try:
            # DTO 사용으로 도메인 모델 직접 의존 제거 (Hexagonal Architecture)
            from apps.orchestrator.orchestrator.dto.memory_dto import MemoryDTO

            dto = MemoryDTO(
                session_id=session_id,
                content=content,
                memory_type=memory_type or "working",
                metadata=metadata or {},
            )
            # DTO → Domain 변환은 DTO 내부에서 처리
            await self.memory_service.save(dto.to_domain())

        except ValueError as e:
            # Invalid memory_type 등
            raise ValueError(f"Invalid memory data: {e}") from e
        except Exception as e:
            _handle_service_error(e, "Memory save", session_id=session_id)

    def _format_memory(self, memory: "Memory") -> dict[str, Any]:
        """Memory 객체를 딕셔너리로 변환 (Type-safe)"""
        return {
            "id": memory.id,
            "content": memory.content,
            "type": memory.type.value if memory.type else "unknown",
            "session_id": memory.session_id,
            "created_at": memory.created_at.isoformat() if memory.created_at else "",
            "metadata": memory.metadata,
        }

    # ============================================================
    # Security Analysis Integration
    # ============================================================

    async def analyze_security(
        self,
        file_path: str,
        repo_id: str,
    ) -> list[dict[str, Any]]:
        """
        보안 취약점 분석

        Args:
            file_path: 분석할 파일 경로 (non-empty)
            repo_id: 저장소 ID (non-empty)

        Returns:
            취약점 리스트

        Raises:
            ValueError: 입력 검증 실패
            RuntimeError: security_analyzer 미설정 또는 분석 실패
        """
        # 입력 검증
        if not file_path or not file_path.strip():
            raise ValueError("file_path cannot be empty")
        if not repo_id or not repo_id.strip():
            raise ValueError("repo_id cannot be empty")

        _require_service(self.security_analyzer, "security_analyzer")

        try:
            vulnerabilities = await self.security_analyzer.analyze(
                file_path=file_path,
                repo_id=repo_id,
            )
            return [self._format_vulnerability(v) for v in vulnerabilities]

        except Exception as e:
            _handle_service_error(e, "Security analysis", file_path=file_path)

    def _format_vulnerability(self, vuln: "Vulnerability") -> dict[str, Any]:
        """Vulnerability 객체를 딕셔너리로 변환 (Type-safe)"""
        return {
            "cwe_id": vuln.cwe.value if vuln.cwe else None,
            "severity": vuln.severity.value if vuln.severity else "unknown",
            "title": vuln.title,
            "description": vuln.description,
            "file_path": vuln.source_location.file_path if vuln.source_location else "",
            "line": vuln.source_location.start_line if vuln.source_location else 0,
            "recommendation": vuln.recommendation,
            "confidence": vuln.confidence,
        }

    # Private helper methods

    def _format_retrieval_for_llm(self, retrieval_result: Any, limit: int) -> str:
        """
        RetrievalResult를 LLM 프롬프트용 Markdown으로 변환

        Raw 객체 → 읽기 쉬운 텍스트
        """
        from codegraph_search.infrastructure.models import RetrievalResult

        if not isinstance(retrieval_result, RetrievalResult):
            # L11 SOTA: Fake 금지 - 에러 전파
            raise TypeError(
                f"Expected RetrievalResult, got {type(retrieval_result)}. Check retrieval_service configuration."
            )

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
