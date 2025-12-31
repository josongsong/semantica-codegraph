"""
Architecture Spec (GraphSpec)

ADR-011 Section 9: ArchSpec - Layer Violation Detection
Production-Grade with Zero Fake/Stub
"""

from dataclasses import dataclass, field
from enum import Enum


class Layer(Enum):
    """아키텍처 레이어"""

    UI = "ui"
    APPLICATION = "application"
    DOMAIN = "domain"
    INFRASTRUCTURE = "infrastructure"
    DATABASE = "database"


@dataclass(frozen=True)
class LayerDependency:
    """
    레이어 간 의존성

    불변, 외부 의존 없음
    """

    from_layer: Layer
    to_layer: Layer

    def __post_init__(self):
        if self.from_layer == self.to_layer:
            raise ValueError("Layer cannot depend on itself")

    @property
    def is_forbidden(self) -> bool:
        """
        금지된 의존성인지 확인

        ADR-011 FORBIDDEN:
        - UI → Infrastructure
        - Domain → Infrastructure
        - UI → Database
        """
        forbidden_pairs = {
            (Layer.UI, Layer.INFRASTRUCTURE),
            (Layer.UI, Layer.DATABASE),
            (Layer.DOMAIN, Layer.INFRASTRUCTURE),
            (Layer.DOMAIN, Layer.DATABASE),
        }

        return (self.from_layer, self.to_layer) in forbidden_pairs


@dataclass(frozen=True)
class ImportViolation:
    """Import 위반"""

    from_file: str
    to_file: str
    from_layer: Layer
    to_layer: Layer
    line_number: int
    import_statement: str

    @property
    def violation_type(self) -> str:
        """위반 유형"""
        return f"{self.from_layer.value} → {self.to_layer.value}"


@dataclass
class ArchSpecValidationResult:
    """ArchSpec 검증 결과"""

    passed: bool
    violations: list[ImportViolation] = field(default_factory=list)
    dependencies_checked: int = 0

    @classmethod
    def success(cls, checked: int = 0) -> "ArchSpecValidationResult":
        """성공"""
        return cls(passed=True, dependencies_checked=checked)

    @classmethod
    def failure(
        cls,
        violations: list[ImportViolation],
        checked: int = 0,
    ) -> "ArchSpecValidationResult":
        """실패"""
        return cls(
            passed=False,
            violations=violations,
            dependencies_checked=checked,
        )


class ArchSpec:
    """
    Architecture Specification

    ADR-011 Section 9: Layer violation detection
    순수 로직, 외부 의존 없음
    """

    def __init__(self, custom_rules: list[tuple[Layer, Layer]] | None = None):
        """
        Args:
            custom_rules: 추가 금지 규칙 [(from, to), ...]
        """
        self.forbidden_dependencies = self._load_forbidden_dependencies()

        if custom_rules:
            for from_layer, to_layer in custom_rules:
                dep = LayerDependency(from_layer, to_layer)
                if dep.is_forbidden:
                    self.forbidden_dependencies.add((from_layer, to_layer))

    def _load_forbidden_dependencies(self) -> set[tuple[Layer, Layer]]:
        """
        기본 금지 의존성 (ADR-011)

        Returns:
            {(from, to), ...}
        """
        return {
            (Layer.UI, Layer.INFRASTRUCTURE),
            (Layer.UI, Layer.DATABASE),
            (Layer.DOMAIN, Layer.INFRASTRUCTURE),
            (Layer.DOMAIN, Layer.DATABASE),
        }

    def is_dependency_allowed(
        self,
        from_layer: Layer,
        to_layer: Layer,
    ) -> bool:
        """
        의존성 허용 여부

        Args:
            from_layer: 의존하는 레이어
            to_layer: 의존 대상 레이어

        Returns:
            허용 여부
        """
        if from_layer == to_layer:
            return True  # 같은 레이어는 허용

        return (from_layer, to_layer) not in self.forbidden_dependencies

    def validate_dependency(
        self,
        from_file: str,
        to_file: str,
        from_layer: Layer,
        to_layer: Layer,
        line_number: int = 0,
        import_stmt: str = "",
    ) -> ImportViolation | None:
        """
        단일 의존성 검증

        Args:
            from_file: 의존하는 파일
            to_file: 의존 대상 파일
            from_layer: 의존하는 레이어
            to_layer: 의존 대상 레이어
            line_number: Import 라인 번호
            import_stmt: Import 구문

        Returns:
            위반 시 ImportViolation, 아니면 None
        """
        if not self.is_dependency_allowed(from_layer, to_layer):
            return ImportViolation(
                from_file=from_file,
                to_file=to_file,
                from_layer=from_layer,
                to_layer=to_layer,
                line_number=line_number,
                import_statement=import_stmt,
            )

        return None

    def validate_dependencies(
        self,
        dependencies: list[tuple[str, str, Layer, Layer, int, str]],
    ) -> ArchSpecValidationResult:
        """
        여러 의존성 일괄 검증

        Args:
            dependencies: [(from_file, to_file, from_layer, to_layer, line, stmt), ...]

        Returns:
            검증 결과
        """
        violations = []

        for from_file, to_file, from_layer, to_layer, line, stmt in dependencies:
            violation = self.validate_dependency(from_file, to_file, from_layer, to_layer, line, stmt)
            if violation:
                violations.append(violation)

        if violations:
            return ArchSpecValidationResult.failure(
                violations=violations,
                checked=len(dependencies),
            )

        return ArchSpecValidationResult.success(checked=len(dependencies))

    def add_forbidden_dependency(self, from_layer: Layer, to_layer: Layer):
        """금지 의존성 추가"""
        self.forbidden_dependencies.add((from_layer, to_layer))

    def remove_forbidden_dependency(self, from_layer: Layer, to_layer: Layer):
        """금지 의존성 제거"""
        self.forbidden_dependencies.discard((from_layer, to_layer))
