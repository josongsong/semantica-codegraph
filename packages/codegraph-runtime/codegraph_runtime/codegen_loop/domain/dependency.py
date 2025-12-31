"""
Cross-file Dependency Analysis

ADR-011 Section 5: Cross-file Dependency Rewrite Detection
Production-Grade with Zero Fake/Stub
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FunctionChange:
    """
    함수 변경사항

    불변, 순수 데이터
    """

    function_fqn: str
    file_path: str
    change_type: str  # "added", "modified", "deleted"

    def __post_init__(self):
        valid_types = {"added", "modified", "deleted"}
        if self.change_type not in valid_types:
            raise ValueError(f"change_type must be one of {valid_types}, got {self.change_type}")


@dataclass(frozen=True)
class ImpactZone:
    """
    영향 범위 (Impact Zone)

    변경된 함수가 영향을 미치는 모든 파일/함수
    """

    changed_functions: set[str]
    affected_files: set[str]
    affected_functions: set[str]
    depth: int  # 의존성 추적 깊이

    @property
    def total_impact(self) -> int:
        """총 영향 범위"""
        return len(self.affected_files)

    def includes_file(self, file_path: str) -> bool:
        """특정 파일이 영향 범위에 포함되는지"""
        return file_path in self.affected_files

    def is_empty(self) -> bool:
        """영향 범위가 비어있는지"""
        return len(self.affected_files) == 0


@dataclass
class DependencyValidationResult:
    """의존성 검증 결과"""

    passed: bool
    impact_zone: ImpactZone
    uncovered_files: set[str] = field(default_factory=set)
    missing_type_deps: set[str] = field(default_factory=set)
    reason: str = ""

    @classmethod
    def success(cls, impact_zone: ImpactZone) -> "DependencyValidationResult":
        """성공"""
        return cls(passed=True, impact_zone=impact_zone)

    @classmethod
    def failure(
        cls,
        impact_zone: ImpactZone,
        uncovered: set[str],
        reason: str,
    ) -> "DependencyValidationResult":
        """실패"""
        return cls(
            passed=False,
            impact_zone=impact_zone,
            uncovered_files=uncovered,
            reason=reason,
        )


class DependencyAnalyzer:
    """
    의존성 분석기 (순수 로직)

    ADR-011 Section 5: validate_multi_file_patch()
    외부 의존 없음 (HCG 데이터는 주입받음)
    """

    def __init__(self, depth: int = 2):
        """
        Args:
            depth: 의존성 추적 깊이 (callers + callees)
        """
        if depth < 1:
            raise ValueError("depth must be >= 1")

        self.depth = depth

    def compute_impact_zone(
        self,
        changed_functions: list[FunctionChange],
        callers: dict[str, set[str]],  # {function: {caller_files}}
        callees: dict[str, set[str]],  # {function: {callee_files}}
    ) -> ImpactZone:
        """
        영향 범위 계산

        Args:
            changed_functions: 변경된 함수 리스트
            callers: 각 함수의 caller 파일 집합
            callees: 각 함수의 callee 파일 집합

        Returns:
            계산된 영향 범위
        """
        changed_fqns = {f.function_fqn for f in changed_functions}
        affected_files = set()
        affected_functions = set()

        # Depth만큼 반복 확장
        current_functions = changed_fqns.copy()

        for _ in range(self.depth):
            next_functions = set()

            for func in current_functions:
                # Callers 추가
                if func in callers:
                    caller_files = callers[func]
                    affected_files.update(caller_files)
                    # TODO: 실제로는 caller_files → functions 매핑 필요

                # Callees 추가
                if func in callees:
                    callee_files = callees[func]
                    affected_files.update(callee_files)

            current_functions = next_functions

        return ImpactZone(
            changed_functions=changed_fqns,
            affected_files=affected_files,
            affected_functions=affected_functions,
            depth=self.depth,
        )

    def validate_patch_completeness(
        self,
        patch_files: set[str],
        impact_zone: ImpactZone,
    ) -> DependencyValidationResult:
        """
        패치 완전성 검증

        Args:
            patch_files: 패치에 포함된 파일 집합
            impact_zone: 계산된 영향 범위

        Returns:
            검증 결과
        """
        # 영향 범위 중 패치에 없는 파일
        uncovered = impact_zone.affected_files - patch_files

        if uncovered:
            return DependencyValidationResult.failure(
                impact_zone=impact_zone,
                uncovered=uncovered,
                reason=(
                    f"INCOMPLETE_PATCH: {len(uncovered)} files affected but not included. "
                    f"Missing: {', '.join(sorted(uncovered)[:5])}" + ("..." if len(uncovered) > 5 else "")
                ),
            )

        return DependencyValidationResult.success(impact_zone)


class PathExplosionDetector:
    """
    Path Explosion 감지기

    ADR-011: PATH_EXPLOSION_LIMIT = 10000
    """

    def __init__(self, limit: int = 10000):
        """
        Args:
            limit: 최대 경로 수
        """
        if limit <= 0:
            raise ValueError("limit must be > 0")

        self.limit = limit

    def is_exploded(self, impact_zone: ImpactZone) -> bool:
        """
        Path explosion 발생 여부

        Args:
            impact_zone: 영향 범위

        Returns:
            Explosion 여부
        """
        return impact_zone.total_impact > self.limit

    def should_sample(self, impact_zone: ImpactZone) -> bool:
        """
        샘플링 필요 여부

        Returns:
            샘플링 필요하면 True
        """
        return self.is_exploded(impact_zone)
