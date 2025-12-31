"""
Integrity Spec (GraphSpec)

ADR-011 Section 9: IntegritySpec - Resource Leak Detection
Production-Grade with Zero Fake/Stub
"""

from dataclasses import dataclass, field
from enum import Enum


class ResourceType(Enum):
    """리소스 유형"""

    FILE = "file"
    CONNECTION = "connection"
    LOCK = "lock"
    SOCKET = "socket"
    TRANSACTION = "transaction"


@dataclass(frozen=True)
class ResourcePattern:
    """
    리소스 패턴

    open/close 쌍 정의
    """

    resource_type: ResourceType
    open_patterns: set[str]  # {"open", "connect", ...}
    close_patterns: set[str]  # {"close", "disconnect", ...}

    def __post_init__(self):
        if not self.open_patterns:
            raise ValueError("open_patterns cannot be empty")
        if not self.close_patterns:
            raise ValueError("close_patterns cannot be empty")


@dataclass(frozen=True)
class ResourcePath:
    """
    리소스 생명주기 경로

    open → ... → close
    """

    resource_type: ResourceType
    open_node: str
    close_nodes: set[str]  # 여러 close가 있을 수 있음
    path_nodes: list[str]

    @property
    def has_close(self) -> bool:
        """Close 호출이 있는지"""
        return len(self.close_nodes) > 0

    @property
    def is_leaked(self) -> bool:
        """리소스 누수 여부"""
        return not self.has_close


@dataclass
class ResourceLeakViolation:
    """리소스 누수 위반"""

    resource_type: ResourceType
    path: ResourcePath
    severity: str  # "critical", "high", "medium"
    description: str

    def __post_init__(self):
        valid_severities = {"critical", "high", "medium"}
        if self.severity not in valid_severities:
            raise ValueError(f"severity must be one of {valid_severities}")


@dataclass
class IntegritySpecValidationResult:
    """IntegritySpec 검증 결과"""

    passed: bool
    violations: list[ResourceLeakViolation] = field(default_factory=list)
    paths_checked: int = 0
    leaked_resources: int = 0

    @classmethod
    def success(cls, checked: int = 0) -> "IntegritySpecValidationResult":
        """성공"""
        return cls(passed=True, paths_checked=checked)

    @classmethod
    def failure(
        cls,
        violations: list[ResourceLeakViolation],
        checked: int = 0,
    ) -> "IntegritySpecValidationResult":
        """실패"""
        return cls(
            passed=False,
            violations=violations,
            paths_checked=checked,
            leaked_resources=len(violations),
        )


class IntegritySpec:
    """
    Integrity Specification (Resource Leak Detection)

    ADR-011 Section 9: 모든 path에서 close 호출 검증
    순수 로직, 외부 의존 없음
    """

    def __init__(self):
        """기본 리소스 패턴 로드"""
        self.resources = self._load_default_resources()

    def _load_default_resources(self) -> dict[ResourceType, ResourcePattern]:
        """
        기본 리소스 패턴 (ADR-011)

        Returns:
            {resource_type: pattern}
        """
        return {
            ResourceType.FILE: ResourcePattern(
                resource_type=ResourceType.FILE,
                open_patterns={"open", "file", "Path.open"},
                close_patterns={"close", "Path.close", "__exit__"},
            ),
            ResourceType.CONNECTION: ResourcePattern(
                resource_type=ResourceType.CONNECTION,
                open_patterns={"connect", "Connection", "create_connection"},
                close_patterns={"close", "disconnect", "dispose", "__exit__"},
            ),
            ResourceType.LOCK: ResourcePattern(
                resource_type=ResourceType.LOCK,
                open_patterns={"acquire", "Lock", "RLock"},
                close_patterns={"release", "__exit__"},
            ),
            ResourceType.SOCKET: ResourcePattern(
                resource_type=ResourceType.SOCKET,
                open_patterns={"socket", "Socket", "connect"},
                close_patterns={"close", "shutdown"},
            ),
            ResourceType.TRANSACTION: ResourcePattern(
                resource_type=ResourceType.TRANSACTION,
                open_patterns={"begin", "begin_transaction", "start_transaction"},
                close_patterns={"commit", "rollback", "__exit__"},
            ),
        }

    def validate_resource_path(
        self,
        path: ResourcePath,
    ) -> ResourceLeakViolation | None:
        """
        단일 리소스 경로 검증

        Args:
            path: 검증할 경로

        Returns:
            누수 시 ResourceLeakViolation, 아니면 None
        """
        if path.is_leaked:
            severity = self._calculate_severity(path)
            return ResourceLeakViolation(
                resource_type=path.resource_type,
                path=path,
                severity=severity,
                description=f"{path.resource_type.value} opened at {path.open_node} but never closed",
            )

        return None

    def validate_resource_paths(
        self,
        paths: list[ResourcePath],
    ) -> IntegritySpecValidationResult:
        """
        여러 리소스 경로 검증

        Args:
            paths: 검증할 경로 리스트

        Returns:
            검증 결과
        """
        violations = []

        for path in paths:
            violation = self.validate_resource_path(path)
            if violation:
                violations.append(violation)

        if violations:
            return IntegritySpecValidationResult.failure(
                violations=violations,
                checked=len(paths),
            )

        return IntegritySpecValidationResult.success(checked=len(paths))

    def _calculate_severity(self, path: ResourcePath) -> str:
        """
        심각도 계산

        기준:
        - FILE, CONNECTION: critical
        - TRANSACTION: critical
        - LOCK: high
        - SOCKET: high
        """
        severity_map = {
            ResourceType.FILE: "critical",
            ResourceType.CONNECTION: "critical",
            ResourceType.TRANSACTION: "critical",
            ResourceType.LOCK: "high",
            ResourceType.SOCKET: "high",
        }

        return severity_map.get(path.resource_type, "medium")

    def add_custom_resource(
        self,
        resource_type: ResourceType,
        open_patterns: set[str],
        close_patterns: set[str],
    ):
        """커스텀 리소스 패턴 추가"""
        if resource_type in self.resources:
            # 기존에 추가
            existing = self.resources[resource_type]
            self.resources[resource_type] = ResourcePattern(
                resource_type=resource_type,
                open_patterns=existing.open_patterns | open_patterns,
                close_patterns=existing.close_patterns | close_patterns,
            )
        else:
            self.resources[resource_type] = ResourcePattern(
                resource_type=resource_type,
                open_patterns=open_patterns,
                close_patterns=close_patterns,
            )
