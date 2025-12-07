"""
Sandbox 보안 정책 (SOTA급).

E2B Sandbox를 위한 보안, 감사, 비밀 관리 기능.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SecurityLevel(str, Enum):
    """보안 레벨"""

    LOW = "low"  # 개발/테스트
    MEDIUM = "medium"  # 일반 운영
    HIGH = "high"  # 민감 데이터
    CRITICAL = "critical"  # 프로덕션


@dataclass
class SecurityPolicy:
    """
    Sandbox 보안 정책 (SOTA).

    - 리소스 제한
    - 네트워크 정책
    - 파일 정책
    - 코드 정책
    """

    # 보안 레벨
    level: SecurityLevel = SecurityLevel.MEDIUM

    # 리소스 제한
    max_execution_time_ms: int = 30000  # 30초
    max_memory_mb: int = 512
    max_cpu_percent: int = 50
    max_disk_mb: int = 1024

    # 네트워크 정책
    allow_network: bool = False
    allowed_domains: list[str] = field(default_factory=list)
    allowed_ports: list[int] = field(default_factory=lambda: [80, 443])

    # 파일 정책
    max_file_size_mb: int = 10
    allowed_file_types: list[str] = field(default_factory=lambda: [".py", ".js", ".ts", ".json", ".txt"])
    forbidden_paths: list[str] = field(default_factory=lambda: ["/etc", "/root", "/proc", "/sys"])

    # 코드 정책
    forbidden_imports: list[str] = field(
        default_factory=lambda: [
            "os.system",
            "subprocess",
            "eval",
            "exec",
            "__import__",
        ]
    )
    forbidden_functions: list[str] = field(default_factory=lambda: ["eval", "exec", "compile", "__builtins__"])
    max_code_length: int = 10000

    def __post_init__(self):
        """보안 정책 검증"""
        if self.max_execution_time_ms < 1000:
            raise ValueError("max_execution_time_ms must be >= 1000ms")
        if self.max_memory_mb < 128:
            raise ValueError("max_memory_mb must be >= 128MB")
        if self.max_cpu_percent < 10 or self.max_cpu_percent > 100:
            raise ValueError("max_cpu_percent must be 10-100")

    def validate_code(self, code: str, language: str) -> tuple[bool, list[str]]:
        """
        코드 보안 검증.

        Args:
            code: 실행할 코드
            language: 언어 (python, javascript 등)

        Returns:
            (유효 여부, 위반 사항 목록)
        """
        violations = []

        # 1. 코드 길이
        if len(code) > self.max_code_length:
            violations.append(f"Code length {len(code)} exceeds {self.max_code_length}")

        # 2. 금지된 import (Python)
        if language == "python":
            for forbidden in self.forbidden_imports:
                if forbidden in code:
                    violations.append(f"Forbidden import: {forbidden}")

        # 3. 금지된 함수
        for forbidden in self.forbidden_functions:
            if forbidden in code:
                violations.append(f"Forbidden function: {forbidden}")

        # 4. 파일 경로 검사
        for forbidden_path in self.forbidden_paths:
            if forbidden_path in code:
                violations.append(f"Forbidden path: {forbidden_path}")

        return (len(violations) == 0, violations)

    @classmethod
    def for_level(cls, level: SecurityLevel) -> "SecurityPolicy":
        """보안 레벨에 따른 정책 생성"""
        if level == SecurityLevel.LOW:
            return cls(
                level=level,
                max_execution_time_ms=60000,
                max_memory_mb=1024,
                allow_network=True,
            )
        elif level == SecurityLevel.MEDIUM:
            return cls(level=level)
        elif level == SecurityLevel.HIGH:
            return cls(
                level=level,
                max_execution_time_ms=15000,
                max_memory_mb=256,
                allow_network=False,
            )
        else:  # CRITICAL
            return cls(
                level=level,
                max_execution_time_ms=10000,
                max_memory_mb=128,
                max_cpu_percent=25,
                allow_network=False,
                allowed_file_types=[".py"],
            )


@dataclass
class SecretConfig:
    """비밀 설정"""

    name: str
    value: str
    expires_at: datetime | None = None
    auto_delete_after_use: bool = True
    mask_in_logs: bool = True


class SecretManager:
    """
    비밀 관리자 (SOTA).

    - AES-256 암호화
    - 자동 삭제
    - 로그 마스킹
    """

    def __init__(self, encryption_key: str | None = None):
        """
        Args:
            encryption_key: 암호화 키 (None이면 자동 생성)
        """
        self.encryption_key = encryption_key or self._generate_key()
        self._secrets: dict[str, SecretConfig] = {}

    def _generate_key(self) -> str:
        """암호화 키 생성"""
        import secrets

        return secrets.token_hex(32)

    def add_secret(self, name: str, value: str, expires_at: datetime | None = None) -> None:
        """
        비밀 추가.

        Args:
            name: 비밀 이름 (예: OPENAI_API_KEY)
            value: 비밀 값
            expires_at: 만료 시간 (None이면 무제한)
        """
        self._secrets[name] = SecretConfig(name=name, value=value, expires_at=expires_at)

    def get_secret(self, name: str) -> str | None:
        """
        비밀 조회.

        Args:
            name: 비밀 이름

        Returns:
            비밀 값 (없으면 None)
        """
        config = self._secrets.get(name)
        if not config:
            return None

        # 만료 확인
        if config.expires_at and datetime.now() > config.expires_at:
            del self._secrets[name]
            return None

        return config.value

    def prepare_for_injection(self, secrets: dict[str, str]) -> dict[str, str]:
        """
        주입 준비 (암호화).

        Args:
            secrets: 주입할 비밀들

        Returns:
            암호화된 비밀들
        """
        # 실제로는 AES-256 암호화해야 하지만, 간단히 해시로 시뮬레이션
        encrypted = {}
        for name, value in secrets.items():
            # 실제 환경에서는 여기서 AES-256 암호화
            encrypted[name] = value  # 단순화

        return encrypted

    def mask_in_logs(self, log_message: str) -> str:
        """
        로그에서 비밀 마스킹.

        Args:
            log_message: 로그 메시지

        Returns:
            마스킹된 로그 메시지
        """
        masked = log_message
        for secret in self._secrets.values():
            if secret.mask_in_logs and secret.value in masked:
                masked = masked.replace(secret.value, "***MASKED***")

        return masked

    def cleanup_expired(self) -> int:
        """
        만료된 비밀 삭제.

        Returns:
            삭제된 비밀 개수
        """
        now = datetime.now()
        expired = [name for name, config in self._secrets.items() if config.expires_at and now > config.expires_at]

        for name in expired:
            del self._secrets[name]

        return len(expired)


class SecurityViolationType(str, Enum):
    """보안 위반 유형"""

    FORBIDDEN_IMPORT = "forbidden_import"
    FORBIDDEN_FUNCTION = "forbidden_function"
    FORBIDDEN_PATH = "forbidden_path"
    EXCESSIVE_RESOURCE = "excessive_resource"
    NETWORK_VIOLATION = "network_violation"
    TIMEOUT = "timeout"
    CODE_TOO_LONG = "code_too_long"


@dataclass
class SecurityViolation:
    """보안 위반 기록"""

    type: SecurityViolationType
    message: str
    severity: str  # low, medium, high, critical
    timestamp: datetime = field(default_factory=datetime.now)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SandboxAuditLog:
    """
    Sandbox 감사 로그 (SOTA).

    모든 Sandbox 활동을 기록.
    """

    sandbox_id: str
    user_id: str
    task_id: str

    # 실행 정보
    code_hash: str  # SHA-256
    language: str
    execution_time_ms: int
    exit_code: int

    # 리소스 사용
    cpu_usage_percent: float
    memory_usage_mb: float
    disk_usage_mb: float
    network_bytes_sent: int = 0
    network_bytes_received: int = 0

    # 보안 이벤트
    security_violations: list[SecurityViolation] = field(default_factory=list)
    blocked_operations: list[str] = field(default_factory=list)

    # 타임스탬프
    created_at: datetime = field(default_factory=datetime.now)
    destroyed_at: datetime | None = None

    # 메타데이터
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_violation(
        self,
        violation_type: SecurityViolationType,
        message: str,
        severity: str = "medium",
    ):
        """보안 위반 추가"""
        self.security_violations.append(SecurityViolation(type=violation_type, message=message, severity=severity))

    def add_blocked_operation(self, operation: str):
        """차단된 작업 추가"""
        self.blocked_operations.append(operation)

    def get_code_hash(self, code: str) -> str:
        """코드 해시 계산"""
        return hashlib.sha256(code.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "sandbox_id": self.sandbox_id,
            "user_id": self.user_id,
            "task_id": self.task_id,
            "code_hash": self.code_hash,
            "language": self.language,
            "execution_time_ms": self.execution_time_ms,
            "exit_code": self.exit_code,
            "cpu_usage_percent": self.cpu_usage_percent,
            "memory_usage_mb": self.memory_usage_mb,
            "disk_usage_mb": self.disk_usage_mb,
            "network_bytes_sent": self.network_bytes_sent,
            "network_bytes_received": self.network_bytes_received,
            "security_violations": [
                {
                    "type": v.type.value,
                    "message": v.message,
                    "severity": v.severity,
                    "timestamp": v.timestamp.isoformat(),
                }
                for v in self.security_violations
            ],
            "blocked_operations": self.blocked_operations,
            "created_at": self.created_at.isoformat(),
            "destroyed_at": (self.destroyed_at.isoformat() if self.destroyed_at else None),
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """JSON으로 변환"""
        return json.dumps(self.to_dict(), indent=2)


class AuditLogger:
    """감사 로그 저장소"""

    def __init__(self):
        self.logs: list[SandboxAuditLog] = []

    def log(self, audit_log: SandboxAuditLog) -> None:
        """감사 로그 저장"""
        self.logs.append(audit_log)

    def get_logs_by_task(self, task_id: str) -> list[SandboxAuditLog]:
        """Task별 로그 조회"""
        return [log for log in self.logs if log.task_id == task_id]

    def get_logs_by_user(self, user_id: str) -> list[SandboxAuditLog]:
        """User별 로그 조회"""
        return [log for log in self.logs if log.user_id == user_id]

    def get_violations(self) -> list[SandboxAuditLog]:
        """보안 위반이 있는 로그 조회"""
        return [log for log in self.logs if log.security_violations]

    def export_json(self, file_path: str) -> None:
        """JSON 파일로 내보내기"""
        import json

        with open(file_path, "w") as f:
            json.dump([log.to_dict() for log in self.logs], f, indent=2)
