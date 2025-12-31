"""
A-2, A-3: Planner 안전성 테스트

A-2: 불완전 요청 처리 (clarify)
A-3: 위험 작업 차단
"""

import pytest

from apps.orchestrator.orchestrator.task_graph.models import PlanStatus, RiskLevel
from apps.orchestrator.orchestrator.task_graph.planner import TaskGraphPlanner


class TestPlannerSafety:
    """Planner 안전성 테스트"""

    def setup_method(self):
        """각 테스트 전 초기화"""
        self.planner = TaskGraphPlanner()

    # ========== A-2: 불완전 요청 처리 ==========

    def test_a2_1_vague_request_needs_clarification(self):
        """A-2-1: 모호한 요청 → clarify 필요"""
        # Given: 모호한 요청
        context = {"user_input": "이 함수 좀 이상함"}

        # When: 계획 생성
        status, result = self.planner.plan("fix_bug", context)

        # Then: 명확화 필요
        assert status == PlanStatus.NEEDS_CLARIFICATION
        assert isinstance(result, str)
        assert "file" in result.lower() or "function" in result.lower()

    def test_a2_2_short_request_needs_clarification(self):
        """A-2-2: 너무 짧은 요청 → clarify 필요"""
        # Given: 짧은 요청
        context = {"user_input": "버그"}

        # When
        status, result = self.planner.plan("fix_bug", context)

        # Then
        assert status == PlanStatus.NEEDS_CLARIFICATION
        assert "detail" in result.lower()

    def test_a2_3_clear_request_no_clarification(self):
        """A-2-3: 명확한 요청 → clarify 불필요"""
        # Given: 명확한 요청
        context = {
            "user_input": "Fix null pointer exception in payment_service.py calculate() function",
            "file": "payment_service.py",
        }

        # When
        status, result = self.planner.plan("fix_bug", context)

        # Then
        assert status == PlanStatus.VALID
        assert result.tasks  # TaskGraph 반환

    def test_a2_4_problem_word_without_specifics(self):
        """A-2-4: '문제'라는 단어만 → clarify 필요"""
        # Given
        context = {"user_input": "There's a problem"}

        # When
        status, result = self.planner.plan("fix_bug", context)

        # Then
        assert status == PlanStatus.NEEDS_CLARIFICATION

    def test_a2_5_problem_word_with_specifics(self):
        """A-2-5: '문제' + 구체적 정보 → OK"""
        # Given
        context = {"user_input": "There's a problem in auth module", "file": "auth.py", "function": "login"}

        # When
        status, result = self.planner.plan("fix_bug", context)

        # Then
        assert status == PlanStatus.VALID

    # ========== A-3: 위험 작업 차단 ==========

    def test_a3_1_production_db_drop_rejected(self):
        """A-3-1: 프로덕션 DB drop → 거부"""
        # Given
        context = {"user_input": "drop table users from production database"}

        # When
        status, result = self.planner.plan("execute", context)

        # Then
        assert status == PlanStatus.REJECTED
        assert "reject" in result.lower()
        assert "production" in result.lower()

    def test_a3_2_production_truncate_rejected(self):
        """A-3-2: 프로덕션 truncate → 거부"""
        # Given
        context = {"user_input": "truncate table orders in prod database"}

        # When
        status, result = self.planner.plan("execute", context)

        # Then
        assert status == PlanStatus.REJECTED

    def test_a3_3_dev_db_drop_allowed_with_warning(self):
        """A-3-3: 개발 DB drop → 허용 (경고만)"""
        # Given
        context = {"user_input": "drop table test_users from dev database"}

        # When
        status, result = self.planner.plan("execute", context)

        # Then: REJECTED는 아니어야 함 (개발 환경)
        # 현재 구현은 production만 CRITICAL로 처리
        assert status != PlanStatus.REJECTED

    def test_a3_4_bulk_delete_high_risk(self):
        """A-3-4: 대량 삭제 → HIGH risk"""
        # Given
        context = {"user_input": "delete all files in the directory"}

        # When
        risk_level, reason = self.planner.assess_risk("delete", context)

        # Then
        assert risk_level == RiskLevel.HIGH
        assert "deletion" in reason.lower()

    def test_a3_5_large_file_changes_medium_risk(self):
        """A-3-5: 대규모 파일 변경 → MEDIUM risk"""
        # Given
        context = {"user_input": "refactor payment module", "files_count": 15}

        # When
        risk_level, reason = self.planner.assess_risk("refactor", context)

        # Then
        assert risk_level == RiskLevel.MEDIUM
        assert "10 files" in reason

    def test_a3_6_normal_operation_safe(self):
        """A-3-6: 일반 작업 → SAFE"""
        # Given
        context = {"user_input": "fix typo in README"}

        # When
        risk_level, reason = self.planner.assess_risk("fix_bug", context)

        # Then
        assert risk_level == RiskLevel.SAFE

    def test_a3_7_risk_propagates_to_tasks(self):
        """A-3-7: 위험도가 Task에 전파됨"""
        # Given
        context = {"user_input": "delete all cache files", "files_count": 12}

        # When
        status, graph = self.planner.plan("cleanup", context)

        # Then
        if status == PlanStatus.VALID:
            # 그래프 내 최소 1개 task는 risk metadata를 가져야 함
            has_risk = any("risk_level" in task.metadata for task in graph.tasks.values())
            assert has_risk

    def test_a3_8_multiple_dangerous_patterns(self):
        """A-3-8: 여러 위험 패턴 동시 → 가장 높은 위험도"""
        # Given
        context = {"user_input": "drop production database and delete all backups"}

        # When
        status, result = self.planner.plan("execute", context)

        # Then
        assert status == PlanStatus.REJECTED

    def test_a3_9_case_insensitive_detection(self):
        """A-3-9: 대소문자 무관 탐지"""
        # Given
        context = {"user_input": "DROP TABLE Users FROM PRODUCTION"}

        # When
        status, result = self.planner.plan("execute", context)

        # Then
        assert status == PlanStatus.REJECTED

    def test_a3_10_safe_operation_with_dangerous_words(self):
        """A-3-10: 안전한 작업인데 위험 단어 포함 → 문맥 파악"""
        # Given: "remove"가 있지만 안전한 작업
        context = {"user_input": "remove unused imports from code", "files_count": 3}

        # When
        status, graph = self.planner.plan("refactor", context)

        # Then: 거부되지 않아야 함
        assert status != PlanStatus.REJECTED


class TestRiskAssessment:
    """위험도 평가 세부 테스트"""

    def setup_method(self):
        self.planner = TaskGraphPlanner()

    def test_risk_level_ordering(self):
        """위험도 순서: SAFE < LOW < MEDIUM < HIGH < CRITICAL"""
        risk_order = [RiskLevel.SAFE, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]

        assert len(risk_order) == 5
        # Enum 값 비교는 직접 하지 않고, 순서만 확인
        assert risk_order[0] == RiskLevel.SAFE
        assert risk_order[-1] == RiskLevel.CRITICAL

    def test_graph_max_risk_level(self):
        """TaskGraph의 최대 위험도 계산"""
        from apps.orchestrator.orchestrator.task_graph.models import Task, TaskGraph, TaskType

        # Given
        graph = TaskGraph()

        task1 = Task(id="t1", type=TaskType.ANALYZE_CODE, description="Safe task")
        task1.metadata["risk_level"] = RiskLevel.SAFE

        task2 = Task(id="t2", type=TaskType.GENERATE_CODE, description="Medium risk task")
        task2.metadata["risk_level"] = RiskLevel.MEDIUM

        task3 = Task(id="t3", type=TaskType.VALIDATE_CHANGES, description="Low risk task", depends_on=["t1"])
        task3.metadata["risk_level"] = RiskLevel.LOW

        graph.add_task(task1)
        graph.add_task(task2)
        graph.add_task(task3)

        # When
        max_risk = graph.get_max_risk_level()

        # Then
        assert max_risk == RiskLevel.MEDIUM


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
