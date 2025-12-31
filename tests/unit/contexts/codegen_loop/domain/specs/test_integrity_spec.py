"""
Integrity Spec Tests

SOTA-Level: Resource Leak Detection
"""

import pytest

from codegraph_runtime.codegen_loop.domain.specs.integrity_spec import (
    IntegritySpec,
    ResourceLeakViolation,
    ResourcePath,
    ResourcePattern,
    ResourceType,
)


class TestResourcePattern:
    """ResourcePattern 테스트"""

    def test_valid_pattern(self):
        """Base: 유효한 패턴"""
        pattern = ResourcePattern(
            resource_type=ResourceType.FILE,
            open_patterns={"open", "file"},
            close_patterns={"close"},
        )

        assert pattern.resource_type == ResourceType.FILE
        assert "open" in pattern.open_patterns
        assert "close" in pattern.close_patterns

    def test_empty_open_patterns_raises(self):
        """Edge: 빈 open 패턴은 에러"""
        with pytest.raises(ValueError, match="open_patterns cannot be empty"):
            ResourcePattern(
                resource_type=ResourceType.FILE,
                open_patterns=set(),
                close_patterns={"close"},
            )

    def test_empty_close_patterns_raises(self):
        """Edge: 빈 close 패턴은 에러"""
        with pytest.raises(ValueError, match="close_patterns cannot be empty"):
            ResourcePattern(
                resource_type=ResourceType.FILE,
                open_patterns={"open"},
                close_patterns=set(),
            )


class TestResourcePath:
    """ResourcePath 테스트"""

    def test_path_with_close(self):
        """Base: Close 있는 경로"""
        path = ResourcePath(
            resource_type=ResourceType.FILE,
            open_node="open('file.txt')",
            close_nodes={"f.close()"},
            path_nodes=["open", "use", "close"],
        )

        assert path.has_close
        assert not path.is_leaked

    def test_path_without_close(self):
        """Base: Close 없는 경로 (누수)"""
        path = ResourcePath(
            resource_type=ResourceType.FILE,
            open_node="open('file.txt')",
            close_nodes=set(),
            path_nodes=["open", "use"],
        )

        assert not path.has_close
        assert path.is_leaked

    def test_path_with_multiple_closes(self):
        """Edge: 여러 close (예: exception handling)"""
        path = ResourcePath(
            resource_type=ResourceType.CONNECTION,
            open_node="connect()",
            close_nodes={"conn.close()", "finally: conn.dispose()"},
            path_nodes=["connect", "use", "close", "dispose"],
        )

        assert path.has_close
        assert len(path.close_nodes) == 2


class TestIntegritySpec:
    """IntegritySpec 테스트"""

    def test_default_resources_loaded(self):
        """Base: 기본 리소스 로드"""
        spec = IntegritySpec()

        assert ResourceType.FILE in spec.resources
        assert ResourceType.CONNECTION in spec.resources
        assert ResourceType.LOCK in spec.resources

        file_pattern = spec.resources[ResourceType.FILE]
        assert "open" in file_pattern.open_patterns
        assert "close" in file_pattern.close_patterns

    def test_validate_file_leak(self):
        """Base: 파일 누수 감지"""
        spec = IntegritySpec()

        path = ResourcePath(
            resource_type=ResourceType.FILE,
            open_node="open('data.txt')",
            close_nodes=set(),
            path_nodes=["open", "read"],
        )

        violation = spec.validate_resource_path(path)

        assert violation is not None
        assert violation.resource_type == ResourceType.FILE
        assert violation.severity == "critical"
        assert "never closed" in violation.description

    def test_validate_file_safe(self):
        """Base: 파일 안전 (close 호출)"""
        spec = IntegritySpec()

        path = ResourcePath(
            resource_type=ResourceType.FILE,
            open_node="open('data.txt')",
            close_nodes={"f.close()"},
            path_nodes=["open", "read", "close"],
        )

        violation = spec.validate_resource_path(path)

        assert violation is None

    def test_validate_connection_leak(self):
        """Base: Connection 누수 감지"""
        spec = IntegritySpec()

        path = ResourcePath(
            resource_type=ResourceType.CONNECTION,
            open_node="connect()",
            close_nodes=set(),
            path_nodes=["connect", "query"],
        )

        violation = spec.validate_resource_path(path)

        assert violation is not None
        assert violation.severity == "critical"

    def test_validate_transaction_leak(self):
        """Base: Transaction 누수 감지"""
        spec = IntegritySpec()

        path = ResourcePath(
            resource_type=ResourceType.TRANSACTION,
            open_node="begin()",
            close_nodes=set(),
            path_nodes=["begin", "execute"],
        )

        violation = spec.validate_resource_path(path)

        assert violation is not None
        assert violation.severity == "critical"

    def test_validate_lock_leak(self):
        """Base: Lock 누수 감지"""
        spec = IntegritySpec()

        path = ResourcePath(
            resource_type=ResourceType.LOCK,
            open_node="lock.acquire()",
            close_nodes=set(),
            path_nodes=["acquire", "critical_section"],
        )

        violation = spec.validate_resource_path(path)

        assert violation is not None
        assert violation.severity == "high"

    def test_validate_resource_paths_batch(self):
        """Base: 여러 리소스 경로 검증"""
        spec = IntegritySpec()

        paths = [
            ResourcePath(ResourceType.FILE, "open1", set(), ["open1"]),
            ResourcePath(ResourceType.CONNECTION, "conn", set(), ["conn"]),
        ]

        result = spec.validate_resource_paths(paths)

        assert not result.passed
        assert len(result.violations) == 2
        assert result.leaked_resources == 2

    def test_validate_resource_paths_all_safe(self):
        """Base: 모든 리소스 안전"""
        spec = IntegritySpec()

        paths = [
            ResourcePath(ResourceType.FILE, "open", {"close"}, ["open", "close"]),
        ]

        result = spec.validate_resource_paths(paths)

        assert result.passed
        assert len(result.violations) == 0

    def test_add_custom_resource(self):
        """Base: 커스텀 리소스 추가"""
        spec = IntegritySpec()

        spec.add_custom_resource(
            ResourceType.FILE,
            open_patterns={"custom_open"},
            close_patterns={"custom_close"},
        )

        assert "custom_open" in spec.resources[ResourceType.FILE].open_patterns
        assert "custom_close" in spec.resources[ResourceType.FILE].close_patterns
        assert "open" in spec.resources[ResourceType.FILE].open_patterns  # 기존 유지

    def test_context_manager_close(self):
        """Edge: Context manager (__exit__)"""
        spec = IntegritySpec()

        path = ResourcePath(
            resource_type=ResourceType.FILE,
            open_node="with open('f') as f:",
            close_nodes={"__exit__"},
            path_nodes=["open", "__enter__", "use", "__exit__"],
        )

        violation = spec.validate_resource_path(path)

        assert violation is None  # Context manager는 안전


# Extreme Cases
class TestExtremeCases:
    """극한 케이스"""

    def test_1000_resource_paths(self):
        """Extreme: 1000개 리소스 경로"""
        spec = IntegritySpec()

        paths = [ResourcePath(ResourceType.FILE, f"open{i}", set(), [f"open{i}"]) for i in range(1000)]

        result = spec.validate_resource_paths(paths)

        assert not result.passed
        assert result.leaked_resources == 1000

    def test_nested_resources(self):
        """Edge: 중첩 리소스 (file in file)"""
        spec = IntegritySpec()

        # 두 파일 모두 닫아야 함
        paths = [
            ResourcePath(
                ResourceType.FILE,
                "open('outer.txt')",
                {"outer.close()"},
                ["open_outer", "close_outer"],
            ),
            ResourcePath(
                ResourceType.FILE,
                "open('inner.txt')",
                set(),  # 내부 파일 닫지 않음
                ["open_inner", "use"],
            ),
        ]

        result = spec.validate_resource_paths(paths)

        assert not result.passed
        assert result.leaked_resources == 1  # 내부 파일만 누수


@pytest.mark.parametrize(
    "resource_type,expected_severity",
    [
        (ResourceType.FILE, "critical"),
        (ResourceType.CONNECTION, "critical"),
        (ResourceType.TRANSACTION, "critical"),
        (ResourceType.LOCK, "high"),
        (ResourceType.SOCKET, "high"),
    ],
)
def test_severity_by_resource_type(resource_type, expected_severity):
    """Parametrize: 리소스 타입별 심각도"""
    spec = IntegritySpec()

    path = ResourcePath(
        resource_type=resource_type,
        open_node="open",
        close_nodes=set(),
        path_nodes=["open"],
    )

    violation = spec.validate_resource_path(path)

    assert violation is not None
    assert violation.severity == expected_severity
