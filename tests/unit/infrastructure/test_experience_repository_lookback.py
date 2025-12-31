"""
Unit Tests: ExperienceRepository.search_by_session() lookback_days 개선

Test Coverage:
- lookback_days 파라미터 (시간 제한)
- Session ID UUID (충돌 방지)
"""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from apps.orchestrator.orchestrator.domain.experience.models import AgentExperience, ProblemType
from apps.orchestrator.orchestrator.infrastructure.experience_repository import ExperienceRepository


class TestSearchBySessionLookback:
    """lookback_days 파라미터 테스트"""

    def test_lookback_days_filters_old_sessions(self):
        """lookback_days로 오래된 세션 제외"""
        # Arrange
        mock_db = Mock()
        repo = ExperienceRepository(db_session=mock_db)
        repo._initialized = True

        # 3일 전 데이터
        recent_date = datetime.now() - timedelta(days=3)
        mock_rows = [
            (
                1,
                "session_123",
                "Recent problem",
                "bugfix",
                "",
                "",
                [],
                [],
                True,
                0.8,
                "",
                None,
                None,
                None,
                [],
                [],
                recent_date,
            ),
        ]

        mock_db.execute.return_value.fetchall.return_value = mock_rows

        # Act
        results = repo.search_by_session("session_123", limit=10, lookback_days=7)

        # Assert
        assert len(results) == 1

        # WHERE 절에 created_at 필터 추가 확인
        call_args = mock_db.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "created_at >= %s" in sql
        assert len(params) == 3  # (session_id, cutoff_date, limit)

        # cutoff_date 검증 (7일 전)
        cutoff_date = params[1]
        expected_cutoff = datetime.now() - timedelta(days=7)

        # 1분 오차 허용
        assert abs((cutoff_date - expected_cutoff).total_seconds()) < 60

    def test_lookback_days_none_returns_all(self):
        """lookback_days=None이면 전체 조회"""
        # Arrange
        mock_db = Mock()
        repo = ExperienceRepository(db_session=mock_db)
        repo._initialized = True

        mock_db.execute.return_value.fetchall.return_value = []

        # Act
        repo.search_by_session("session_123", limit=10, lookback_days=None)

        # Assert
        call_args = mock_db.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        # created_at 필터 없어야 함
        assert "created_at >=" not in sql
        assert len(params) == 2  # (session_id, limit)

    def test_lookback_days_30(self):
        """lookback_days=30 (한 달)"""
        # Arrange
        mock_db = Mock()
        repo = ExperienceRepository(db_session=mock_db)
        repo._initialized = True

        mock_db.execute.return_value.fetchall.return_value = []

        # Act
        repo.search_by_session("session_123", lookback_days=30)

        # Assert
        call_args = mock_db.execute.call_args
        params = call_args[0][1]

        cutoff_date = params[1]
        expected_cutoff = datetime.now() - timedelta(days=30)

        assert abs((cutoff_date - expected_cutoff).total_seconds()) < 60


# NOTE: TestSessionIDUUID removed - ExecutionContext no longer has session_id field
# Session ID generation is now handled by DeepReasoningRequest


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
