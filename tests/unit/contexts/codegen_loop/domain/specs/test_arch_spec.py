"""
Architecture Spec Tests

SOTA-Level: Layer Violation Detection
"""

import pytest

from codegraph_runtime.codegen_loop.domain.specs.arch_spec import (
    ArchSpec,
    ImportViolation,
    Layer,
    LayerDependency,
)


class TestLayerDependency:
    """LayerDependency 테스트"""

    def test_valid_dependency(self):
        """Base: 유효한 의존성"""
        dep = LayerDependency(Layer.UI, Layer.APPLICATION)

        assert dep.from_layer == Layer.UI
        assert dep.to_layer == Layer.APPLICATION

    def test_self_dependency_raises(self):
        """Edge: 자기 의존은 에러"""
        with pytest.raises(ValueError, match="Layer cannot depend on itself"):
            LayerDependency(Layer.UI, Layer.UI)

    def test_forbidden_ui_to_infrastructure(self):
        """Base: UI → Infrastructure 금지"""
        dep = LayerDependency(Layer.UI, Layer.INFRASTRUCTURE)

        assert dep.is_forbidden

    def test_forbidden_ui_to_database(self):
        """Base: UI → Database 금지"""
        dep = LayerDependency(Layer.UI, Layer.DATABASE)

        assert dep.is_forbidden

    def test_forbidden_domain_to_infrastructure(self):
        """Base: Domain → Infrastructure 금지"""
        dep = LayerDependency(Layer.DOMAIN, Layer.INFRASTRUCTURE)

        assert dep.is_forbidden

    def test_allowed_ui_to_application(self):
        """Base: UI → Application 허용"""
        dep = LayerDependency(Layer.UI, Layer.APPLICATION)

        assert not dep.is_forbidden

    def test_allowed_application_to_domain(self):
        """Base: Application → Domain 허용"""
        dep = LayerDependency(Layer.APPLICATION, Layer.DOMAIN)

        assert not dep.is_forbidden

    def test_allowed_infrastructure_to_domain(self):
        """Base: Infrastructure → Domain 허용 (Adapter pattern)"""
        dep = LayerDependency(Layer.INFRASTRUCTURE, Layer.DOMAIN)

        assert not dep.is_forbidden


class TestArchSpec:
    """ArchSpec 테스트"""

    def test_default_forbidden_dependencies(self):
        """Base: 기본 금지 의존성 로드"""
        spec = ArchSpec()

        assert (Layer.UI, Layer.INFRASTRUCTURE) in spec.forbidden_dependencies
        assert (Layer.UI, Layer.DATABASE) in spec.forbidden_dependencies
        assert (Layer.DOMAIN, Layer.INFRASTRUCTURE) in spec.forbidden_dependencies
        assert (Layer.DOMAIN, Layer.DATABASE) in spec.forbidden_dependencies

    def test_is_dependency_allowed_forbidden(self):
        """Base: 금지된 의존성"""
        spec = ArchSpec()

        assert not spec.is_dependency_allowed(Layer.UI, Layer.INFRASTRUCTURE)
        assert not spec.is_dependency_allowed(Layer.DOMAIN, Layer.DATABASE)

    def test_is_dependency_allowed_same_layer(self):
        """Edge: 같은 레이어는 허용"""
        spec = ArchSpec()

        assert spec.is_dependency_allowed(Layer.DOMAIN, Layer.DOMAIN)

    def test_is_dependency_allowed_valid(self):
        """Base: 허용된 의존성"""
        spec = ArchSpec()

        assert spec.is_dependency_allowed(Layer.UI, Layer.APPLICATION)
        assert spec.is_dependency_allowed(Layer.APPLICATION, Layer.DOMAIN)

    def test_validate_dependency_violation(self):
        """Base: 의존성 위반 감지"""
        spec = ArchSpec()

        violation = spec.validate_dependency(
            from_file="ui/component.py",
            to_file="infrastructure/db.py",
            from_layer=Layer.UI,
            to_layer=Layer.INFRASTRUCTURE,
            line_number=10,
            import_stmt="from infrastructure.db import Session",
        )

        assert violation is not None
        assert violation.from_layer == Layer.UI
        assert violation.to_layer == Layer.INFRASTRUCTURE
        assert violation.line_number == 10

    def test_validate_dependency_allowed(self):
        """Base: 허용된 의존성"""
        spec = ArchSpec()

        violation = spec.validate_dependency(
            from_file="ui/component.py",
            to_file="application/service.py",
            from_layer=Layer.UI,
            to_layer=Layer.APPLICATION,
            line_number=5,
            import_stmt="from application.service import UserService",
        )

        assert violation is None

    def test_validate_dependencies_batch(self):
        """Base: 여러 의존성 일괄 검증"""
        spec = ArchSpec()

        dependencies = [
            ("ui/a.py", "app/b.py", Layer.UI, Layer.APPLICATION, 1, "import app"),
            ("ui/c.py", "infra/d.py", Layer.UI, Layer.INFRASTRUCTURE, 2, "import infra"),  # 위반
            ("domain/e.py", "infra/f.py", Layer.DOMAIN, Layer.INFRASTRUCTURE, 3, "import infra"),  # 위반
        ]

        result = spec.validate_dependencies(dependencies)

        assert not result.passed
        assert len(result.violations) == 2
        assert result.dependencies_checked == 3

    def test_validate_dependencies_all_allowed(self):
        """Base: 모든 의존성 허용"""
        spec = ArchSpec()

        dependencies = [
            ("ui/a.py", "app/b.py", Layer.UI, Layer.APPLICATION, 1, ""),
            ("app/c.py", "domain/d.py", Layer.APPLICATION, Layer.DOMAIN, 2, ""),
        ]

        result = spec.validate_dependencies(dependencies)

        assert result.passed
        assert len(result.violations) == 0

    def test_add_custom_forbidden_dependency(self):
        """Base: 커스텀 금지 규칙 추가"""
        spec = ArchSpec()

        # 새 금지 규칙: Application → UI (보통은 허용)
        spec.add_forbidden_dependency(Layer.APPLICATION, Layer.UI)

        assert (Layer.APPLICATION, Layer.UI) in spec.forbidden_dependencies
        assert not spec.is_dependency_allowed(Layer.APPLICATION, Layer.UI)

    def test_remove_forbidden_dependency(self):
        """Edge: 금지 규칙 제거"""
        spec = ArchSpec()

        # 기존 금지 규칙 제거
        spec.remove_forbidden_dependency(Layer.UI, Layer.INFRASTRUCTURE)

        assert (Layer.UI, Layer.INFRASTRUCTURE) not in spec.forbidden_dependencies
        assert spec.is_dependency_allowed(Layer.UI, Layer.INFRASTRUCTURE)


class TestImportViolation:
    """ImportViolation 테스트"""

    def test_violation_type_property(self):
        """Base: 위반 유형 문자열"""
        violation = ImportViolation(
            from_file="ui/a.py",
            to_file="infra/b.py",
            from_layer=Layer.UI,
            to_layer=Layer.INFRASTRUCTURE,
            line_number=10,
            import_statement="from infra import db",
        )

        assert violation.violation_type == "ui → infrastructure"


# Extreme Cases
@pytest.mark.parametrize(
    "from_layer,to_layer,expected_forbidden",
    [
        (Layer.UI, Layer.INFRASTRUCTURE, True),
        (Layer.UI, Layer.DATABASE, True),
        (Layer.DOMAIN, Layer.INFRASTRUCTURE, True),
        (Layer.DOMAIN, Layer.DATABASE, True),
        (Layer.UI, Layer.APPLICATION, False),
        (Layer.APPLICATION, Layer.DOMAIN, False),
        (Layer.INFRASTRUCTURE, Layer.DOMAIN, False),
    ],
)
def test_forbidden_dependency_matrix(from_layer, to_layer, expected_forbidden):
    """Parametrize: 금지 의존성 매트릭스"""
    dep = LayerDependency(from_layer, to_layer)

    assert dep.is_forbidden == expected_forbidden
