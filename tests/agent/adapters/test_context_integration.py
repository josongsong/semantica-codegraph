"""Context 통합 테스트

Phase 1-4 Context 통합 검증:
- multi_index (심볼 검색)
- session_memory (메모리 저장/검색)
- security_analysis (취약점 분석)
- codegen_loop (ShadowFS 격리 실행)

테스트 범위:
- Happy Path
- Corner Cases (empty input, None)
- Edge Cases (서비스 미설정)
- Error Cases (예외 처리)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.orchestrator.orchestrator.adapters.context_adapter import ContextAdapter


class TestMultiIndexIntegration:
    """Phase 1: multi_index 통합 테스트"""

    @pytest.fixture
    def mock_symbol_index(self):
        """Mock SymbolIndex"""
        index = AsyncMock()
        index.search = AsyncMock(
            return_value=[
                MagicMock(
                    file_path="src/app.py",
                    score=0.95,
                    metadata={
                        "line_number": 10,
                        "symbol_type": "function",
                        "fqn": "src.app.calculate_total",
                        "preview": "def calculate_total(items): ...",
                    },
                )
            ]
        )
        return index

    @pytest.mark.asyncio
    async def test_get_symbol_definition_with_real_index(self, mock_symbol_index):
        """Happy Path: 실제 SymbolIndex 연동"""
        adapter = ContextAdapter(symbol_index=mock_symbol_index)

        result = await adapter.get_symbol_definition(
            symbol_name="calculate_total",
            repo_id="test-repo",
            snapshot_id="main",
        )

        assert result["found"] is True
        assert result["name"] == "calculate_total"
        assert result["file_path"] == "src/app.py"
        assert result["type"] == "function"
        mock_symbol_index.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_symbol_definition_not_found(self, mock_symbol_index):
        """Edge Case: 심볼 미발견"""
        mock_symbol_index.search.return_value = []
        adapter = ContextAdapter(symbol_index=mock_symbol_index)

        result = await adapter.get_symbol_definition(
            symbol_name="unknown_function",
            repo_id="test-repo",
        )

        assert result["found"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_symbol_definition_fallback_to_mock(self):
        """Edge Case: SymbolIndex 없을 때 Mock fallback"""
        adapter = ContextAdapter()  # symbol_index=None

        result = await adapter.get_symbol_definition(
            symbol_name="calculate_total",
            repo_id="test-repo",
        )

        assert result["found"] is True  # Mock은 항상 found=True


class TestSessionMemoryIntegration:
    """Phase 2: session_memory 통합 테스트"""

    @pytest.fixture
    def mock_memory_service(self):
        """Mock MemoryService (Memory 도메인 모델 구조에 맞춤)"""
        from datetime import datetime

        # Mock MemoryType enum
        mock_memory_type = MagicMock()
        mock_memory_type.value = "working"

        service = AsyncMock()
        service.search = AsyncMock(
            return_value=[
                MagicMock(
                    id="mem-001",
                    content="이전에 calculate_total 함수의 null check 버그를 수정함",
                    type=mock_memory_type,  # memory_type → type
                    session_id="session-001",
                    created_at=datetime(2024, 1, 1, 0, 0, 0),  # datetime 객체
                    metadata={"tags": ["bugfix", "null-check"]},
                )
            ]
        )
        service.save = AsyncMock()
        return service

    # ============================================================
    # get_relevant_memories 테스트
    # ============================================================

    @pytest.mark.asyncio
    async def test_get_relevant_memories_happy_path(self, mock_memory_service):
        """Happy Path: 메모리 검색 성공"""
        adapter = ContextAdapter(memory_service=mock_memory_service)

        result = await adapter.get_relevant_memories(
            query="null check 버그",
            session_id="session-001",
            limit=5,
        )

        assert len(result) == 1
        assert "calculate_total" in result[0]["content"]
        mock_memory_service.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_relevant_memories_empty_query_raises(self, mock_memory_service):
        """Corner Case: 빈 쿼리"""
        adapter = ContextAdapter(memory_service=mock_memory_service)

        with pytest.raises(ValueError, match="query cannot be empty"):
            await adapter.get_relevant_memories(
                query="",
                session_id="session-001",
            )

    @pytest.mark.asyncio
    async def test_get_relevant_memories_whitespace_query_raises(self, mock_memory_service):
        """Corner Case: 공백만 있는 쿼리"""
        adapter = ContextAdapter(memory_service=mock_memory_service)

        with pytest.raises(ValueError, match="query cannot be empty"):
            await adapter.get_relevant_memories(
                query="   ",
                session_id="session-001",
            )

    @pytest.mark.asyncio
    async def test_get_relevant_memories_empty_session_raises(self, mock_memory_service):
        """Corner Case: 빈 세션 ID"""
        adapter = ContextAdapter(memory_service=mock_memory_service)

        with pytest.raises(ValueError, match="session_id cannot be empty"):
            await adapter.get_relevant_memories(
                query="test query",
                session_id="",
            )

    @pytest.mark.asyncio
    async def test_get_relevant_memories_invalid_limit_raises(self, mock_memory_service):
        """Corner Case: 잘못된 limit"""
        adapter = ContextAdapter(memory_service=mock_memory_service)

        with pytest.raises(ValueError, match="limit must be positive"):
            await adapter.get_relevant_memories(
                query="test query",
                session_id="session-001",
                limit=0,
            )

        with pytest.raises(ValueError, match="limit must be positive"):
            await adapter.get_relevant_memories(
                query="test query",
                session_id="session-001",
                limit=-1,
            )

    @pytest.mark.asyncio
    async def test_get_relevant_memories_no_service_raises(self):
        """Edge Case: MemoryService 미설정"""
        adapter = ContextAdapter()  # memory_service=None

        with pytest.raises(RuntimeError, match="memory_service not configured"):
            await adapter.get_relevant_memories(
                query="test",
                session_id="session-001",
            )

    @pytest.mark.asyncio
    async def test_get_relevant_memories_service_error_raises(self, mock_memory_service):
        """Error Case: 서비스 에러"""
        mock_memory_service.search.side_effect = Exception("DB connection failed")
        adapter = ContextAdapter(memory_service=mock_memory_service)

        with pytest.raises(RuntimeError, match="Memory search failed"):
            await adapter.get_relevant_memories(
                query="test",
                session_id="session-001",
            )

    # ============================================================
    # save_experience 테스트
    # ============================================================

    @pytest.mark.asyncio
    async def test_save_experience_happy_path(self, mock_memory_service):
        """Happy Path: 경험 저장 성공"""
        adapter = ContextAdapter(memory_service=mock_memory_service)

        # 예외가 발생하지 않으면 성공
        await adapter.save_experience(
            session_id="session-001",
            content="버그 수정 완료",
            memory_type="experience",
        )

        mock_memory_service.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_experience_empty_session_raises(self, mock_memory_service):
        """Corner Case: 빈 세션 ID"""
        adapter = ContextAdapter(memory_service=mock_memory_service)

        with pytest.raises(ValueError, match="session_id cannot be empty"):
            await adapter.save_experience(
                session_id="",
                content="test content",
            )

    @pytest.mark.asyncio
    async def test_save_experience_empty_content_raises(self, mock_memory_service):
        """Corner Case: 빈 컨텐츠"""
        adapter = ContextAdapter(memory_service=mock_memory_service)

        with pytest.raises(ValueError, match="content cannot be empty"):
            await adapter.save_experience(
                session_id="session-001",
                content="",
            )

    @pytest.mark.asyncio
    async def test_save_experience_no_service_raises(self):
        """Edge Case: MemoryService 미설정"""
        adapter = ContextAdapter()  # memory_service=None

        with pytest.raises(RuntimeError, match="memory_service not configured"):
            await adapter.save_experience(
                session_id="session-001",
                content="test content",
            )


class TestSecurityAnalysisIntegration:
    """Phase 3: security_analysis 통합 테스트"""

    @pytest.fixture
    def mock_security_analyzer(self):
        """Mock SecurityAnalyzer"""
        # Mock Location
        mock_location = MagicMock()
        mock_location.file_path = "src/db.py"
        mock_location.start_line = 42

        # Mock CWE enum
        mock_cwe = MagicMock()
        mock_cwe.value = "CWE-89"

        # Mock Severity enum
        mock_severity = MagicMock()
        mock_severity.value = "high"

        analyzer = AsyncMock()
        analyzer.analyze = AsyncMock(
            return_value=[
                MagicMock(
                    cwe=mock_cwe,
                    severity=mock_severity,
                    title="SQL Injection in login function",
                    description="SQL Injection vulnerability detected",
                    source_location=mock_location,
                    recommendation="Use parameterized queries",
                    confidence=0.95,
                )
            ]
        )
        return analyzer

    @pytest.mark.asyncio
    async def test_analyze_security_happy_path(self, mock_security_analyzer):
        """Happy Path: 보안 분석 성공"""
        adapter = ContextAdapter(security_analyzer=mock_security_analyzer)

        result = await adapter.analyze_security(
            file_path="src/db.py",
            repo_id="test-repo",
        )

        assert len(result) == 1
        assert result[0]["severity"] == "high"
        assert result[0]["cwe_id"] == "CWE-89"
        assert result[0]["title"] == "SQL Injection in login function"
        assert result[0]["confidence"] == 0.95
        mock_security_analyzer.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_security_empty_file_path_raises(self, mock_security_analyzer):
        """Corner Case: 빈 파일 경로"""
        adapter = ContextAdapter(security_analyzer=mock_security_analyzer)

        with pytest.raises(ValueError, match="file_path cannot be empty"):
            await adapter.analyze_security(
                file_path="",
                repo_id="test-repo",
            )

    @pytest.mark.asyncio
    async def test_analyze_security_empty_repo_id_raises(self, mock_security_analyzer):
        """Corner Case: 빈 repo_id"""
        adapter = ContextAdapter(security_analyzer=mock_security_analyzer)

        with pytest.raises(ValueError, match="repo_id cannot be empty"):
            await adapter.analyze_security(
                file_path="src/db.py",
                repo_id="",
            )

    @pytest.mark.asyncio
    async def test_analyze_security_no_analyzer_raises(self):
        """Edge Case: SecurityAnalyzer 미설정"""
        adapter = ContextAdapter()  # security_analyzer=None

        with pytest.raises(RuntimeError, match="security_analyzer not configured"):
            await adapter.analyze_security(
                file_path="src/db.py",
                repo_id="test-repo",
            )

    @pytest.mark.asyncio
    async def test_analyze_security_service_error_raises(self, mock_security_analyzer):
        """Error Case: 서비스 에러"""
        mock_security_analyzer.analyze.side_effect = Exception("Analysis failed")
        adapter = ContextAdapter(security_analyzer=mock_security_analyzer)

        with pytest.raises(RuntimeError, match="Security analysis failed"):
            await adapter.analyze_security(
                file_path="src/db.py",
                repo_id="test-repo",
            )
