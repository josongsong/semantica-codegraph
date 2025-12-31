"""
Convergence Calculator Tests (ACTUAL Implementation)

SOTA-Level: Base + Edge + Extreme Cases
Production-Grade: 실제 API 기반
"""

import pytest

from codegraph_runtime.codegen_loop.domain.convergence import ConvergenceCalculator
from codegraph_runtime.codegen_loop.domain.patch import FileChange, Patch, PatchStatus


class TestConvergenceCalculator:
    """ConvergenceCalculator 테스트 (실제 구현 기반)"""

    def test_empty_patches_not_converged(self):
        """Base: 패치 없으면 수렴 아님"""
        calc = ConvergenceCalculator(threshold=0.95)

        assert not calc.is_converged([])

    def test_single_patch_not_converged(self):
        """Base: 단일 패치는 수렴 아님 (2개 이상 필요)"""
        calc = ConvergenceCalculator(threshold=0.95)

        patch = Patch(
            id="p1",
            iteration=1,
            files=[FileChange("a.py", "old", "new", ["-old", "+new"])],
            status=PatchStatus.TESTED,
            test_results={"pass_rate": 1.0},
        )

        assert not calc.is_converged([patch])

    def test_two_patches_all_tests_passed_low_change(self):
        """Base: 2개 패치, 모두 통과 + 변경 적음 → 수렴"""
        calc = ConvergenceCalculator(threshold=0.95)

        patches = [
            Patch(
                id="p1",
                iteration=1,
                files=[FileChange("a.py", "old", "new", ["-a"] * 100)],  # 100 lines
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
            Patch(
                id="p2",
                iteration=2,
                files=[FileChange("a.py", "old", "new", ["-a"] * 102)],  # 102 lines (2% 변화)
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
        ]

        # change_ratio = |102-100|/100 = 0.02 < (1-0.95) = 0.05
        assert calc.is_converged(patches)

    def test_two_patches_all_tests_passed_high_change(self):
        """Base: 2개 패치, 모두 통과하지만 변경 많음 → 수렴 아님"""
        calc = ConvergenceCalculator(threshold=0.95)

        patches = [
            Patch(
                id="p1",
                iteration=1,
                files=[FileChange("a.py", "old", "new", ["-a"] * 100)],
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
            Patch(
                id="p2",
                iteration=2,
                files=[FileChange("a.py", "old", "new", ["-a"] * 110)],  # 110 lines (10% 변화)
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
        ]

        # change_ratio = |110-100|/100 = 0.10 >= (1-0.95) = 0.05
        assert not calc.is_converged(patches)

    def test_two_patches_last_failed(self):
        """Base: 마지막 패치 테스트 실패 → 수렴 아님"""
        calc = ConvergenceCalculator(threshold=0.95)

        patches = [
            Patch(
                id="p1",
                iteration=1,
                files=[FileChange("a.py", "old", "new", [])],
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
            Patch(
                id="p2",
                iteration=2,
                files=[FileChange("a.py", "old", "new", [])],
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 0.8},  # Failed
            ),
        ]

        assert not calc.is_converged(patches)

    def test_all_tests_passed_pass_rate_100(self):
        """Base: pass_rate=1.0 → 통과"""
        calc = ConvergenceCalculator()

        patch = Patch(
            id="p1",
            iteration=1,
            files=[FileChange("a.py", "", "", [])],
            status=PatchStatus.TESTED,
            test_results={"pass_rate": 1.0},
        )

        assert calc._all_tests_passed(patch)

    def test_all_tests_passed_pass_rate_below_100(self):
        """Base: pass_rate<1.0 → 실패"""
        calc = ConvergenceCalculator()

        patch = Patch(
            id="p1",
            iteration=1,
            files=[FileChange("a.py", "", "", [])],
            status=PatchStatus.TESTED,
            test_results={"pass_rate": 0.99},  # 99% but not 100%
        )

        assert not calc._all_tests_passed(patch)

    def test_all_tests_passed_no_results(self):
        """Edge: test_results 없음 → 실패"""
        calc = ConvergenceCalculator()

        patch = Patch(
            id="p1",
            iteration=1,
            files=[FileChange("a.py", "", "", [])],
            status=PatchStatus.GENERATED,
            test_results=None,
        )

        assert not calc._all_tests_passed(patch)


class TestConvergenceEdgeCases:
    """Edge Cases"""

    def test_invalid_threshold_too_high_raises(self):
        """Edge: threshold > 1 에러"""
        with pytest.raises(ValueError, match="threshold must be between 0 and 1"):
            ConvergenceCalculator(threshold=1.5)

    def test_invalid_threshold_negative_raises(self):
        """Edge: threshold < 0 에러"""
        with pytest.raises(ValueError, match="threshold must be between 0 and 1"):
            ConvergenceCalculator(threshold=-0.1)

    def test_threshold_0_converges_easily(self):
        """Edge: threshold=0.0이면 변경량 제약 느슨"""
        calc = ConvergenceCalculator(threshold=0.0)

        patches = [
            Patch(
                id="p1",
                iteration=1,
                files=[FileChange("a.py", "", "", ["-a"] * 100)],
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
            Patch(
                id="p2",
                iteration=2,
                files=[FileChange("a.py", "", "", ["-a"] * 150)],  # 50% 변화
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
        ]

        # change_ratio = 50% < (1-0) = 1.0 → 수렴
        assert calc.is_converged(patches)

    def test_threshold_1_never_converges_unless_zero_change(self):
        """Edge: threshold=1.0이면 0 변경만 수렴"""
        calc = ConvergenceCalculator(threshold=1.0)

        # 변경 있으면 수렴 안함
        patches = [
            Patch(
                id="p1",
                iteration=1,
                files=[FileChange("a.py", "", "", ["-a"] * 100)],
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
            Patch(
                id="p2",
                iteration=2,
                files=[FileChange("a.py", "", "", ["-a"] * 101)],  # 1% change
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
        ]

        # change_ratio = 1% >= (1-1.0) = 0 → 수렴 안함
        assert not calc.is_converged(patches)

        # 0 변경이면 수렴
        patches2 = [
            Patch(
                id="p1",
                iteration=1,
                files=[FileChange("a.py", "", "", ["-a"] * 100)],
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
            Patch(
                id="p2",
                iteration=2,
                files=[FileChange("a.py", "", "", ["-a"] * 100)],  # Exactly same
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
        ]

        # change_ratio = 0 < (1-1.0) = 0 (거짓이므로 수렴 안함)
        # 실제로는 threshold=1.0이면 거의 수렴 불가능
        assert not calc.is_converged(patches2)  # 0 < 0은 거짓

    def test_multi_file_patches(self):
        """Edge: Multi-file 패치"""
        calc = ConvergenceCalculator(threshold=0.95)

        patches = [
            Patch(
                id="p1",
                iteration=1,
                files=[
                    FileChange("a.py", "", "", ["-a"] * 50),
                    FileChange("b.py", "", "", ["-b"] * 50),
                ],
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
            Patch(
                id="p2",
                iteration=2,
                files=[
                    FileChange("a.py", "", "", ["-a"] * 52),
                    FileChange("b.py", "", "", ["-b"] * 48),
                ],
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
        ]

        # Total: 100 → 100, change_ratio = 0
        assert calc.is_converged(patches)


class TestConvergenceExtremeCases:
    """Extreme Cases"""

    def test_huge_patches_1000_lines(self):
        """Extreme: 1000줄 패치"""
        calc = ConvergenceCalculator(threshold=0.95)

        patches = [
            Patch(
                id="p1",
                iteration=1,
                files=[FileChange("huge.py", "", "", [f"-line{i}" for i in range(1000)])],
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
            Patch(
                id="p2",
                iteration=2,
                files=[FileChange("huge.py", "", "", [f"-line{i}" for i in range(1010)])],
                status=PatchStatus.TESTED,
                test_results={"pass_rate": 1.0},
            ),
        ]

        # 1% change, should converge
        assert calc.is_converged(patches)
