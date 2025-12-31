"""
Unit Tests: ExperienceRepository.search_by_session()

Test Coverage:
- Happy path (세션 검색 성공)
- Corner cases (빈 session_id, 존재하지 않는 세션)
- Edge cases (DB 없음, 여러 세션)
- Error handling (Validation, DB 오류)
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock

import pytest

from apps.orchestrator.orchestrator.domain.experience.models import AgentExperience, ProblemType
from apps.orchestrator.orchestrator.infrastructure.experience_repository import ExperienceRepository


class TestSearchBySession:
    """search_by_session() 메서드 테스트"""

    def test_search_by_session_success(self):
        """Happy Path: 세션 검색 성공"""
        # Arrange
        mock_db = Mock()
        repo = ExperienceRepository(db_session=mock_db)
        repo._initialized = True  # Skip _ensure_tables()

        # Mock DB response
        mock_rows = [
            (
                1,
                "session_123",
                "Fix bug in login",
                "bugfix",
                "strategy_1",
                "LATS",
                [],
                ["login.py"],
                True,
                0.85,
                "ACCEPT",
                None,
                None,
                None,
                [],
                ["bug", "login"],
                datetime(2025, 12, 7, 10, 0, 0),
            ),
            (
                2,
                "session_123",
                "Add test for login",
                "feature",
                "strategy_2",
                "LATS",
                [],
                ["test_login.py"],
                True,
                0.90,
                "ACCEPT",
                None,
                None,
                None,
                [],
                ["test", "login"],
                datetime(2025, 12, 7, 10, 5, 0),
            ),
        ]

        mock_db.execute.return_value.fetchall.return_value = mock_rows
        mock_db.execute.return_value = Mock(fetchall=Mock(return_value=mock_rows))

        # Act
        results = repo.search_by_session("session_123", limit=10)

        # Assert
        assert len(results) == 2
        assert results[0].session_id == "session_123"
        assert results[0].problem_description == "Fix bug in login"
        assert results[1].problem_description == "Add test for login"

        # Verify SQL (마지막 호출 검증, _ensure_tables 무시)
        call_args = mock_db.execute.call_args  # 마지막 호출
        assert "ORDER BY created_at DESC" in call_args[0][0]
        assert "WHERE session_id = %s" in call_args[0][0]
        assert call_args[0][1] == ("session_123", 10)

    def test_search_by_session_empty_result(self):
        """Corner Case: 존재하지 않는 세션"""
        # Arrange
        mock_db = Mock()
        repo = ExperienceRepository(db_session=mock_db)
        repo._initialized = True

        mock_db.execute.return_value.fetchall.return_value = []

        # Act
        results = repo.search_by_session("nonexistent_session")

        # Assert
        assert len(results) == 0
        assert results == []

    def test_search_by_session_empty_string_raises_error(self):
        """Edge Case: 빈 session_id (Validation Error)"""
        # Arrange
        mock_db = Mock()
        repo = ExperienceRepository(db_session=mock_db)
        repo._initialized = True

        # Act & Assert
        with pytest.raises(ValueError, match="session_id must be a non-empty string"):
            repo.search_by_session("")

    def test_search_by_session_whitespace_raises_error(self):
        """Edge Case: 공백만 있는 session_id (Validation Error)"""
        # Arrange
        mock_db = Mock()
        repo = ExperienceRepository(db_session=mock_db)
        repo._initialized = True

        # Act & Assert
        with pytest.raises(ValueError, match="session_id must be a non-empty string"):
            repo.search_by_session("   ")

    def test_search_by_session_no_db_returns_empty(self):
        """Edge Case: DB 세션 없음 (Graceful Degradation)"""
        # Arrange
        repo = ExperienceRepository(db_session=None)

        # Act
        results = repo.search_by_session("session_123")

        # Assert
        assert results == []

    def test_search_by_session_db_error_raises(self):
        """Error Handling: DB 오류 발생 시 예외 전파"""
        # Arrange
        mock_db = Mock()
        repo = ExperienceRepository(db_session=mock_db)
        repo._initialized = True

        mock_db.execute.side_effect = Exception("DB connection lost")

        # Act & Assert
        with pytest.raises(Exception, match="DB connection lost"):
            repo.search_by_session("session_123")

    def test_search_by_session_limit_applied(self):
        """Edge Case: Limit 적용 확인"""
        # Arrange
        mock_db = Mock()
        repo = ExperienceRepository(db_session=mock_db)
        repo._initialized = True

        mock_db.execute.return_value.fetchall.return_value = []

        # Act
        repo.search_by_session("session_123", limit=5)

        # Assert
        call_args = mock_db.execute.call_args
        assert call_args[0][1] == ("session_123", 5)

    def test_search_by_session_schema_mapping(self):
        """Schema Strictness: DB Row → Domain Model 매핑 검증"""
        # Arrange
        mock_db = Mock()
        repo = ExperienceRepository(db_session=mock_db)
        repo._initialized = True

        # 모든 필드 포함 (Nullable 포함)
        mock_row = (
            42,  # id
            "session_xyz",  # session_id
            "Test problem",  # problem_description
            "performance",  # problem_type
            "strat_1",  # strategy_id
            "LATS",  # strategy_type
            ["chunk1", "chunk2"],  # code_chunk_ids
            ["file1.py", "file2.py"],  # file_paths
            True,  # success
            0.75,  # tot_score
            "ACCEPT",  # reflection_verdict
            0.95,  # test_pass_rate (Nullable)
            0.3,  # graph_impact (Nullable)
            12.5,  # execution_time (Nullable)
            [1, 2],  # similar_to_ids
            ["tag1", "tag2"],  # tags
            datetime(2025, 12, 7, 12, 0, 0),  # created_at
        )

        mock_db.execute.return_value.fetchall.return_value = [mock_row]

        # Act
        results = repo.search_by_session("session_xyz")

        # Assert - 모든 필드 매핑 확인
        assert len(results) == 1
        exp = results[0]

        assert exp.id == 42
        assert exp.session_id == "session_xyz"
        assert exp.problem_description == "Test problem"
        assert exp.problem_type == ProblemType.PERFORMANCE
        assert exp.strategy_id == "strat_1"
        assert exp.strategy_type == "LATS"
        assert exp.code_chunk_ids == ["chunk1", "chunk2"]
        assert exp.file_paths == ["file1.py", "file2.py"]
        assert exp.success is True
        assert exp.tot_score == 0.75
        assert exp.reflection_verdict == "ACCEPT"
        assert exp.test_pass_rate == 0.95
        assert exp.graph_impact == 0.3
        assert exp.execution_time == 12.5
        assert exp.similar_to_ids == [1, 2]
        assert exp.tags == ["tag1", "tag2"]
        assert exp.created_at == datetime(2025, 12, 7, 12, 0, 0)

    def test_search_by_session_nullable_fields(self):
        """Schema Strictness: Nullable 필드 처리"""
        # Arrange
        mock_db = Mock()
        repo = ExperienceRepository(db_session=mock_db)
        repo._initialized = True

        # Nullable 필드가 None인 경우
        mock_row = (
            1,
            "session_123",
            "Problem",
            "bugfix",
            "",  # strategy_id (빈 문자열)
            "",  # strategy_type
            None,  # code_chunk_ids (NULL)
            None,  # file_paths
            False,
            0.0,
            "",
            None,  # test_pass_rate (NULL)
            None,  # graph_impact
            None,  # execution_time
            None,  # similar_to_ids
            None,  # tags
            datetime.now(),
        )

        mock_db.execute.return_value.fetchall.return_value = [mock_row]

        # Act
        results = repo.search_by_session("session_123")

        # Assert - Nullable 처리 (빈 리스트로 변환)
        exp = results[0]
        assert exp.code_chunk_ids == []
        assert exp.file_paths == []
        assert exp.similar_to_ids == []
        assert exp.tags == []
        assert exp.test_pass_rate is None
        assert exp.graph_impact is None
        assert exp.execution_time is None


# NOTE: Integration tests는 E2E에서 수행 (async 함수 때문에)


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
