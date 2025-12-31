"""
TestAdequacy Domain Model Tests

SOTA L11급:
- Base, Edge, Corner cases
- MC/DC validation
- Domain-specific thresholds
"""

import pytest

from codegraph_runtime.codegen_loop.domain.test_adequacy import TestAdequacy


class TestTestAdequacyBase:
    """Base cases - 정상 동작"""

    def test_adequate_default_domain(self):
        """기본 도메인 적정성 (60%)"""
        adequacy = TestAdequacy(
            branch_coverage=0.65,
            condition_coverage={"c1": {True: True, False: True}},
            error_path_count=1,
            flakiness_ratio=0.1,
        )

        assert adequacy.is_adequate("default")
        assert adequacy.get_coverage_gap("default") < 0  # 초과

    def test_inadequate_low_coverage(self):
        """커버리지 부족 (50% < 60%)"""
        adequacy = TestAdequacy(
            branch_coverage=0.50,
            condition_coverage={},
            error_path_count=1,
            flakiness_ratio=0.1,
        )

        assert not adequacy.is_adequate("default")
        assert adequacy.get_coverage_gap("default") == pytest.approx(0.10)

    def test_inadequate_flaky(self):
        """Flaky 테스트 (40% > 30%)"""
        adequacy = TestAdequacy(
            branch_coverage=0.70,
            condition_coverage={},
            error_path_count=1,
            flakiness_ratio=0.40,
        )

        assert not adequacy.is_adequate()


class TestTestAdequacyEdge:
    """Edge cases - 경계 조건"""

    def test_exactly_60_percent(self):
        """정확히 60% (경계값)"""
        adequacy = TestAdequacy(
            branch_coverage=0.60,
            condition_coverage={},
            error_path_count=1,
            flakiness_ratio=0.0,
        )

        assert adequacy.is_adequate("default")
        assert adequacy.get_coverage_gap("default") == 0.0

    def test_exactly_30_percent_flakiness(self):
        """정확히 30% flakiness (경계값)"""
        adequacy = TestAdequacy(
            branch_coverage=0.70,
            condition_coverage={},
            error_path_count=1,
            flakiness_ratio=0.30,
        )

        # < 0.3 이어야 통과 (0.3은 실패)
        assert not adequacy.is_adequate()

    def test_zero_error_path(self):
        """Error path 없음"""
        adequacy = TestAdequacy(
            branch_coverage=0.70,
            condition_coverage={},
            error_path_count=0,
            flakiness_ratio=0.1,
        )

        assert not adequacy.is_adequate()

    def test_no_conditions(self):
        """조건문 없음 (MC/DC 통과)"""
        adequacy = TestAdequacy(
            branch_coverage=0.70,
            condition_coverage={},
            error_path_count=1,
            flakiness_ratio=0.1,
        )

        assert adequacy.is_adequate()


class TestTestAdequacyCorner:
    """Corner cases - 특수 케이스"""

    def test_payment_domain_high_threshold(self):
        """Payment 도메인 (90% 요구)"""
        # 80%는 default에선 충분하지만 payment에선 부족
        adequacy = TestAdequacy(
            branch_coverage=0.80,
            condition_coverage={},
            error_path_count=1,
            flakiness_ratio=0.1,
        )

        assert adequacy.is_adequate("default")  # 60% 요구
        assert not adequacy.is_adequate("payment")  # 90% 요구

    def test_auth_domain_perfect_coverage(self):
        """Auth 도메인 (100% 요구)"""
        adequacy = TestAdequacy(
            branch_coverage=0.99,
            condition_coverage={},
            error_path_count=1,
            flakiness_ratio=0.0,
        )

        assert not adequacy.is_adequate("auth")  # 99% < 100%

    def test_mc_dc_incomplete_true_only(self):
        """MC/DC 불완전 (True만 테스트)"""
        adequacy = TestAdequacy(
            branch_coverage=0.70,
            condition_coverage={"c1": {True: True, False: False}},  # False 미실행
            error_path_count=1,
            flakiness_ratio=0.1,
        )

        assert not adequacy.is_adequate()

    def test_mc_dc_incomplete_false_only(self):
        """MC/DC 불완전 (False만 테스트)"""
        adequacy = TestAdequacy(
            branch_coverage=0.70,
            condition_coverage={"c1": {True: False, False: True}},  # True 미실행
            error_path_count=1,
            flakiness_ratio=0.1,
        )

        assert not adequacy.is_adequate()

    def test_mc_dc_multiple_conditions(self):
        """여러 조건문 MC/DC"""
        adequacy = TestAdequacy(
            branch_coverage=0.70,
            condition_coverage={
                "c1": {True: True, False: True},
                "c2": {True: True, False: True},
                "c3": {True: True, False: False},  # c3만 불완전
            },
            error_path_count=1,
            flakiness_ratio=0.1,
        )

        assert not adequacy.is_adequate()  # 하나라도 불완전하면 실패

    def test_immutability(self):
        """불변성"""
        adequacy = TestAdequacy(
            branch_coverage=0.70,
            condition_coverage={},
            error_path_count=1,
            flakiness_ratio=0.1,
        )

        with pytest.raises(AttributeError):
            adequacy.branch_coverage = 0.80  # type: ignore

    def test_branch_coverage_100_percent(self):
        """100% branch coverage"""
        adequacy = TestAdequacy(
            branch_coverage=1.0,
            condition_coverage={},
            error_path_count=1,
            flakiness_ratio=0.0,
        )
        assert adequacy.is_adequate("auth")  # Even auth (100% required) passes

    def test_branch_coverage_0_percent(self):
        """0% branch coverage"""
        adequacy = TestAdequacy(
            branch_coverage=0.0,
            condition_coverage={},
            error_path_count=1,
            flakiness_ratio=0.0,
        )
        assert not adequacy.is_adequate()

    def test_branch_coverage_invalid_negative(self):
        """Invalid: negative coverage"""
        with pytest.raises((ValueError, AssertionError)):
            TestAdequacy(
                branch_coverage=-0.1,
                condition_coverage={},
                error_path_count=1,
                flakiness_ratio=0.0,
            )

    def test_branch_coverage_invalid_over_100(self):
        """Invalid: > 100% coverage"""
        with pytest.raises((ValueError, AssertionError)):
            TestAdequacy(
                branch_coverage=1.5,
                condition_coverage={},
                error_path_count=1,
                flakiness_ratio=0.0,
            )

    def test_error_path_count_negative(self):
        """Invalid: negative error path count"""
        with pytest.raises((ValueError, AssertionError)):
            TestAdequacy(
                branch_coverage=0.7,
                condition_coverage={},
                error_path_count=-1,
                flakiness_ratio=0.0,
            )

    def test_flakiness_100_percent(self):
        """100% flaky (완전히 불안정)"""
        adequacy = TestAdequacy(
            branch_coverage=0.9,
            condition_coverage={},
            error_path_count=1,
            flakiness_ratio=1.0,
        )
        assert not adequacy.is_adequate()

    def test_large_error_path_count(self):
        """매우 많은 error paths (1000개)"""
        adequacy = TestAdequacy(
            branch_coverage=0.7,
            condition_coverage={},
            error_path_count=1000,
            flakiness_ratio=0.0,
        )
        assert adequacy.is_adequate()

    def test_many_conditions_mc_dc(self):
        """많은 조건문 (100개) MC/DC"""
        conditions = {f"c{i}": {True: True, False: True} for i in range(100)}
        adequacy = TestAdequacy(
            branch_coverage=0.7,
            condition_coverage=conditions,
            error_path_count=1,
            flakiness_ratio=0.0,
        )
        assert adequacy.is_adequate()
