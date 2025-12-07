"""
Taint Rule 기본 클래스 및 타입 정의

Design Goals:
1. 언어·프레임워크별 Taint Rules를 독립 모듈로 관리
2. 프로젝트별로 조합/토글 가능한 RuleSet 제공
3. TaintAnalyzer/Reasoning Engine과 stable한 contract 유지

SOTA급 Rule Set을 위한 구조화된 Rule 시스템
"""

import re
from dataclasses import dataclass, field
from enum import Enum


class VulnerabilityType(Enum):
    """보안 취약점 타입"""

    SQL_INJECTION = "sql_injection"
    COMMAND_INJECTION = "command_injection"
    PATH_TRAVERSAL = "path_traversal"
    XSS = "xss"
    CODE_INJECTION = "code_injection"
    SSRF = "ssrf"
    XXE = "xxe"
    LDAP_INJECTION = "ldap_injection"
    XPATH_INJECTION = "xpath_injection"
    OPEN_REDIRECT = "open_redirect"


class Severity(Enum):
    """심각도"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class TaintKind(Enum):
    """Taint 데이터 종류"""

    USER_INPUT = "user_input"  # HTTP request, form, etc
    DATABASE = "database"  # DB query results
    FILE = "file"  # File contents
    NETWORK = "network"  # Network responses
    ENVIRONMENT = "environment"  # ENV vars, argv
    EXTERNAL_API = "external_api"  # Third-party API responses


class MatchKind(Enum):
    """Rule 매칭 방식 (IR 기반)"""

    CALL_NAME = "call_name"  # 함수 호출 이름
    FQ_NAME = "fq_name"  # Fully Qualified Name
    ATTRIBUTE = "attribute"  # 속성 접근
    RAW_PATTERN = "raw_pattern"  # Regex (fallback)


# ============================================================
# VulnerabilityType × CWE 매트릭스
# ============================================================

VULN_CWE_MATRIX = {
    VulnerabilityType.SQL_INJECTION: {
        "primary_cwe": "CWE-89",
        "related_cwes": ["CWE-564"],
        "description": "SQL Injection",
        "severity_default": Severity.CRITICAL,
    },
    VulnerabilityType.COMMAND_INJECTION: {
        "primary_cwe": "CWE-78",
        "related_cwes": ["CWE-77", "CWE-88"],
        "description": "OS Command Injection",
        "severity_default": Severity.CRITICAL,
    },
    VulnerabilityType.PATH_TRAVERSAL: {
        "primary_cwe": "CWE-22",
        "related_cwes": ["CWE-23", "CWE-36"],
        "description": "Path Traversal",
        "severity_default": Severity.HIGH,
    },
    VulnerabilityType.XSS: {
        "primary_cwe": "CWE-79",
        "related_cwes": ["CWE-80", "CWE-83"],
        "description": "Cross-Site Scripting",
        "severity_default": Severity.MEDIUM,
    },
    VulnerabilityType.CODE_INJECTION: {
        "primary_cwe": "CWE-94",
        "related_cwes": ["CWE-95", "CWE-96"],
        "description": "Code Injection",
        "severity_default": Severity.CRITICAL,
    },
    VulnerabilityType.SSRF: {
        "primary_cwe": "CWE-918",
        "related_cwes": [],
        "description": "Server-Side Request Forgery",
        "severity_default": Severity.HIGH,
    },
    VulnerabilityType.XXE: {
        "primary_cwe": "CWE-611",
        "related_cwes": ["CWE-827"],
        "description": "XML External Entity",
        "severity_default": Severity.HIGH,
    },
    VulnerabilityType.LDAP_INJECTION: {
        "primary_cwe": "CWE-90",
        "related_cwes": [],
        "description": "LDAP Injection",
        "severity_default": Severity.HIGH,
    },
    VulnerabilityType.XPATH_INJECTION: {
        "primary_cwe": "CWE-643",
        "related_cwes": [],
        "description": "XPath Injection",
        "severity_default": Severity.HIGH,
    },
    VulnerabilityType.OPEN_REDIRECT: {
        "primary_cwe": "CWE-601",
        "related_cwes": [],
        "description": "Open Redirect",
        "severity_default": Severity.MEDIUM,
    },
}


@dataclass
class TaintRule:
    """
    Taint Rule 기본 클래스

    ⭐ v2.0: Stable Identifier & Version Tracking
    """

    # Core identification
    pattern: str  # Regex pattern for matching
    description: str  # Human-readable description

    # Categorization
    severity: Severity  # Risk level
    vuln_type: VulnerabilityType  # Vulnerability category

    # Stable ID (auto-generated if not provided)
    id: str = field(default="")  # Stable ID (e.g., "PY_CORE_SOURCE_001")

    # Metadata (auto-filled from VULN_CWE_MATRIX if not provided)
    cwe_id: str | None = None  # CWE identifier

    # Version tracking
    version_introduced: str = "v1.1"  # When this rule was added
    version_modified: str | None = None  # Last modification version

    # Tags for filtering/searching
    tags: list[str] = field(default_factory=list)  # ["python", "core", "user_input"]

    # Examples & documentation
    examples: list[str] = field(default_factory=list)  # Code examples

    # Matching strategy (IR-based preferred)
    match_kind: MatchKind = MatchKind.RAW_PATTERN  # How to match this rule
    target_name: str | None = None  # For CALL_NAME/FQ_NAME matching

    # Runtime state
    enabled: bool = True  # Can be toggled per-project
    hit_count: int = field(default=0, init=False)  # Runtime hit counter

    def __post_init__(self):
        """Compile regex pattern and auto-generate ID if needed"""
        # Auto-generate ID if not provided (empty string)
        if not self.id:
            import hashlib

            # Generate stable ID from pattern
            pattern_hash = hashlib.md5(self.pattern.encode()).hexdigest()[:8]
            self.id = f"AUTO_{pattern_hash.upper()}"

        # Compile regex pattern
        try:
            self._compiled_pattern = re.compile(self.pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern '{self.pattern}': {e}")

    def matches(self, text: str) -> bool:
        """
        Check if text matches this rule

        ⭐ v2.0: Increments hit_count for metrics
        """
        if not self.enabled:
            return False

        matched = self._compiled_pattern.search(text) is not None
        if matched:
            self.hit_count += 1
        return matched

    def matches_ir_node(self, node) -> bool:
        """
        IR-based matching (preferred over regex)

        Args:
            node: IRDocument Node object

        Returns:
            True if node matches this rule
        """
        if not self.enabled:
            return False

        if self.match_kind == MatchKind.CALL_NAME:
            # Match by call name (e.g., "eval", "os.system")
            if hasattr(node, "call_name") and node.call_name == self.target_name:
                self.hit_count += 1
                return True

        elif self.match_kind == MatchKind.FQ_NAME:
            # Match by fully qualified name
            if hasattr(node, "fq_name") and node.fq_name == self.target_name:
                self.hit_count += 1
                return True

        elif self.match_kind == MatchKind.ATTRIBUTE:
            # Match by attribute access (e.g., "request.args")
            if hasattr(node, "attribute") and node.attribute == self.target_name:
                self.hit_count += 1
                return True

        # Fallback to regex
        return self.matches(str(node.name) if hasattr(node, "name") else "")


@dataclass
class SourceRule(TaintRule):
    """
    Taint Source Rule

    Source는 오염된 데이터가 시작되는 지점
    예: HTTP request parameters, user input, file reads
    """

    taint_kind: TaintKind = TaintKind.USER_INPUT

    # Framework-specific metadata
    framework: str | None = None

    def __post_init__(self):
        """
        Post-initialization for SourceRule
        Note: Must replicate parent logic due to dataclass inheritance
        """
        # Compile pattern
        try:
            self._compiled_pattern = re.compile(self.pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern '{self.pattern}': {e}")

        # Auto-fill CWE from matrix if not provided
        if self.cwe_id is None and self.vuln_type in VULN_CWE_MATRIX:
            self.cwe_id = VULN_CWE_MATRIX[self.vuln_type]["primary_cwe"]

        # Validate ID format
        if self.id and not re.match(r"^[A-Z_]+_\d{3}$", self.id):
            import warnings

            warnings.warn(
                f"Rule ID '{self.id}' doesn't match recommended format. Use 'PREFIX_NNN' like 'PY_CORE_SOURCE_001'"
            )  # e.g., "flask", "django", "fastapi"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "type": "source",
            "pattern": self.pattern,
            "description": self.description,
            "severity": self.severity.value,
            "vuln_type": self.vuln_type.value,
            "taint_kind": self.taint_kind.value,
            "cwe_id": self.cwe_id,
            "framework": self.framework,
        }


@dataclass
class SinkRule(TaintRule):
    """
    Taint Sink Rule

    Sink는 오염된 데이터가 위험하게 사용되는 지점
    예: SQL execution, OS command execution, file writes
    """

    requires_sanitization: bool = True

    # Framework-specific metadata
    framework: str | None = None

    # Safe usage patterns (exceptions)
    safe_patterns: list[str] = field(default_factory=list)

    def __post_init__(self):
        """
        Post-initialization for SinkRule
        Note: Must replicate parent logic due to dataclass inheritance
        """
        # Compile pattern
        try:
            self._compiled_pattern = re.compile(self.pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern '{self.pattern}': {e}")

        # Auto-fill CWE from matrix if not provided
        if self.cwe_id is None and self.vuln_type in VULN_CWE_MATRIX:
            self.cwe_id = VULN_CWE_MATRIX[self.vuln_type]["primary_cwe"]

        # Validate ID format
        if self.id and not re.match(r"^[A-Z_]+_\d{3}$", self.id):
            import warnings

            warnings.warn(f"Rule ID '{self.id}' doesn't match recommended format")

        # Compile safe patterns
        self._safe_compiled = [re.compile(p) for p in self.safe_patterns]

    def is_safe_usage(self, text: str) -> bool:
        """Check if usage matches a safe pattern"""
        return any(p.search(text) for p in self._safe_compiled)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "type": "sink",
            "pattern": self.pattern,
            "description": self.description,
            "severity": self.severity.value,
            "vuln_type": self.vuln_type.value,
            "requires_sanitization": self.requires_sanitization,
            "cwe_id": self.cwe_id,
            "framework": self.framework,
        }


@dataclass
class SanitizerRule:
    """
    Sanitizer Rule

    Sanitizer는 오염을 제거/정화하는 함수
    예: HTML escape, SQL parameterization, input validation
    """

    pattern: str
    sanitizes: dict[VulnerabilityType, float]  # Vuln type -> effectiveness (0.0-1.0)
    description: str
    framework: str | None = None
    enabled: bool = True

    def __post_init__(self):
        """Compile regex pattern"""
        try:
            self._compiled_pattern = re.compile(self.pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern '{self.pattern}': {e}")

        # Validate effectiveness values
        for vuln, eff in self.sanitizes.items():
            if not 0.0 <= eff <= 1.0:
                raise ValueError(f"Effectiveness must be 0.0-1.0, got {eff}")

    def matches(self, text: str) -> bool:
        """Check if text matches this sanitizer"""
        return self._compiled_pattern.search(text) is not None

    def effectiveness(self, vuln_type: VulnerabilityType) -> float:
        """Get effectiveness for a vulnerability type (0.0 = no effect, 1.0 = full protection)"""
        return self.sanitizes.get(vuln_type, 0.0)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "type": "sanitizer",
            "pattern": self.pattern,
            "description": self.description,
            "sanitizes": {v.value: e for v, e in self.sanitizes.items()},
            "framework": self.framework,
        }


@dataclass
class RuleSet:
    """Collection of related rules"""

    name: str
    description: str
    sources: list[SourceRule] = field(default_factory=list)
    sinks: list[SinkRule] = field(default_factory=list)
    sanitizers: list[SanitizerRule] = field(default_factory=list)
    framework: str | None = None

    def get_stats(self) -> dict:
        """Get statistics about this rule set"""
        return {
            "name": self.name,
            "framework": self.framework,
            "sources": len(self.sources),
            "sinks": len(self.sinks),
            "sanitizers": len(self.sanitizers),
            "total": len(self.sources) + len(self.sinks) + len(self.sanitizers),
        }

    def merge(self, other: "RuleSet") -> "RuleSet":
        """Merge with another rule set"""
        return RuleSet(
            name=f"{self.name} + {other.name}",
            description=f"{self.description} + {other.description}",
            sources=self.sources + other.sources,
            sinks=self.sinks + other.sinks,
            sanitizers=self.sanitizers + other.sanitizers,
        )
