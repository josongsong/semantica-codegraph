"""
Domain Models Tests

SOTA-Level: Base + Edge + Corner + Extreme Cases
Production-Grade: 실제 데이터, 완전 검증
"""

from datetime import datetime, timedelta

import pytest

from codegraph_runtime.codegen_loop.domain.models import (
    Budget,
    Contract,
    LoopState,
    LoopStatus,
    Metrics,
    Violation,
)
from codegraph_runtime.codegen_loop.domain.patch import (
    FileChange,
    Patch,
    PatchStatus,
)

# ========== Test Helper ==========


def create_test_patch(patch_id: str, iteration: int, pass_rate: float = 0.0) -> Patch:
    """테스트용 Patch 생성 (patch.py 버전)"""
    return Patch(
        id=patch_id,
        iteration=iteration,
        files=[
            FileChange(
                file_path="main.py",
                old_content="",
                new_content="",
                diff_lines=[],
            )
        ],
        status=PatchStatus.GENERATED,
        test_results={
            "pass_rate": pass_rate,
            "passed": int(10 * pass_rate),
            "failed": int(10 * (1 - pass_rate)),
        },
    )


class TestBudget:
    """Budget 테스트 - Production-Grade"""

    # ========== Base Cases ==========

    def test_default_budget(self):
        """Base: 기본 Budget 생성"""
        budget = Budget()

        assert budget.max_iterations == 10
        assert budget.max_tokens == 100_000
        assert budget.max_time_seconds == 300
        assert budget.current_iterations == 0
        assert not budget.is_exceeded()

    def test_custom_budget(self):
        """Base: 커스텀 Budget"""
        budget = Budget(
            max_iterations=20,
            max_tokens=200_000,
            max_time_seconds=600,
            max_llm_calls=100,
            max_test_runs=40,
        )

        assert budget.max_iterations == 20
        assert budget.max_tokens == 200_000

    def test_is_exceeded_iterations(self):
        """Base: iterations 초과"""
        budget = Budget(
            max_iterations=10,
            current_iterations=10,
        )

        assert budget.is_exceeded()

    def test_is_exceeded_tokens(self):
        """Base: tokens 초과"""
        budget = Budget(
            max_tokens=1000,
            current_tokens=1000,
        )

        assert budget.is_exceeded()

    def test_is_exceeded_time(self):
        """Base: time 초과"""
        budget = Budget(
            max_time_seconds=60,
            current_time_seconds=60.0,
        )

        assert budget.is_exceeded()

    def test_not_exceeded(self):
        """Base: 초과 안함"""
        budget = Budget(
            max_iterations=10,
            current_iterations=5,
        )

        assert not budget.is_exceeded()

    def test_remaining_iterations(self):
        """Base: 남은 iterations"""
        budget = Budget(
            max_iterations=10,
            current_iterations=3,
        )

        assert budget.remaining_iterations() == 7

    def test_remaining_iterations_zero(self):
        """Edge: 남은 iterations 0"""
        budget = Budget(
            max_iterations=10,
            current_iterations=10,
        )

        assert budget.remaining_iterations() == 0

    def test_remaining_iterations_negative_clamped(self):
        """Edge: Over-consumption → clamped to 0"""
        budget = Budget(
            max_iterations=10,
            current_iterations=15,  # Over!
        )

        assert budget.remaining_iterations() == 0  # max(0, -5) = 0

    def test_usage_ratio_all_zero(self):
        """Base: 사용률 0%"""
        budget = Budget()

        assert budget.usage_ratio() == 0.0

    def test_usage_ratio_half(self):
        """Base: 사용률 50%"""
        budget = Budget(
            max_iterations=10,
            current_iterations=5,
        )

        assert budget.usage_ratio() == 0.5

    def test_usage_ratio_full(self):
        """Base: 사용률 100%"""
        budget = Budget(
            max_iterations=10,
            current_iterations=10,
        )

        assert budget.usage_ratio() == 1.0

    def test_usage_ratio_max_of_multiple(self):
        """Base: 여러 리소스 중 최대값"""
        budget = Budget(
            max_iterations=10,
            current_iterations=3,  # 30%
            max_tokens=1000,
            current_tokens=800,  # 80%
            max_time_seconds=100,
            current_time_seconds=50.0,  # 50%
        )

        # max(0.3, 0.8, 0.5, ...) = 0.8
        assert budget.usage_ratio() == 0.8

    def test_with_usage_iterations(self):
        """Base: Iteration 증가"""
        budget = Budget(current_iterations=5)
        new_budget = budget.with_usage(iterations=3)

        assert budget.current_iterations == 5  # 불변
        assert new_budget.current_iterations == 8

    def test_with_usage_multiple(self):
        """Base: 여러 리소스 동시 증가"""
        budget = Budget()
        new_budget = budget.with_usage(
            iterations=2,
            tokens=1000,
            time_seconds=10.5,
            llm_calls=5,
            test_runs=3,
        )

        assert new_budget.current_iterations == 2
        assert new_budget.current_tokens == 1000
        assert new_budget.current_time_seconds == 10.5
        assert new_budget.current_llm_calls == 5
        assert new_budget.current_test_runs == 3

    def test_with_usage_accumulates(self):
        """Base: 누적 증가"""
        budget = Budget(current_iterations=5)
        budget = budget.with_usage(iterations=2)
        budget = budget.with_usage(iterations=3)

        assert budget.current_iterations == 10

    # ========== Edge Cases ==========

    def test_invalid_max_iterations_zero_raises(self):
        """Edge: max_iterations=0 에러"""
        with pytest.raises(ValueError, match="max_iterations must be > 0"):
            Budget(max_iterations=0)

    def test_invalid_max_iterations_negative_raises(self):
        """Edge: max_iterations 음수 에러"""
        with pytest.raises(ValueError, match="max_iterations must be > 0"):
            Budget(max_iterations=-1)

    def test_invalid_current_iterations_negative_raises(self):
        """Edge: current_iterations 음수 에러"""
        with pytest.raises(ValueError, match="current_iterations cannot be negative"):
            Budget(current_iterations=-1)

    def test_invalid_max_tokens_negative_raises(self):
        """Edge: max_tokens 음수 에러"""
        with pytest.raises(ValueError, match="max_tokens must be > 0"):
            Budget(max_tokens=-1000)

    def test_min_valid_budget(self):
        """Edge: 최소 유효 Budget"""
        budget = Budget(
            max_iterations=1,
            max_tokens=1,
            max_time_seconds=1,
            max_llm_calls=1,
            max_test_runs=1,
        )

        assert budget.max_iterations == 1
        assert not budget.is_exceeded()

    def test_exactly_at_limit(self):
        """Edge: 정확히 limit"""
        budget = Budget(
            max_iterations=10,
            current_iterations=10,
        )

        assert budget.is_exceeded()  # >= 이므로 초과

    def test_one_over_limit(self):
        """Edge: limit + 1"""
        budget = Budget(
            max_iterations=10,
            current_iterations=11,
        )

        assert budget.is_exceeded()

    # ========== Corner Cases ==========

    def test_usage_ratio_division_by_zero_safe(self):
        """Corner: max=1이면 division safe"""
        budget = Budget(
            max_iterations=1,
            current_iterations=1,
        )

        # 1/1 = 1.0, no division by zero
        assert budget.usage_ratio() == 1.0

    def test_fractional_time(self):
        """Corner: 소수점 시간"""
        budget = Budget(
            max_time_seconds=10,
            current_time_seconds=5.5,
        )

        assert budget.usage_ratio() == 0.55

    # ========== Extreme Cases ==========

    def test_huge_budget(self):
        """Extreme: 거대한 Budget"""
        budget = Budget(
            max_iterations=1_000_000,
            max_tokens=1_000_000_000,
            max_time_seconds=86400,  # 24 hours
        )

        assert not budget.is_exceeded()

    def test_many_increments(self):
        """Extreme: 1000번 증가"""
        budget = Budget(max_iterations=2000)

        for _ in range(1000):
            budget = budget.with_usage(iterations=1)

        assert budget.current_iterations == 1000
        assert not budget.is_exceeded()


class TestMetrics:
    """Metrics 테스트"""

    # ========== Base Cases ==========

    def test_default_metrics(self):
        """Base: 기본 Metrics"""
        metrics = Metrics()

        assert metrics.test_pass_rate == 0.0
        assert metrics.coverage == 0.0
        assert metrics.syntax_valid is False
        assert metrics.overall_score() == 0.0

    def test_perfect_metrics(self):
        """Base: 완벽한 Metrics"""
        metrics = Metrics(
            test_pass_rate=1.0,
            coverage=1.0,
            quality_score=1.0,
            syntax_valid=True,
            type_valid=True,
            lint_score=1.0,
            violations_count=0,
        )

        # Weights: 0.4 + 0.2 + 0.2 + 0.1 = 0.9 (violations은 penalty만)
        assert metrics.overall_score() == 0.9

    def test_overall_score_zero_if_syntax_invalid(self):
        """Base: Syntax invalid이면 score=0"""
        metrics = Metrics(
            test_pass_rate=1.0,
            syntax_valid=False,  # Invalid!
            type_valid=True,
        )

        assert metrics.overall_score() == 0.0

    def test_overall_score_zero_if_type_invalid(self):
        """Base: Type invalid이면 score=0"""
        metrics = Metrics(
            test_pass_rate=1.0,
            syntax_valid=True,
            type_valid=False,  # Invalid!
        )

        assert metrics.overall_score() == 0.0

    def test_overall_score_weighted(self):
        """Base: 가중 평균 계산"""
        metrics = Metrics(
            test_pass_rate=0.8,  # 40% weight
            coverage=0.9,  # 20% weight
            quality_score=0.7,  # 20% weight
            lint_score=0.6,  # 10% weight
            syntax_valid=True,
            type_valid=True,
            violations_count=1,  # 10% weight, penalty 0.1
        )

        # 0.8*0.4 + 0.9*0.2 + 0.7*0.2 + 0.6*0.1 - 0.1*0.1
        # = 0.32 + 0.18 + 0.14 + 0.06 - 0.01 = 0.69
        score = metrics.overall_score()
        assert 0.68 <= score <= 0.70

    def test_overall_score_with_violations_penalty(self):
        """Base: Violation penalty 적용"""
        metrics = Metrics(
            test_pass_rate=1.0,
            coverage=1.0,
            quality_score=1.0,
            lint_score=1.0,
            syntax_valid=True,
            type_valid=True,
            violations_count=5,  # penalty = min(1.0, 5*0.1) = 0.5
        )

        # Perfect 0.9 - 0.5*0.1 = 0.9 - 0.05 = 0.85
        assert metrics.overall_score() == pytest.approx(0.85, abs=0.01)

    def test_overall_score_clamped_to_0(self):
        """Edge: Score < 0이면 0으로 clamp"""
        metrics = Metrics(
            test_pass_rate=0.0,
            coverage=0.0,
            quality_score=0.0,
            lint_score=0.0,
            syntax_valid=True,
            type_valid=True,
            violations_count=100,  # Huge penalty
        )

        score = metrics.overall_score()
        assert score >= 0.0

    def test_overall_score_clamped_to_1(self):
        """Edge: Score > 1이면 1로 clamp (이론적)"""
        # Weights sum to 0.9, 최대 1.0 - penalty이므로 실제로는 >1 불가능
        # 하지만 clamp 로직 테스트
        metrics = Metrics(
            test_pass_rate=1.0,
            coverage=1.0,
            quality_score=1.0,
            lint_score=1.0,
            syntax_valid=True,
            type_valid=True,
        )

        score = metrics.overall_score()
        assert score <= 1.0

    # ========== Edge Cases ==========

    def test_invalid_test_pass_rate_over_1_raises(self):
        """Edge: test_pass_rate > 1 에러"""
        with pytest.raises(ValueError, match="test_pass_rate must be between 0 and 1"):
            Metrics(
                test_pass_rate=1.5,
                syntax_valid=True,
                type_valid=True,
            )

    def test_invalid_test_pass_rate_negative_raises(self):
        """Edge: test_pass_rate < 0 에러"""
        with pytest.raises(ValueError, match="test_pass_rate must be between 0 and 1"):
            Metrics(
                test_pass_rate=-0.1,
                syntax_valid=True,
                type_valid=True,
            )

    def test_invalid_coverage_raises(self):
        """Edge: coverage 범위 밖 에러"""
        with pytest.raises(ValueError, match="coverage must be between 0 and 1"):
            Metrics(
                coverage=1.1,
                syntax_valid=True,
                type_valid=True,
            )

    def test_invalid_violations_count_negative_raises(self):
        """Edge: violations_count 음수 에러"""
        with pytest.raises(ValueError, match="violations_count cannot be negative"):
            Metrics(
                violations_count=-1,
                syntax_valid=True,
                type_valid=True,
            )

    def test_boundary_values_0(self):
        """Edge: 모든 값 0"""
        metrics = Metrics(
            test_pass_rate=0.0,
            coverage=0.0,
            quality_score=0.0,
            lint_score=0.0,
            syntax_valid=True,  # 최소 True여야 score > 0
            type_valid=True,
            violations_count=0,
        )

        assert metrics.overall_score() == 0.0

    def test_boundary_values_1(self):
        """Edge: 모든 값 1"""
        metrics = Metrics(
            test_pass_rate=1.0,
            coverage=1.0,
            quality_score=1.0,
            lint_score=1.0,
            syntax_valid=True,
            type_valid=True,
        )

        # Weights sum = 0.9
        assert metrics.overall_score() == 0.9


class TestViolation:
    """Violation 테스트"""

    def test_valid_violation(self):
        """Base: 유효한 Violation"""
        violation = Violation(
            contract_id="contract-123",
            rule="no_sql_injection",
            severity="critical",
            message="SQL injection detected",
        )

        assert violation.severity == "critical"
        assert violation.contract_id == "contract-123"

    def test_violation_with_location(self):
        """Base: location 포함"""
        violation = Violation(
            contract_id="c1",
            rule="r1",
            severity="major",
            message="msg",
            location="file.py:42",
        )

        assert violation.location == "file.py:42"

    def test_violation_with_suggested_fix(self):
        """Base: suggested_fix 포함"""
        violation = Violation(
            contract_id="c1",
            rule="r1",
            severity="minor",
            message="msg",
            suggested_fix="Use parameterized query",
        )

        assert "parameterized" in violation.suggested_fix

    def test_invalid_severity_raises(self):
        """Edge: 잘못된 severity 에러"""
        with pytest.raises(ValueError, match="severity must be one of"):
            Violation(
                contract_id="c1",
                rule="r1",
                severity="invalid",
                message="msg",
            )

    def test_empty_contract_id_raises(self):
        """Edge: 빈 contract_id 에러"""
        with pytest.raises(ValueError, match="contract_id cannot be empty"):
            Violation(
                contract_id="",
                rule="r1",
                severity="critical",
                message="msg",
            )

    def test_empty_rule_raises(self):
        """Edge: 빈 rule 에러"""
        with pytest.raises(ValueError, match="rule cannot be empty"):
            Violation(
                contract_id="c1",
                rule="",
                severity="critical",
                message="msg",
            )

    def test_empty_message_raises(self):
        """Edge: 빈 message 에러"""
        with pytest.raises(ValueError, match="message cannot be empty"):
            Violation(
                contract_id="c1",
                rule="r1",
                severity="critical",
                message="",
            )


class TestContract:
    """Contract 테스트"""

    def test_valid_contract(self):
        """Base: 유효한 Contract"""
        contract = Contract(
            target="module.function",
            preconditions=["x > 0"],
            postconditions=["result > 0"],
            invariants=["balance >= 0"],
            side_effects=["logs to file"],
            dependencies={"os", "sys"},
            complexity=5,
        )

        assert contract.target == "module.function"
        assert contract.complexity == 5

    def test_empty_target_raises(self):
        """Edge: 빈 target 에러"""
        with pytest.raises(ValueError, match="target cannot be empty"):
            Contract(
                target="",
                preconditions=[],
                postconditions=[],
                invariants=[],
                side_effects=[],
                dependencies=set(),
                complexity=0,
            )

    def test_negative_complexity_raises(self):
        """Edge: 음수 complexity 에러"""
        with pytest.raises(ValueError, match="complexity cannot be negative"):
            Contract(
                target="func",
                preconditions=[],
                postconditions=[],
                invariants=[],
                side_effects=[],
                dependencies=set(),
                complexity=-1,
            )

    def test_zero_complexity(self):
        """Edge: complexity=0 허용"""
        contract = Contract(
            target="simple_func",
            preconditions=[],
            postconditions=[],
            invariants=[],
            side_effects=[],
            dependencies=set(),
            complexity=0,
        )

        assert contract.complexity == 0


class TestPatchFromModels:
    """Patch (from patch.py) 테스트 - models.py Patch 제거됨"""

    def test_patch_lifecycle(self):
        """Integration: Patch 생명주기"""
        patch = Patch(
            id="p1",
            iteration=1,
            files=[
                FileChange(
                    file_path="main.py",
                    old_content="old",
                    new_content="new",
                    diff_lines=["-old", "+new"],
                )
            ],
            status=PatchStatus.GENERATED,
        )

        assert patch.status == PatchStatus.GENERATED

        # Validate
        patch = patch.with_status(PatchStatus.VALIDATED)
        assert patch.status == PatchStatus.VALIDATED

        # Test
        test_results = {
            "pass_rate": 1.0,
            "passed": 10,
            "failed": 0,
        }
        patch = patch.with_test_results(test_results).with_status(PatchStatus.TESTED)
        assert patch.status == PatchStatus.TESTED
        assert patch.test_results is not None

        # Accept
        patch = patch.with_status(PatchStatus.ACCEPTED)
        assert patch.is_accepted()
        assert not patch.is_rejected()

    def test_patch_rejection(self):
        """Base: Patch 거부"""
        patch = Patch(
            id="p1",
            iteration=1,
            files=[
                FileChange(
                    file_path="main.py",
                    old_content="",
                    new_content="",
                    diff_lines=[],
                )
            ],
            status=PatchStatus.FAILED,
        )

        assert patch.is_rejected()
        assert not patch.is_accepted()

    def test_patch_multi_file(self):
        """Base: Multi-file Patch"""
        patch = Patch(
            id="p1",
            iteration=1,
            files=[
                FileChange(
                    file_path="main.py",
                    old_content="",
                    new_content="",
                    diff_lines=[],
                ),
                FileChange(
                    file_path="utils.py",
                    old_content="",
                    new_content="",
                    diff_lines=[],
                ),
            ],
            status=PatchStatus.GENERATED,
        )

        assert len(patch.files) == 2
        assert "main.py" in patch.modified_files
        assert "utils.py" in patch.modified_files


class TestLoopState:
    """LoopState 테스트"""

    def test_initial_state(self):
        """Base: 초기 상태"""
        budget = Budget()
        state = LoopState(
            task_id="task-1",
            status=LoopStatus.RUNNING,
            current_iteration=0,
            patches=[],
            budget=budget,
        )

        assert state.status == LoopStatus.RUNNING
        assert len(state.patches) == 0
        assert not state.should_stop()

    def test_with_patch(self):
        """Base: Patch 추가"""
        budget = Budget()
        state = LoopState(
            task_id="task-1",
            status=LoopStatus.RUNNING,
            current_iteration=0,
            patches=[],
            budget=budget,
        )

        patch = Patch(
            id="p1",
            iteration=1,
            files=[
                FileChange(
                    file_path="main.py",
                    old_content="",
                    new_content="",
                    diff_lines=[],
                )
            ],
            status=PatchStatus.GENERATED,
            test_results={
                "pass_rate": 0.8,
                "passed": 8,
                "failed": 2,
            },
        )

        new_state = state.with_patch(patch)

        assert len(state.patches) == 0  # 불변
        assert len(new_state.patches) == 1
        assert new_state.best_patch == patch

    def test_next_iteration(self):
        """Base: 다음 iteration"""
        budget = Budget()
        state = LoopState(
            task_id="task-1",
            status=LoopStatus.RUNNING,
            current_iteration=0,
            patches=[],
            budget=budget,
        )

        new_state = state.next_iteration()

        assert state.current_iteration == 0  # 불변
        assert new_state.current_iteration == 1
        assert new_state.budget.current_iterations == 1

    def test_should_stop_converged(self):
        """Base: 수렴 시 stop"""
        budget = Budget()
        state = LoopState(
            task_id="task-1",
            status=LoopStatus.CONVERGED,
            current_iteration=0,
            patches=[],
            budget=budget,
        )

        assert state.should_stop()

    def test_should_stop_budget_exceeded(self):
        """Base: Budget 초과 시 stop"""
        budget = Budget(
            max_iterations=10,
            current_iterations=10,
        )
        state = LoopState(
            task_id="task-1",
            status=LoopStatus.RUNNING,
            current_iteration=10,
            patches=[],
            budget=budget,
        )

        assert state.should_stop()

    def test_should_stop_accepted_and_converged(self):
        """Base: Accepted + convergence > 0.95 시 stop"""
        budget = Budget()
        patch = create_test_patch("p1", 1, pass_rate=1.0)
        patch = patch.with_status(PatchStatus.ACCEPTED)

        state = LoopState(
            task_id="task-1",
            status=LoopStatus.RUNNING,
            current_iteration=1,
            patches=[patch],
            budget=budget,
            best_patch=patch,
            convergence_score=0.96,
        )

        assert state.should_stop()

    def test_get_recent_patches(self):
        """Base: 최근 N개 패치"""
        budget = Budget()
        patches = [create_test_patch(f"p{i}", i) for i in range(10)]

        state = LoopState(
            task_id="task-1",
            status=LoopStatus.RUNNING,
            current_iteration=10,
            patches=patches,
            budget=budget,
        )

        recent = state.get_recent_patches(3)

        assert len(recent) == 3
        assert recent[0].id == "p7"
        assert recent[-1].id == "p9"

    def test_get_accepted_patches(self):
        """Base: Accepted 패치만 필터"""
        budget = Budget()
        patches = [
            create_test_patch("p1", 1).with_status(PatchStatus.ACCEPTED),
            create_test_patch("p2", 2).with_status(PatchStatus.FAILED),
            create_test_patch("p3", 3).with_status(PatchStatus.ACCEPTED),
        ]

        state = LoopState(
            task_id="task-1",
            status=LoopStatus.RUNNING,
            current_iteration=3,
            patches=patches,
            budget=budget,
        )

        accepted = state.get_accepted_patches()

        assert len(accepted) == 2
        assert all(p.is_accepted() for p in accepted)

    def test_update_best_patch(self):
        """Integration: Best patch 자동 업데이트"""
        budget = Budget()
        state = LoopState(
            task_id="task-1",
            status=LoopStatus.RUNNING,
            current_iteration=0,
            patches=[],
            budget=budget,
        )

        # First patch
        patch1 = create_test_patch("p1", 1, pass_rate=0.7)
        state = state.with_patch(patch1)
        assert state.best_patch == patch1

        # Better patch
        patch2 = create_test_patch("p2", 2, pass_rate=0.9)
        state = state.with_patch(patch2)
        assert state.best_patch == patch2

        # Worse patch (no update)
        patch3 = create_test_patch("p3", 3, pass_rate=0.6)
        state = state.with_patch(patch3)
        assert state.best_patch == patch2  # Still p2


# ========== Integration & Extreme Tests ==========


class TestIntegrationScenarios:
    """통합 시나리오"""

    def test_full_loop_simulation(self):
        """Integration: 전체 루프 시뮬레이션"""
        budget = Budget(max_iterations=5)
        state = LoopState(
            task_id="fix-bug-123",
            status=LoopStatus.RUNNING,
            current_iteration=0,
            patches=[],
            budget=budget,
        )

        # Iteration 1-4: Improving patches
        for i in range(4):
            patch = create_test_patch(f"p{i}", i + 1, pass_rate=0.5 + i * 0.1)
            state = state.with_patch(patch)
            state = state.next_iteration()

        assert state.current_iteration == 4
        assert len(state.patches) == 4
        assert state.best_patch.id == "p3"  # Best: 0.8 pass_rate
        assert not state.should_stop()  # Not converged yet

        # Iteration 5: Perfect patch
        final_patch = create_test_patch("p_final", 5, pass_rate=1.0)
        final_patch = final_patch.with_status(PatchStatus.ACCEPTED)
        state = state.with_patch(final_patch)
        state = state.with_status(LoopStatus.CONVERGED)

        assert state.status == LoopStatus.CONVERGED
        assert state.best_patch.test_results["pass_rate"] == 1.0
        assert state.should_stop()


class TestExtremeScenarios:
    """극한 시나리오"""

    def test_1000_patches(self):
        """Extreme: 1000개 패치"""
        budget = Budget(max_iterations=2000)
        state = LoopState(
            task_id="extreme",
            status=LoopStatus.RUNNING,
            current_iteration=0,
            patches=[],
            budget=budget,
        )

        for i in range(1000):
            patch = create_test_patch(f"p{i}", i)
            state = state.with_patch(patch)

        assert len(state.patches) == 1000
        recent = state.get_recent_patches(10)
        assert len(recent) == 10
