"""
Dependency Analysis Tests

SOTA-Level: Cross-file Impact + Path Explosion
"""

import pytest

from codegraph_runtime.codegen_loop.domain.dependency import (
    DependencyAnalyzer,
    DependencyValidationResult,
    FunctionChange,
    ImpactZone,
    PathExplosionDetector,
)


class TestFunctionChange:
    """FunctionChange 테스트"""

    def test_valid_added_function(self):
        """Base: 추가된 함수"""
        change = FunctionChange(
            function_fqn="module.new_function",
            file_path="module.py",
            change_type="added",
        )

        assert change.function_fqn == "module.new_function"
        assert change.change_type == "added"

    def test_valid_modified_function(self):
        """Base: 수정된 함수"""
        change = FunctionChange(
            function_fqn="module.existing",
            file_path="module.py",
            change_type="modified",
        )

        assert change.change_type == "modified"

    def test_valid_deleted_function(self):
        """Base: 삭제된 함수"""
        change = FunctionChange(
            function_fqn="module.old",
            file_path="module.py",
            change_type="deleted",
        )

        assert change.change_type == "deleted"

    def test_invalid_change_type_raises(self):
        """Edge: 잘못된 change_type은 에러"""
        with pytest.raises(ValueError, match="change_type must be one of"):
            FunctionChange(
                function_fqn="module.func",
                file_path="module.py",
                change_type="invalid",
            )


class TestImpactZone:
    """ImpactZone 테스트"""

    def test_empty_impact_zone(self):
        """Base: 영향 없음"""
        zone = ImpactZone(
            changed_functions={"func_a"},
            affected_files=set(),
            affected_functions=set(),
            depth=2,
        )

        assert zone.is_empty()
        assert zone.total_impact == 0

    def test_single_file_impact(self):
        """Base: 단일 파일 영향"""
        zone = ImpactZone(
            changed_functions={"func_a"},
            affected_files={"caller.py"},
            affected_functions={"caller.func"},
            depth=2,
        )

        assert not zone.is_empty()
        assert zone.total_impact == 1
        assert zone.includes_file("caller.py")
        assert not zone.includes_file("other.py")

    def test_multi_file_impact(self):
        """Base: 여러 파일 영향"""
        zone = ImpactZone(
            changed_functions={"func_a", "func_b"},
            affected_files={"file1.py", "file2.py", "file3.py"},
            affected_functions={"f1", "f2", "f3"},
            depth=2,
        )

        assert zone.total_impact == 3
        assert all(zone.includes_file(f) for f in ["file1.py", "file2.py", "file3.py"])

    def test_extreme_impact_zone(self):
        """Extreme: 1000개 파일 영향"""
        affected = {f"file{i}.py" for i in range(1000)}
        zone = ImpactZone(
            changed_functions={"critical_func"},
            affected_files=affected,
            affected_functions=set(),
            depth=5,
        )

        assert zone.total_impact == 1000
        assert zone.includes_file("file500.py")


class TestDependencyAnalyzer:
    """DependencyAnalyzer 테스트"""

    def test_analyzer_creation(self):
        """Base: Analyzer 생성"""
        analyzer = DependencyAnalyzer(depth=2)

        assert analyzer.depth == 2

    def test_analyzer_invalid_depth_raises(self):
        """Edge: 음수 depth는 에러"""
        with pytest.raises(ValueError, match="depth must be >= 1"):
            DependencyAnalyzer(depth=0)

    def test_compute_impact_zone_no_dependencies(self):
        """Base: 의존성 없음"""
        analyzer = DependencyAnalyzer(depth=2)

        changed = [
            FunctionChange("func_a", "a.py", "added"),
        ]

        zone = analyzer.compute_impact_zone(
            changed_functions=changed,
            callers={},
            callees={},
        )

        assert zone.is_empty()
        assert zone.total_impact == 0

    def test_compute_impact_zone_with_callers(self):
        """Base: Caller 있는 경우"""
        analyzer = DependencyAnalyzer(depth=2)

        changed = [
            FunctionChange("module.func_a", "module.py", "modified"),
        ]

        callers = {
            "module.func_a": {"caller1.py", "caller2.py"},
        }

        zone = analyzer.compute_impact_zone(
            changed_functions=changed,
            callers=callers,
            callees={},
        )

        assert zone.total_impact == 2
        assert "caller1.py" in zone.affected_files
        assert "caller2.py" in zone.affected_files

    def test_compute_impact_zone_with_callees(self):
        """Base: Callee 있는 경우"""
        analyzer = DependencyAnalyzer(depth=2)

        changed = [
            FunctionChange("module.func_a", "module.py", "modified"),
        ]

        callees = {
            "module.func_a": {"callee1.py", "callee2.py"},
        }

        zone = analyzer.compute_impact_zone(
            changed_functions=changed,
            callers={},
            callees=callees,
        )

        assert zone.total_impact == 2
        assert "callee1.py" in zone.affected_files

    def test_validate_patch_completeness_success(self):
        """Base: 완전한 패치"""
        analyzer = DependencyAnalyzer()

        patch_files = {"a.py", "caller.py", "callee.py"}
        zone = ImpactZone(
            changed_functions={"func"},
            affected_files={"caller.py", "callee.py"},
            affected_functions=set(),
            depth=2,
        )

        result = analyzer.validate_patch_completeness(patch_files, zone)

        assert result.passed
        assert len(result.uncovered_files) == 0

    def test_validate_patch_completeness_incomplete(self):
        """Base: 불완전한 패치 (누락)"""
        analyzer = DependencyAnalyzer()

        patch_files = {"a.py", "caller.py"}  # callee.py 누락
        zone = ImpactZone(
            changed_functions={"func"},
            affected_files={"caller.py", "callee.py", "other.py"},
            affected_functions=set(),
            depth=2,
        )

        result = analyzer.validate_patch_completeness(patch_files, zone)

        assert not result.passed
        assert "callee.py" in result.uncovered_files
        assert "other.py" in result.uncovered_files
        assert "INCOMPLETE_PATCH" in result.reason

    def test_validate_patch_completeness_many_missing(self):
        """Edge: 많은 파일 누락 (5개 이상)"""
        analyzer = DependencyAnalyzer()

        patch_files = {"a.py"}
        affected = {f"file{i}.py" for i in range(10)}
        zone = ImpactZone(
            changed_functions={"func"},
            affected_files=affected,
            affected_functions=set(),
            depth=2,
        )

        result = analyzer.validate_patch_completeness(patch_files, zone)

        assert not result.passed
        assert len(result.uncovered_files) == 10
        # 메시지에 "..." 포함 (너무 많은 파일)
        assert "..." in result.reason or len(result.uncovered_files) <= 5


class TestPathExplosionDetector:
    """PathExplosionDetector 테스트"""

    def test_no_explosion(self):
        """Base: Explosion 없음"""
        detector = PathExplosionDetector(limit=10000)

        zone = ImpactZone(
            changed_functions={"func"},
            affected_files={f"file{i}.py" for i in range(100)},
            affected_functions=set(),
            depth=2,
        )

        assert not detector.is_exploded(zone)
        assert not detector.should_sample(zone)

    def test_explosion_detected(self):
        """Base: Explosion 감지"""
        detector = PathExplosionDetector(limit=10000)

        zone = ImpactZone(
            changed_functions={"critical_func"},
            affected_files={f"file{i}.py" for i in range(15000)},
            affected_functions=set(),
            depth=5,
        )

        assert detector.is_exploded(zone)
        assert detector.should_sample(zone)

    def test_exactly_at_limit(self):
        """Edge: 정확히 limit"""
        detector = PathExplosionDetector(limit=1000)

        zone = ImpactZone(
            changed_functions={"func"},
            affected_files={f"file{i}.py" for i in range(1000)},
            affected_functions=set(),
            depth=2,
        )

        assert not detector.is_exploded(zone)

    def test_one_over_limit(self):
        """Edge: limit + 1"""
        detector = PathExplosionDetector(limit=1000)

        zone = ImpactZone(
            changed_functions={"func"},
            affected_files={f"file{i}.py" for i in range(1001)},
            affected_functions=set(),
            depth=2,
        )

        assert detector.is_exploded(zone)

    def test_invalid_limit_raises(self):
        """Edge: 0 이하 limit은 에러"""
        with pytest.raises(ValueError, match="limit must be > 0"):
            PathExplosionDetector(limit=0)

        with pytest.raises(ValueError, match="limit must be > 0"):
            PathExplosionDetector(limit=-1)

    def test_custom_limit(self):
        """Base: 커스텀 limit"""
        detector = PathExplosionDetector(limit=100)

        zone = ImpactZone(
            changed_functions={"func"},
            affected_files={f"file{i}.py" for i in range(150)},
            affected_functions=set(),
            depth=2,
        )

        assert detector.is_exploded(zone)


# Integration Tests
class TestDependencyAnalysisIntegration:
    """통합 시나리오 테스트"""

    def test_full_validation_flow(self):
        """Integration: 전체 검증 흐름"""
        analyzer = DependencyAnalyzer(depth=2)

        # 1. 변경된 함수
        changed = [
            FunctionChange("auth.login", "auth.py", "modified"),
        ]

        # 2. Callers
        callers = {
            "auth.login": {"handlers/user.py", "api/routes.py"},
        }

        # 3. 영향 범위 계산
        zone = analyzer.compute_impact_zone(changed, callers, {})

        assert zone.total_impact == 2

        # 4. 패치 검증 (불완전)
        patch_files = {"auth.py", "handlers/user.py"}  # api/routes.py 누락
        result = analyzer.validate_patch_completeness(patch_files, zone)

        assert not result.passed
        assert "api/routes.py" in result.uncovered_files

    def test_complete_patch_with_explosion_check(self):
        """Integration: 완전한 패치 + Explosion 체크"""
        analyzer = DependencyAnalyzer(depth=3)
        detector = PathExplosionDetector(limit=100)

        # 많은 caller
        callers = {
            "core.func": {f"module{i}/file.py" for i in range(200)},
        }

        changed = [FunctionChange("core.func", "core.py", "modified")]
        zone = analyzer.compute_impact_zone(changed, callers, {})

        # Explosion 발생
        assert detector.is_exploded(zone)

        # 패치는 모든 파일 포함 (비현실적이지만 테스트)
        patch_files = {"core.py"} | zone.affected_files
        result = analyzer.validate_patch_completeness(patch_files, zone)

        assert result.passed


@pytest.mark.parametrize(
    "changed,callers,callees,expected_min_impact",
    [
        # 단일 함수, 2 callers
        (
            [FunctionChange("f", "a.py", "modified")],
            {"f": {"b.py", "c.py"}},
            {},
            2,
        ),
        # 단일 함수, 1 caller + 1 callee
        (
            [FunctionChange("f", "a.py", "modified")],
            {"f": {"b.py"}},
            {"f": {"c.py"}},
            2,
        ),
        # 여러 함수
        (
            [
                FunctionChange("f1", "a.py", "modified"),
                FunctionChange("f2", "b.py", "modified"),
            ],
            {"f1": {"c.py"}, "f2": {"d.py"}},
            {},
            2,
        ),
    ],
)
def test_impact_zone_scenarios(changed, callers, callees, expected_min_impact):
    """Parametrize: 다양한 시나리오"""
    analyzer = DependencyAnalyzer(depth=2)

    zone = analyzer.compute_impact_zone(changed, callers, callees)

    assert zone.total_impact >= expected_min_impact
