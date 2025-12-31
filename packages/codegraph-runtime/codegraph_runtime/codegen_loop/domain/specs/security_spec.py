"""
Security Spec (GraphSpec)

ADR-011 Section 9: SecuritySpec with CWE Patterns
Production-Grade with Zero Fake/Stub
"""

from dataclasses import dataclass, field
from enum import Enum


class CWECategory(Enum):
    """CWE 카테고리"""

    XSS = "CWE-79"  # Cross-Site Scripting
    SQL_INJECTION = "CWE-89"  # SQL Injection
    OS_COMMAND = "CWE-78"  # OS Command Injection
    PATH_TRAVERSAL = "CWE-22"  # Path Traversal
    XXE = "CWE-611"  # XML External Entity
    CSRF = "CWE-352"  # Cross-Site Request Forgery
    HARDCODED_SECRET = "CWE-798"  # Hardcoded Credentials


@dataclass(frozen=True)
class TaintSource:
    """
    Taint Source (오염 소스)

    불변, 외부 의존 없음
    """

    cwe: CWECategory
    source_patterns: set[str]  # e.g., {"request.args", "request.form"}

    def __post_init__(self):
        if not self.source_patterns:
            raise ValueError("source_patterns cannot be empty")


@dataclass(frozen=True)
class TaintSink:
    """
    Taint Sink (오염 싱크)

    불변, 외부 의존 없음
    """

    cwe: CWECategory
    sink_patterns: set[str]  # e.g., {"render_template_string", "execute"}

    def __post_init__(self):
        if not self.sink_patterns:
            raise ValueError("sink_patterns cannot be empty")


@dataclass(frozen=True)
class Sanitizer:
    """
    Sanitizer (정화기)

    불변, 외부 의존 없음
    """

    cwe: CWECategory
    sanitizer_patterns: set[str]  # e.g., {"escape", "parameterize"}

    def __post_init__(self):
        if not self.sanitizer_patterns:
            raise ValueError("sanitizer_patterns cannot be empty")


@dataclass(frozen=True)
class DataflowPath:
    """
    Data Flow Path

    Source → Sink 경로
    """

    source: str
    sink: str
    path_nodes: list[str]  # Intermediate nodes
    has_sanitizer: bool
    sanitizers_used: list[str] = field(default_factory=list)

    @property
    def is_vulnerable(self) -> bool:
        """취약한 경로인지 (sanitizer 없음)"""
        return not self.has_sanitizer

    @property
    def path_length(self) -> int:
        """경로 길이"""
        return len(self.path_nodes)


@dataclass
class SecurityViolation:
    """Security 위반"""

    cwe: CWECategory
    path: DataflowPath
    severity: str  # "critical", "high", "medium", "low"
    description: str
    remediation: str | None = None

    def __post_init__(self):
        valid_severities = {"critical", "high", "medium", "low"}
        if self.severity not in valid_severities:
            raise ValueError(f"severity must be one of {valid_severities}, got {self.severity}")


@dataclass
class SecuritySpecValidationResult:
    """Security Spec 검증 결과"""

    passed: bool
    violations: list[SecurityViolation] = field(default_factory=list)
    paths_checked: int = 0
    vulnerable_paths: int = 0

    @classmethod
    def success(cls, paths_checked: int = 0) -> "SecuritySpecValidationResult":
        """성공"""
        return cls(passed=True, paths_checked=paths_checked)

    @classmethod
    def failure(
        cls,
        violations: list[SecurityViolation],
        paths_checked: int = 0,
    ) -> "SecuritySpecValidationResult":
        """실패"""
        return cls(
            passed=False,
            violations=violations,
            paths_checked=paths_checked,
            vulnerable_paths=len(violations),
        )


class SecuritySpec:
    """
    Security Specification (CWE Patterns)

    ADR-011 Section 9: GraphSpec Implementation
    순수 로직, 외부 의존 없음
    """

    def __init__(self):
        """
        기본 CWE 패턴 로드 (ADR-011 명시된 값)
        """
        self.sources = self._load_default_sources()
        self.sinks = self._load_default_sinks()
        self.sanitizers = self._load_default_sanitizers()

    def _load_default_sources(self) -> dict[CWECategory, TaintSource]:
        """기본 Taint Sources"""
        return {
            CWECategory.XSS: TaintSource(
                cwe=CWECategory.XSS,
                source_patterns={
                    "request.args",
                    "request.form",
                    "request.json",
                    "request.data",
                    "request.cookies",
                },
            ),
            CWECategory.SQL_INJECTION: TaintSource(
                cwe=CWECategory.SQL_INJECTION,
                source_patterns={
                    "request.args",
                    "request.form",
                    "os.environ",
                    "sys.argv",
                },
            ),
            CWECategory.OS_COMMAND: TaintSource(
                cwe=CWECategory.OS_COMMAND,
                source_patterns={
                    "os.environ",
                    "sys.argv",
                    "request.args",
                },
            ),
            CWECategory.PATH_TRAVERSAL: TaintSource(
                cwe=CWECategory.PATH_TRAVERSAL,
                source_patterns={
                    "request.args",
                    "request.form",
                    "request.files",
                },
            ),
        }

    def _load_default_sinks(self) -> dict[CWECategory, TaintSink]:
        """기본 Taint Sinks"""
        return {
            CWECategory.XSS: TaintSink(
                cwe=CWECategory.XSS,
                sink_patterns={
                    "render_template_string",
                    "Markup",
                    "html.write",
                    "Response",
                },
            ),
            CWECategory.SQL_INJECTION: TaintSink(
                cwe=CWECategory.SQL_INJECTION,
                sink_patterns={
                    "execute",
                    "executemany",
                    "cursor.execute",
                    "raw",
                },
            ),
            CWECategory.OS_COMMAND: TaintSink(
                cwe=CWECategory.OS_COMMAND,
                sink_patterns={
                    "os.system",
                    "subprocess.run",
                    "subprocess.call",
                    "subprocess.Popen",
                    "eval",
                    "exec",
                },
            ),
            CWECategory.PATH_TRAVERSAL: TaintSink(
                cwe=CWECategory.PATH_TRAVERSAL,
                sink_patterns={
                    "open",
                    "file",
                    "Path",
                    "os.path.join",
                },
            ),
        }

    def _load_default_sanitizers(self) -> dict[CWECategory, Sanitizer]:
        """기본 Sanitizers"""
        return {
            CWECategory.XSS: Sanitizer(
                cwe=CWECategory.XSS,
                sanitizer_patterns={
                    "escape",
                    "bleach.clean",
                    "MarkupSafe",
                    "html.escape",
                },
            ),
            CWECategory.SQL_INJECTION: Sanitizer(
                cwe=CWECategory.SQL_INJECTION,
                sanitizer_patterns={
                    "parameterize",
                    "bind_params",
                    "prepared_statement",
                },
            ),
            CWECategory.OS_COMMAND: Sanitizer(
                cwe=CWECategory.OS_COMMAND,
                sanitizer_patterns={
                    "shlex.quote",
                    "pipes.quote",
                },
            ),
            CWECategory.PATH_TRAVERSAL: Sanitizer(
                cwe=CWECategory.PATH_TRAVERSAL,
                sanitizer_patterns={
                    "os.path.abspath",
                    "Path.resolve",
                    "secure_filename",
                },
            ),
        }

    def validate_path(
        self,
        path: DataflowPath,
        cwe: CWECategory,
    ) -> SecurityViolation | None:
        """
        단일 dataflow path 검증

        Args:
            path: 검증할 경로
            cwe: CWE 카테고리

        Returns:
            위반 시 SecurityViolation, 아니면 None
        """
        # Source 확인
        source_spec = self.sources.get(cwe)
        if not source_spec:
            raise ValueError(f"Unknown CWE category: {cwe}")

        if not any(pattern in path.source for pattern in source_spec.source_patterns):
            return None  # Source가 아니면 pass

        # Sink 확인
        sink_spec = self.sinks.get(cwe)
        if not sink_spec:
            return None

        if not any(pattern in path.sink for pattern in sink_spec.sink_patterns):
            return None  # Sink가 아니면 pass

        # Sanitizer 확인
        if path.is_vulnerable:
            severity = self._calculate_severity(path, cwe)
            return SecurityViolation(
                cwe=cwe,
                path=path,
                severity=severity,
                description=f"{cwe.value}: {path.source} → {path.sink} without sanitization",
                remediation=self._suggest_remediation(cwe),
            )

        return None  # Sanitizer 있으면 안전

    def validate_paths(
        self,
        paths: list[DataflowPath],
        cwe: CWECategory,
    ) -> SecuritySpecValidationResult:
        """
        여러 경로 검증

        Args:
            paths: 검증할 경로 리스트
            cwe: CWE 카테고리

        Returns:
            검증 결과
        """
        violations = []

        for path in paths:
            violation = self.validate_path(path, cwe)
            if violation:
                violations.append(violation)

        if violations:
            return SecuritySpecValidationResult.failure(
                violations=violations,
                paths_checked=len(paths),
            )

        return SecuritySpecValidationResult.success(paths_checked=len(paths))

    def validate_all_cwes(
        self,
        paths_by_cwe: dict[CWECategory, list[DataflowPath]],
    ) -> SecuritySpecValidationResult:
        """
        모든 CWE 카테고리 검증

        Args:
            paths_by_cwe: {CWE: [paths]}

        Returns:
            집계된 검증 결과
        """
        all_violations = []
        total_paths = 0

        for cwe, paths in paths_by_cwe.items():
            result = self.validate_paths(paths, cwe)
            all_violations.extend(result.violations)
            total_paths += result.paths_checked

        if all_violations:
            return SecuritySpecValidationResult.failure(
                violations=all_violations,
                paths_checked=total_paths,
            )

        return SecuritySpecValidationResult.success(paths_checked=total_paths)

    def _calculate_severity(self, path: DataflowPath, cwe: CWECategory) -> str:
        """
        심각도 계산

        기준:
        - SQL Injection, OS Command: critical
        - XSS: high
        - Path Traversal: high
        - 경로 길이 짧을수록 심각 (직접 연결)
        """
        # CWE별 기본 심각도
        base_severity = {
            CWECategory.SQL_INJECTION: "critical",
            CWECategory.OS_COMMAND: "critical",
            CWECategory.XSS: "high",
            CWECategory.PATH_TRAVERSAL: "high",
            CWECategory.XXE: "high",
            CWECategory.CSRF: "medium",
            CWECategory.HARDCODED_SECRET: "high",
        }

        severity = base_severity.get(cwe, "medium")

        # 경로 길이가 짧으면 더 심각 (직접 연결)
        if path.path_length <= 2 and severity == "high":
            severity = "critical"

        return severity

    def _suggest_remediation(self, cwe: CWECategory) -> str:
        """
        수정 제안

        CWE별 구체적인 remediation 가이드
        """
        remediations = {
            CWECategory.XSS: "Use escape() or MarkupSafe before rendering",
            CWECategory.SQL_INJECTION: "Use parameterized queries or ORM",
            CWECategory.OS_COMMAND: "Use shlex.quote() or avoid shell=True",
            CWECategory.PATH_TRAVERSAL: "Use os.path.abspath() and validate path",
        }

        return remediations.get(cwe, "Add appropriate sanitization")

    def add_custom_source(self, cwe: CWECategory, patterns: set[str]):
        """커스텀 Source 추가"""
        if cwe not in self.sources:
            self.sources[cwe] = TaintSource(cwe=cwe, source_patterns=patterns)
        else:
            # 기존에 추가
            existing = self.sources[cwe]
            self.sources[cwe] = TaintSource(
                cwe=cwe,
                source_patterns=existing.source_patterns | patterns,
            )

    def add_custom_sink(self, cwe: CWECategory, patterns: set[str]):
        """커스텀 Sink 추가"""
        if cwe not in self.sinks:
            self.sinks[cwe] = TaintSink(cwe=cwe, sink_patterns=patterns)
        else:
            existing = self.sinks[cwe]
            self.sinks[cwe] = TaintSink(
                cwe=cwe,
                sink_patterns=existing.sink_patterns | patterns,
            )

    def add_custom_sanitizer(self, cwe: CWECategory, patterns: set[str]):
        """커스텀 Sanitizer 추가"""
        if cwe not in self.sanitizers:
            self.sanitizers[cwe] = Sanitizer(cwe=cwe, sanitizer_patterns=patterns)
        else:
            existing = self.sanitizers[cwe]
            self.sanitizers[cwe] = Sanitizer(
                cwe=cwe,
                sanitizer_patterns=existing.sanitizer_patterns | patterns,
            )
